from __future__ import annotations

STABLE_CHECK_RAW_STATUS_METRIC = "metta.infra.cron.stable.check.raw_status"
STABLE_CHECK_EFFECTIVE_STATUS_SERVICE_CHECK = "metta.infra.cron.stable.check.last_effective_status"
STABLE_CHECK_EFFECTIVE_STATUS_METRIC = "metta.infra.cron.stable.check.effective_status"
STABLE_CHECK_COMPLETED_AT_METRIC = "metta.infra.cron.stable.check.completed_at"
STABLE_CHECK_ACCEPTANCE_CRITERION_VALUE_METRIC = "metta.infra.cron.stable.acceptance.value"
STABLE_CHECK_ACCEPTANCE_CRITERION_TARGET_METRIC = "metta.infra.cron.stable.acceptance.target"
STABLE_CHECK_ACCEPTANCE_CRITERION_STATUS_METRIC = "metta.infra.cron.stable.acceptance.status"


def job_path_to_job_tag(job_path: str) -> str:
    if job_path.startswith("recipes."):
        return job_path.replace("recipes.", "", 1).replace(".", "_")
    elif job_path.startswith("devops.stable.function_checks."):
        return job_path.replace("devops.stable.function_checks.", "prod.", 1).replace(".", "_")
    return job_path.replace(".", "_")
