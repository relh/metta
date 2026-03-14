"""Test LayerNorm and skip connections in PreUp and PostUp scaffolds."""

import torch
import torch.nn as nn
from cortex.config import LSTMCoreConfig, PostUpScaffoldConfig, PreUpScaffoldConfig
from cortex.cores.lstm import LSTMCore
from cortex.scaffolds.postup import PostUpScaffold
from cortex.scaffolds.preup import PreUpScaffold


def test_preup_scaffold_has_layernorm():
    """Verify PreUpScaffold has LayerNorm."""
    config = PreUpScaffoldConfig(core=LSTMCoreConfig(hidden_size=256), proj_factor=2.0)
    d_hidden = 128
    core = LSTMCore(LSTMCoreConfig(hidden_size=256))

    scaffold = PreUpScaffold(config, d_hidden, core)

    # Check LayerNorm exists
    assert hasattr(scaffold, "norm")
    assert isinstance(scaffold.norm, nn.LayerNorm)
    assert scaffold.norm.normalized_shape[0] == d_hidden
    assert scaffold.norm.elementwise_affine
    assert scaffold.norm.bias is None


def test_postup_scaffold_has_layernorms():
    """Verify PostUpScaffold has both LayerNorms."""
    config = PostUpScaffoldConfig(core=LSTMCoreConfig(hidden_size=128), proj_factor=2.0)
    d_hidden = 128
    core = LSTMCore(LSTMCoreConfig(hidden_size=128))

    scaffold = PostUpScaffold(config, d_hidden, core)

    # Check both LayerNorms exist
    assert hasattr(scaffold, "norm")
    assert isinstance(scaffold.norm, nn.LayerNorm)
    assert scaffold.norm.normalized_shape[0] == d_hidden

    assert hasattr(scaffold, "ffn_norm")
    assert isinstance(scaffold.ffn_norm, nn.LayerNorm)
    assert scaffold.ffn_norm.normalized_shape[0] == d_hidden


def test_preup_residual_connection():
    """Verify PreUpScaffold properly applies residual connection."""
    config = PreUpScaffoldConfig(core=LSTMCoreConfig(hidden_size=256), proj_factor=2.0)
    d_hidden = 128
    core = LSTMCore(LSTMCoreConfig(hidden_size=256))

    scaffold = PreUpScaffold(config, d_hidden, core)

    # Create input
    batch_size = 2
    seq_len = 10
    x = torch.randn(batch_size, seq_len, d_hidden)

    # Initialize state
    state = scaffold.init_state(batch=batch_size, device="cpu", dtype=torch.float32)

    # Forward pass
    with torch.no_grad():
        # Set output projection to zero to test residual
        scaffold.out_proj.weight.zero_()
        scaffold.out_proj.bias.zero_() if scaffold.out_proj.bias is not None else None

        y, _ = scaffold(x, state)

        # Output should be close to input due to residual connection
        # (the processed part contributes zero due to zeroed projection)
        assert torch.allclose(y, x, atol=1e-5)


def test_postup_residual_connections():
    """Verify PostUpScaffold properly applies dual residual connections."""
    config = PostUpScaffoldConfig(core=LSTMCoreConfig(hidden_size=128), proj_factor=2.0)
    d_hidden = 128
    core = LSTMCore(LSTMCoreConfig(hidden_size=128))

    scaffold = PostUpScaffold(config, d_hidden, core)

    # Create input
    batch_size = 2
    seq_len = 10
    x = torch.randn(batch_size, seq_len, d_hidden)

    # Initialize state
    state = scaffold.init_state(batch=batch_size, device="cpu", dtype=torch.float32)

    # Forward pass - test that residuals are preserved
    with torch.no_grad():
        y, _ = scaffold(x, state)

        # Output should have similar magnitude to input due to residual connections
        assert y.shape == x.shape
        # Check that norms are in reasonable range (not exploding/vanishing)
        input_norm = torch.norm(x, dim=-1).mean()
        output_norm = torch.norm(y, dim=-1).mean()
        ratio = output_norm / input_norm
        assert 0.5 < ratio < 3.0, f"Output/input norm ratio {ratio} is out of expected range"


if __name__ == "__main__":
    test_preup_scaffold_has_layernorm()
    test_postup_scaffold_has_layernorms()
    test_preup_residual_connection()
    test_postup_residual_connections()
    print("All tests passed!")
