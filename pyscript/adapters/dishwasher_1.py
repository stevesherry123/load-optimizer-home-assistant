ACTIVE_PROGRAM = "sensor.replace_with_active_program"
SELECTED_PROGRAM = "sensor.replace_with_selected_program"
OPERATION_STATE = "sensor.replace_with_operation_state"
POWER_SENSOR = "sensor.replace_with_power"
ENERGY_SENSOR = "sensor.replace_with_energy"


def normalise_program(raw):
    if raw in (None, "", "unknown", "unavailable"):
        return "Unknown"
    raw = str(raw)
    raw = raw.replace("Dishcare.Dishwasher.Program.", "")
    if raw == "Express 60°C":
        return "Express60C"
    return raw


def current_program(state):
    active = normalise_program(state.get(ACTIVE_PROGRAM))
    if active != "Unknown":
        return active
    return normalise_program(state.get(SELECTED_PROGRAM))


def is_running(state):
    value = state.get(OPERATION_STATE) or ""
    return ".Run" in value


def is_delayed_start(state):
    value = state.get(OPERATION_STATE) or ""
    return ".DelayedStart" in value


def current_power(state):
    try:
        return float(state.get(POWER_SENSOR) or 0)
    except Exception:
        return 0.0


def current_energy(state):
    try:
        return float(state.get(ENERGY_SENSOR) or 0)
    except Exception:
        return 0.0
