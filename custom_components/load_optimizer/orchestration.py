"""Native dishwasher orchestration for learned Load Optimizer appliances."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Callable
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .orchestration_migration import LEGACY_AUTOMATION_IDS, OrchestrationMigration

LOGGER = logging.getLogger(__name__)
STORE_VERSION = 1
PROGRAM_PREFIX = "Dishcare.Dishwasher.Program."
RUNNING_OPERATION = "BSH.Common.EnumType.OperationState.Run"
UNKNOWN_STATES = {"", "none", "unknown", "unavailable"}
COOLDOWN_CONFIDENCE_FLOOR = 20

CONTROL_DEFAULTS: dict[str, Any] = {
    "active": False,
    "auto_mode_enabled": False,
    "auto_negative_price_enabled": False,
    "door_opened_since_last_cycle": False,
    "override_program": "engine",
    "special_price_window_enabled": False,
    "special_price_window_start": None,
    "special_price_window_end": None,
    "special_price_window_price": 0.0,
    "special_price_window_label": "Octopus special price",
    "request": None,
    "execution_status": "idle",
    "last_result": None,
    "last_reason": None,
    "last_message": None,
    "last_program": None,
    "last_mode": None,
    "last_attempt": None,
    "last_auto_negative_price_request": None,
    "last_auto_normal_request": None,
    "run_history": [],
    "schedule_events": [],
    "shadow_decision": None,
}

LEGACY_CONFIG_HELPERS = {
    "bosch_device_id": "input_text.load_optimizer_1_bosch_device_id",
    "bosch_power_switch": "input_text.load_optimizer_1_bosch_power_switch",
    "bosch_program_select": "input_text.load_optimizer_1_bosch_program_select",
    "bosch_start_button": "input_text.load_optimizer_1_bosch_start_button",
    "bosch_selected_program_sensor": "input_text.load_optimizer_1_bosch_selected_program_sensor",
    "bosch_power_state_sensor": "input_text.load_optimizer_1_bosch_power_state_sensor",
    "bosch_connected_sensor": "input_text.load_optimizer_1_bosch_connected_sensor",
    "bosch_door_sensor": "input_text.load_optimizer_1_bosch_door_sensor",
    "bosch_remote_control_sensor": "input_text.load_optimizer_1_bosch_remote_control_sensor",
    "bosch_remote_start_sensor": "input_text.load_optimizer_1_bosch_remote_start_sensor",
    "bosch_operation_state_sensor": "input_text.load_optimizer_1_bosch_operation_state_sensor",
}


class NativeOrchestrator:
    """Own requests, safety checks, and appliance execution after handover."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        migration: OrchestrationMigration,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.migration = migration
        self.store = Store(
            hass,
            STORE_VERSION,
            f"{DOMAIN}.native_orchestration.{entry.entry_id}",
        )
        self.state: dict[str, Any] = dict(CONTROL_DEFAULTS)
        self.config: dict[str, str] = {}
        self.program_options: list[str] = ["engine"]
        self._loaded = False
        self._remove_listeners: list[Callable[[], None]] = []
        self._execution_task: asyncio.Task | None = None
        self._update_callback: Callable[[dict[str, Any]], None] | None = None

    def set_update_callback(
        self,
        update_callback: Callable[[dict[str, Any]], None],
    ) -> None:
        """Set the coordinator data callback."""
        self._update_callback = update_callback

    async def async_load(self) -> None:
        """Load native state and seed it from the captured package once."""
        if self._loaded:
            return
        stored = await self.store.async_load()
        if isinstance(stored, dict):
            self.state.update(stored.get("state", {}))
            self.config.update(stored.get("config", {}))
            self.program_options = stored.get("program_options", ["engine"])
        else:
            self._seed_from_migration()
            await self._async_save()
        configured = {**self.entry.data, **self.entry.options}
        for key in LEGACY_CONFIG_HELPERS:
            if configured.get(key):
                self.config[key] = str(configured[key])
        if self._refresh_program_options():
            await self._async_save()
        self._loaded = True

    def _refresh_program_options(self) -> bool:
        """Use the appliance's current capabilities, retaining a last-good fallback."""
        selector = self.hass.states.get(self.config.get("bosch_program_select", ""))
        if not selector or selector.state in UNKNOWN_STATES:
            return False
        programmes = [
            value.removeprefix(PROGRAM_PREFIX)
            for value in selector.attributes.get("options", [])
            if isinstance(value, str) and value.startswith(PROGRAM_PREFIX)
            and value != PROGRAM_PREFIX
        ]
        if not programmes:
            return False
        options = list(dict.fromkeys(["engine", *programmes]))
        if options == self.program_options:
            return False
        self.program_options = options
        return True

    def _seed_from_migration(self) -> None:
        helpers = (self.migration.snapshot or {}).get("helpers", {})

        def helper_state(entity_id: str, default: Any = None) -> Any:
            return helpers.get(entity_id, {}).get("state", default)

        self.state.update(
            {
                "auto_mode_enabled": helper_state(
                    "input_boolean.load_optimizer_1_auto_mode_enabled",
                    "off",
                )
                == STATE_ON,
                "auto_negative_price_enabled": helper_state(
                    "input_boolean.load_optimizer_1_auto_negative_price_enabled",
                    "off",
                )
                == STATE_ON,
                "door_opened_since_last_cycle": helper_state(
                    "input_boolean.load_optimizer_1_door_opened_since_last_cycle",
                    "off",
                )
                == STATE_ON,
                "override_program": helper_state(
                    "input_select.load_optimizer_1_override_program",
                    "engine",
                ),
                "special_price_window_enabled": helper_state(
                    "input_boolean.load_optimizer_special_price_window_enabled",
                    "off",
                )
                == STATE_ON,
                "special_price_window_start": helper_state(
                    "input_datetime.load_optimizer_special_price_window_start"
                ),
                "special_price_window_end": helper_state(
                    "input_datetime.load_optimizer_special_price_window_end"
                ),
                "special_price_window_price": float(
                    helper_state(
                        "input_number.load_optimizer_special_price_window_price",
                        0,
                    )
                    or 0
                ),
                "special_price_window_label": (
                    "Octopus special price"
                    if str(
                        helper_state(
                            "input_text.load_optimizer_special_price_window_label",
                            "Octopus special price",
                        )
                    ).lower()
                    in UNKNOWN_STATES
                    else helper_state(
                        "input_text.load_optimizer_special_price_window_label",
                        "Octopus special price",
                    )
                ),
                "last_auto_negative_price_request": helper_state(
                    "input_datetime.load_optimizer_1_last_auto_negative_price_request"
                ),
                "last_auto_normal_request": helper_state(
                    "input_datetime.load_optimizer_1_last_auto_normal_request"
                ),
            }
        )
        override = helpers.get(
            "input_select.load_optimizer_1_override_program",
            {},
        )
        options = override.get("attributes", {}).get("options") or []
        self.program_options = list(dict.fromkeys(["engine", *options]))
        for key, entity_id in LEGACY_CONFIG_HELPERS.items():
            value = helper_state(entity_id, "")
            if str(value).lower() not in UNKNOWN_STATES:
                self.config[key] = str(value)

    async def async_start(self) -> None:
        """Start shadow evaluation and native event tracking."""
        await self.async_load()
        watched = {
            "sensor.load_optimizer_1_cycle_state",
            "sensor.load_optimizer_1_overnight_recommendation",
            "sensor.load_optimizer_1_negative_price_recommendation",
            "input_datetime.load_optimizer_1_must_finish_by",
        }
        watched.update(
            entity_id
            for key, entity_id in self.config.items()
            if key.endswith("sensor")
        )
        if self.config.get("bosch_program_select"):
            watched.add(self.config["bosch_program_select"])
        self._remove_listeners.append(
            async_track_state_change_event(
                self.hass,
                watched,
                self._async_state_changed,
            )
        )
        self._remove_listeners.append(
            async_track_time_interval(
                self.hass,
                self._async_interval,
                timedelta(minutes=1),
            )
        )
        await self.async_evaluate()

    async def async_stop(self) -> None:
        """Stop listeners and any pending execution task."""
        for remove in self._remove_listeners:
            remove()
        self._remove_listeners.clear()
        if self._execution_task and not self._execution_task.done():
            self._execution_task.cancel()

    @callback
    def _async_state_changed(self, event: Event) -> None:
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if entity_id == self.config.get("bosch_operation_state_sensor") and new_state:
            if new_state.state == RUNNING_OPERATION and (
                not old_state or old_state.state != RUNNING_OPERATION
            ):
                self.state["capture_had_reported_run"] = True
                self.hass.async_create_task(self.async_set(
                    "confirmed_cycle_started_at", new_state.last_changed.isoformat()
                ))
                self.hass.async_create_task(self.async_set("door_opened_since_last_cycle", False))
        if entity_id == self.config.get("bosch_door_sensor") and new_state:
            if new_state.state in {"on", "open"}:
                self.hass.async_create_task(self.async_set("door_opened_since_last_cycle", True))
        if entity_id == "sensor.load_optimizer_1_cycle_state" and new_state:
            if new_state.state == "running" and (not old_state or old_state.state != "running"):
                self.state["capture_had_reported_run"] = (
                    self._state(self.config.get("bosch_operation_state_sensor")) == RUNNING_OPERATION
                )
            if old_state and old_state.state == "running" and new_state.state == "idle":
                self.hass.async_create_task(self._async_record_cycle_end(old_state.last_changed))
        self.hass.async_create_task(self.async_evaluate())

    async def _async_interval(self, now: datetime) -> None:
        await self.async_evaluate(now)

    async def async_set(self, key: str, value: Any) -> None:
        """Update and persist one native orchestration value."""
        self.state[key] = value
        await self._async_save()
        self._publish()
        if key in {"auto_mode_enabled", "auto_negative_price_enabled"}:
            await self.async_evaluate()

    async def async_request(self, mode: str, *, override: bool = False) -> None:
        """Capture a user request from a native button."""
        recommendation = self._recommendation(mode)
        selected_override = (
            override
            and self.state.get("override_program") not in {None, "", "engine"}
        )
        manual_now_override = selected_override and mode == "now"
        attributes = recommendation.attributes if recommendation else {}
        program = (
            self.state.get("override_program")
            if selected_override
            else attributes.get("program") or (recommendation.state if recommendation else None)
        )
        options = attributes.get(
            "display_program_options" if override else "program_options", []
        ) or attributes.get("program_options", [])
        option = next(
            (
                item
                for item in options
                if item.get("program") == program
            ),
            {},
        )
        if not manual_now_override and not (selected_override and option) and (
            recommendation is None or attributes.get("status") != "ready"
        ):
            await self._async_outcome(
                "blocked", mode, program, "recommendation_not_ready",
                f"No ready {mode} recommendation is available.",
            )
            return
        if mode == "now":
            start_time = datetime.now(timezone.utc)
            option_start = self._parse_datetime(option.get("start"))
            option_finish = self._parse_datetime(option.get("finish"))
            start = start_time.isoformat()
            finish = (
                (start_time + (option_finish - option_start)).isoformat()
                if option_start and option_finish and option_finish > option_start else None
            )
        elif selected_override and not option:
            await self._async_outcome(
                "blocked", mode, program, "selected_program_not_available_in_window",
                f"No {mode} plan is available for {program}; choose another window or an explicit start now.",
            )
            return
        else:
            start = option.get("start") or attributes.get("start")
            finish = option.get("finish") or attributes.get("finish")
        self.state["request"] = {
            "mode": mode,
            "program": program,
            "start": start,
            "finish": finish,
            "explicit_program_override": override,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.state["execution_status"] = "queued"
        self.state["last_message"] = f"Queued {program} for {start}."
        self._record_schedule_event("queued", "user_request_queued", program=program, start=start)
        await self._async_save()
        self._publish()
        await self.async_evaluate()

    async def async_cancel(self) -> None:
        """Cancel a pending native request."""
        request = self.state.get("request") or {}
        self.state["request"] = None
        await self._async_outcome(
            "cancelled",
            request.get("mode"),
            request.get("program"),
            "cancelled_by_user",
            "Pending dishwasher request cancelled.",
        )

    async def async_recalculate(self) -> None:
        """Request a fresh optimizer scan."""
        coordinator = self.hass.data[DOMAIN].get(self.entry.entry_id)
        if coordinator:
            await coordinator.async_request_refresh()

    async def async_activate(self) -> None:
        """Disable package automations and enable native command ownership."""
        missing_config = [key for key in LEGACY_CONFIG_HELPERS if not self.config.get(key)]
        if missing_config:
            raise HomeAssistantError(
                f"Missing captured Bosch configuration: {', '.join(missing_config)}"
            )
        existing_automations = [
            entity_id
            for entity_id in LEGACY_AUTOMATION_IDS
            if self.hass.states.get(entity_id) is not None
        ]
        if (
            self.migration.status.get("status") != "prepared"
            and existing_automations
        ):
            raise HomeAssistantError(
                "Prepare orchestration migration before replacing package automations"
            )
        if existing_automations:
            await self.hass.services.async_call(
                "automation",
                "turn_off",
                {"entity_id": existing_automations, "stop_actions": True},
                blocking=True,
            )
        self.state["active"] = True
        self.state["execution_status"] = "idle"
        self.state["last_message"] = "Native orchestration activated."
        await self._async_save()
        self._publish()
        await self.async_evaluate()

    async def async_deactivate(self) -> None:
        """Return command ownership to the package automations."""
        self.state["active"] = False
        await self._async_save()
        self._publish()
        existing_automations = [
            entity_id
            for entity_id in LEGACY_AUTOMATION_IDS
            if self.hass.states.get(entity_id) is not None
        ]
        if existing_automations:
            await self.hass.services.async_call(
                "automation",
                "turn_on",
                {"entity_id": existing_automations},
                blocking=True,
            )

    async def async_evaluate(self, now: datetime | None = None) -> None:
        """Evaluate shadow or active scheduling decisions."""
        now = now or datetime.now(timezone.utc)
        options_changed = self._refresh_program_options()
        decision = self._automatic_decision(now)
        changed = decision != self.state.get("shadow_decision")
        save_required = changed or options_changed
        self.state["shadow_decision"] = decision
        if changed:
            self._record_schedule_event(
                "decision", decision.get("reason", "automatic_request_available"),
                now=now, **{key: value for key, value in decision.items() if key != "reason"},
            )
        if not self.state.get("active"):
            if save_required:
                await self._async_save()
            self._publish()
            return
        if self.state.get("request") is None and decision.get("action") == "queue":
            recommendation = self._recommendation(decision["mode"])
            if recommendation:
                self.state["request"] = {
                    "mode": decision["request_mode"],
                    "program": decision["program"],
                    "start": recommendation.attributes.get("start"),
                    "finish": recommendation.attributes.get("finish"),
                    "explicit_program_override": False,
                    "created_at": now.isoformat(),
                }
                self.state["execution_status"] = "queued"
                self.state[
                    "last_auto_negative_price_request"
                    if decision["request_mode"] == "negative_price"
                    else "last_auto_normal_request"
                ] = now.isoformat()
                self._record_schedule_event(
                    "queued", "automatic_request_queued", now=now,
                    program=decision["program"], start=recommendation.attributes.get("start"),
                )
                save_required = True
        if save_required:
            await self._async_save()
        request = self.state.get("request")
        if request and self._request_due(request, now):
            if not self._execution_task or self._execution_task.done():
                self._execution_task = self.hass.async_create_task(
                    self._async_execute(dict(request)),
                )
        self._publish()

    def _automatic_decision(self, now: datetime) -> dict[str, Any]:
        if self.state.get("request") is not None:
            return {"action": "wait", "reason": "request_already_pending"}
        if self._state("sensor.load_optimizer_1_cycle_state") != "idle":
            return {"action": "wait", "reason": "appliance_not_idle"}
        negative = self._recommendation("negative_price")
        if (
            self.state.get("auto_negative_price_enabled")
            and negative
            and negative.attributes.get("status") == "ready"
            and negative.attributes.get("ready_to_start") is True
            and self._recommendation_confident(negative)
            and self._cooldown_elapsed("last_auto_negative_price_request", 30, now)
        ):
            return {
                "action": "queue",
                "mode": "negative_price",
                "request_mode": "negative_price",
                "program": negative.attributes.get("program") or negative.state,
            }
        overnight = self._recommendation("overnight")
        if not self.state.get("auto_mode_enabled"):
            return {"action": "wait", "reason": "automatic_overnight_mode_off"}
        if not self.state.get("door_opened_since_last_cycle"):
            return {"action": "wait", "reason": "door_not_opened_since_last_cycle"}
        if not overnight or overnight.attributes.get("status") != "ready":
            return {"action": "wait", "reason": "overnight_recommendation_not_ready"}
        if not self._recommendation_confident(overnight):
            return {"action": "wait", "reason": "confidence_below_threshold"}
        if not self._overnight_window_unused(now):
            return {"action": "wait", "reason": "automatic_window_already_used"}
        return {
            "action": "queue",
            "mode": "overnight",
            "request_mode": "automatic",
            "program": overnight.attributes.get("program") or overnight.state,
        }

    async def _async_execute(self, request: dict[str, Any]) -> None:
        mode = request.get("mode")
        program = request.get("program")
        reason = self._safety_block(
            mode,
            program,
            explicit_override=bool(request.get("explicit_program_override")),
        )
        if reason:
            self.state["request"] = None
            await self._async_outcome("blocked", mode, program, reason, reason.replace("_", " "))
            return
        start = self._parse_datetime(request.get("start"))
        if start and datetime.now(timezone.utc) > start + timedelta(minutes=30):
            self.state["request"] = None
            await self._async_outcome(
                "expired",
                mode,
                program,
                "stale_request",
                "The queued start time is more than 30 minutes old.",
            )
            return
        self.state["execution_status"] = "commanding"
        self.state["last_attempt"] = datetime.now(timezone.utc).isoformat()
        self._publish()
        program_key = str(program)
        if not program_key.startswith(PROGRAM_PREFIX):
            program_key = f"{PROGRAM_PREFIX}{program_key}"
        select_entity = self.config["bosch_program_select"]
        options = (self.hass.states.get(select_entity).attributes.get("options", [])
                   if self.hass.states.get(select_entity) else [])
        if program_key not in options:
            self.state["request"] = None
            await self._async_outcome(
                "blocked",
                mode,
                program,
                "program_not_selectable",
                f"{program_key} is not available on the Bosch program selector.",
            )
            return
        try:
            await self._async_call(
                "switch",
                "turn_on",
                {"entity_id": self.config["bosch_power_switch"]},
                ignore_error=True,
            )
            await asyncio.sleep(15)
            await self._async_call(
                "select",
                "select_option",
                {"entity_id": select_entity, "option": program_key},
                ignore_error=True,
            )
            await asyncio.sleep(5)
            await self._async_call(
                "button",
                "press",
                {"entity_id": self.config["bosch_start_button"]},
                ignore_error=True,
            )
            await asyncio.sleep(20)
            if not self._is_running():
                await self._async_call(
                    "home_connect_alt",
                    "start_program",
                    {
                        "validate": True,
                        "device_id": self.config["bosch_device_id"],
                        "program_key": program_key,
                    },
                    ignore_error=True,
                )
            await asyncio.sleep(20)
            if not self._is_running():
                await self._async_call(
                    "home_connect",
                    "start_program",
                    {
                        "validate": True,
                        "device_id": self.config["bosch_device_id"],
                        "program_key": program_key,
                    },
                    ignore_error=True,
                )
            await asyncio.sleep(120)
        except (HomeAssistantError, ValueError) as error:
            self.state["request"] = None
            await self._async_outcome(
                "failed",
                mode,
                program,
                "command_error",
                f"Dishwasher start command failed: {error}",
            )
            return
        self.state["request"] = None
        if self._is_running():
            self.state["door_opened_since_last_cycle"] = False
            await self._async_outcome(
                "confirmed",
                mode,
                program,
                "start_confirmed",
                f"Dishwasher program {program} started successfully.",
            )
        else:
            await self._async_outcome(
                "failed",
                mode,
                program,
                "not_running_after_start",
                f"Dishwasher program {program} did not enter a running state.",
            )

    def _safety_block(
        self,
        mode: str | None,
        program: str | None,
        *,
        explicit_override: bool = False,
    ) -> str | None:
        if not program or str(program).lower() in UNKNOWN_STATES:
            return "program_missing"
        if self._is_running():
            return "appliance_already_running"
        checks = {
            "dishwasher_not_connected": self.config.get("bosch_connected_sensor"),
            "remote_control_disabled": self.config.get("bosch_remote_control_sensor"),
            "remote_start_disabled": self.config.get("bosch_remote_start_sensor"),
        }
        for reason, entity_id in checks.items():
            if self._state(entity_id) != STATE_ON:
                return reason
        if self._state(self.config.get("bosch_door_sensor")) in {"on", "open"}:
            return "door_open"
        if mode == "negative_price":
            recommendation = self._recommendation("negative_price")
            if (
                recommendation
                and recommendation.attributes.get(
                    "power_hungry_window_fits_negative_price"
                )
                is not True
            ):
                return "power_hungry_window_outside_negative_price"
        if (
            mode != "negative_price"
            and not (mode == "now" and explicit_override)
            and not self.state.get("door_opened_since_last_cycle")
        ):
            return "door_not_opened_since_last_cycle"
        return None

    async def _async_record_cycle_end(self, capture_started_at: datetime) -> None:
        operation = self._state(self.config.get("bosch_operation_state_sensor"))
        now = datetime.now(timezone.utc)
        learned_finish = self._parse_datetime(self._state("sensor.load_optimizer_1_last_finish"))
        confirmed_start = self._parse_datetime(self.state.get("confirmed_cycle_started_at"))
        observed_run = self.state.pop("capture_had_reported_run", False)
        # A rejected power capture is not proof that the queued wash happened.
        if not (
            observed_run
            or learned_finish and learned_finish >= capture_started_at
            or confirmed_start and confirmed_start >= capture_started_at
        ):
            discarded = self.hass.states.get("sensor.load_optimizer_1_last_discarded_cycle")
            self._record_schedule_event(
                "capture_ignored", "capture_not_confirmed_as_wash",
                capture_started_at=capture_started_at.isoformat(),
                exclusion_reason=discarded.attributes.get("exclusion_reason") if discarded else None,
                pending_request_preserved=self.state.get("request") is not None,
            )
            await self._async_save()
            self._publish()
            return
        self.state.update(
            {
                "request": None,
                "execution_status": "idle",
                "last_result": "completed",
                "last_reason": "cycle_state_returned_to_idle",
                "last_message": (
                    "Cycle completion confirmed by the running-to-idle transition; "
                    f"operation={operation}."
                ),
                "last_cycle_completed_at": now.isoformat(),
                "last_cycle_operation_state": operation,
                "last_outcome_at": now.isoformat(),
                "door_opened_since_last_cycle": False,
            }
        )
        self._record_schedule_event("completed", "cycle_state_returned_to_idle")
        await self._async_save()
        self._publish()

    async def _async_outcome(
        self,
        result: str,
        mode: str | None,
        program: str | None,
        reason: str,
        message: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        self.state.update(
            {
                "execution_status": result,
                "last_result": result,
                "last_reason": reason,
                "last_message": message[:255],
                "last_program": program,
                "last_mode": mode,
                "last_outcome_at": now.isoformat(),
            }
        )
        history = list(self.state.get("run_history") or [])
        history.insert(
            0,
            {
                "timestamp": now.isoformat(),
                "mode": mode,
                "program": program,
                "result": result,
                "reason": reason,
            },
        )
        self.state["run_history"] = history[:10]
        self._record_schedule_event(result, reason, program=program, message=message[:255])
        await self._async_save()
        self._publish()
        if result in {"blocked", "expired", "failed"}:
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "notification_id": "load_optimizer_1_native_start",
                    "title": f"Dishwasher start {result}",
                    "message": message,
                },
                blocking=False,
            )

    async def _async_call(
        self,
        domain: str,
        service: str,
        data: dict[str, Any],
        *,
        ignore_error: bool = False,
    ) -> None:
        try:
            await self.hass.services.async_call(
                domain,
                service,
                data,
                blocking=True,
            )
        except (HomeAssistantError, ValueError):
            if not ignore_error:
                raise
            LOGGER.warning("Optional dishwasher command failed: %s.%s", domain, service)

    def _is_running(self) -> bool:
        return (
            self._state("sensor.load_optimizer_1_cycle_state") == "running"
            or self._state(self.config.get("bosch_operation_state_sensor"))
            == RUNNING_OPERATION
        )

    def _recommendation(self, mode: str):
        return self.hass.states.get(f"sensor.load_optimizer_1_{mode}_recommendation")

    def _recommendation_confident(self, recommendation) -> bool:
        threshold = self._confidence_threshold()
        confidence = float(recommendation.attributes.get("confidence", 0) or 0)
        if confidence >= float(threshold):
            return True
        decision_policy = recommendation.attributes.get("decision_policy") or {}
        selection_factors = decision_policy.get("selection_factors") or []
        return (
            "cooldown_rotation_active" in selection_factors
            and confidence >= min(float(threshold), COOLDOWN_CONFIDENCE_FLOOR)
        )

    def _confidence_threshold(self) -> float:
        threshold_state = self.hass.states.get("sensor.load_optimizer_1_schedule_status")
        value = threshold_state.attributes.get("confidence_threshold") if threshold_state else None
        try:
            threshold = float(value)
        except (TypeError, ValueError):
            return 20.0
        return threshold if 0 <= threshold <= 100 else 20.0

    def _cooldown_elapsed(self, key: str, minutes: int, now: datetime) -> bool:
        previous = self._parse_datetime(self.state.get(key))
        return previous is None or now >= previous + timedelta(minutes=minutes)

    def _overnight_window_unused(self, now: datetime) -> bool:
        previous = self._parse_datetime(self.state.get("last_auto_normal_request"))
        local_now = now.astimezone(ZoneInfo(self.hass.config.time_zone))
        cutoff = local_now.replace(hour=16, minute=0, second=0, microsecond=0)
        if local_now < cutoff:
            cutoff -= timedelta(days=1)
        return (
            previous is None or previous < cutoff.astimezone(timezone.utc)
        ) and self._cooldown_elapsed("last_auto_normal_request", 720, now)

    def _request_due(self, request: dict[str, Any], now: datetime) -> bool:
        start = self._parse_datetime(request.get("start"))
        return start is None or start <= now + timedelta(minutes=1)

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value or str(value).lower() in UNKNOWN_STATES:
            return None
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _state(self, entity_id: str | None) -> str:
        state = self.hass.states.get(entity_id) if entity_id else None
        return state.state if state else "unavailable"

    async def _async_save(self) -> None:
        await self.store.async_save(
            {
                "state": self.state,
                "config": self.config,
                "program_options": self.program_options,
            }
        )

    def _record_schedule_event(self, event: str, reason: str, *, now=None, **detail) -> None:
        item = {"timestamp": (now or datetime.now(timezone.utc)).isoformat(),
                **detail, "event": event, "reason": reason}
        self.state["schedule_events"] = [item, *self.state.get("schedule_events", [])][:20]
        LOGGER.info("Dishwasher scheduling: %s (%s)", event, reason)

    def _publish(self) -> None:
        if self._update_callback:
            self._update_callback(self.status)

    @property
    def status(self) -> dict[str, Any]:
        """Return public native orchestration status."""
        return {
            **self.state,
            "configured": len(self.config) == len(LEGACY_CONFIG_HELPERS),
            "missing_config": sorted(
                key for key in LEGACY_CONFIG_HELPERS if not self.config.get(key)
            ),
            "program_options": self.program_options,
            "legacy_automations_enabled": sorted(
                entity_id
                for entity_id in LEGACY_AUTOMATION_IDS
                if self.hass.states.get(entity_id)
                and self.hass.states.get(entity_id).state == STATE_ON
            ),
            "remote_activation": self.remote_activation_status,
            "overnight_readiness": self.readiness("overnight"),
            "negative_price_readiness": self.readiness("negative_price"),
            "data_freshness": self.data_freshness,
            "automatic_plan_resilience": self.automatic_plan_resilience,
            "automation_explanation": self.automation_explanation,
        }

    @property
    def remote_activation_status(self) -> dict[str, Any]:
        required = {
            "connected": self.config.get("bosch_connected_sensor"),
            "remote_control": self.config.get("bosch_remote_control_sensor"),
            "remote_start": self.config.get("bosch_remote_start_sensor"),
        }
        values = {key: self._state(entity_id) for key, entity_id in required.items()}
        blockers = [key for key, value in values.items() if value != STATE_ON]
        power = self._state(self.config.get("bosch_power_switch"))
        status = "blocked" if blockers else (
            "ready" if power == STATE_ON else "ready_power_on_required"
        )
        return {"state": status, "blockers": blockers, "power": power, **values}

    def readiness(self, mode: str) -> dict[str, Any]:
        recommendation = self._recommendation(mode)
        blockers: list[str] = []
        warnings: list[str] = []
        if self._state("sensor.load_optimizer_1_status") != "ready":
            blockers.append("optimizer_not_ready")
        if recommendation is None or recommendation.attributes.get("status") != "ready":
            blockers.append("recommendation_not_ready")
        elif not self._recommendation_confident(recommendation):
            blockers.append("confidence_below_threshold")
        elif (
            float(recommendation.attributes.get("confidence", 0) or 0)
            < self._confidence_threshold()
        ):
            warnings.append("confidence_relaxed_for_cooldown_rotation")
        blockers.extend(self.remote_activation_status["blockers"])
        if mode == "overnight" and not self.state.get("door_opened_since_last_cycle"):
            blockers.append("door_not_opened_since_last_cycle")
        if (
            mode == "negative_price"
            and recommendation
            and recommendation.attributes.get("reason")
            == "maximum_runs_per_window_reached"
        ):
            blockers.append("maximum_runs_per_window_reached")
        enabled_key = (
            "auto_mode_enabled"
            if mode == "overnight"
            else "auto_negative_price_enabled"
        )
        if not self.state.get(enabled_key):
            warnings.append("automatic_mode_off")
        if self._state("sensor.load_optimizer_1_cycle_state") != "idle":
            warnings.append("appliance_not_idle")
        if self.state.get("request"):
            warnings.append("request_already_pending")
        elif mode == "overnight" and self.state.get("auto_mode_enabled") and not self._overnight_window_unused(datetime.now(timezone.utc)):
            warnings.append("automatic_window_already_used")
        if self._state(self.config.get("bosch_door_sensor")) in {"on", "open"}:
            warnings.append("door_currently_open")
        if (
            mode == "negative_price"
            and recommendation
            and recommendation.attributes.get("ready_to_start") is not True
        ):
            warnings.append("negative_window_not_started")
        status = "red" if blockers else ("amber" if warnings else "green")
        return {
            "state": status,
            "blockers": sorted(set(blockers)),
            "warnings": sorted(set(warnings)),
            "program": recommendation.attributes.get("program") if recommendation else None,
            "start": recommendation.attributes.get("start") if recommendation else None,
            "confidence": recommendation.attributes.get("confidence") if recommendation else None,
        }

    @property
    def automation_explanation(self) -> dict[str, Any]:
        """Explain the actual queue separately from a possible recommendation."""
        now = datetime.now(timezone.utc)
        request = self.state.get("request") or {}
        decision = self._automatic_decision(now)
        reason = decision.get("reason", "automatic_request_available")
        messages = {
            "automatic_overnight_mode_off": "Automatic overnight mode is off.",
            "door_not_opened_since_last_cycle": "Waiting for the dishwasher to be loaded: the door has not opened since the last wash.",
            "overnight_recommendation_not_ready": "Waiting for a fully priced, eligible overnight programme.",
            "confidence_below_threshold": "The overnight programme's learning confidence is below the allowed threshold.",
            "automatic_window_already_used": "No wash is queued. A previous automatic request has already reserved this overnight window.",
            "appliance_not_idle": "A cycle capture is active; no new automatic request will be created.",
            "automatic_request_available": "An automatic recommendation is available; a saved request has not yet been created.",
        }
        state = "waiting"
        summary = messages.get(reason, "Waiting for the next scheduling evaluation.")
        action_required = None
        if not self.state.get("active"):
            state, reason = "inactive", "native_orchestration_inactive"
            summary = "Native automatic control is inactive; recommendations will not start the dishwasher."
        elif request:
            state, reason = "scheduled", "request_queued"
            summary = f"{request.get('program', 'Programme')} is queued for a start-time safety check."
            if self._request_due(request, now):
                state = "starting"
                summary = "The queued start is due; check the execution result for confirmation."
        elif reason == "automatic_window_already_used":
            state = "attention_required"
            action_required = "Review the last request and result. Request a new overnight run explicitly if a wash is still needed."
        elif reason == "automatic_overnight_mode_off":
            state = "paused"
        readiness = self.readiness("overnight")
        recommendation = self._recommendation("overnight")
        attributes = recommendation.attributes if recommendation else {}
        previous = self._parse_datetime(self.state.get("last_auto_normal_request"))
        eligible_after = None
        if previous and not self._overnight_window_unused(now):
            local_now = now.astimezone(ZoneInfo(self.hass.config.time_zone))
            cutoff = local_now.replace(hour=16, minute=0, second=0, microsecond=0)
            if local_now >= cutoff:
                cutoff += timedelta(days=1)
            eligible_after = max(cutoff.astimezone(timezone.utc), previous + timedelta(hours=12)).isoformat()
        return {
            "state": state, "reason_code": reason, "summary": summary,
            "action_required": action_required,
            "queued_program": request.get("program"), "queued_start": request.get("start"),
            "queued_finish": request.get("finish"),
            "recommended_program": attributes.get("program"),
            "recommended_start": attributes.get("start"),
            "confidence": attributes.get("confidence"),
            "confidence_threshold": self._confidence_threshold(),
            "blockers": readiness["blockers"], "warnings": readiness["warnings"],
            "automatic_eligible_after": eligible_after,
            "last_automatic_request": self.state.get("last_auto_normal_request"),
            "last_start_attempt": self.state.get("last_attempt"),
            "last_result": self.state.get("last_result"),
            "last_result_message": self.state.get("last_message"),
            "last_result_at": self.state.get("last_outcome_at") or self.state.get("last_cycle_completed_at"),
            "recent_events": self.state.get("schedule_events", []),
            "timezone": self.hass.config.time_zone,
        }

    @property
    def data_freshness(self) -> dict[str, Any]:
        runtime = self.hass.states.get("sensor.load_optimizer_status")
        completed = runtime.attributes.get("last_scan_completed") if runtime else None
        parsed = self._parse_datetime(completed)
        age = (
            (datetime.now(timezone.utc) - parsed).total_seconds() / 60
            if parsed
            else None
        )
        return {
            "state": "unknown" if age is None else ("stale" if age > 7 else "fresh"),
            "last_scan_completed": completed,
            "age_minutes": round(age, 1) if age is not None else None,
            "stale_after_minutes": 7,
        }

    @property
    def automatic_plan_resilience(self) -> dict[str, Any]:
        request = self.state.get("request") or {}
        if request.get("mode") != "automatic":
            status = "idle"
        elif self.data_freshness["state"] != "fresh":
            status = "protected_attention_required"
        elif self._request_due(request, datetime.now(timezone.utc)):
            status = "executing_or_verifying"
        else:
            status = "protected"
        return {
            "state": status,
            "plan_mode": request.get("mode", "none"),
            "planned_start": request.get("start"),
            "planned_finish": request.get("finish"),
            "optimizer_freshness": self.data_freshness["state"],
        }

    def legacy_state(self, entity_id: str) -> dict[str, Any] | None:
        """Expose native controls through old helper IDs during transition."""
        request = self.state.get("request") or {}
        program = self.state.get("last_program")
        program_key = (
            f"{PROGRAM_PREFIX}{program}"
            if program and not str(program).startswith(PROGRAM_PREFIX)
            else program
        )
        mapping = {
            "input_boolean.load_optimizer_1_auto_mode_enabled": (
                "on" if self.state.get("auto_mode_enabled") else "off"
            ),
            "input_boolean.load_optimizer_1_auto_negative_price_enabled": (
                "on" if self.state.get("auto_negative_price_enabled") else "off"
            ),
            "input_boolean.load_optimizer_1_door_opened_since_last_cycle": (
                "on" if self.state.get("door_opened_since_last_cycle") else "off"
            ),
            "input_boolean.load_optimizer_special_price_window_enabled": (
                "on" if self.state.get("special_price_window_enabled") else "off"
            ),
            "input_datetime.load_optimizer_special_price_window_start": self.state.get(
                "special_price_window_start"
            ),
            "input_datetime.load_optimizer_special_price_window_end": self.state.get(
                "special_price_window_end"
            ),
            "input_number.load_optimizer_special_price_window_price": self.state.get(
                "special_price_window_price"
            ),
            "input_text.load_optimizer_special_price_window_label": self.state.get(
                "special_price_window_label"
            ),
            "input_select.load_optimizer_1_override_program": self.state.get(
                "override_program"
            ),
            "input_select.load_optimizer_1_requested_mode": request.get("mode", "none"),
            "input_boolean.load_optimizer_1_explicit_program_override": (
                "on" if request.get("explicit_program_override") else "off"
            ),
            "input_text.load_optimizer_1_requested_program": request.get(
                "program", "none"
            ),
            "input_datetime.load_optimizer_1_requested_start": request.get("start"),
            "input_datetime.load_optimizer_1_requested_finish": request.get("finish"),
            "input_text.load_optimizer_1_scheduler_message": self.state.get(
                "last_message"
            ),
            "input_text.load_optimizer_1_start_attempt_status": self.state.get(
                "execution_status"
            ),
            "input_text.load_optimizer_1_start_attempt_message": self.state.get(
                "last_message"
            ),
            "input_text.load_optimizer_1_last_start_result": self.state.get(
                "last_result"
            ),
            "input_text.load_optimizer_1_last_start_failure_reason": self.state.get(
                "last_reason"
            ),
            "input_text.load_optimizer_1_last_start_reason_code": self.state.get(
                "last_reason"
            ),
            "input_text.load_optimizer_1_last_start_reason_detail": self.state.get(
                "last_message"
            ),
            "input_text.load_optimizer_1_last_start_program": program,
            "input_datetime.load_optimizer_1_last_start_attempt": self.state.get(
                "last_attempt"
            ),
            "input_text.load_optimizer_1_last_start_mode": self.state.get("last_mode"),
            "input_text.load_optimizer_1_last_start_program_key": program_key,
            "input_text.load_optimizer_1_last_start_selected_program": self._state(
                self.config.get("bosch_selected_program_sensor")
            ),
            "input_text.load_optimizer_1_last_start_operation_state": self._state(
                self.config.get("bosch_operation_state_sensor")
            ),
            "input_text.load_optimizer_1_last_start_readiness": self.remote_activation_status[
                "state"
            ],
            "input_text.load_optimizer_1_last_execution_event": self.state.get(
                "last_message"
            ),
            "input_text.load_optimizer_1_last_start_decision_snapshot": str(
                self.state.get("shadow_decision") or {}
            )[:255],
            "input_text.load_optimizer_1_remote_start_blocked_programs": "",
        }
        mapping.update(
            {
                entity_id: self.config.get(key)
                for key, entity_id in LEGACY_CONFIG_HELPERS.items()
            }
        )
        if entity_id not in mapping:
            return None
        return {"state": mapping[entity_id], "attributes": {}}
