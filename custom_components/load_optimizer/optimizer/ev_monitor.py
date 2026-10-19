"""Compare metered wall energy with observed battery gain, without health claims."""

from __future__ import annotations

import math


def measurement(state, quantity):
    """Normalise explicit W/kW and Wh/kWh units; never guess a unit."""
    if not state:
        return None
    try:
        value = float(state.state)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    unit = state.attributes.get("unit_of_measurement")
    factors = {"power": {"W": 1, "kW": 1000}, "energy": {"Wh": 0.001, "kWh": 1}}
    return value * factors[quantity][unit] if unit in factors[quantity] else None


class EVDeliveryMonitor:
    """One controlled session; cumulative energy is required for delivery checks."""

    def __init__(self):
        self.started_at = None
        self.battery_start = None
        self.energy_start = None
        self.result = {"status": "not_started"}

    def start(self, now, battery, energy):
        self.started_at, self.battery_start, self.energy_start = now, battery, energy

    def update(self, now, *, battery, capacity, efficiency, power, energy, charging_status,
               minimum_power=100, confirmation_seconds=120, tolerance_percent=30):
        if self.started_at is None:
            return None
        if any(value is None or not math.isfinite(value) for value in (battery, capacity, efficiency, power, energy)):
            self.result = {"status": "telemetry_unavailable"}
            return "delivery_telemetry_unavailable"
        if capacity <= 0 or not 0 < efficiency <= 1:
            self.result = {"status": "invalid_inputs"}
            return "delivery_inputs_invalid"
        delivered = energy - self.energy_start
        if delivered < 0:
            self.result = {"status": "energy_meter_reset"}
            return "energy_meter_reset"
        expected_gain = delivered * efficiency / capacity * 100
        actual_gain = battery - self.battery_start
        self.result = {"status": "confirming", "delivered_wall_kwh": round(delivered, 4),
                       "expected_battery_gain_percent": round(expected_gain, 3),
                       "observed_battery_gain_percent": round(actual_gain, 3),
                       "power_w": round(power, 1)}
        if (now - self.started_at).total_seconds() < confirmation_seconds:
            return None
        if power < minimum_power or charging_status != "charging":
            self.result["status"] = "charging_not_confirmed"
            return "charging_not_confirmed"
        if delivered < 0.001:
            self.result["status"] = "energy_not_increasing"
            return "charging_energy_not_increasing"
        # SOC is coarse and cloud-delayed; allow at least five percentage points.
        if expected_gain - actual_gain > max(5, expected_gain * tolerance_percent / 100):
            self.result["status"] = "battery_gain_below_expected"
            return "battery_gain_below_expected"
        self.result["status"] = "charging_confirmed"
        return None
