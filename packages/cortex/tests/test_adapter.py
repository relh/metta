"""Tests for the AdapterScaffold wrapper."""

import torch
from cortex import (
    AdapterScaffoldConfig,
    CortexStack,
    CortexStackConfig,
    LSTMCoreConfig,
    PassThroughScaffoldConfig,
    PreUpScaffoldConfig,
)


def test_adapter_identity_at_init():
    """Test that adapter block is identity at initialization."""
    device = torch.device("cpu")
    dtype = torch.float32
    batch_size = 2
    seq_len = 5
    d_hidden = 64

    # Create a stack with an adapter wrapping a PassThrough block
    config = CortexStackConfig(
        d_hidden=d_hidden,
        scaffolds=[
            AdapterScaffoldConfig(
                base_scaffold=PassThroughScaffoldConfig(core=LSTMCoreConfig(hidden_size=64, num_layers=1)),
                bottleneck=16,
                per_channel_gate=False,
            )
        ],
        post_norm=False,  # No post norm to test pure adapter behavior
    )

    stack = CortexStack(config)
    stack.to(device=device, dtype=dtype)
    stack.eval()

    # Create input
    x = torch.randn(batch_size, seq_len, d_hidden, device=device, dtype=dtype)
    state = stack.init_state(batch=batch_size, device=device, dtype=dtype)

    # Run the wrapped block directly (without adapter)
    base_block = stack.scaffolds[0].wrapped_scaffold
    base_state = state["AdapterScaffold_0"]["wrapped"]
    y_base, _ = base_block(x, base_state)

    # Run through adapter
    y_adapter, _ = stack(x, state)

    # Should be identical at init (gate=0)
    assert torch.allclose(y_adapter, y_base, atol=1e-6), (
        f"Adapter should be identity at init. Max diff: {(y_adapter - y_base).abs().max()}"
    )


def test_adapter_wraps_preup():
    """Test adapter wrapping a PreUp block."""
    device = torch.device("cpu")
    dtype = torch.float32
    batch_size = 2
    seq_len = 5
    d_hidden = 64

    config = CortexStackConfig(
        d_hidden=d_hidden,
        scaffolds=[
            AdapterScaffoldConfig(
                base_scaffold=PreUpScaffoldConfig(
                    core=LSTMCoreConfig(hidden_size=None, num_layers=1),
                    proj_factor=2.0,
                ),
                bottleneck=16,
                per_channel_gate=True,
            )
        ],
        post_norm=True,
    )

    stack = CortexStack(config)
    stack.to(device=device, dtype=dtype)

    x = torch.randn(batch_size, seq_len, d_hidden, device=device, dtype=dtype)
    state = stack.init_state(batch=batch_size, device=device, dtype=dtype)

    y, new_state = stack(x, state)

    # Check shapes
    assert y.shape == x.shape, f"Expected {x.shape}, got {y.shape}"
    assert "AdapterScaffold_0" in new_state
    assert "wrapped" in new_state["AdapterScaffold_0"]


def test_adapter_state_management():
    """Test that adapter properly manages wrapped block state."""
    device = torch.device("cpu")
    dtype = torch.float32
    batch_size = 2
    d_hidden = 64

    config = CortexStackConfig(
        d_hidden=d_hidden,
        scaffolds=[
            AdapterScaffoldConfig(
                base_scaffold=PassThroughScaffoldConfig(core=LSTMCoreConfig(hidden_size=64, num_layers=1)),
                bottleneck=16,
            )
        ],
        post_norm=False,
    )

    stack = CortexStack(config)
    stack.to(device=device, dtype=dtype)

    # Single-step mode
    x1 = torch.randn(batch_size, d_hidden, device=device, dtype=dtype)
    state = stack.init_state(batch=batch_size, device=device, dtype=dtype)

    y1, state = stack.step(x1, state)
    assert y1.shape == (batch_size, d_hidden)

    # State should be carried forward
    x2 = torch.randn(batch_size, d_hidden, device=device, dtype=dtype)
    y2, state = stack.step(x2, state)
    assert y2.shape == (batch_size, d_hidden)

    # Check state structure
    assert "AdapterScaffold_0" in state
    assert "wrapped" in state["AdapterScaffold_0"]
    assert "LSTMCore" in state["AdapterScaffold_0"]["wrapped"]
    assert "h" in state["AdapterScaffold_0"]["wrapped"]["LSTMCore"]


def test_adapter_reset_handling():
    """Test that adapter properly handles resets."""
    device = torch.device("cpu")
    dtype = torch.float32
    batch_size = 4
    seq_len = 10
    d_hidden = 64

    config = CortexStackConfig(
        d_hidden=d_hidden,
        scaffolds=[
            AdapterScaffoldConfig(
                base_scaffold=PassThroughScaffoldConfig(core=LSTMCoreConfig(hidden_size=64, num_layers=1)),
                bottleneck=16,
            )
        ],
        post_norm=False,
    )

    stack = CortexStack(config)
    stack.to(device=device, dtype=dtype)

    x = torch.randn(batch_size, seq_len, d_hidden, device=device, dtype=dtype)
    state = stack.init_state(batch=batch_size, device=device, dtype=dtype)

    # Create reset mask - reset half the batch at timestep 5
    resets = torch.zeros(batch_size, seq_len, dtype=torch.bool, device=device)
    resets[:2, 5] = True

    y, new_state = stack(x, state, resets=resets)

    assert y.shape == x.shape
    assert new_state is not None


def test_adapter_gradient_flow():
    """Test that gradients flow through adapter but can be frozen separately."""
    device = torch.device("cpu")
    dtype = torch.float32
    batch_size = 2
    seq_len = 5
    d_hidden = 64

    config = CortexStackConfig(
        d_hidden=d_hidden,
        scaffolds=[
            AdapterScaffoldConfig(
                base_scaffold=PassThroughScaffoldConfig(core=LSTMCoreConfig(hidden_size=64, num_layers=1)),
                bottleneck=16,
            )
        ],
        post_norm=False,
    )

    stack = CortexStack(config)
    stack.to(device=device, dtype=dtype)
    stack.train()

    # Freeze wrapped block
    for param in stack.scaffolds[0].wrapped_scaffold.parameters():
        param.requires_grad = False

    x = torch.randn(batch_size, seq_len, d_hidden, device=device, dtype=dtype)
    state = stack.init_state(batch=batch_size, device=device, dtype=dtype)

    y, _ = stack(x, state)
    loss = y.sum()
    loss.backward()

    # Check that adapter params have gradients
    assert stack.scaffolds[0].gate.grad is not None, "Adapter gate should have gradients"
    assert stack.scaffolds[0].down.weight.grad is not None, "Adapter down proj should have gradients"

    # Check that wrapped block params do NOT have gradients
    for name, param in stack.scaffolds[0].wrapped_scaffold.named_parameters():
        assert param.grad is None, f"Wrapped block param {name} should not have gradients"


def test_adapter_multiple_in_stack():
    """Test multiple adapters in a stack."""
    device = torch.device("cpu")
    dtype = torch.float32
    batch_size = 2
    seq_len = 5
    d_hidden = 64

    config = CortexStackConfig(
        d_hidden=d_hidden,
        scaffolds=[
            PassThroughScaffoldConfig(core=LSTMCoreConfig(hidden_size=64, num_layers=1)),
            AdapterScaffoldConfig(
                base_scaffold=PassThroughScaffoldConfig(core=LSTMCoreConfig(hidden_size=64, num_layers=1)),
                bottleneck=16,
            ),
            PassThroughScaffoldConfig(core=LSTMCoreConfig(hidden_size=64, num_layers=1)),
            AdapterScaffoldConfig(
                base_scaffold=PreUpScaffoldConfig(
                    core=LSTMCoreConfig(hidden_size=None, num_layers=1),
                    proj_factor=2.0,
                ),
                bottleneck=32,
                per_channel_gate=True,
            ),
        ],
        post_norm=True,
    )

    stack = CortexStack(config)
    stack.to(device=device, dtype=dtype)

    x = torch.randn(batch_size, seq_len, d_hidden, device=device, dtype=dtype)
    state = stack.init_state(batch=batch_size, device=device, dtype=dtype)

    y, new_state = stack(x, state)

    assert y.shape == x.shape
    assert len(new_state.keys()) == 4  # 4 scaffolds
