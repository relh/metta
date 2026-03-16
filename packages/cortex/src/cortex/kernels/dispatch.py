"""Backend-dispatch helpers that keep Cortex cells focused on composition."""

from __future__ import annotations

import torch
import torch.nn.functional as F
from cortex.kernels.pytorch.agalite import discounted_sum_pytorch
from cortex.kernels.pytorch.conv1d import causal_conv1d_pytorch
from cortex.kernels.pytorch.mlstm import mlstm_chunkwise_simple, mlstm_recurrent_step_stabilized_simple
from cortex.kernels.pytorch.rtu.rtu_stream_diag import rtu_stream_diag_pytorch
from cortex.kernels.pytorch.rtu.rtu_stream_fullrank import rtu_stream_full_pytorch
from cortex.kernels.pytorch.slstm import slstm_sequence_pytorch
from cortex.utils import is_batchedtensor, select_backend, unwrap_batchedtensor, wrap_batchedtensor


def _physical_or_shared(tensor: torch.Tensor | None, ensemble_size: int) -> torch.Tensor | None:
    if tensor is None:
        return None
    value, level = unwrap_batchedtensor(tensor)
    if level is None:
        return tensor.unsqueeze(0).expand(ensemble_size, *tensor.shape)
    return value


def _shared_resets_or_none(resets: torch.Tensor | None, op_name: str) -> torch.Tensor | None:
    if resets is None or not is_batchedtensor(resets):
        return resets
    resets_phys, _ = unwrap_batchedtensor(resets)
    if not torch.equal(resets_phys, resets_phys[0].expand_as(resets_phys)):
        raise ValueError(f"{op_name} parameter-batched vmap expects shared resets across models")
    return resets_phys[0]


def apply_multihead_layernorm_physical(
    input_phys: torch.Tensor,
    *,
    weight_phys: torch.Tensor | None,
    bias_phys: torch.Tensor | None,
    eps: float,
) -> torch.Tensor:
    mean = input_phys.mean(dim=-1, keepdim=True)
    var = input_phys.var(dim=-1, unbiased=False, keepdim=True)
    out = (input_phys - mean) * torch.rsqrt(var + eps)
    if weight_phys is not None:
        out = out * weight_phys.view(weight_phys.shape[0], 1, input_phys.shape[2], 1, input_phys.shape[-1])
    if bias_phys is not None:
        out = out + bias_phys.view(bias_phys.shape[0], 1, input_phys.shape[2], 1, input_phys.shape[-1])
    return out


def apply_multihead_layernorm(
    input_tensor: torch.Tensor,
    *,
    weight: torch.Tensor | None,
    bias: torch.Tensor | None,
    eps: float,
) -> torch.Tensor:
    if input_tensor.dim() == 5:
        return apply_multihead_layernorm_physical(
            input_tensor,
            weight_phys=weight,
            bias_phys=bias,
            eps=eps,
        )

    if input_tensor.dim() != 4:
        raise ValueError(f"Expected 4D or 5D tensor for multi-head layernorm, got {input_tensor.dim()}D")

    batch, num_heads, seq_len, head_dim = input_tensor.shape
    gn_in = input_tensor.transpose(1, 2).reshape(batch * seq_len, num_heads * head_dim)
    out = F.group_norm(
        gn_in,
        num_groups=num_heads,
        weight=weight,
        bias=bias,
        eps=eps,
    )
    return out.view(batch, seq_len, num_heads, head_dim).transpose(1, 2)


def run_discounted_sum(
    *,
    start_state: torch.Tensor,
    x: torch.Tensor,
    discounts: torch.Tensor,
    tensor_for_backend: torch.Tensor,
) -> torch.Tensor:
    cuda_fn = (
        "cortex.kernels.cuda.agalite.discounted_sum_cuda:discounted_sum_cuda" if tensor_for_backend.is_cuda else None
    )
    ds_fn = select_backend(
        triton_fn=None,
        pytorch_fn=discounted_sum_pytorch,
        tensor=tensor_for_backend,
        allow_triton=False,
        cuda_fn=cuda_fn,
        allow_cuda=tensor_for_backend.is_cuda,
    )
    if not is_batchedtensor(start_state):
        return ds_fn(start_state, x, discounts)

    start_phys, level = unwrap_batchedtensor(start_state)
    if level is None:
        raise RuntimeError("Expected a functorch batch level for discounted-sum vmapped execution")
    ensemble = start_phys.shape[0]
    x_phys = _physical_or_shared(x, ensemble)
    discounts_phys = _physical_or_shared(discounts, ensemble)
    assert x_phys is not None and discounts_phys is not None
    out_fold = ds_fn(
        start_phys.movedim(0, 1),
        x_phys.permute(1, 2, 0, *range(3, x_phys.dim())),
        discounts_phys.permute(1, 2, 0, *range(3, discounts_phys.dim())),
    )
    out_phys = out_fold.permute(2, 0, 1, *range(3, out_fold.dim()))
    return wrap_batchedtensor(out_phys, level)


def run_causal_conv1d(
    *,
    x: torch.Tensor,
    conv_state: torch.Tensor,
    weight: torch.Tensor,
    bias: torch.Tensor | None,
    groups: int,
    pad: int,
    conv: torch.nn.Conv1d | None,
    resets: torch.Tensor | None,
    channel_mixing: bool,
) -> tuple[torch.Tensor, torch.Tensor]:
    is_step = x.shape[1] == 1
    triton_fn = "cortex.kernels.triton.conv1d:causal_conv1d_triton" if channel_mixing else None

    if channel_mixing and is_batchedtensor(weight):
        weight_phys, level = unwrap_batchedtensor(weight)
        if level is None:
            raise RuntimeError("Expected a functorch batch level for CausalConv1d vmapped execution")

        ensemble, hidden_size, _, kernel_size = weight_phys.shape
        conv_state_phys = _physical_or_shared(conv_state, ensemble)
        x_phys = _physical_or_shared(x, ensemble)
        bias_phys = _physical_or_shared(bias, ensemble)
        resets = _shared_resets_or_none(resets, "CausalConv1dCore")
        assert conv_state_phys is not None and x_phys is not None

        eye = torch.eye(ensemble, device=weight_phys.device, dtype=weight_phys.dtype)
        weight_block = (eye[:, :, None, None, None] * weight_phys[:, None]).permute(0, 2, 1, 3, 4)
        weight_fold = weight_block.reshape(ensemble * hidden_size, ensemble * hidden_size, kernel_size).contiguous()
        state_fold = conv_state_phys.permute(1, 2, 0, 3).reshape(x.shape[0], kernel_size, ensemble * hidden_size)
        x_fold = x_phys.permute(1, 2, 0, 3).reshape(x.shape[0], x.shape[1], ensemble * hidden_size)
        bias_fold = bias_phys.reshape(ensemble * hidden_size).contiguous() if bias_phys is not None else None

        backend_fn = select_backend(
            triton_fn=triton_fn,
            pytorch_fn=causal_conv1d_pytorch,
            tensor=x_fold,
        )
        backend_kwargs = {
            "conv_state": state_fold,
            "x": x_fold,
            "weight": weight_fold,
            "bias": bias_fold,
            "groups": 1,
            "resets": resets if not is_step else None,
        }
        if backend_fn == causal_conv1d_pytorch:
            backend_kwargs["pad"] = pad
            backend_kwargs["conv"] = None
        y_fold, conv_state_fold = backend_fn(**backend_kwargs)
        y_phys = y_fold.view(x.shape[0], x.shape[1], ensemble, hidden_size).permute(2, 0, 1, 3)
        conv_state_phys_new = conv_state_fold.view(x.shape[0], kernel_size, ensemble, hidden_size).permute(2, 0, 1, 3)
        return wrap_batchedtensor(y_phys, level), wrap_batchedtensor(conv_state_phys_new, level)

    backend_fn = select_backend(
        triton_fn=triton_fn,
        pytorch_fn=causal_conv1d_pytorch,
        tensor=x,
    )
    if backend_fn == causal_conv1d_pytorch:
        return backend_fn(
            conv_state=conv_state,
            x=x,
            weight=weight,
            bias=bias,
            groups=groups,
            pad=pad,
            conv=conv,
            resets=resets if not is_step else None,
        )
    return backend_fn(
        conv_state=conv_state,
        x=x,
        weight=weight,
        bias=bias,
        groups=groups,
        resets=resets if not is_step else None,
    )


def run_axon_rtu(
    *,
    x_btd: torch.Tensor,
    nu_log: torch.Tensor,
    theta_log: torch.Tensor,
    hc1_init_bh: torch.Tensor,
    hc2_init_bh: torch.Tensor,
    trace_in: tuple[torch.Tensor, ...] | None,
    resets_bt: torch.Tensor | None,
    activation_name: str,
    out_weight: torch.Tensor,
    out_bias: torch.Tensor | None,
    use_fullrank: bool,
    prefer_cuda: bool,
    is_step: bool,
    w1: torch.Tensor | None = None,
    w2: torch.Tensor | None = None,
    Wc1: torch.Tensor | None = None,
    Wc2: torch.Tensor | None = None,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, tuple[torch.Tensor, ...]]:
    batch, seq_len, hidden_size = x_btd.shape
    use_batched_kernel = is_batchedtensor(nu_log)

    if use_batched_kernel:
        nu_log_phys, level = unwrap_batchedtensor(nu_log)
        theta_log_phys, _ = unwrap_batchedtensor(theta_log)
        hc1_phys, _ = unwrap_batchedtensor(hc1_init_bh)
        hc2_phys, _ = unwrap_batchedtensor(hc2_init_bh)
        if level is None:
            raise RuntimeError("Expected a functorch batch level for AxonCore vmapped execution")

        ensemble = nu_log_phys.shape[0]
        resets_bt = _shared_resets_or_none(resets_bt, "AxonCore")
        trace_phys = None if trace_in is None else tuple(_physical_or_shared(t, ensemble) for t in trace_in)

        if use_fullrank:
            x_phys, x_level = unwrap_batchedtensor(x_btd)
            if x_level is not None:
                raise ValueError("AxonCore full-rank vmapped path requires shared pre-projection inputs")
            Wc1_phys = _physical_or_shared(Wc1, ensemble)
            Wc2_phys = _physical_or_shared(Wc2, ensemble)
            assert Wc1_phys is not None and Wc2_phys is not None
            trace_fold = None
            if trace_phys is not None:
                trace_fold = tuple(
                    t.permute(1, 2, 0, 3).reshape(batch, hidden_size, ensemble * hidden_size) for t in trace_phys
                )
            y2h_fold, (h1_fold, h2_fold), trace_out_fold = select_backend(
                triton_fn=None,
                pytorch_fn=rtu_stream_full_pytorch,
                tensor=x_btd,
                cuda_fn="cortex.kernels.cuda.rtu:rtu_stream_full_cuda",
                allow_cuda=x_btd.is_cuda,
            )(
                x_btd=x_btd,
                nu_log=nu_log_phys.reshape(ensemble * hidden_size),
                theta_log=theta_log_phys.reshape(ensemble * hidden_size),
                Wc1=Wc1_phys.permute(1, 0, 2).reshape(hidden_size, ensemble * hidden_size),
                Wc2=Wc2_phys.permute(1, 0, 2).reshape(hidden_size, ensemble * hidden_size),
                activation_name=activation_name,
                hc1_init_bh=hc1_phys.permute(1, 0, 2).reshape(batch, ensemble * hidden_size),
                hc2_init_bh=hc2_phys.permute(1, 0, 2).reshape(batch, ensemble * hidden_size),
                trace_in=trace_fold,
                resets_bt=resets_bt,
            )
            trace_out_phys = tuple(
                t.view(batch, hidden_size, ensemble, hidden_size).permute(2, 0, 1, 3) for t in trace_out_fold
            )
        else:
            x_phys = _physical_or_shared(x_btd, ensemble)
            w1_phys = _physical_or_shared(w1, ensemble)
            w2_phys = _physical_or_shared(w2, ensemble)
            assert x_phys is not None and w1_phys is not None and w2_phys is not None
            trace_fold = None
            if trace_phys is not None:
                trace_fold = tuple(t.permute(1, 0, 2).reshape(batch, ensemble * hidden_size) for t in trace_phys)
            y2h_fold, (h1_fold, h2_fold), trace_out_fold = select_backend(
                triton_fn="cortex.kernels.triton.rtu:rtu_stream_diag_triton",
                pytorch_fn=rtu_stream_diag_pytorch,
                tensor=x_phys,
                cuda_fn="cortex.kernels.cuda.rtu:rtu_stream_diag_cuda",
                allow_cuda=x_phys.is_cuda,
            )(
                x_btd=x_phys.permute(1, 2, 0, 3).reshape(batch, seq_len, ensemble * hidden_size),
                nu_log=nu_log_phys.reshape(ensemble * hidden_size),
                theta_log=theta_log_phys.reshape(ensemble * hidden_size),
                w1=w1_phys.reshape(ensemble * hidden_size),
                w2=w2_phys.reshape(ensemble * hidden_size),
                activation_name=activation_name,
                hc1_init_bh=hc1_phys.permute(1, 0, 2).reshape(batch, ensemble * hidden_size),
                hc2_init_bh=hc2_phys.permute(1, 0, 2).reshape(batch, ensemble * hidden_size),
                trace_in=trace_fold,
                resets_bt=resets_bt,
            )
            trace_out_phys = tuple(t.view(batch, ensemble, hidden_size).permute(1, 0, 2) for t in trace_out_fold)

        y1_phys = (
            y2h_fold[:, :, : ensemble * hidden_size].view(batch, seq_len, ensemble, hidden_size).permute(2, 0, 1, 3)
        )
        y2_phys = (
            y2h_fold[:, :, ensemble * hidden_size :].view(batch, seq_len, ensemble, hidden_size).permute(2, 0, 1, 3)
        )
        y2h_phys = torch.cat((y1_phys, y2_phys), dim=-1)
        y_phys = torch.einsum("ebti,eoi->ebto", y2h_phys, _physical_or_shared(out_weight, ensemble))
        out_bias_phys = _physical_or_shared(out_bias, ensemble)
        if out_bias_phys is not None:
            y_phys = y_phys + out_bias_phys[:, None, None, :]
        y = wrap_batchedtensor(y_phys[:, :, 0, :] if is_step else y_phys, level)
        h1_n = wrap_batchedtensor(h1_fold.view(batch, ensemble, hidden_size).permute(1, 0, 2), level)
        h2_n = wrap_batchedtensor(h2_fold.view(batch, ensemble, hidden_size).permute(1, 0, 2), level)
        trace_out = tuple(wrap_batchedtensor(t, level) for t in trace_out_phys)
        return y, h1_n, h2_n, trace_out

    if use_fullrank:
        y2h_t, (h1_n, h2_n), trace_out = select_backend(
            triton_fn=None,
            pytorch_fn=rtu_stream_full_pytorch,
            tensor=x_btd,
            cuda_fn="cortex.kernels.cuda.rtu:rtu_stream_full_cuda",
            allow_cuda=x_btd.is_cuda and prefer_cuda,
        )(
            x_btd=x_btd,
            nu_log=nu_log,
            theta_log=theta_log,
            Wc1=Wc1,
            Wc2=Wc2,
            activation_name=activation_name,
            hc1_init_bh=hc1_init_bh,
            hc2_init_bh=hc2_init_bh,
            trace_in=trace_in,
            resets_bt=resets_bt,
        )
    else:
        y2h_t, (h1_n, h2_n), trace_out = select_backend(
            triton_fn="cortex.kernels.triton.rtu:rtu_stream_diag_triton",
            pytorch_fn=rtu_stream_diag_pytorch,
            tensor=x_btd,
            cuda_fn="cortex.kernels.cuda.rtu:rtu_stream_diag_cuda",
            allow_cuda=x_btd.is_cuda and prefer_cuda,
        )(
            x_btd=x_btd,
            nu_log=nu_log,
            theta_log=theta_log,
            w1=w1,
            w2=w2,
            activation_name=activation_name,
            hc1_init_bh=hc1_init_bh,
            hc2_init_bh=hc2_init_bh,
            trace_in=trace_in,
            resets_bt=resets_bt,
        )

    if is_step:
        return F.linear(y2h_t.squeeze(1), out_weight, out_bias), h1_n, h2_n, trace_out

    y = F.linear(y2h_t.reshape(batch * seq_len, -1), out_weight, out_bias)
    return y.reshape(batch, seq_len, out_weight.shape[0]), h1_n, h2_n, trace_out


def run_slstm_sequence(
    *,
    Wx: torch.Tensor,
    R: torch.Tensor,
    b: torch.Tensor,
    initial_states: torch.Tensor,
    resets: torch.Tensor | None,
    hidden_size: int,
    num_heads: int,
    head_dim: int,
    outnorm_weight: torch.Tensor | None,
    outnorm_bias: torch.Tensor | None,
    outnorm_eps: float,
    dropout: torch.nn.Module,
    is_step: bool,
) -> tuple[torch.Tensor, tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]]:
    batch, seq_len = Wx.shape[:2]
    allow_triton = head_dim >= 16 and (head_dim & (head_dim - 1)) == 0 and head_dim <= 512

    if is_batchedtensor(R):
        R_phys, level = unwrap_batchedtensor(R)
        if level is None:
            raise RuntimeError("Expected a functorch batch level for sLSTM vmapped execution")
        ensemble = R_phys.shape[0]
        Wx_phys = _physical_or_shared(Wx, ensemble)
        b_phys = _physical_or_shared(b, ensemble)
        states_phys = _physical_or_shared(initial_states, ensemble)
        resets = _shared_resets_or_none(resets, "sLSTMCore")
        assert Wx_phys is not None and b_phys is not None and states_phys is not None

        all_states_fold, last_state_fold = select_backend(
            triton_fn="cortex.kernels.triton.slstm:slstm_sequence_triton",
            pytorch_fn=slstm_sequence_pytorch,
            tensor=Wx_phys,
            allow_triton=allow_triton,
        )(
            Wx=Wx_phys.permute(1, 2, 3, 0, 4, 5).reshape(batch, seq_len, 4, ensemble * num_heads, head_dim),
            R=R_phys.permute(1, 0, 2, 3, 4).reshape(4, ensemble * num_heads, head_dim, head_dim),
            b=b_phys.permute(1, 0, 2, 3).reshape(4, ensemble * num_heads, head_dim),
            initial_states=states_phys.permute(1, 2, 0, 3, 4).reshape(4, batch, ensemble * num_heads, head_dim),
            resets=resets,
        )

        y_heads_phys = all_states_fold[:, 0].view(seq_len, batch, ensemble, num_heads, head_dim).permute(2, 1, 3, 0, 4)
        y_heads_phys = dropout(y_heads_phys)
        y_norm_phys = apply_multihead_layernorm(
            y_heads_phys,
            weight=_physical_or_shared(outnorm_weight, ensemble),
            bias=_physical_or_shared(outnorm_bias, ensemble),
            eps=outnorm_eps,
        )
        y_out_phys = y_norm_phys.transpose(2, 3).reshape(ensemble, batch, seq_len, hidden_size)
        y_out = wrap_batchedtensor(y_out_phys[:, :, 0, :] if is_step else y_out_phys, level)
        last_states = tuple(
            wrap_batchedtensor(
                last_state_fold[index]
                .view(batch, ensemble, num_heads, head_dim)
                .permute(1, 0, 2, 3)
                .reshape(ensemble, batch, hidden_size),
                level,
            )
            for index in range(4)
        )
        return y_out, last_states  # type: ignore[return-value]

    all_states, last_state = select_backend(
        triton_fn="cortex.kernels.triton.slstm:slstm_sequence_triton",
        pytorch_fn=slstm_sequence_pytorch,
        tensor=Wx,
        allow_triton=allow_triton,
    )(
        Wx=Wx,
        R=R,
        b=b,
        initial_states=initial_states,
        resets=resets,
    )
    y_heads = dropout(all_states[:, 0].permute(1, 2, 0, 3))
    y_out = (
        apply_multihead_layernorm(
            y_heads,
            weight=outnorm_weight,
            bias=outnorm_bias,
            eps=outnorm_eps,
        )
        .transpose(1, 2)
        .reshape(batch, seq_len, hidden_size)
    )
    return (
        y_out[:, 0, :] if is_step else y_out,
        tuple(last_state[index].reshape(batch, hidden_size) for index in range(4)),
    )


def run_mlstm(
    *,
    queries: torch.Tensor,
    keys: torch.Tensor,
    values: torch.Tensor,
    igate_preact: torch.Tensor,
    fgate_preact: torch.Tensor,
    c_state: torch.Tensor,
    n_state: torch.Tensor,
    m_state: torch.Tensor,
    resets: torch.Tensor | None,
    hidden_size: int,
    num_heads: int,
    head_dim: int,
    chunk_size: int,
    outnorm_weight: torch.Tensor | None,
    outnorm_bias: torch.Tensor | None,
    outnorm_eps: float,
    is_step: bool,
) -> tuple[torch.Tensor, tuple[torch.Tensor, torch.Tensor, torch.Tensor]]:
    batch = queries.shape[0]

    if is_step:
        if is_batchedtensor(c_state):
            c_phys, level = unwrap_batchedtensor(c_state)
            if level is None:
                raise RuntimeError("Expected a functorch batch level for mLSTM vmapped step execution")
            ensemble = c_phys.shape[0]
            n_phys = _physical_or_shared(n_state, ensemble)
            m_phys = _physical_or_shared(m_state, ensemble)
            q_phys = _physical_or_shared(queries, ensemble)
            k_phys = _physical_or_shared(keys, ensemble)
            v_phys = _physical_or_shared(values, ensemble)
            igate_phys = _physical_or_shared(igate_preact, ensemble)
            fgate_phys = _physical_or_shared(fgate_preact, ensemble)
            reset_step = _shared_resets_or_none(resets, "mLSTMCore")
            reset_step = None if reset_step is None else reset_step.view(batch)
            assert n_phys is not None and m_phys is not None
            assert q_phys is not None and k_phys is not None and v_phys is not None
            assert igate_phys is not None and fgate_phys is not None

            h_fold, (c_fold_new, n_fold_new, m_fold_new) = mlstm_recurrent_step_stabilized_simple(
                c_state=c_phys.permute(1, 0, 2, 3, 4).reshape(batch, ensemble * num_heads, head_dim, head_dim),
                n_state=n_phys.permute(1, 0, 2, 3, 4).reshape(batch, ensemble * num_heads, head_dim, 1),
                m_state=m_phys.permute(1, 0, 2, 3, 4).reshape(batch, ensemble * num_heads, 1, 1),
                q=q_phys.permute(1, 0, 2, 3, 4).reshape(batch, ensemble * num_heads, 1, head_dim),
                k=k_phys.permute(1, 0, 2, 3, 4).reshape(batch, ensemble * num_heads, 1, head_dim),
                v=v_phys.permute(1, 0, 2, 3, 4).reshape(batch, ensemble * num_heads, 1, head_dim),
                igate_preact=igate_phys.permute(1, 0, 2, 3).reshape(batch, ensemble * num_heads, 1).unsqueeze(-1),
                fgate_preact=fgate_phys.permute(1, 0, 2, 3).reshape(batch, ensemble * num_heads, 1).unsqueeze(-1),
                reset_mask=reset_step,
            )
            h_phys = h_fold.view(batch, ensemble, num_heads, 1, head_dim).permute(1, 0, 2, 3, 4)
            y_out = wrap_batchedtensor(
                apply_multihead_layernorm(
                    h_phys,
                    weight=_physical_or_shared(outnorm_weight, ensemble),
                    bias=_physical_or_shared(outnorm_bias, ensemble),
                    eps=outnorm_eps,
                )
                .transpose(2, 3)
                .reshape(ensemble, batch, 1, hidden_size)[:, :, 0, :],
                level,
            )
            c_new = wrap_batchedtensor(
                c_fold_new.view(batch, ensemble, num_heads, head_dim, head_dim).permute(1, 0, 2, 3, 4),
                level,
            )
            n_new = wrap_batchedtensor(
                n_fold_new.view(batch, ensemble, num_heads, head_dim, 1).permute(1, 0, 2, 3, 4),
                level,
            )
            m_new = wrap_batchedtensor(
                m_fold_new.view(batch, ensemble, num_heads, 1, 1).permute(1, 0, 2, 3, 4),
                level,
            )
            return y_out, (c_new, n_new, m_new)

        reset_step = None if resets is None else resets.view(batch)
        h_state, (c_new, n_new, m_new) = mlstm_recurrent_step_stabilized_simple(
            c_state=c_state,
            n_state=n_state,
            m_state=m_state,
            q=queries,
            k=keys,
            v=values,
            igate_preact=igate_preact.unsqueeze(-1),
            fgate_preact=fgate_preact.unsqueeze(-1),
            reset_mask=reset_step,
        )
        y_out = (
            apply_multihead_layernorm(
                h_state,
                weight=outnorm_weight,
                bias=outnorm_bias,
                eps=outnorm_eps,
            )
            .transpose(1, 2)
            .reshape(batch, 1, hidden_size)
        )
        return y_out[:, 0, :], (c_new, n_new, m_new)

    if resets is not None:
        if resets.dim() == 1:
            reset_mask = torch.zeros(batch, queries.shape[2], dtype=resets.dtype, device=queries.device)
            reset_mask[:, 0] = resets
        else:
            reset_mask = resets
    else:
        reset_mask = None

    if is_batchedtensor(c_state):
        c_phys, level = unwrap_batchedtensor(c_state)
        if level is None:
            raise RuntimeError("Expected a functorch batch level for mLSTM vmapped execution")
        ensemble = c_phys.shape[0]
        n_phys = _physical_or_shared(n_state, ensemble)
        m_phys = _physical_or_shared(m_state, ensemble)
        q_phys = _physical_or_shared(queries, ensemble)
        k_phys = _physical_or_shared(keys, ensemble)
        v_phys = _physical_or_shared(values, ensemble)
        igate_phys = _physical_or_shared(igate_preact, ensemble)
        fgate_phys = _physical_or_shared(fgate_preact, ensemble)
        reset_mask = _shared_resets_or_none(reset_mask, "mLSTMCore")
        assert n_phys is not None and m_phys is not None
        assert q_phys is not None and k_phys is not None and v_phys is not None
        assert igate_phys is not None and fgate_phys is not None

        h_fold, (c_fold_new, n_fold_new, m_fold_new) = select_backend(
            triton_fn="cortex.kernels.triton.mlstm:mlstm_chunkwise_triton",
            pytorch_fn=mlstm_chunkwise_simple,
            tensor=q_phys,
        )(
            queries=q_phys.permute(1, 0, 2, 3, 4).reshape(batch, ensemble * num_heads, queries.shape[2], head_dim),
            keys=k_phys.permute(1, 0, 2, 3, 4).reshape(batch, ensemble * num_heads, queries.shape[2], head_dim),
            values=v_phys.permute(1, 0, 2, 3, 4).reshape(batch, ensemble * num_heads, queries.shape[2], head_dim),
            igate_preact=igate_phys.permute(1, 0, 2, 3).reshape(batch, ensemble * num_heads, queries.shape[2]),
            fgate_preact=fgate_phys.permute(1, 0, 2, 3).reshape(batch, ensemble * num_heads, queries.shape[2]),
            initial_C=c_phys.permute(1, 0, 2, 3, 4).reshape(batch, ensemble * num_heads, head_dim, head_dim),
            initial_n=n_phys.permute(1, 0, 2, 3, 4).reshape(batch, ensemble * num_heads, head_dim, 1),
            initial_m=m_phys.permute(1, 0, 2, 3, 4).reshape(batch, ensemble * num_heads, 1, 1),
            reset_mask=reset_mask,
            chunk_size=chunk_size,
            return_last_state=True,
        )
        h_phys = h_fold.view(batch, ensemble, num_heads, queries.shape[2], head_dim).permute(1, 0, 2, 3, 4)
        y_out = wrap_batchedtensor(
            apply_multihead_layernorm(
                h_phys,
                weight=_physical_or_shared(outnorm_weight, ensemble),
                bias=_physical_or_shared(outnorm_bias, ensemble),
                eps=outnorm_eps,
            )
            .transpose(2, 3)
            .reshape(ensemble, batch, queries.shape[2], hidden_size),
            level,
        )
        c_new = wrap_batchedtensor(
            c_fold_new.view(batch, ensemble, num_heads, head_dim, head_dim).permute(1, 0, 2, 3, 4),
            level,
        )
        n_new = wrap_batchedtensor(
            n_fold_new.view(batch, ensemble, num_heads, head_dim, 1).permute(1, 0, 2, 3, 4),
            level,
        )
        m_new = wrap_batchedtensor(
            m_fold_new.view(batch, ensemble, num_heads, 1, 1).permute(1, 0, 2, 3, 4),
            level,
        )
        return y_out, (c_new, n_new, m_new)

    h_state, (c_new, n_new, m_new) = select_backend(
        triton_fn="cortex.kernels.triton.mlstm:mlstm_chunkwise_triton",
        pytorch_fn=mlstm_chunkwise_simple,
        tensor=queries,
    )(
        queries=queries,
        keys=keys,
        values=values,
        igate_preact=igate_preact,
        fgate_preact=fgate_preact,
        initial_C=c_state,
        initial_n=n_state,
        initial_m=m_state,
        reset_mask=reset_mask,
        chunk_size=chunk_size,
        return_last_state=True,
    )
    y_out = (
        apply_multihead_layernorm(
            h_state,
            weight=outnorm_weight,
            bias=outnorm_bias,
            eps=outnorm_eps,
        )
        .transpose(1, 2)
        .reshape(batch, queries.shape[2], hidden_size)
    )
    return y_out, (c_new, n_new, m_new)


__all__ = [
    "apply_multihead_layernorm",
    "apply_multihead_layernorm_physical",
    "run_axon_rtu",
    "run_causal_conv1d",
    "run_discounted_sum",
    "run_mlstm",
    "run_slstm_sequence",
]
