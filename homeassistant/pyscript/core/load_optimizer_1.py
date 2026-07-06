from datetime import datetime
from adapters.dishwasher_1 import (
    current_energy as adapter_current_energy,
    current_power as adapter_current_power,
    current_program as adapter_current_program,
    is_delayed_start as adapter_is_delayed_start,
    is_running as adapter_is_running,
)


PREFIX = "load_optimizer_1"

ACTIVE = f"input_boolean.{PREFIX}_learning_active"
PROGRAM = f"input_text.{PREFIX}_cycle_program"
PROFILE = f"input_text.{PREFIX}_cycle_profile"
DATABASE = f"input_text.{PREFIX}_learning_database"
SUMMARY = f"input_text.{PREFIX}_learning_summary"
LAST_PROGRAM = f"input_text.{PREFIX}_last_program"
STATE = f"input_text.{PREFIX}_cycle_state"

CYCLE_SAMPLE_COUNT = f"input_number.{PREFIX}_cycle_sample_count"
CYCLE_START_ENERGY = f"input_number.{PREFIX}_cycle_start_energy"
PEAK_POWER = f"input_number.{PREFIX}_peak_power"
LAST_RUNTIME = f"input_number.{PREFIX}_last_runtime_minutes"
LAST_ENERGY = f"input_number.{PREFIX}_last_energy_kwh"
EXPECTED_RUNTIME = f"input_number.{PREFIX}_expected_runtime"
EXPECTED_ENERGY = f"input_number.{PREFIX}_expected_energy"

CYCLE_START = f"input_datetime.{PREFIX}_cycle_start"
LAST_FINISH = f"input_datetime.{PREFIX}_last_finish"


def _state(entity_id, default=None):
    value = state.get(entity_id)
    if value in (None, "", "unknown", "unavailable"):
        return default
    return value


def _float(entity_id, default=0.0):
    try:
        return float(state.get(entity_id))
    except Exception:
        return default


def _set_text(entity_id, value):
    service.call(
        "input_text",
        "set_value",
        entity_id=entity_id,
        value=str(value)[:255],
    )


def _set_number(entity_id, value):
    service.call(
        "input_number",
        "set_value",
        entity_id=entity_id,
        value=value,
    )


def _set_boolean(entity_id, value):
    service.call(
        "input_boolean",
        "turn_on" if value else "turn_off",
        entity_id=entity_id,
    )


def _set_datetime(entity_id, value):
    service.call(
        "input_datetime",
        "set_datetime",
        entity_id=entity_id,
        datetime=value.strftime("%Y-%m-%d %H:%M:%S"),
    )


def _append_profile_sample(sample):
    current = _state(PROFILE, "")
    updated = sample if not current else f"{current};{sample}"
    _set_text(PROFILE, updated)


def _parse_datetime(entity_id):
    value = _state(entity_id)
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _load_database():
    raw = _state(DATABASE, "")
    if not raw:
        return {}

    results = {}
    for item in raw.split(";"):
        parts = item.split("|")
        if len(parts) != 4:
            continue
        try:
            results[parts[0]] = {
                "runs": int(parts[1]),
                "runtime": float(parts[2]),
                "energy": float(parts[3]),
            }
        except Exception:
            continue
    return results


def _save_database(entries):
    output = []
    for program, stats in entries.items():
        output.append(
            program
            + "|"
            + str(stats["runs"])
            + "|"
            + str(round(stats["runtime"], 1))
            + "|"
            + str(round(stats["energy"], 3))
        )
    _set_text(DATABASE, ";".join(output))


def _update_expected_values(program):
    database = _load_database()
    stats = database.get(program)
    if not stats:
        return
    _set_number(EXPECTED_RUNTIME, stats["runtime"])
    _set_number(EXPECTED_ENERGY, stats["energy"])


@service
def load_optimizer_1_start_cycle(program=None):
    now = datetime.now()
    selected_program = program or adapter_current_program(state)
    _set_boolean(ACTIVE, True)
    _set_text(STATE, "RUNNING")
    _set_text(PROGRAM, selected_program)
    _set_text(PROFILE, "")
    _set_text(LAST_PROGRAM, selected_program)
    _set_datetime(CYCLE_START, now)
    _set_number(CYCLE_START_ENERGY, adapter_current_energy(state))
    _set_number(PEAK_POWER, 0)
    _set_number(CYCLE_SAMPLE_COUNT, 0)


@service
def load_optimizer_1_capture_sample(power=None):
    if not is_state(ACTIVE, "on"):
        return
    value = power if power is not None else adapter_current_power(state)
    _append_profile_sample(round(value))
    _set_number(CYCLE_SAMPLE_COUNT, _float(CYCLE_SAMPLE_COUNT, 0) + 1)
    if value > _float(PEAK_POWER, 0):
        _set_number(PEAK_POWER, value)


@service
def load_optimizer_1_finish_cycle():
    now = datetime.now()
    start = _parse_datetime(CYCLE_START)
    program = _state(PROGRAM, "Unknown")
    runtime_minutes = 0
    if start is not None:
        runtime_minutes = int((now - start).total_seconds() / 60)

    energy_used = max(0.0, adapter_current_energy(state) - _float(CYCLE_START_ENERGY, 0))

    database = _load_database()
    current = database.get(program)
    if current:
        runs = current["runs"] + 1
        avg_runtime = ((current["runtime"] * current["runs"]) + runtime_minutes) / runs
        avg_energy = ((current["energy"] * current["runs"]) + energy_used) / runs
    else:
        runs = 1
        avg_runtime = runtime_minutes
        avg_energy = energy_used

    database[program] = {
        "runs": runs,
        "runtime": avg_runtime,
        "energy": avg_energy,
    }
    _save_database(database)
    _set_text(
        SUMMARY,
        program
        + ": "
        + str(runs)
        + " runs, "
        + str(round(avg_runtime))
        + " min avg, "
        + str(round(avg_energy, 3))
        + " kWh avg",
    )
    _set_text(LAST_PROGRAM, program)
    _set_number(LAST_RUNTIME, runtime_minutes)
    _set_number(LAST_ENERGY, round(energy_used, 3))
    _update_expected_values(program)
    _set_boolean(ACTIVE, False)
    _set_text(STATE, "IDLE")
    _set_datetime(LAST_FINISH, now)


@service
def load_optimizer_1_check():
    running = adapter_is_running(state)
    active = is_state(ACTIVE, "on")

    if running and not active:
        load_optimizer_1_start_cycle()
        load_optimizer_1_capture_sample()
        return

    if running and active:
        load_optimizer_1_capture_sample()
        return

    if active and not running and not adapter_is_delayed_start(state):
        load_optimizer_1_finish_cycle()
        return

    if adapter_is_delayed_start(state):
        _set_text(STATE, "DELAYED_START")
    else:
        _set_text(STATE, "IDLE")


@time_trigger("startup")
def load_optimizer_1_startup():
    if adapter_is_running(state):
        if not is_state(ACTIVE, "on"):
            load_optimizer_1_start_cycle()
        _set_text(STATE, "RUNNING")
    elif adapter_is_delayed_start(state):
        _set_text(STATE, "DELAYED_START")
    else:
        _set_text(STATE, "IDLE")


@time_trigger("cron(*/5 * * * *)")
def load_optimizer_1_scheduled_check():
    load_optimizer_1_check()
