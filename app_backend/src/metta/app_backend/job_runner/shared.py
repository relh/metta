"""Shared utilities for job runner components (watcher, event processor)."""

from __future__ import annotations

import logging
import threading
import time
from uuid import UUID

import boto3
from botocore.client import BaseClient
from kubernetes import client

from metta.app_backend.job_runner.config import get_dispatch_config
from metta.app_backend.job_runner.job_artifacts import job_logs_key, job_replay_key

logger = logging.getLogger(__name__)

_s3_client: BaseClient | None = None
_s3_client_lock = threading.Lock()


def get_s3_client() -> BaseClient:
    global _s3_client
    if _s3_client is None:
        with _s3_client_lock:
            if _s3_client is None:
                _s3_client = boto3.client("s3")
    return _s3_client


def copy_replay_to_public(job_id: UUID, replay_uri: str | None) -> bool:
    if not replay_uri or not replay_uri.startswith("s3://"):
        return True

    cfg = get_dispatch_config()
    if not cfg.EVAL_S3_BUCKET:
        return False

    source_key = job_replay_key(job_id)
    s3 = get_s3_client()

    delays = [1, 2, 4, 8]
    replay_exists = False
    for i, delay in enumerate(delays):
        try:
            s3.head_object(Bucket=cfg.EVAL_S3_BUCKET, Key=source_key)
            replay_exists = True
            break
        except s3.exceptions.ClientError:
            if i < len(delays) - 1:
                time.sleep(delay)

    if not replay_exists:
        logger.warning(f"Replay not found in EVAL bucket for job {job_id}, skipping copy")
        return True

    parts = replay_uri.removeprefix("s3://").split("/", 1)
    if len(parts) != 2:
        logger.warning(f"Invalid replay_uri format: {replay_uri}")
        return False
    dest_bucket, dest_key = parts

    try:
        s3.copy_object(
            Bucket=dest_bucket,
            Key=dest_key,
            CopySource={"Bucket": cfg.EVAL_S3_BUCKET, "Key": source_key},
            MetadataDirective="COPY",
        )
        logger.info(f"Copied replay to s3://{dest_bucket}/{dest_key} for job {job_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to copy replay for job {job_id}: {e}")
        return False


def capture_pod_logs(core_v1: client.CoreV1Api, pod_name: str, job_id: UUID):
    cfg = get_dispatch_config()
    try:
        logs = core_v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=cfg.JOB_NAMESPACE,
            container="worker",
            tail_lines=10000,
        )
    except Exception as e:
        logger.warning(f"Failed to read logs for job {job_id} pod {pod_name}: {e}")
        return
    if not logs:
        return
    try:
        get_s3_client().put_object(
            Bucket=cfg.EVAL_S3_BUCKET,
            Key=job_logs_key(job_id),
            Body=logs.encode("utf-8"),
            ContentType="text/plain",
        )
        logger.info(f"Captured logs for job {job_id} ({len(logs)} bytes)")
    except Exception as e:
        logger.error(f"Failed to upload logs for job {job_id}: {e}")
