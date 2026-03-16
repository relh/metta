from __future__ import annotations

import os

import torch
from cortex.utils import autograd_function_vmap_passthrough
from torch.autograd import Function
from torch.utils.cpp_extension import load

_mod_path = os.path.dirname(__file__)
_ext = None


def _load_ext():
    global _ext
    if _ext is not None:
        return _ext

    _ext = load(
        name="srht_cuda",
        sources=[
            os.path.join(_mod_path, "srht_binding.cpp"),
            os.path.join(_mod_path, "srht_kernels.cu"),
        ],
        extra_cflags=["-O3"],
        extra_cuda_cflags=["-O3", "-Xptxas", "-O3"],
        build_directory=None,
        verbose=False,
    )
    return _ext


class _SRHTCudaFunc(Function):
    @staticmethod
    def forward(
        x_btd: torch.Tensor,
        signs_h: torch.Tensor,
        perm_h: torch.Tensor | None,
        normalize: bool,
    ):
        ext = _load_ext()
        perm_ctg = None if perm_h is None else perm_h.contiguous()
        (y,) = ext.forward(x_btd.contiguous(), signs_h.contiguous(), perm_ctg, normalize)
        return y

    @staticmethod
    def setup_context(ctx, inputs, output):
        _x_btd, signs_h, perm_h, normalize = inputs
        empty = torch.tensor([], dtype=torch.long, device=signs_h.device)
        ctx.save_for_backward(signs_h, perm_h if perm_h is not None else empty)
        ctx.normalize = normalize

    @staticmethod
    def backward(ctx, grad_y: torch.Tensor):
        signs_h, perm = ctx.saved_tensors
        perm_h = None if perm.numel() == 0 else perm
        ext = _load_ext()
        perm_ctg = None if perm_h is None else perm_h.contiguous()
        (grad_x,) = ext.backward(grad_y.contiguous(), signs_h.contiguous(), perm_ctg, ctx.normalize)
        return grad_x, None, None, None

    @staticmethod
    def vmap(info, in_dims, *args):
        return autograd_function_vmap_passthrough("srht_cuda", _SRHTCudaFunc.forward, in_dims, *args)


def srht_cuda(
    x_btd: torch.Tensor,
    signs_h: torch.Tensor,
    perm_h: torch.Tensor | None,
    *,
    normalize: bool = True,
) -> torch.Tensor:
    return _SRHTCudaFunc.apply(x_btd, signs_h, perm_h, normalize)


__all__ = ["srht_cuda"]
