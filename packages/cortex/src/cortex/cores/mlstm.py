"""Matrix LSTM core with parallel chunk processing and normalized state."""

from __future__ import annotations

from typing import Optional, Tuple

import torch
import torch.nn as nn
from tensordict import TensorDict

from cortex.config import CausalConv1dCoreConfig, mLSTMCoreConfig
from cortex.cores.base import MemoryCore
from cortex.cores.conv import CausalConv1dCore
from cortex.cores.core import AxonLayer, update_parent_state
from cortex.cores.registry import register_core
from cortex.kernels.dispatch import apply_multihead_layernorm, run_mlstm
from cortex.types import MaybeState, ResetMask, Tensor


def bias_linspace_init_(param: torch.Tensor, start: float = 3.4, end: float = 6.0) -> torch.Tensor:
    """Linearly spaced bias init across dimensions."""
    assert param.dim() == 1, f"param must be 1-dimensional (typically a bias), got {param.dim()}"
    n_dims = param.shape[0]
    init_vals = torch.linspace(start, end, n_dims)
    with torch.no_grad():
        param.copy_(init_vals)
    return param


class MultiHeadLayerNorm(nn.Module):
    """Multi-head layer normalization using group normalization."""

    def __init__(self, ndim: int, weight: bool = True, bias: bool = False, eps: float = 1e-5):
        super().__init__()
        self.weight = nn.Parameter(torch.ones(ndim)) if weight else None
        self.bias = nn.Parameter(torch.zeros(ndim)) if bias else None
        self.eps = eps
        self.ndim = ndim

    def forward(self, input: torch.Tensor) -> torch.Tensor:
        return apply_multihead_layernorm(
            input,
            weight=self.weight,
            bias=self.bias,
            eps=self.eps,
        )

    def reset_parameters(self):
        if self.weight is not None:
            nn.init.ones_(self.weight)
        if self.bias is not None:
            nn.init.zeros_(self.bias)


@register_core(mLSTMCoreConfig)
class mLSTMCore(MemoryCore):
    """Matrix LSTM core with matrix-valued state and parallel/recurrent processing modes."""

    def __init__(self, cfg: mLSTMCoreConfig) -> None:
        super().__init__(hidden_size=cfg.hidden_size)
        self.cfg = cfg

        assert cfg.hidden_size % cfg.num_heads == 0, "hidden_size must be divisible by num_heads"
        self.head_dim = cfg.hidden_size // cfg.num_heads

        # Input/forget gates: either Axon-backed or legacy Linear depending on flag
        H = cfg.hidden_size
        NH = cfg.num_heads
        if cfg.use_axon_layer:
            in_features = 3 * H
            out_features = NH
            # Allow override from parent config; if None, AxonLayer chooses defaults.
            ax_cfg = cfg.axon_layer_config
            self.igate = AxonLayer(
                in_features,
                out_features,
                cfg=ax_cfg,
                name="igate",
                group="mlstm",
            )
            self.fgate = AxonLayer(in_features, out_features, cfg=ax_cfg, name="fgate", group="mlstm")
        else:
            self.igate = nn.Linear(3 * H, NH)
            self.fgate = nn.Linear(3 * H, NH)

        # Q/K/V preprocessing: always apply causal conv; optionally add Axon QKV
        self.conv_kernel_size = cfg.conv1d_kernel_size
        conv_config = CausalConv1dCoreConfig(
            hidden_size=cfg.hidden_size,
            kernel_size=self.conv_kernel_size,
            causal_conv_bias=True,
            channel_mixing=False,  # depthwise convolution
        )
        self.conv1d_core = CausalConv1dCore(conv_config)
        self.conv_act = nn.SiLU()

        if not cfg.use_axon_qkv:
            self.qkv_act = None
            self.q_layer = None
            self.k_layer = None
            self.v_layer = None
            self.qk_layer = None
            self.use_axon_qkv = False
        else:
            self.use_axon_qkv = True
            H = int(cfg.hidden_size)

            qkv_cfg = cfg.axon_qkv_config or None
            self.qkv_act = nn.SiLU()  # match conv+SiLU behavior
            # Shared-QK: single layer feeds both q and k; v has its own layer
            self.qk_layer = AxonLayer(H, H, cfg=qkv_cfg, name="qk", group="mlstm_qkv")
            self.v_layer = AxonLayer(H, H, cfg=qkv_cfg, name="v", group="mlstm_qkv")
            self.q_layer = None
            self.k_layer = None

        # Output normalization
        self.outnorm = MultiHeadLayerNorm(cfg.hidden_size, weight=True, bias=False)

        self.reset_parameters()

    def reset_parameters(self):
        """Initialize parameters."""
        self.outnorm.reset_parameters()
        if self.conv1d_core is not None:
            self.conv1d_core.reset_parameters()
        # Initialize gates
        if not self.cfg.use_axon_layer:
            # Forget gate initialization (encourages retention)
            torch.nn.init.zeros_(self.fgate.weight)
            bias_linspace_init_(self.fgate.bias, start=3.0, end=6.0)
            # Input gate initialization
            torch.nn.init.zeros_(self.igate.weight)
            torch.nn.init.normal_(self.igate.bias, mean=0.0, std=0.1)
        else:
            # When using Axon-backed gates, initialize the internal linear branch
            f_lin = getattr(self.fgate, "linear", None)
            if f_lin is not None:
                torch.nn.init.zeros_(f_lin.weight)
                if f_lin.bias is not None:
                    bias_linspace_init_(f_lin.bias, start=3.0, end=6.0)
            i_lin = getattr(self.igate, "linear", None)
            if i_lin is not None:
                torch.nn.init.zeros_(i_lin.weight)
                if i_lin.bias is not None:
                    torch.nn.init.normal_(i_lin.bias, mean=0.0, std=0.1)

    def init_state(self, batch: int, *, device: torch.device | str, dtype: torch.dtype) -> TensorDict:
        """Initialize state tensors."""
        B = batch
        NH = self.cfg.num_heads
        DH = self.head_dim

        c_state = torch.zeros(B, NH, DH, DH, device=device, dtype=dtype)
        n_state = torch.zeros(B, NH, DH, 1, device=device, dtype=dtype)
        m_state = torch.zeros(B, NH, 1, 1, device=device, dtype=dtype)

        # Get conv state from the conv1d cell if in use
        if self.conv1d_core is not None:
            conv_state = self.conv1d_core.init_state(batch, device=device, dtype=dtype)
        else:
            conv_state = TensorDict({}, batch_size=[B])

        # Combine all states
        combined_state = TensorDict({"c": c_state, "n": n_state, "m": m_state}, batch_size=[B])
        combined_state.update(conv_state)  # Add conv state
        if self.cfg.use_axon_layer:
            gate_group = TensorDict({}, batch_size=[B])
            gate_group[self.igate.state_path()[1]] = self.igate.core.init_state(batch=B, device=device, dtype=dtype)
            gate_group[self.fgate.state_path()[1]] = self.fgate.core.init_state(batch=B, device=device, dtype=dtype)
            combined_state[self.igate.state_path()[0]] = gate_group
        if self.cfg.use_axon_qkv:
            qkv_group = TensorDict({}, batch_size=[B])
            qkv_group[self.qk_layer.state_path()[1]] = self.qk_layer.core.init_state(
                batch=B,
                device=device,
                dtype=dtype,
            )
            qkv_group[self.v_layer.state_path()[1]] = self.v_layer.core.init_state(batch=B, device=device, dtype=dtype)
            combined_state[self.qk_layer.state_path()[0]] = qkv_group
        return combined_state

    def forward(
        self,
        x: Tensor,
        state: MaybeState,
        *,
        resets: Optional[ResetMask] = None,
    ) -> Tuple[Tensor, MaybeState]:
        """Apply mLSTM with automatic backend selection for step or chunk processing."""
        # Check if single step
        is_step = x.dim() == 2
        if is_step:
            x_seq = x.unsqueeze(1)  # [B, H] -> [B, 1, H]
        else:
            x_seq = x  # [B, T, H]

        B, T, H = x_seq.shape

        # Initialize or get state
        if state is None or not all(k in state for k in ["c", "n", "m"]):
            st = self.init_state(batch=B, device=x.device, dtype=x.dtype)
        else:
            st = state

        c_state = st.get("c")  # [B, NH, DH, DH]
        n_state = st.get("n")  # [B, NH, DH, 1]
        m_state = st.get("m")  # [B, NH, 1, 1]

        # Note: mLSTM backends support reset masks directly. For step we pass a
        # [B] mask; for sequences we pass a [B, T] mask to the chunkwise backend.

        # Always run causal conv to precondition Q/K inputs
        if st is not None and "conv" in st:
            conv_state_dict = TensorDict({"conv": st.get("conv")}, batch_size=[B])
        else:
            conv_state_dict = None
        if is_step:
            x_conv, conv_state_new = self.conv1d_core(x_seq.squeeze(1), conv_state_dict, resets=resets)
            x_conv = x_conv.unsqueeze(1)  # [B, H] -> [B, 1, H]
        else:
            x_conv, conv_state_new = self.conv1d_core(x_seq, conv_state_dict, resets=resets)
        x_conv_act = self.conv_act(x_conv)

        # Build Q, K, V
        if not self.cfg.use_axon_qkv:
            # Q/K from conv, V is raw input
            q = x_conv_act
            k = x_conv_act
            v = x_seq
        else:
            # Axon-backed Q,K use conv-preconditioned input; V from raw input
            qk = self.qk_layer(x_conv_act, state=st, resets=resets)
            q = self.qkv_act(qk)
            k = self.qkv_act(qk)
            v = self.v_layer(x_seq, state=st, resets=resets)

        if_gate_input = torch.cat([q, k, v], dim=-1)

        # Reshape Q, K, V
        q = q.view(B, T, self.cfg.num_heads, self.head_dim)  # [B, T, NH, DH]
        k = k.view(B, T, self.cfg.num_heads, self.head_dim)  # [B, T, NH, DH]
        v = v.view(B, T, self.cfg.num_heads, self.head_dim)  # [B, T, NH, DH]

        # Transpose for processing
        q = q.transpose(1, 2)  # [B, NH, T, DH]
        k = k.transpose(1, 2)  # [B, NH, T, DH]
        v = v.transpose(1, 2)  # [B, NH, T, DH]

        # Compute gates
        if self.cfg.use_axon_layer:
            igate_preact = self.igate(if_gate_input, state=st, resets=resets)  # [B, T, NH]
            fgate_preact = self.fgate(if_gate_input, state=st, resets=resets)  # [B, T, NH]
        else:
            igate_preact = self.igate(if_gate_input)  # [B, T, NH]
            fgate_preact = self.fgate(if_gate_input)  # [B, T, NH]
        igate_preact = igate_preact.transpose(-1, -2)  # [B, NH, T]
        fgate_preact = fgate_preact.transpose(-1, -2)  # [B, NH, T]
        h_state_norm, (c_new, n_new, m_new) = run_mlstm(
            queries=q,
            keys=k,
            values=v,
            igate_preact=igate_preact,
            fgate_preact=fgate_preact,
            c_state=c_state,
            n_state=n_state,
            m_state=m_state,
            resets=resets,
            hidden_size=H,
            num_heads=self.cfg.num_heads,
            head_dim=self.head_dim,
            chunk_size=self.cfg.chunk_size,
            outnorm_weight=self.outnorm.weight,
            outnorm_bias=self.outnorm.bias,
            outnorm_eps=self.outnorm.eps,
            is_step=is_step,
        )
        new_state = TensorDict({"c": c_new, "n": n_new, "m": m_new}, batch_size=[B])
        if conv_state_new is not None:
            new_state.update(conv_state_new)
        update_parent_state(new_state, st)

        # Return in original shape
        if is_step:
            return h_state_norm.squeeze(1), new_state  # [B, H]
        else:
            return h_state_norm, new_state  # [B, T, H]

    def reset_state(self, state: MaybeState, mask: ResetMask) -> MaybeState:
        """Reset state for masked batch elements."""
        if state is None:
            return state

        mask_expanded = mask.to(dtype=state["c"].dtype).view(-1, 1, 1, 1)
        state["c"] = state["c"] * (1.0 - mask_expanded)
        state["n"] = state["n"] * (1.0 - mask_expanded)
        state["m"] = state["m"] * (1.0 - mask_expanded)

        # Reset conv state using the CausalConv1d cell's reset_state method (if used)
        if self.conv1d_core is not None and "conv" in state:
            conv_state_dict = TensorDict({"conv": state["conv"]}, batch_size=[state["c"].shape[0]])
            conv_state_dict = self.conv1d_core.reset_state(conv_state_dict, mask)
            # Avoid boolean conversion of TensorDict
            if "conv" in conv_state_dict:
                state["conv"] = conv_state_dict["conv"]

        # Reset Axon gate substates if AxonLayer is enabled
        if self.cfg.use_axon_layer:
            self.igate.reset_state(mask, state)
            self.fgate.reset_state(mask, state)

        # Reset Axon QKV substates when enabled (shared QK + V)
        if self.cfg.use_axon_qkv:
            self.qk_layer.reset_state(mask, state)
            self.v_layer.reset_state(mask, state)

        return state


__all__ = ["mLSTMCore", "mLSTMCoreConfig"]
