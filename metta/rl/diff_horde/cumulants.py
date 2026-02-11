from __future__ import annotations

from functools import partial
from typing import Any, Literal, Optional

import torch
from pydantic import Field, field_validator, model_validator
from tensordict import TensorDict
from torch import Tensor
from torchrl.data import Composite

from mettagrid.base_config import Config
from mettagrid.policy.policy_env_interface import PolicyEnvInterface

_EMPTY_TOKEN_LOCATION = 0xFF
_OBS_TOKEN_LOCATION = 0
_OBS_TOKEN_FEATURE_ID = 1
_OBS_TOKEN_VALUE = 2


def _flattened_size(*, values: Tensor, batch_size: int) -> int:
    if values.dim() == 1:
        return 1
    return int(values.reshape(batch_size, -1).shape[1])


def _zeros_from_composite(spec: Composite, *, batch_size: int) -> TensorDict:
    return spec.zero(torch.Size([batch_size]))


def _parse_slice_bounds(slice_str: str) -> tuple[int, int]:
    parts = slice_str.split(":")
    if len(parts) != 2:
        raise ValueError(f"slice must be formatted as 'start:end', got {slice_str!r}")
    if parts[0] == "" or parts[1] == "":
        raise ValueError(f"slice must include both start and end, got {slice_str!r}")
    start = int(parts[0])
    end = int(parts[1])
    if start < 0 or end <= start:
        raise ValueError(f"slice must satisfy 0 <= start < end, got {slice_str!r}")
    return start, end


class _BaseCumulantSpec(Config):
    name: str
    kind: str
    scale: float = 1.0
    clip: Optional[tuple[float, float]] = None

    @model_validator(mode="after")
    def _validate_clip(self) -> "_BaseCumulantSpec":
        if self.clip is not None and self.clip[0] > self.clip[1]:
            raise ValueError(f"clip bounds must satisfy min <= max, got {self.clip}")
        return self


class TDKeyCumulantSpec(_BaseCumulantSpec):
    kind: Literal["td_key"] = "td_key"
    key: str
    slice: Optional[str] = None
    reduce: Optional[Literal["mean", "sum", "max"]] = None
    size: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _validate_size(self) -> "TDKeyCumulantSpec":
        inferred_size: Optional[int] = None
        if self.slice is not None:
            start, end = _parse_slice_bounds(self.slice)
            if self.reduce is None:
                inferred_size = end - start
            else:
                inferred_size = 1
        elif self.reduce is not None:
            inferred_size = 1

        if self.size is None:
            self.size = inferred_size
        elif inferred_size is not None and self.size != inferred_size:
            raise ValueError(
                f"td_key cumulant '{self.name}' size mismatch: expected {inferred_size} "
                f"from slice/reduce, got {self.size}"
            )
        return self


class EnvObsFeatureCumulantSpec(_BaseCumulantSpec):
    kind: Literal["env_obs_feature"] = "env_obs_feature"
    feature: str | int
    reduce: Literal["mean", "sum", "max"] = "mean"
    normalize: bool = False
    size: Literal[1] = 1


class InfoScalarCumulantSpec(_BaseCumulantSpec):
    kind: Literal["info_scalar"] = "info_scalar"
    key: str
    size: Literal[1] = 1


CumulantSpec = TDKeyCumulantSpec | EnvObsFeatureCumulantSpec | InfoScalarCumulantSpec


class DiffHordeCumulantsConfig(Config):
    specs: list[CumulantSpec] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _normalize_root_input(cls, value: Any) -> Any:
        if isinstance(value, DiffHordeCumulantsConfig):
            return value
        if isinstance(value, list):
            return {"specs": value}
        if isinstance(value, dict):
            if "specs" in value:
                return value
            normalized_specs: list[dict[str, Any]] = []
            for name, spec in value.items():
                if not isinstance(spec, dict):
                    raise TypeError(f"Cumulant spec {name!r} must be a mapping, got {type(spec).__name__}")
                named_spec = dict(spec)
                if "name" in named_spec and named_spec["name"] != name:
                    raise ValueError(f"Cumulant spec name mismatch: key={name!r} spec.name={named_spec['name']!r}")
                named_spec["name"] = name
                normalized_specs.append(named_spec)
            return {"specs": normalized_specs}
        raise TypeError("DiffHordeCumulantsConfig expects a list of specs or name->spec mapping")

    @field_validator("specs", mode="before")
    @classmethod
    def _parse_specs(cls, value: Any) -> list[CumulantSpec]:
        if not isinstance(value, list):
            raise TypeError(f"specs must be a list, got {type(value).__name__}")
        parsed: list[CumulantSpec] = []
        for index, item in enumerate(value):
            parsed.append(cls._parse_single_spec(item, index))
        return parsed

    @staticmethod
    def _parse_single_spec(value: Any, index: int) -> CumulantSpec:
        if isinstance(value, (TDKeyCumulantSpec, EnvObsFeatureCumulantSpec, InfoScalarCumulantSpec)):
            return value
        if not isinstance(value, dict):
            raise TypeError(f"Cumulant spec at index {index} must be a mapping, got {type(value).__name__}")

        spec_data = dict(value)
        if "name" not in spec_data:
            spec_data["name"] = f"cumulant_{index}"
        if "kind" not in spec_data:
            raise ValueError(f"Cumulant spec '{spec_data['name']}' is missing required field 'kind'")
        kind = spec_data["kind"]

        if kind == "td_key":
            return TDKeyCumulantSpec.model_validate(spec_data)
        if kind == "env_obs_feature":
            return EnvObsFeatureCumulantSpec.model_validate(spec_data)
        if kind == "info_scalar":
            return InfoScalarCumulantSpec.model_validate(spec_data)
        raise ValueError(f"Unsupported cumulant kind {kind!r}")

    @model_validator(mode="after")
    def _validate_names_unique(self) -> "DiffHordeCumulantsConfig":
        names = [spec.name for spec in self.specs]
        if len(set(names)) != len(names):
            raise ValueError(f"Cumulant names must be unique, got {names}")
        return self

    @property
    def num_cumulants(self) -> int:
        unresolved_td_key_specs = [
            spec.name for spec in self.specs if isinstance(spec, TDKeyCumulantSpec) and spec.size is None
        ]
        if unresolved_td_key_specs:
            raise ValueError(
                "Unresolved td_key cumulant size for specs "
                f"{unresolved_td_key_specs}. Provide size or resolve via infer_td_key_sizes_from_policy()."
            )
        return sum(int(spec.size) for spec in self.specs)

    def infer_td_key_sizes(self, td_key_flat_sizes: dict[str, int]) -> None:
        for spec in self.specs:
            if not isinstance(spec, TDKeyCumulantSpec) or spec.size is not None:
                continue
            if spec.key not in td_key_flat_sizes:
                raise ValueError(
                    f"Could not infer size for td_key cumulant '{spec.name}' using key '{spec.key}'. "
                    "Provide size explicitly."
                )
            inferred_size = int(td_key_flat_sizes[spec.key])
            if inferred_size < 1:
                raise ValueError(f"Inferred size for td_key cumulant '{spec.name}' must be >= 1, got {inferred_size}")
            spec.size = inferred_size

    def infer_td_key_sizes_from_policy(self, policy: Any, *, batch_size: int = 1) -> None:
        unresolved = [spec for spec in self.specs if isinstance(spec, TDKeyCumulantSpec) and spec.size is None]
        if not unresolved:
            return
        if batch_size < 1:
            raise ValueError(f"batch_size must be >= 1, got {batch_size}")

        policy_spec = policy.get_agent_experience_spec()
        if not isinstance(policy_spec, Composite):
            raise TypeError(
                f"Expected policy.get_agent_experience_spec() to return Composite, got {type(policy_spec).__name__}"
            )
        sample_td = _zeros_from_composite(policy_spec, batch_size=batch_size)
        sample_td["batch"] = torch.full((batch_size,), batch_size, dtype=torch.int64)
        sample_td["bptt"] = torch.ones(batch_size, dtype=torch.int64)
        inferred_sizes: dict[str, int] = {}
        for spec in unresolved:
            if spec.key in sample_td.keys():
                inferred_sizes[spec.key] = _flattened_size(values=sample_td[spec.key], batch_size=batch_size)

        with torch.no_grad():
            policy_td = policy(sample_td.clone())
        if not isinstance(policy_td, TensorDict):
            raise TypeError(f"Expected policy forward to return TensorDict, got {type(policy_td).__name__}")
        for spec in unresolved:
            if spec.key in policy_td.keys():
                values = policy_td[spec.key]
                if values.shape[0] != batch_size:
                    raise ValueError(
                        f"Cannot infer size for td_key cumulant '{spec.name}': expected batch {batch_size}, "
                        f"got {tuple(values.shape)}"
                    )
                inferred_sizes[spec.key] = _flattened_size(values=values, batch_size=batch_size)

        self.infer_td_key_sizes(inferred_sizes)

    def required_td_keys(self) -> set[str]:
        keys: set[str] = set()
        for spec in self.specs:
            if isinstance(spec, TDKeyCumulantSpec):
                keys.add(spec.key)
            elif isinstance(spec, EnvObsFeatureCumulantSpec):
                keys.add("env_obs")
        return keys

    def required_info_keys(self) -> set[str]:
        keys: set[str] = set()
        for spec in self.specs:
            if isinstance(spec, InfoScalarCumulantSpec):
                keys.add(spec.key)
        return keys

    def required_obs_features(self) -> set[str | int]:
        features: set[str | int] = set()
        for spec in self.specs:
            if isinstance(spec, EnvObsFeatureCumulantSpec):
                features.add(spec.feature)
        return features


class DiffHordeCumulantExtractor:
    def __init__(
        self,
        cumulants_cfg: DiffHordeCumulantsConfig,
        policy_env_info: Optional[PolicyEnvInterface],
    ) -> None:
        self.cumulants_cfg = cumulants_cfg
        self._feature_id_by_name: dict[str, int] = {}
        self._feature_normalization_by_id: dict[int, float] = {}
        if policy_env_info is not None:
            for feature in policy_env_info.obs_features:
                feature_id = int(feature.id)
                self._feature_id_by_name[feature.name] = feature_id
                self._feature_normalization_by_id[feature_id] = float(feature.normalization)

        self._resolved_obs_feature_ids: dict[str, int] = {}
        for spec in self.cumulants_cfg.specs:
            if isinstance(spec, EnvObsFeatureCumulantSpec):
                self._resolved_obs_feature_ids[spec.name] = self._resolve_feature_id(spec.feature, spec.name)

        self._compiled_specs = []
        for spec in self.cumulants_cfg.specs:
            if isinstance(spec, TDKeyCumulantSpec):
                extractor = partial(self._extract_td_key, spec=spec)
            elif isinstance(spec, EnvObsFeatureCumulantSpec):
                extractor = partial(self._extract_env_obs_feature, spec=spec)
            elif isinstance(spec, InfoScalarCumulantSpec):
                extractor = partial(self._extract_info_scalar, spec=spec)
            else:
                raise RuntimeError(f"Unhandled cumulant spec type {type(spec).__name__}")
            self._compiled_specs.append((spec, extractor))

        self._output_widths: list[int] | None = None
        self._total_output_width = 0
        self._refresh_output_layout()

    def _resolve_feature_id(self, feature: str | int, spec_name: str) -> int:
        if isinstance(feature, str):
            if feature not in self._feature_id_by_name:
                raise RuntimeError(f"Unknown obs feature name {feature!r} for cumulant {spec_name!r}")
            return self._feature_id_by_name[feature]
        feature_id = int(feature)
        if feature_id not in self._feature_normalization_by_id:
            raise RuntimeError(f"Unknown obs feature id {feature_id} for cumulant {spec_name!r}")
        return feature_id

    def __call__(self, student_td: TensorDict) -> Tensor:
        batch_dims = list(student_td.batch_size)
        if not batch_dims:
            raise RuntimeError("Cumulant extractor expected a batched TensorDict")
        batch_size = int(batch_dims[0])

        if self._output_widths is not None:
            output: Tensor | None = None
            offset = 0
            for (spec, extractor), expected_width in zip(self._compiled_specs, self._output_widths, strict=True):
                values = extractor(student_td=student_td, batch_size=batch_size)
                values = self._apply_scale_and_clip(values, spec)
                if values.shape[1] != expected_width:
                    raise RuntimeError(
                        f"Cumulant '{spec.name}' expected width {expected_width}, "
                        f"got extracted shape {tuple(values.shape)}"
                    )
                if output is None:
                    output = torch.empty(
                        (batch_size, self._total_output_width),
                        device=values.device,
                        dtype=torch.float32,
                    )
                output[:, offset : offset + expected_width] = values.to(dtype=torch.float32, device=output.device)
                offset += expected_width
            if output is None:
                raise RuntimeError("DiffHordeCumulantExtractor has no cumulant specs to extract")
            return output

        outputs: list[Tensor] = []
        for spec, extractor in self._compiled_specs:
            values = extractor(student_td=student_td, batch_size=batch_size)
            outputs.append(self._apply_scale_and_clip(values, spec))

        if not outputs:
            raise RuntimeError("DiffHordeCumulantExtractor has no cumulant specs to extract")
        self._refresh_output_layout()
        return torch.cat(outputs, dim=1).to(dtype=torch.float32)

    def _refresh_output_layout(self) -> None:
        widths: list[int] = []
        for spec in self.cumulants_cfg.specs:
            if getattr(spec, "size", None) is None:
                self._output_widths = None
                self._total_output_width = 0
                return
            widths.append(int(spec.size))
        self._output_widths = widths
        self._total_output_width = sum(widths)

    @staticmethod
    def _apply_scale_and_clip(values: Tensor, spec: _BaseCumulantSpec) -> Tensor:
        out = values.to(dtype=torch.float32)
        if spec.scale != 1.0:
            out = out * float(spec.scale)
        if spec.clip is not None:
            out = out.clamp(min=float(spec.clip[0]), max=float(spec.clip[1]))
        return out

    @staticmethod
    def _extract_td_key(*, spec: TDKeyCumulantSpec, student_td: TensorDict, batch_size: int) -> Tensor:
        if spec.key not in student_td.keys():
            raise RuntimeError(f"Missing td_key cumulant source '{spec.key}'")

        values = student_td[spec.key].detach()
        if values.shape[0] != batch_size:
            raise RuntimeError(
                f"td_key cumulant '{spec.name}' expected batch dimension {batch_size}, got {tuple(values.shape)}"
            )
        if spec.slice is not None:
            start, end = _parse_slice_bounds(spec.slice)
            if values.shape[-1] < end:
                raise RuntimeError(
                    f"td_key cumulant '{spec.name}' slice {spec.slice!r} incompatible with shape {tuple(values.shape)}"
                )
            values = values[..., start:end]

        if spec.reduce is None:
            if values.dim() == 1:
                out = values.unsqueeze(-1)
            else:
                out = values.reshape(batch_size, -1)
        else:
            if values.dim() == 1:
                values = values.unsqueeze(-1)
            values = values.to(dtype=torch.float32)
            reduce_dims = tuple(range(1, values.dim()))
            if spec.reduce == "mean":
                reduced = values.mean(dim=reduce_dims)
            elif spec.reduce == "sum":
                reduced = values.sum(dim=reduce_dims)
            elif spec.reduce == "max":
                reduced = values.amax(dim=reduce_dims)
            else:
                raise RuntimeError(f"Unsupported td_key reduction {spec.reduce!r}")
            out = reduced.reshape(batch_size, 1)

        if spec.size is None:
            spec.size = int(out.shape[1])
        elif out.shape[1] != int(spec.size):
            raise RuntimeError(
                f"td_key cumulant '{spec.name}' expected size {spec.size}, got extracted shape {tuple(out.shape)}"
            )
        return out.to(dtype=torch.float32)

    def _extract_env_obs_feature(
        self,
        *,
        spec: EnvObsFeatureCumulantSpec,
        student_td: TensorDict,
        batch_size: int,
    ) -> Tensor:
        if "env_obs" not in student_td.keys():
            raise RuntimeError(f"Missing env_obs for env_obs_feature cumulant '{spec.name}'")

        env_obs = student_td["env_obs"].detach()
        if env_obs.dim() != 3 or env_obs.shape[-1] < 3:
            raise RuntimeError(
                f"env_obs_feature cumulant '{spec.name}' expected env_obs shape [B,M,3], got {tuple(env_obs.shape)}"
            )
        if env_obs.shape[0] != batch_size:
            raise RuntimeError(
                f"env_obs_feature cumulant '{spec.name}' expected batch size {batch_size}, got {tuple(env_obs.shape)}"
            )

        feature_id = self._resolved_obs_feature_ids[spec.name]
        token_locations = env_obs[..., _OBS_TOKEN_LOCATION]
        feature_ids = env_obs[..., _OBS_TOKEN_FEATURE_ID].to(dtype=torch.long)
        values = env_obs[..., _OBS_TOKEN_VALUE].to(dtype=torch.float32)
        valid_tokens = token_locations != _EMPTY_TOKEN_LOCATION
        matches = valid_tokens & (feature_ids == feature_id)

        if spec.normalize:
            normalization = self._feature_normalization_by_id[feature_id]
            values = values / max(normalization, 1e-6)

        matches_float = matches.to(dtype=values.dtype)
        if spec.reduce == "sum":
            reduced = (values * matches_float).sum(dim=1)
        elif spec.reduce == "mean":
            counts = matches_float.sum(dim=1)
            reduced = (values * matches_float).sum(dim=1) / counts.clamp(min=1.0)
        elif spec.reduce == "max":
            neg_inf = torch.full_like(values, fill_value=torch.finfo(values.dtype).min)
            masked = torch.where(matches, values, neg_inf)
            reduced = masked.max(dim=1).values
            has_match = matches.any(dim=1)
            reduced = torch.where(has_match, reduced, torch.zeros_like(reduced))
        else:
            raise RuntimeError(f"Unsupported env_obs_feature reduction {spec.reduce!r}")

        return reduced.reshape(batch_size, 1)

    @staticmethod
    def _extract_info_scalar(*, spec: InfoScalarCumulantSpec, student_td: TensorDict, batch_size: int) -> Tensor:
        if "env_info" not in student_td.keys():
            raise RuntimeError(f"Missing env_info for info_scalar cumulant '{spec.name}'")
        env_info = student_td["env_info"]
        if not isinstance(env_info, TensorDict):
            raise RuntimeError(f"Expected env_info TensorDict, got {type(env_info).__name__}")
        if spec.key not in env_info.keys():
            raise RuntimeError(f"Missing env_info key '{spec.key}' for info_scalar cumulant '{spec.name}'")

        values = env_info[spec.key].detach()
        if values.shape[0] != batch_size:
            raise RuntimeError(
                f"info_scalar cumulant '{spec.name}' expected batch size {batch_size}, got {tuple(values.shape)}"
            )
        if values.dim() == 1:
            return values.unsqueeze(-1).to(dtype=torch.float32)
        if values.dim() == 2 and values.shape[1] == 1:
            return values.to(dtype=torch.float32)
        raise RuntimeError(f"info_scalar cumulant '{spec.name}' expected shape [B] or [B,1], got {tuple(values.shape)}")


__all__ = [
    "CumulantSpec",
    "DiffHordeCumulantExtractor",
    "DiffHordeCumulantsConfig",
    "EnvObsFeatureCumulantSpec",
    "InfoScalarCumulantSpec",
    "TDKeyCumulantSpec",
]
