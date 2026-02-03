from __future__ import annotations

import logging
import os
from typing import Any

from datadog_api_client import ApiClient, Configuration
from datadog_api_client.v1.api.dashboards_api import DashboardsApi
from datadog_api_client.v1.model.dashboard import Dashboard
from datadog_api_client.v1.model.dashboard_layout_type import DashboardLayoutType

from metta.common.datadog.config import datadog_config
from softmax.aws.secrets_manager import get_secretsmanager_secret

logger = logging.getLogger(__name__)


class DatadogDashboardsClient:
    def __init__(self) -> None:
        self._configuration = self._build_configuration()

    def list_dashboards(self) -> list[dict[str, Any]]:
        with ApiClient(self._configuration) as api_client:
            api = DashboardsApi(api_client)
            response = api.list_dashboards()
            return [d.to_dict() for d in (response.dashboards or [])]

    def get_dashboard(self, dashboard_id: str) -> dict[str, Any] | None:
        with ApiClient(self._configuration) as api_client:
            api = DashboardsApi(api_client)
            try:
                dashboard = api.get_dashboard(dashboard_id)
                return dashboard.to_dict()
            except Exception as e:
                logger.warning("Could not get dashboard %s: %s", dashboard_id, e)
                return None

    def create_dashboard(self, config: dict[str, Any]) -> dict[str, Any]:
        with ApiClient(self._configuration) as api_client:
            api = DashboardsApi(api_client)
            dashboard = api.create_dashboard(body=self._build_dashboard(config))
            logger.info("Created dashboard: %s (id=%s)", dashboard.title, dashboard.id)
            return dashboard.to_dict()

    def update_dashboard(self, dashboard_id: str, config: dict[str, Any]) -> dict[str, Any]:
        with ApiClient(self._configuration) as api_client:
            api = DashboardsApi(api_client)
            dashboard = api.update_dashboard(dashboard_id, body=self._build_dashboard(config))
            logger.info("Updated dashboard: %s (id=%s)", dashboard.title, dashboard.id)
            return dashboard.to_dict()

    def delete_dashboard(self, dashboard_id: str) -> None:
        with ApiClient(self._configuration) as api_client:
            api = DashboardsApi(api_client)
            api.delete_dashboard(dashboard_id)
            logger.info("Deleted dashboard: %s", dashboard_id)

    def find_by_title(self, title: str) -> dict[str, Any] | None:
        dashboards = self.list_dashboards()
        matches = [d for d in dashboards if d.get("title") == title]
        if len(matches) > 1:
            logger.warning("Found %d dashboards with title '%s', using first match", len(matches), title)
        return matches[0] if matches else None

    def sync_dashboard(self, config: dict[str, Any]) -> dict[str, Any]:
        title = config["title"]
        existing = self.find_by_title(title)
        if existing:
            logger.info("Dashboard '%s' exists (id=%s), updating...", title, existing["id"])
            return self.update_dashboard(existing["id"], config)
        logger.info("Dashboard '%s' not found, creating...", title)
        return self.create_dashboard(config)

    def _build_dashboard(self, config: dict[str, Any]) -> Dashboard:
        return Dashboard(
            title=config["title"],
            description=config.get("description", ""),
            layout_type=DashboardLayoutType(config.get("layout_type", "ordered")),
            widgets=config.get("widgets", []),
            tags=config.get("tags"),
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
