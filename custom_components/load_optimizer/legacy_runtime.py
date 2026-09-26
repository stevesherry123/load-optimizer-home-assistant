"""Home Assistant adapter for the legacy Load Optimizer add-on engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
import re
from typing import Any
from urllib.parse import unquote, urlparse

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .legacy import app_runtime

LOGGER = logging.getLogger(__name__)
LEGACY_STORE_VERSION = 1
LEGACY_STORE_KEY = f"{DOMAIN}_legacy_state"
TOKEN = "__hass_adapter__"


@dataclass
class LegacyScanResult:
    """Summary of a legacy compatibility scan."""

    status: str
    instance_count: int
    entity_count: int
    last_scan: str
    message: str | None = None


class LegacyRuntime:
    """Run the old add-on scan loop inside a Home Assistant integration."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.store = Store(hass, LEGACY_STORE_VERSION, LEGACY_STORE_KEY)
        self.state: dict[str, Any] | None = None
        self.last_signature: str | None = None
        self.entity_count = 0
        self.calendar_events: dict[str, list[dict[str, Any]]] = {}
        self.started = False
        self._patch_legacy_runtime()

    async def async_load(self) -> None:
        """Load persisted legacy state from Home Assistant storage."""
        if self.state is not None:
            return
        stored = await self.store.async_load()
        if isinstance(stored, dict) and stored.get("schema_version"):
            self.state = stored
        else:
            self.state = dict(app_runtime.EMPTY_STATE)
        self.last_signature = app_runtime.state_signature(self.state)

    async def async_import_state(self, payload: str | dict[str, Any]) -> dict[str, Any]:
        """Import legacy add-on JSON into integration storage."""
        if isinstance(payload, str):
            data = json.loads(payload)
        else:
            data = payload
        if not isinstance(data, dict) or "instances" not in data:
            raise ValueError("Imported state must be a Load Optimizer database with an instances object")
        data.setdefault("schema_version", 1)
        self.state = data
        self.last_signature = app_runtime.state_signature(data)
        await self.store.async_save(data)
        return {
            "status": "imported",
            "instances": sorted(str(key) for key in data.get("instances", {})),
        }

    async def async_scan(self, options: dict[str, Any]) -> LegacyScanResult:
        """Run one legacy compatibility scan."""
        await self.async_load()
        assert self.state is not None
        now = datetime.now(timezone.utc)
        self.entity_count = 0
        app_runtime.refresh_publish_cache()
        configs = app_runtime.instance_configs(options)
        await self._async_prefetch_calendar_events(configs, now)
        if not self.started:
            app_runtime.RUNTIME_STARTED_AT = now
            app_runtime.SCAN_HEALTH_TIMEOUT_SECONDS = max(180, (int(options.get("scan_interval", 60)) * 3) + 30)
            app_runtime.reset_configured_instances(self.state, options)
            app_runtime.bootstrap_program_models(self.state)
            app_runtime.repair_learning_quality(self.state, configs)
            startup_running = app_runtime.running_instances(self.state, configs)
            app_runtime.mark_interrupted_captures(self.state, startup_running)
            app_runtime.publish_restart_warning(TOKEN, startup_running)
            self.started = True
        reset_status = app_runtime.reset_request_status(self.state, options)
        app_runtime.LAST_SCAN_STARTED_AT = now
        for config in configs:
            try:
                app_runtime.update_instance(TOKEN, self.state, config, now=now)
            except Exception as error:  # pragma: no cover - defensive integration isolation
                LOGGER.exception("Legacy Load Optimizer scan failed for instance %s", config.get("instance_id"))
                app_runtime.publish_entity(
                    TOKEN,
                    f"sensor.load_optimizer_{config.get('instance_id')}_status",
                    "error",
                    {
                        "friendly_name": f"{config.get('name', 'Load Optimizer')} Optimizer Status",
                        "icon": "mdi:alert-circle",
                        "reason": str(error),
                    },
                )
        running = app_runtime.running_instances(self.state, configs)
        app_runtime.publish_restart_safety(TOKEN, running)
        app_runtime.LAST_SCAN_COMPLETED_AT = datetime.now(timezone.utc)
        app_runtime.publish_status(TOKEN, len(configs), running=running, reset_status=reset_status)
        app_runtime.publish_logging_diagnostics(TOKEN)
        signature = app_runtime.state_signature(self.state)
        if signature != self.last_signature:
            await self.store.async_save(self.state)
            self.last_signature = signature
        return LegacyScanResult(
            status="ready" if configs else "configuration_required",
            instance_count=len(configs),
            entity_count=self.entity_count,
            last_scan=now.isoformat(),
            message=None if configs else "Configure learned appliance instances to enable compatibility publishing.",
        )

    def _patch_legacy_runtime(self) -> None:
        app_runtime.source_state = self._source_state
        app_runtime.publish_entity = self._publish_entity
        app_runtime.render_template = self._render_template
        app_runtime.api_request = self._api_request
        app_runtime.save_state = self._save_state_ignored
        app_runtime.load_state = self._load_state_ignored
        app_runtime.save_state_if_changed = self._save_state_if_changed_ignored

    def _source_state(self, token: str, entity_id: str) -> dict[str, Any] | None:
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        return {
            "entity_id": entity_id,
            "state": state.state,
            "attributes": dict(state.attributes),
            "last_changed": state.last_changed.isoformat(),
            "last_updated": state.last_updated.isoformat(),
        }

    def _publish_entity(self, token: str, entity_id: str, state: object, attributes: dict) -> None:
        self.entity_count += 1
        self.hass.states.async_set(entity_id, str(state), attributes)

    def _api_request(self, token: str, path: str, payload: dict | None = None) -> object | None:
        if path == "/services/persistent_notification/create" and payload:
            self.hass.async_create_task(
                self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    payload,
                    blocking=False,
                )
            )
            return {"status": "queued"}
        if path.startswith("/states/") and payload is not None:
            entity_id = path.removeprefix("/states/")
            self._publish_entity(token, entity_id, payload.get("state"), payload.get("attributes", {}))
            return {"entity_id": entity_id}
        if path.startswith("/calendars/"):
            parsed = urlparse(path)
            entity_id = unquote(parsed.path.removeprefix("/calendars/"))
            return self.calendar_events.get(entity_id, [])
        return None

    async def _async_prefetch_calendar_events(self, configs: list[dict[str, Any]], now: datetime) -> None:
        calendar_ids: set[str] = set()
        horizon_hours = 24
        for config in configs:
            horizon_hours = max(
                horizon_hours,
                int(config.get("cost_search_hours", 24) or 24),
                int(config.get("cost_forecast_hours", 12) or 12),
            )
            for key in ("green_window_entity", "blocked_window_entity"):
                for entity_id in app_runtime.entity_list(config.get(key, "")):
                    if entity_id.startswith("calendar."):
                        calendar_ids.add(entity_id)
        self.calendar_events = {}
        if not calendar_ids:
            return
        end = now + timedelta(hours=horizon_hours)
        for entity_id in sorted(calendar_ids):
            try:
                response = await self.hass.services.async_call(
                    "calendar",
                    "get_events",
                    {
                        "entity_id": entity_id,
                        "start_date_time": now.isoformat(),
                        "end_date_time": end.isoformat(),
                    },
                    blocking=True,
                    return_response=True,
                )
            except Exception as error:  # pragma: no cover - depends on HA calendar platform
                LOGGER.debug("Could not prefetch calendar events for %s: %s", entity_id, error)
                continue
            events = []
            if isinstance(response, dict):
                payload = response.get(entity_id, response)
                if isinstance(payload, dict):
                    raw_events = payload.get("events", [])
                    if isinstance(raw_events, list):
                        events = raw_events
                elif isinstance(payload, list):
                    events = payload
            self.calendar_events[entity_id] = events

    def _render_template(self, token: str, template: str) -> object | None:
        state_attr_match = re.search(r"state_attr\('([^']+)',\s*'([^']+)'\)", template)
        if state_attr_match:
            state = self.hass.states.get(state_attr_match.group(1))
            return state.attributes.get(state_attr_match.group(2)) if state else None
        helper_prefix_match = re.search(r"helper_prefix = '([^']+)'", template)
        if helper_prefix_match:
            return self._execution_snapshot(helper_prefix_match.group(1))
        return None

    def _execution_snapshot(self, helper_prefix: str) -> dict[str, Any]:
        def state(entity_id: str) -> str:
            item = self.hass.states.get(entity_id)
            return item.state if item else "unknown"

        def helper(domain: str, suffix: str) -> str:
            return state(f"{domain}.{helper_prefix}_{suffix}")

        connected_entity = helper("input_text", "bosch_connected_sensor")
        door_entity = helper("input_text", "bosch_door_sensor")
        remote_control_entity = helper("input_text", "bosch_remote_control_sensor")
        remote_start_entity = helper("input_text", "bosch_remote_start_sensor")
        operation_entity = helper("input_text", "bosch_operation_state_sensor")
        selected_program_entity = helper("input_text", "bosch_selected_program_sensor")
        power_state_entity = helper("input_text", "bosch_power_state_sensor")
        return {
            "status": helper("input_text", "start_attempt_status"),
            "message": helper("input_text", "start_attempt_message"),
            "result": helper("input_text", "last_start_result"),
            "failure_reason": helper("input_text", "last_start_failure_reason"),
            "reason_code": helper("input_text", "last_start_reason_code"),
            "reason_detail": helper("input_text", "last_start_reason_detail"),
            "decision_snapshot": helper("input_text", "last_start_decision_snapshot"),
            "execution_event": helper("input_text", "last_execution_event"),
            "program": helper("input_text", "last_start_program"),
            "attempt": helper("input_datetime", "last_start_attempt"),
            "mode": helper("input_text", "last_start_mode"),
            "program_key": helper("input_text", "last_start_program_key"),
            "selected_program_state": helper("input_text", "last_start_selected_program"),
            "operation_state": helper("input_text", "last_start_operation_state"),
            "readiness": helper("input_text", "last_start_readiness"),
            "remote_blocked_programs": helper("input_text", "remote_start_blocked_programs"),
            "bosch_connected_entity": connected_entity,
            "bosch_connected_state": state(connected_entity),
            "bosch_door_entity": door_entity,
            "bosch_door_state": state(door_entity),
            "bosch_remote_control_entity": remote_control_entity,
            "bosch_remote_control_state": state(remote_control_entity),
            "bosch_remote_start_entity": remote_start_entity,
            "bosch_remote_start_state": state(remote_start_entity),
            "bosch_operation_entity": operation_entity,
            "bosch_operation_state": state(operation_entity),
            "bosch_selected_program_entity": selected_program_entity,
            "bosch_selected_program_state_current": state(selected_program_entity),
            "bosch_power_state_entity": power_state_entity,
            "bosch_power_state": state(power_state_entity),
            "cycle_state": state(f"sensor.{helper_prefix}_cycle_state"),
        }

    def _load_state_ignored(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.state or dict(app_runtime.EMPTY_STATE)

    def _save_state_ignored(self, *args: Any, **kwargs: Any) -> None:
        return None

    def _save_state_if_changed_ignored(self, data: dict, previous_signature: str | None, *args: Any, **kwargs: Any) -> str:
        return app_runtime.state_signature(data)
