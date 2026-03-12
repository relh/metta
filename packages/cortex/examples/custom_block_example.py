#!/usr/bin/env -S uv run python
"""Example showing how to create custom block types for the cortex architecture."""

import torch
import torch.nn as nn
from cortex import register_scaffold
from cortex.config import CortexStackConfig, LSTMCoreConfig, ScaffoldConfig
from cortex.cores.base import MemoryCell
from cortex.scaffolds.base import BaseBlock
from cortex.types import MaybeState, ResetMask, Tensor
from pydantic import Field


# Step 1: Define custom block configuration
class GatedResidualBlockConfig(ScaffoldConfig):
    """Configuration for a custom gated residual block.

    This block applies a gate to control the residual connection.
    """

    gate_activation: str = Field(default="sigmoid")
    residual_weight: float = Field(default=0.5, ge=0.0, le=1.0)


# Step 2: Implement and register the custom block
@register_scaffold(GatedResidualBlockConfig)
class GatedResidualBlock(BaseBlock):
    """A custom block with gated residual connections.

    This block processes input through a cell and applies a learned
    gate to blend between the cell output and the original input.
    """

    def __init__(self, config: GatedResidualBlockConfig, d_hidden: int, cell: MemoryCell) -> None:
        super().__init__(d_hidden=d_hidden, cell=cell)
        self.config = config

        # Create gate layers
        self.gate_proj = nn.Linear(d_hidden * 2, d_hidden)

        # Choose activation
        if config.gate_activation == "sigmoid":
            self.gate_act = nn.Sigmoid()
        elif config.gate_activation == "tanh":
            self.gate_act = nn.Tanh()
        else:
            self.gate_act = nn.SiLU()

        self.residual_weight = config.residual_weight
        assert cell.hidden_size == d_hidden, "GatedResidualBlock requires cell.hidden_size == d_hidden"

    def forward(
        self,
        x: Tensor,
        state: MaybeState,
        *,
        resets: ResetMask | None = None,
    ) -> tuple[Tensor, MaybeState]:
        from tensordict import TensorDict  # noqa: PLC0415

        # Extract cell state from block state
        cell_key = self.cell.__class__.__name__
        cell_state = state.get(cell_key, None) if state is not None else None

        # Process through cell
        y, new_cell_state = self.cell(x, cell_state, resets=resets)

        # Compute gate based on input and cell output
        gate_input = torch.cat([x, y], dim=-1)
        gate = self.gate_act(self.gate_proj(gate_input))

        # Apply gated residual
        output = gate * y + (1 - gate) * self.residual_weight * x

        # Wrap cell state in block state
        return output, TensorDict({cell_key: new_cell_state}, batch_size=[])


def test_custom_block():
    """Test the custom gated residual block."""
    print("Testing Custom Block Implementation\n" + "=" * 40)

    device = torch.device("cpu")
    dtype = torch.float32
    batch_size = 2
    seq_len = 5
    d_hidden = 128

    # Create a recipe with custom blocks
    recipe = CortexStackConfig(
        d_hidden=d_hidden,
        scaffolds=[
            # Mix standard and custom blocks
            GatedResidualBlockConfig(
                core=LSTMCoreConfig(hidden_size=128, num_layers=1),
                gate_activation="sigmoid",
                residual_weight=0.3,
            ),
            GatedResidualBlockConfig(
                core=LSTMCoreConfig(hidden_size=128, num_layers=2),
                gate_activation="tanh",
                residual_weight=0.7,
            ),
        ],
        post_norm=True,
    )

    print("Custom Recipe Configuration:")
    print(f"  d_hidden: {recipe.d_hidden}")
    print(f"  num_scaffolds: {len(recipe.blocks)}")
    for i, block in enumerate(recipe.blocks):
        if isinstance(block, GatedResidualBlockConfig):
            print(f"  Scaffold {i}: GatedResidual (gate={block.gate_activation}, weight={block.residual_weight})")
    print()

    # Build the stack using the standard CortexStack - no custom class needed!
    # The registry system automatically handles our custom block type
    from cortex.stacks import CortexStack  # noqa: PLC0415

    stack = CortexStack(recipe)

    print(f"Built custom stack with {len(stack.blocks)} scaffolds")

    # Test forward pass
    x = torch.randn(batch_size, seq_len, d_hidden, device=device, dtype=dtype)
    print(f"\nInput shape: {x.shape}")

    state = stack.init_state(batch=batch_size, device=device, dtype=dtype)
    output, new_state = stack(x, state)

    print(f"Output shape: {output.shape}")
    assert output.shape == x.shape, "Output shape mismatch!"
    print("\n✓ Custom block test passed!")

    # Show how the registry works
    print("\n" + "=" * 40)
    print("How the registry system works:")
    print("1. Custom scaffolds are registered with @register_scaffold decorator")
    print("2. CortexStack automatically builds any registered scaffold type")
    print("3. No need to modify CortexStack or create custom classes!")
    print("\nThe registry makes the system fully extensible:")
    print("- Define your ScaffoldConfig subclass")
    print("- Define your scaffold class")
    print("- Use @register_scaffold(YourConfig) on your scaffold class")
    print("- That's it! Your scaffold is now usable in any CortexStack")


if __name__ == "__main__":
    test_custom_block()
