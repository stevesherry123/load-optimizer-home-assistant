"""Charger-independent command lifecycle; deliberately not connected to services.

The future adapter must persist the session before dispatching a returned command,
report dispatch failures, and supply fresh physical charging telemetry. A service
call returning successfully is not charging confirmation.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4


class EVControlSession:
    """Reserve one command at a time and require observation before proceeding."""

    def __init__(self, *, confirmation_seconds: int = 60) -> None:
        if isinstance(confirmation_seconds, bool) or not isinstance(confirmation_seconds, int) or not 1 <= confirmation_seconds <= 600:
            raise ValueError("Confirmation timeout must be between 1 and 600 seconds")
        self.confirmation_seconds = confirmation_seconds
        self.phase = "idle"
        self.owned = False
        self.pending = None
        self.requires_review = False
        self.reason = "control_disabled"

    def checkpoint(self) -> dict:
        """Return JSON-safe evidence for persistence before command dispatch."""
        return {
            "phase": self.phase, "owned": self.owned, "reason": self.reason,
            "requires_review": self.requires_review,
            "pending": {**self.pending, "issued": self.pending["issued"].isoformat(),
                        "deadline": self.pending["deadline"].isoformat()}
            if self.pending else None,
        }

    @classmethod
    def restored(cls, checkpoint: dict) -> "EVControlSession":
        """Quarantine restored authority; never replay a saved command."""
        session = cls()
        # Even an apparently idle checkpoint needs fresh reconciliation. The
        # process could have stopped between persistence and service dispatch.
        session.owned = checkpoint.get("owned") is True
        session.phase = "blocked"
        session.reason = "restart_requires_reconciliation"
        return session

    def reconcile_stopped(self, *, charging: bool | None, telemetry_fresh: bool) -> bool:
        """Explicitly clear ambiguity only after a fresh stopped observation."""
        if not telemetry_fresh or charging is not False:
            return False
        self.phase, self.owned, self.pending = "idle", False, None
        self.requires_review = False
        self.reason = "reconciled_stopped"
        return True

    def dispatch_failed(self, command_id: str) -> None:
        """A failed call may still have reached hardware; never retry blindly."""
        if self.pending and self.pending["id"] == command_id:
            self.phase = "blocked"
            self.reason = "command_result_uncertain"

    def stop_enabled_power(self, now: datetime, *, require_review: bool = False) -> dict | None:
        """Stop owned, observed enabled power without waiting for car delivery.

        The switch adapter must verify its own switch is freshly on and demand
        has ended. This can supersede an unconfirmed start once dispatch has
        returned. It never supersedes a stop or an ambiguous failed command.
        """
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Control time must be timezone-aware")
        if not self.owned or self.phase == "blocked" or self.pending and self.pending["action"] == "stop":
            return None
        self.requires_review = self.requires_review or require_review
        return self._reserve("stop", now.astimezone(timezone.utc))

    def evaluate(
        self, *, now: datetime, enabled: bool, desired: bool,
        connected: bool | None, charging: bool | None, telemetry_fresh: bool,
        observed_at: datetime | None,
    ) -> dict | None:
        """Return one reserved command, or wait; never operate hardware here.

        desired must come from a freshly revalidated active plan interval, target,
        and prices. enabled is separate explicit control permission. charging is
        actual observed charging, not merely a switch's requested state.
        """
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Control time must be timezone-aware")
        now = now.astimezone(timezone.utc)
        if observed_at is not None and observed_at.tzinfo is not None and observed_at.utcoffset() is not None:
            observed_at = observed_at.astimezone(timezone.utc)
        telemetry_fresh = bool(telemetry_fresh and observed_at is not None
                               and observed_at.tzinfo is not None
                               and observed_at.utcoffset() is not None
                               and timedelta(0) <= now - observed_at <= timedelta(seconds=60))
        if self.phase == "blocked":
            return None
        if self.pending:
            if now >= self.pending["deadline"]:
                self.phase, self.reason = "blocked", "confirmation_timeout"
                return None
            expected = self.pending["action"] == "start"
            if not telemetry_fresh or observed_at <= self.pending["issued"] or charging is not expected:
                self.reason = "awaiting_confirmation"
                return None
            self.pending = None
            self.phase = "charging" if expected else "idle"
            self.owned = expected
            if not expected and self.requires_review:
                self.phase, self.reason = "blocked", "delivery_requires_review"
                return None
        if not telemetry_fresh or type(charging) is not bool:
            self.reason = "charging_state_unavailable"
            return None
        if self.owned:
            if charging is False:
                # A car/user/charger stopped independently. Do not fight it.
                self.phase, self.reason = "blocked", "charging_stopped_externally"
                return None
            if enabled is not True or desired is not True or connected is not True:
                return self._reserve("stop", now)
            self.reason = "following_plan"
            return None
        if charging is True:
            self.reason = "external_charging_not_owned"
            return None
        if enabled is not True:
            self.reason = "control_disabled"
        elif connected is not True:
            self.reason = "connection_not_verified"
        elif desired is not True:
            self.reason = "outside_active_plan"
        else:
            # Ownership is reserved before sending, including ambiguous starts.
            self.owned = True
            return self._reserve("start", now)
        return None

    def _reserve(self, action: str, now: datetime) -> dict:
        self.pending = {
            "id": uuid4().hex, "action": action, "issued": now,
            "deadline": now + timedelta(seconds=self.confirmation_seconds),
        }
        self.phase = "starting" if action == "start" else "stopping"
        self.reason = "awaiting_confirmation"
        return {"id": self.pending["id"], "action": action}
