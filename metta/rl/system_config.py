import os
import platform
from datetime import timedelta
from pathlib import Path
from typing import ClassVar, Literal

import numpy as np
from pydantic import ConfigDict, Field

from mettagrid.base_config import Config

_SEED_UPPER_BOUND = 1_000_000


def guess_device() -> str:
    if platform.system() == "Darwin":
        return "cpu"

    import torch  # Lazy import: torch is heavy and not needed at module load time  # noqa: PLC0415

    if not torch.cuda.is_available():
        return "cpu"

    local_rank = int(os.environ.get("LOCAL_RANK", "0"))

    return f"cuda:{local_rank}"


def guess_vectorization() -> Literal["serial", "multiprocessing"]:
    if platform.system() == "Darwin":
        return "serial"
    return "multiprocessing"


def guess_data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR") or "./train_dir")


class SystemConfig(Config):
    vectorization: Literal["serial", "multiprocessing"] = Field(default_factory=guess_vectorization)
    seed: int = Field(default_factory=lambda: int(np.random.randint(0, _SEED_UPPER_BOUND)))
    torch_deterministic: bool = Field(default=True)
    device: str = Field(default_factory=guess_device)
    data_dir: Path = Field(default_factory=guess_data_dir)
    local_only: bool = Field(default=False)
    nccl_timeout: timedelta = Field(default=timedelta(minutes=10))

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        populate_by_name=True,
    )
