from __future__ import annotations

import logging
import os
from typing import Any

from datadog_api_client import ApiClient, Configuration
from datadog_api_client.v1.api.monitors_api import MonitorsApi
from datadog_api_client.v1.model.monitor import Monitor
from datadog_api_client.v1.model.monitor_options import MonitorOptions
from datadog_api_client.v1.model.monitor_thresholds import MonitorThresholds
from datadog_api_client.v1.model.monitor_type import MonitorType
from datadog_api_client.v1.model.monitor_update_request import MonitorUpdateRequest

from metta.common.datadog.config import datadog_config
from softmax.aws.secrets_manager import get_secretsmanager_secret

logger = logging.getLogger(__name__)


class DatadogMonitorsClient:
    def __init__(self) -> None:
        self._configuration = self._build_configuration()

    def list_monitors(self, name_filter: str | None = None) -> list[dict[str, Any]]:
        with ApiClient(self._configuration) as api_client:
            api = MonitorsApi(api_client)
            monitors = api.list_monitors(name=name_filter) if name_filter else api.list_monitors()
            return [m.to_dict() for m in monitors]

    def get_monitor(self, monitor_id: int) -> dict[str, Any] | None:
        with ApiClient(self._configuration) as api_client:
            api = MonitorsApi(api_client)
            try:
                monitor = api.get_monitor(monitor_id)
                return monitor.to_dict()
            except Exception as e:
                logger.warning("Could not get monitor %s: %s", monitor_id, e)
                return None

    def create_monitor(self, config: dict[str, Any]) -> dict[str, Any]:
        with ApiClient(self._configuration) as api_client:
            api = MonitorsApi(api_client)
            monitor = api.create_monitor(body=self._build_monitor(config))
            logger.info("Created monitor: %s (id=%s)", monitor.name, monitor.id)
            return monitor.to_dict()

    def update_monitor(self, monitor_id: int, config: dict[str, Any]) -> dict[str, Any]:
        with ApiClient(self._configuration) as api_client:
            api = MonitorsApi(api_client)
            monitor = api.update_monitor(
                monitor_id=monitor_id,
                body=self._build_update_request(config),
            )
            logger.info("Updated monitor: %s (id=%s)", monitor.name, monitor.id)
            return monitor.to_dict()

    def find_monitor_by_name(self, name: str) -> dict[str, Any] | None:
        monitors = self.list_monitors(name_filter=name)
        for m in monitors:
            if m.get("name") == name:
                return m
        return None

    def delete_monitor(self, monitor_id: int) -> None:
        with ApiClient(self._configuration) as api_client:
            api = MonitorsApi(api_client)
            api.delete_monitor(monitor_id)
            logger.info("Deleted monitor: %s", monitor_id)

    def sync_monitor(self, config: dict[str, Any]) -> dict[str, Any]:
        name = config["name"]
        existing = self.find_monitor_by_name(name)
        if existing:
            logger.info("Monitor '%s' exists (id=%s), updating...", name, existing["id"])
            return self.update_monitor(existing["id"], config)
        else:
            logger.info("Monitor '%s' not found, creating...", name)
            return self.create_monitor(config)

    def _build_monitor(self, config: dict[str, Any]) -> Monitor:
        thresholds = MonitorThresholds(**config.get("thresholds", {}))
        options = MonitorOptions(
            thresholds=thresholds,
            **{k: v for k, v in config.get("options", {}).items() if k != "thresholds"},
        )
        return Monitor(
            name=config["name"],
            type=MonitorType(config["type"]),
            query=config["query"],
            message=config.get("message", ""),
            tags=config.get("tags", []),
            priority=config.get("priority"),
            options=options,
        )

    def _build_update_request(self, config: dict[str, Any]) -> MonitorUpdateRequest:
        thresholds = MonitorThresholds(**config.get("thresholds", {}))
        options = MonitorOptions(
            thresholds=thresholds,
            **{k: v for k, v in config.get("options", {}).items() if k != "thresholds"},
        )
        return MonitorUpdateRequest(
            name=config["name"],
            type=MonitorType(config["type"]),
            query=config["query"],
            message=config.get("message", ""),
            tags=config.get("tags", []),
            priority=config.get("priority"),
            options=options,
        )

    def _build_configuration(self) -> Configuration:
        configuration = Configuration()
        configuration.server_variables["site"] = os.environ.get("DD_SITE", datadog_config.DD_SITE)

        api_key = self._get_api_key()
        app_key = self._get_app_key()

        if not api_key:
            raise RuntimeError("Missing Datadog API key (datadog/api-key in Secrets Manager)")
        if not app_key:
            raise RuntimeError("Missing Datadog app key (datadog/app-key in Secrets Manager)")

        configuration.api_key["apiKeyAuth"] = api_key
        configuration.api_key["appKeyAuth"] = app_key
        return configuration

    def _get_api_key(self) -> str | None:
        return get_secretsmanager_secret("datadog/api-key", require_exists=False)

    def _get_app_key(self) -> str | None:
        return get_secretsmanager_secret("datadog/app-key", require_exists=False)
