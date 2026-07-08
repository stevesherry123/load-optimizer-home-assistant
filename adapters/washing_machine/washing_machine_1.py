POWER_SENSOR = "sensor.washing_machine_current_consumption"
ENERGY_SENSOR = "sensor.washing_machine_today_s_consumption"


def classify_program(runtime_minutes, energy_used, peak_power):
    if runtime_minutes <= 30 and energy_used < 0.20:
        return "Spin"
    if peak_power >= 1500 or energy_used >= 0.50 or runtime_minutes >= 60:
        return "Wash"
    return "Unknown"


def is_running():
    try:
        power = float(state.get(POWER_SENSOR) or 0)
    except Exception:
        power = 0
    return power > 10


def current_power():
    try:
        return float(state.get(POWER_SENSOR) or 0)
    except Exception:
        return 0.0


def current_energy():
    try:
        return float(state.get(ENERGY_SENSOR) or 0)
    except Exception:
        return 0.0

