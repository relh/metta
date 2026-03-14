#!/usr/bin/env -S uv run python
"""Example showing how to create custom scaffold types for the cortex architecture."""

import torch
import torch.nn as nn
from cortex import CortexStack, register_scaffold
from cortex.config import CortexStackConfig, LSTMCoreConfig, ScaffoldConfig
from cortex.cores.base import MemoryCore
from cortex.scaffolds.base import BaseScaffold
from cortex.types import MaybeState, ResetMask, Tensor
from pydantic import Field
from tensordict import TensorDict


# Step 1: Define custom scaffold configuration.
class GatedResidualScaffoldConfig(ScaffoldConfig):
    """Configuration for a custom gated residual scaffold.

    This scaffold applies a gate to control the residual connection.
    """

    scaffold_type: str = "gated_residual"
    gate_activation: str = Field(default="sigmoid")
    residual_weight: float = Field(default=0.5, ge=0.0, le=1.0)


# Step 2: Implement and register the custom scaffold.
@register_scaffold(GatedResidualScaffoldConfig)
class GatedResidualScaffold(BaseScaffold):
    """A custom scaffold with gated residual connections.

    This scaffold processes input through a core and applies a learned
    gate to blend between the core output and the original input.
    """

    def __init__(self, config: GatedResidualScaffoldConfig, d_hidden: int, core: MemoryCore) -> None:
        super().__init__(d_hidden=d_hidden, core=core)
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
        assert core.hidden_size == d_hidden, "GatedResidualScaffold requires core.hidden_size == d_hidden"

    def forward(
        self,
        x: Tensor,
        state: MaybeState,
        *,
        resets: ResetMask | None = None,
    ) -> tuple[Tensor, MaybeState]:
        # Extract core state from scaffold state.
        core_key = self.core.__class__.__name__
        core_state = state.get(core_key, None) if state is not None else None

        # Process through the wrapped core.
        y, new_core_state = self.core(x, core_state, resets=resets)

        # Compute gate based on input and core output.
        gate_input = torch.cat([x, y], dim=-1)
        gate = self.gate_act(self.gate_proj(gate_input))

        # Apply gated residual
        output = gate * y + (1 - gate) * self.residual_weight * x

        # Wrap core state in scaffold state.
        return output, TensorDict({core_key: new_core_state}, batch_size=[x.shape[0]])


def test_custom_scaffold():
    """Test the custom gated residual scaffold."""
    print("Testing Custom Scaffold Implementation\n" + "=" * 40)

    device = torch.device("cpu")
    dtype = torch.float32
    batch_size = 2
    seq_len = 5
    d_hidden = 128

    # Create a recipe with custom scaffolds.
    recipe = CortexStackConfig(
        d_hidden=d_hidden,
        scaffolds=[
            # Mix standard and custom scaffolds.
            GatedResidualScaffoldConfig(
                core=LSTMCoreConfig(hidden_size=128, num_layers=1),
                gate_activation="sigmoid",
                residual_weight=0.3,
            ),
            GatedResidualScaffoldConfig(
                core=LSTMCoreConfig(hidden_size=128, num_layers=1),
                gate_activation="tanh",
                residual_weight=0.7,
            ),
        ],
        post_norm=True,
    )

    print("Custom Recipe Configuration:")
    print(f"  d_hidden: {recipe.d_hidden}")
    print(f"  num_scaffolds: {len(recipe.scaffolds)}")
    for i, scaffold in enumerate(recipe.scaffolds):
        if isinstance(scaffold, GatedResidualScaffoldConfig):
            print(f"  Scaffold {i}: GatedResidual (gate={scaffold.gate_activation}, weight={scaffold.residual_weight})")
    print()

    # Build the stack using the standard CortexStack; the registry system handles our custom scaffold type.
    stack = CortexStack(recipe)

    print(f"Built custom stack with {len(stack.scaffolds)} scaffolds")

    # Test forward pass
    x = torch.randn(batch_size, seq_len, d_hidden, device=device, dtype=dtype)
    print(f"\nInput shape: {x.shape}")

    state = stack.init_state(batch=batch_size, device=device, dtype=dtype)
    output, new_state = stack(x, state)

    print(f"Output shape: {output.shape}")
    assert output.shape == x.shape, "Output shape mismatch!"
    print("\n✓ Custom scaffold test passed!")

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
    test_custom_scaffold()
