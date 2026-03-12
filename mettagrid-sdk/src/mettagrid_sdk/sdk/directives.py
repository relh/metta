from __future__ import annotations

from pydantic import BaseModel, Field


class MacroDirective(BaseModel):
    role: str | None = None
    target_entity_id: str | None = None
    target_region: str | None = None
    resource_bias: str | None = None
    objective: str | None = None
    note: str = ""
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)

    def is_empty(self) -> bool:
        return (
            self.role is None
            and self.target_entity_id is None
            and self.target_region is None
            and self.resource_bias is None
            and self.objective is None
            and not self.note
            and not self.metadata
        )
