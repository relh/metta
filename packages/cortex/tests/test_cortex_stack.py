"""Test script for the cortex stack implementation."""

import torch
from cortex import (
    CortexStackConfig,
    LSTMCoreConfig,
    PassThroughScaffoldConfig,
    PostUpScaffoldConfig,
    PreUpScaffoldConfig,
    build_cortex,
)


def test_cortex_stack():
    """Test the cortex stack with different block types."""
    print("Testing Cortex Stack Implementation\n" + "=" * 40)

    # Device and dtype setup
    device = torch.device("cpu")
    dtype = torch.float32
    batch_size = 4
    seq_len = 10
    d_hidden = 256

    # Create a recipe with mixed block types
    recipe = CortexStackConfig(
        d_hidden=d_hidden,
        scaffolds=[
            PreUpScaffoldConfig(
                core=LSTMCoreConfig(
                    hidden_size=None,  # Inferred as d_inner = proj_factor * d_hidden
                    num_layers=1,
                    dropout=0.1,
                ),
                proj_factor=2.0,
            ),
            PassThroughScaffoldConfig(
                core=LSTMCoreConfig(
                    hidden_size=256,  # Must match d_hidden
                    num_layers=1,
                ),
            ),
            PostUpScaffoldConfig(
                core=LSTMCoreConfig(
                    hidden_size=None,  # Inferred as d_hidden
                    num_layers=1,
                ),
                proj_factor=1.5,
            ),
        ],
        post_norm=True,
    )

    print("Recipe Configuration:")
    print(f"  d_hidden: {recipe.d_hidden}")
    print(f"  num_scaffolds: {len(recipe.scaffolds)}")
    for i, scaffold in enumerate(recipe.scaffolds):
        scaffold_type = type(scaffold).__name__.replace("ScaffoldConfig", "")
        proj_str = f" (proj_factor={scaffold.proj_factor})" if hasattr(scaffold, "proj_factor") else ""
        print(f"  Scaffold {i}: {scaffold_type}{proj_str}")
    print()

    # Build the cortex stack
    cortex = build_cortex(recipe)
    print(f"Built CortexStack with {len(cortex.scaffolds)} scaffolds")

    # Count parameters
    num_params = sum(p.numel() for p in cortex.parameters())
    print(f"Total parameters: {num_params:,}\n")

    # Test 1: Sequence mode (batch-first)
    print("Test 1: Sequence Mode (Batch-First)")
    print("-" * 40)
    x_seq = torch.randn(batch_size, seq_len, d_hidden, device=device, dtype=dtype)
    print(f"Input shape: {x_seq.shape}")

    # Initialize state
    state = cortex.init_state(batch=batch_size, device=device, dtype=dtype)
    print(f"State keys: {list(state.keys())}")

    # Forward pass
    output, new_state = cortex(x_seq, state)
    print(f"Output shape: {output.shape}")
    print(f"Output preserved d_hidden: {output.shape[-1] == d_hidden}")
    assert output.shape == x_seq.shape, "Output shape mismatch!"
    print("✓ Sequence mode test passed\n")

    # Test 2: Different sequence length
    print("Test 2: Different Sequence Length")
    print("-" * 40)
    x_longer = torch.randn(batch_size, seq_len * 2, d_hidden, device=device, dtype=dtype)
    print(f"Input shape: {x_longer.shape}")

    output_longer, state_longer = cortex(x_longer, state)
    print(f"Output shape: {output_longer.shape}")
    assert output_longer.shape == x_longer.shape, "Output shape mismatch!"
    print("✓ Different sequence length test passed\n")

    # Test 3: Single step mode
    print("Test 3: Single Step Mode")
    print("-" * 40)
    x_step = torch.randn(batch_size, d_hidden, device=device, dtype=dtype)
    print(f"Input shape: {x_step.shape}")

    output_step, state_step = cortex.step(x_step, new_state)
    print(f"Output shape: {output_step.shape}")
    assert output_step.shape == x_step.shape, "Output shape mismatch!"
    print("✓ Step mode test passed\n")

    # Test 4: Reset mask
    print("Test 4: Reset Mask")
    print("-" * 40)
    reset_mask = torch.tensor([True, False, True, False], device=device)
    print(f"Reset mask: {reset_mask}")

    # Apply reset
    reset_state = cortex.reset_state(new_state, reset_mask)

    # Verify reset was applied.
    for scaffold_key in reset_state.keys():
        scaffold_state = reset_state[scaffold_key]
        core_key = next(iter(scaffold_state.keys()), None)
        if core_key is None:
            continue
        core_state = scaffold_state[core_key]
        if "h" in core_state:
            h_state = core_state["h"]  # [B, L, H]
            for i, should_reset in enumerate(reset_mask):
                if should_reset:
                    assert torch.allclose(h_state[i, :, :], torch.zeros_like(h_state[i, :, :])), (
                        f"State not properly reset for batch {i}"
                    )
    print("✓ Reset mask test passed\n")

    # Test 5: Per-timestep resets
    print("Test 5: Per-Timestep Resets")
    print("-" * 40)
    resets_seq = torch.randint(0, 2, (batch_size, seq_len), device=device).bool()
    print(f"Resets shape: {resets_seq.shape}")

    output_with_resets, state_with_resets = cortex(x_seq, state, resets=resets_seq)
    print(f"Output shape: {output_with_resets.shape}")
    assert output_with_resets.shape == x_seq.shape, "Output shape mismatch!"
    print("✓ Per-timestep resets test passed\n")

    # Test 6: Different scaffold configurations.
    print("Test 6: Different Scaffold Configurations")
    print("-" * 40)

    # Test passthrough-only stack
    passthrough_recipe = CortexStackConfig(
        d_hidden=128,
        scaffolds=[
            PassThroughScaffoldConfig(
                core=LSTMCoreConfig(hidden_size=128, num_layers=1),
            )
            for _ in range(3)
        ],
        post_norm=False,
    )
    passthrough_cortex = build_cortex(passthrough_recipe)
    x_test = torch.randn(2, 5, 128)
    output, _ = passthrough_cortex(x_test, state=None)
    assert output.shape == x_test.shape
    print("✓ Passthrough-only stack test passed")

    # Test preup-only stack
    preup_recipe = CortexStackConfig(
        d_hidden=64,
        scaffolds=[
            PreUpScaffoldConfig(
                core=LSTMCoreConfig(hidden_size=None, num_layers=1),
                proj_factor=2.0,
            )
        ],
    )
    preup_cortex = build_cortex(preup_recipe)
    x_test = torch.randn(2, 5, 64)
    output, _ = preup_cortex(x_test, state=None)
    assert output.shape == x_test.shape
    print("✓ PreUp-only stack test passed")

    print("\n" + "=" * 40)
    print("All tests passed successfully! ✓")


if __name__ == "__main__":
    test_cortex_stack()
