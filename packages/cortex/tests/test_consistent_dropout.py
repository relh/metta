"""Tests for ConsistentDropout module."""

import pytest
import torch
import torch.nn as nn
from cortex.blocks import build_block
from cortex.cells import build_cell
from cortex.config import LSTMCellConfig, PostUpBlockConfig, PostUpGatedBlockConfig, PreUpBlockConfig
from cortex.consistent_dropout import ConsistentDropout, ConsistentDropoutModule, reset_consistent_dropout
from cortex.stacks import build_cortex_auto_stack


class TestConsistentDropout:
    """Tests for the ConsistentDropout class."""

    def test_basic_functionality(self):
        """Test that dropout produces non-zero output in training mode."""
        dropout = ConsistentDropout(p=0.5)
        dropout.train()

        x = torch.ones(32, 64)
        out = dropout(x)

        # Output should not be all zeros or all ones
        assert not torch.allclose(out, torch.zeros_like(out))
        # Due to scaling by 1/(1-p), some values should be > 1
        assert out.max() > 1.0

    def test_mask_consistency(self):
        """Test that mask is cached and reused between forward passes."""
        dropout = ConsistentDropout(p=0.5)
        dropout.train()

        x = torch.ones(32, 64)

        # First forward pass - generates and caches mask
        out1 = dropout(x)

        # Second forward pass - should use same mask
        out2 = dropout(x)

        # Outputs should be identical
        assert torch.allclose(out1, out2)

    def test_batch_time_reshape_reuses_mask(self):
        """Test that rollout masks are reused after B*TT reshaping."""
        dropout = ConsistentDropout(p=0.5)
        dropout.train()

        x = torch.ones(4, 8)
        out1 = dropout(x)

        x_flat = torch.ones(4 * 3, 8)
        out2 = dropout(x_flat)

        expected = out1.repeat_interleave(3, dim=0)
        assert torch.allclose(out2, expected)

    def test_mask_reset(self):
        """Test that reset_mask() clears cached mask and new mask is generated."""
        torch.manual_seed(42)
        dropout = ConsistentDropout(p=0.5)
        dropout.train()

        x = torch.ones(32, 64)

        # First forward pass
        out1 = dropout(x)

        # Reset mask
        dropout.reset_mask()

        # Second forward pass after reset - should have different mask
        torch.manual_seed(123)  # Different seed
        out2 = dropout(x)

        # Outputs should differ (very high probability with p=0.5)
        assert not torch.allclose(out1, out2)

    def test_eval_mode_passthrough(self):
        """Test that dropout does nothing in eval mode."""
        dropout = ConsistentDropout(p=0.5)
        dropout.eval()

        x = torch.randn(32, 64)
        out = dropout(x)

        assert torch.allclose(x, out)

    def test_zero_probability(self):
        """Test that p=0 means no dropout."""
        dropout = ConsistentDropout(p=0.0)
        dropout.train()

        x = torch.randn(32, 64)
        out = dropout(x)

        assert torch.allclose(x, out)

    def test_one_probability(self):
        """Test that p=1 means full dropout."""
        dropout = ConsistentDropout(p=1.0)
        dropout.train()

        x = torch.randn(32, 64)
        out = dropout(x)

        assert torch.allclose(out, torch.zeros_like(out))

    def test_shape_change_regenerates_mask(self):
        """Test that changing input shape regenerates the mask."""
        dropout = ConsistentDropout(p=0.5)
        dropout.train()

        # First shape
        x1 = torch.ones(32, 64)
        _ = dropout(x1)

        # Different shape
        x2 = torch.ones(16, 128)
        out2 = dropout(x2)

        # Should work without error and produce valid output
        assert out2.shape == x2.shape
        assert not torch.allclose(out2, torch.zeros_like(out2))

    def test_invalid_probability(self):
        """Test that invalid probabilities raise errors."""
        with pytest.raises(ValueError):
            ConsistentDropout(p=-0.1)

        with pytest.raises(ValueError):
            ConsistentDropout(p=1.5)

    def test_gradient_flow(self):
        """Test that gradients flow through the dropout layer."""
        dropout = ConsistentDropout(p=0.3)
        dropout.train()

        x = torch.randn(8, 32, requires_grad=True)
        out = dropout(x)
        loss = out.sum()
        loss.backward()

        # Gradient should exist and not be all zeros
        assert x.grad is not None
        assert not torch.allclose(x.grad, torch.zeros_like(x.grad))


class TestConsistentDropoutModule:
    """Tests for the ConsistentDropoutModule wrapper."""

    def test_wraps_module(self):
        """Test that it correctly wraps a module with dropout."""
        linear = nn.Linear(64, 32)
        wrapped = ConsistentDropoutModule(linear, p=0.3)
        wrapped.train()

        x = torch.randn(8, 64)
        out = wrapped(x)

        assert out.shape == (8, 32)

    def test_mask_reset(self):
        """Test that reset_mask propagates to inner dropout."""
        linear = nn.Linear(64, 32)
        wrapped = ConsistentDropoutModule(linear, p=0.3)
        wrapped.train()

        x = torch.randn(8, 64)

        out1 = wrapped(x)
        torch.manual_seed(42)

        wrapped.reset_mask()
        torch.manual_seed(123)
        out2 = wrapped(x)

        # Outputs should differ after reset
        assert not torch.allclose(out1, out2)


class TestResetConsistentDropout:
    """Tests for the reset_consistent_dropout helper function."""

    def test_resets_all_dropout_layers(self):
        """Test that it resets all ConsistentDropout layers in a module tree."""

        class Model(nn.Module):
            def __init__(self):
                super().__init__()
                self.linear1 = nn.Linear(64, 32)
                self.dropout1 = ConsistentDropout(p=0.3)
                self.linear2 = nn.Linear(32, 16)
                self.dropout2 = ConsistentDropout(p=0.3)

            def forward(self, x):
                x = self.dropout1(self.linear1(x))
                x = self.dropout2(self.linear2(x))
                return x

        model = Model()
        model.train()

        x = torch.randn(8, 64)

        # First pass
        _ = model(x)

        # Both dropouts should have cached masks
        assert model.dropout1._cached_mask is not None
        assert model.dropout2._cached_mask is not None

        # Reset all
        reset_consistent_dropout(model)

        # Masks should be cleared
        assert model.dropout1._cached_mask is None
        assert model.dropout2._cached_mask is None


class TestConsistentDropoutWithBlocks:
    """Integration tests with cortex blocks."""

    def test_postup_block_with_dropout(self):
        """Test that PostUpBlock works with dropout configuration."""
        config = PostUpBlockConfig(
            proj_factor=2.0,
            dropout=0.1,
            cell=LSTMCellConfig(hidden_size=64),
        )

        cell = build_cell(LSTMCellConfig(hidden_size=64))
        block = build_block(config=config, d_hidden=64, cell=cell)
        block.train()

        x = torch.randn(8, 64)
        state = block.init_state(batch=8, device="cpu", dtype=torch.float32)

        # Should work without error
        out, new_state = block(x, state)
        assert out.shape == x.shape

        # Verify dropout is present and working
        assert hasattr(block, "dropout")
        assert isinstance(block.dropout, ConsistentDropout)

    def test_preup_block_with_dropout(self):
        """Test that PreUpBlock works with dropout configuration."""
        d_hidden = 64
        proj_factor = 2.0
        d_inner = int(proj_factor * d_hidden)

        config = PreUpBlockConfig(
            proj_factor=proj_factor,
            dropout=0.1,
            cell=LSTMCellConfig(hidden_size=d_inner),
        )

        cell = build_cell(LSTMCellConfig(hidden_size=d_inner))
        block = build_block(config=config, d_hidden=d_hidden, cell=cell)
        block.train()

        x = torch.randn(8, d_hidden)
        state = block.init_state(batch=8, device="cpu", dtype=torch.float32)

        # Should work without error
        out, new_state = block(x, state)
        assert out.shape == x.shape

        # Verify dropout is present
        assert hasattr(block, "dropout")
        assert isinstance(block.dropout, ConsistentDropout)

    def test_postup_gated_block_with_dropout(self):
        """Test that PostUpGatedBlock works with dropout configuration."""
        config = PostUpGatedBlockConfig(
            proj_factor=2.0,
            dropout=0.1,
            cell=LSTMCellConfig(hidden_size=64),
        )

        cell = build_cell(LSTMCellConfig(hidden_size=64))
        block = build_block(config=config, d_hidden=64, cell=cell)
        block.train()

        x = torch.randn(8, 64)
        state = block.init_state(batch=8, device="cpu", dtype=torch.float32)

        # Should work without error
        out, new_state = block(x, state)
        assert out.shape == x.shape

        # Verify dropout is present
        assert hasattr(block, "dropout")
        assert isinstance(block.dropout, ConsistentDropout)

    def test_auto_stack_with_dropout(self):
        """Test that build_cortex_auto_stack wires consistent dropout."""
        stack = build_cortex_auto_stack(
            d_hidden=32,
            num_layers=1,
            compile_blocks=False,
            override_global_configs=[
                PostUpBlockConfig(dropout=0.1),
                PostUpGatedBlockConfig(dropout=0.1),
                PreUpBlockConfig(dropout=0.1),
            ],
        )
        stack.train()

        x = torch.randn(8, 32)
        state = stack.init_state(batch=8, device="cpu", dtype=torch.float32)
        out, _ = stack(x, state)

        assert out.shape == x.shape
        assert any(isinstance(module, ConsistentDropout) for module in stack.modules())
