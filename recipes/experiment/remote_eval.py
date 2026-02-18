from __future__ import annotations

import metta.tools as tools
from metta.sim.remote import RemoteEvalTaskData


# Used by eval_task_worker.py
def eval(
    task_data_path: str,
    result_file_path: str,
) -> tools.EvalWithResultTool:
    with open(task_data_path, "rb") as f:
        task_data = RemoteEvalTaskData.model_validate_json(f.read())

    return tools.EvalWithResultTool(
        simulations=task_data.simulations,
        policy_uris=task_data.policy_uris,
        push_metrics_to_wandb=True,
        result_file_path=result_file_path,
    )
