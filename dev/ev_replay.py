"""Generate a read-only review of actual EV decisions using synthetic I/O only."""

import argparse
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "custom_components/load_optimizer"))
from test_ev_control import EVControlTests, Clock
from optimizer.ev_charging import plan_ev_charge
from optimizer.ev_review import review_snapshot


async def scenario(kind="normal"):
    case = EVControlTests()
    case.setUp()
    try:
        start = datetime(2026, 10, 19, 8, tzinfo=timezone.utc)
        Clock.current = start
        case.config.update(target_percent=70, charge_power_kw=5, tariff_timezone="Europe/London")
        case.put("sensor.battery", "20", "%")
        case.put("sensor.power", "0", "W")
        case.put("sensor.charging", "idle")
        controller = case.controller
        prices = [{"start": start + timedelta(minutes=i * 30), "end": start + timedelta(minutes=(i + 1) * 30),
                   "price_p_per_kwh": -15 if i % 2 else -2} for i in range(24)]
        frames = []
        enabled = False
        delivered = 0.0
        previous = start
        minutes = sorted(set([0] + [30 * i for i in range(1, 25)] + [30 * i + 3 for i in range(1, 24, 2)]))
        if kind != "normal":
            minutes = [0, 30, 33, 34]
        for minute in minutes:
            Clock.current = start + timedelta(minutes=minute)
            was_on = case.values["switch.charger"].state == "on"
            if was_on and kind not in {"energy_stall", "no_charge"}:
                delivered += 5 * (Clock.current - previous).total_seconds() / 3600
            previous = Clock.current
            case.put("sensor.energy", str(100 + delivered), "kWh")
            case.put("sensor.battery", str(20 + delivered / 60 * 100), "%")
            case.put("sensor.power", "5000" if was_on else "0", "W")
            case.put("sensor.charging", "charging" if was_on else "idle")
            if minute >= 33 and kind == "disconnect":
                case.put("sensor.connection", "disconnected")
            if minute >= 33 and kind == "no_charge":
                case.put("sensor.power", "0", "W")
                case.put("sensor.charging", "idle")
            for state in case.values.values():
                state.last_reported = Clock.current
            plan = plan_ev_charge(periods=prices, battery_percent=float(case.values["sensor.battery"].state),
                battery_capacity_kwh=60, target_percent=70, charge_power_kw=5, charger_efficiency=1,
                connected=case.values["sensor.connection"].state == "connected", reference_utc=Clock.current)
            generated = Clock.current - timedelta(seconds=91) if kind == "stale_plan" and minute >= 33 else Clock.current
            controller.set_plan(plan, generated)
            if not enabled:
                await controller.async_enable()
                enabled = True
            else:
                await controller.async_tick()
            await controller.async_tick()
            plug_on = case.values["switch.charger"].state == "on"
            case.put("sensor.power", "5000" if plug_on and kind != "no_charge" else "0", "W")
            case.put("sensor.charging", "charging" if plug_on and kind != "no_charge" else "idle")
            states = {key: {"state": value.state, "attributes": value.attributes,
                      "last_reported": value.last_reported.isoformat()} for key, value in case.values.items()}
            snapshot = review_snapshot(case.config, plan, prices, states, controller.status, Clock.current)
            commands = [{"service": call.args[1], "entity_id": call.args[2]["entity_id"]}
                        for call in case.hass.services.async_call.call_args_list]
            assert all(command["entity_id"] == "switch.charger" for command in commands)
            frames.append(deepcopy({"time": Clock.current.isoformat(), "snapshot": snapshot,
                "commands": commands, "simulated_delivered_kwh": round(delivered, 4)}))
        return {"id": kind, "frames": frames}
    finally:
        case.doCleanups()


async def all_scenarios():
    result = {"simulation": True, "physical_services_possible": False,
              "scenarios": [await scenario(kind) for kind in ("normal", "no_charge", "energy_stall", "disconnect", "stale_plan")]}
    normal = result["scenarios"][0]["frames"]
    assert normal[0]["snapshot"]["selected_slot_count"] == 12
    assert normal[0]["snapshot"]["planned_charging_minutes"] == 360
    assert abs(normal[-1]["simulated_delivered_kwh"] - 30) < 0.001
    assert normal[-1]["snapshot"]["charger_state"] == "off"
    for replay in result["scenarios"][1:]:
        assert replay["frames"][-1]["snapshot"]["charger_state"] == "off"
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    data = asyncio.run(all_scenarios())
    template = (ROOT / "dev/ev-review.html").read_text()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(template.replace("__SIMULATION_DATA__", json.dumps(data).replace("</", "<\\/")))
    if args.json_output:
        args.json_output.write_text(json.dumps(data))
    print(f"Generated {len(data['scenarios'])} hardware-free scenarios: {args.output}")
