from typing import Literal

from pydantic import BaseModel

Operator = Literal[">=", ">", "<=", "<", "==", "in"]


class AcceptanceCriterion(BaseModel):
    metric: str
    threshold: float | tuple[float, float]
    operator: Operator = ">="
    metric_name: str | None = None
