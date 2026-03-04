import torch
from tensordict import TensorDict

from metta.rl.utils import _infer_tensordict_device, add_dummy_loss_for_unused_params


def test_infer_tensordict_device_from_tensor_values() -> None:
    td = TensorDict(
        {
            "obs": torch.randn(2, 3),
            "values": torch.randn(2, 1),
        },
        batch_size=[2],
    )

    assert _infer_tensordict_device(td) == torch.device("cpu")


def test_add_dummy_loss_for_unused_params_handles_tensordict_keys() -> None:
    td = TensorDict(
        {
            "used": torch.randn(2, requires_grad=True),
            "unused": torch.randn(2, requires_grad=True),
        },
        batch_size=[2],
    )

    loss = td["used"].sum()
    loss = add_dummy_loss_for_unused_params(loss, td=td, used_keys={"used"})
    loss.backward()

    assert td["unused"].grad is not None
    assert torch.allclose(td["unused"].grad, torch.zeros_like(td["unused"].grad))
