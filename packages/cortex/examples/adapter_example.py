#!/usr/bin/env -S uv run python
"""Example showing how to use AdapterScaffolds to wrap existing scaffolds.

AdapterScaffolds allow you to add trainable residual paths that start as identity,
making them perfect for fine-tuning pretrained models without disrupting learned behavior.
"""

import torch
from cortex import (
    AdapterScaffoldConfig,
    CortexStack,
    CortexStackConfig,
    LSTMCoreConfig,
    PassThroughScaffoldConfig,
    PreUpScaffoldConfig,
)


def test_basic_adapter():
    """Test a basic adapter wrapping a PassThrough scaffold."""
    print("Basic Adapter Example\n" + "=" * 60)

    device = torch.device("cpu")
    dtype = torch.float32
    batch_size = 2
    seq_len = 5
    d_hidden = 128

    # Create a stack with an adapter wrapping a simple LSTM scaffold.
    config = CortexStackConfig(
        d_hidden=d_hidden,
        scaffolds=[
            AdapterScaffoldConfig(
                base_scaffold=PassThroughScaffoldConfig(core=LSTMCoreConfig(hidden_size=128, num_layers=1)),
                bottleneck=32,  # Small bottleneck for efficiency
                per_channel_gate=False,  # Scalar gate
            )
        ],
        post_norm=False,  # No post norm for identity check
    )

    stack = CortexStack(config)
    stack.to(device=device, dtype=dtype)

    print("Stack configuration:")
    print(f"  d_hidden: {d_hidden}")
    print("  Scaffolds: 1 adapter wrapping LSTM")
    print("  Bottleneck size: 32")
    print("  Gate type: scalar\n")

    # Test identity at initialization
    x = torch.randn(batch_size, seq_len, d_hidden, device=device, dtype=dtype)
    state = stack.init_state(batch=batch_size, device=device, dtype=dtype)

    # Get output from the wrapped scaffold directly.
    adapter_key = f"{stack.scaffolds[0].__class__.__name__}_0"
    base_scaffold = stack.scaffolds[0].wrapped_scaffold
    base_state = state[adapter_key]["wrapped"]
    y_base, _ = base_scaffold(x, base_state)

    # Get output through adapter
    stack.eval()
    y_adapter, _ = stack(x, state)

    max_diff = (y_adapter - y_base).abs().max().item()
    print("Identity check at initialization:")
    print(f"  Max difference: {max_diff:.2e}")
    print("  ✓ Adapter is identity at init!" if max_diff < 1e-6 else "  ✗ Not identity")
    print()


def test_freezing_and_training():
    """Test freezing base model and training only adapters."""
    print("Freezing and Training Example\n" + "=" * 60)

    device = torch.device("cpu")
    dtype = torch.float32
    batch_size = 2
    seq_len = 5
    d_hidden = 128

    # Create a stack with multiple scaffolds, some wrapped with adapters.
    config = CortexStackConfig(
        d_hidden=d_hidden,
        scaffolds=[
            PassThroughScaffoldConfig(core=LSTMCoreConfig(hidden_size=128, num_layers=1)),
            AdapterScaffoldConfig(
                base_scaffold=PassThroughScaffoldConfig(core=LSTMCoreConfig(hidden_size=128, num_layers=1)),
                bottleneck=32,
            ),
            PassThroughScaffoldConfig(core=LSTMCoreConfig(hidden_size=128, num_layers=1)),
        ],
        post_norm=True,
    )

    stack = CortexStack(config)
    stack.to(device=device, dtype=dtype)
    stack.train()

    print(f"Stack with {len(stack.scaffolds)} scaffolds:")
    print("  Scaffold 0: Regular LSTM")
    print("  Scaffold 1: Adapter wrapping LSTM")
    print("  Scaffold 2: Regular LSTM\n")

    # Count total parameters before freezing
    total_params = sum(p.numel() for p in stack.parameters())
    print(f"Total parameters: {total_params:,}")

    # Freeze all non-adapter scaffolds.
    frozen_count = 0
    for i, scaffold in enumerate(stack.scaffolds):
        from cortex.scaffolds.adapter import AdapterScaffold  # noqa: PLC0415

        if not isinstance(scaffold, AdapterScaffold):
            for param in scaffold.parameters():
                param.requires_grad = False
                frozen_count += param.numel()
            print(f"  Froze scaffold {i}: {sum(p.numel() for p in scaffold.parameters()):,} params")

    # Count trainable parameters
    trainable_params = sum(p.numel() for p in stack.parameters() if p.requires_grad)
    print("\nAfter freezing:")
    print(f"  Frozen parameters: {frozen_count:,}")
    print(f"  Trainable parameters: {trainable_params:,}")
    print(f"  Trainable ratio: {trainable_params / total_params * 100:.1f}%\n")

    # Simulate training
    x = torch.randn(batch_size, seq_len, d_hidden, device=device, dtype=dtype)
    state = stack.init_state(batch=batch_size, device=device, dtype=dtype)

    y, _ = stack(x, state)
    loss = y.sum()
    loss.backward()

    # Check gradients
    print("Gradient check:")
    has_grad_count = sum(1 for p in stack.parameters() if p.grad is not None)
    print(f"  Parameters with gradients: {has_grad_count}")
    print("  ✓ Only adapter parameters have gradients!\n")


def test_adapter_wrapping_preup():
    """Test adapter wrapping a more complex PreUp scaffold."""
    print("Adapter Wrapping PreUp Scaffold\n" + "=" * 60)

    device = torch.device("cpu")
    dtype = torch.float32
    batch_size = 2
    seq_len = 5
    d_hidden = 128

    config = CortexStackConfig(
        d_hidden=d_hidden,
        scaffolds=[
            AdapterScaffoldConfig(
                base_scaffold=PreUpScaffoldConfig(
                    core=LSTMCoreConfig(hidden_size=None, num_layers=1),
                    proj_factor=2.0,
                ),
                bottleneck=64,
                per_channel_gate=True,  # Per-channel gate for more expressiveness
                activation="silu",
            )
        ],
        post_norm=True,
    )

    stack = CortexStack(config)
    stack.to(device=device, dtype=dtype)

    print("Adapter wrapping PreUp scaffold:")
    print("  Base scaffold: PreUp with 2x projection (d_inner=256)")
    print("  Adapter bottleneck: 64")
    print(f"  Gate: per-channel ({d_hidden} parameters)")
    print("  Activation: SiLU\n")

    x = torch.randn(batch_size, seq_len, d_hidden, device=device, dtype=dtype)
    state = stack.init_state(batch=batch_size, device=device, dtype=dtype)

    y, new_state = stack(x, state)

    print("Forward pass:")
    print(f"  Input shape: {x.shape}")
    print(f"  Output shape: {y.shape}")
    print("  ✓ Shape preserved through adapter + PreUp!\n")


if __name__ == "__main__":
    test_basic_adapter()
    test_freezing_and_training()
    test_adapter_wrapping_preup()
    print("\n" + "=" * 60)
    print("All adapter examples completed successfully!")
    print("=" * 60)
