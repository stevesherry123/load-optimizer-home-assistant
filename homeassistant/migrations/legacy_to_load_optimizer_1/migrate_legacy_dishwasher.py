MAPPING = {
    "input_boolean.dishwasher_learning_active": "input_boolean.load_optimizer_1_learning_active",
    "input_text.dishwasher_cycle_program": "input_text.load_optimizer_1_cycle_program",
    "input_text.dishwasher_cycle_profile": "input_text.load_optimizer_1_cycle_profile",
    "input_number.dishwasher_cycle_sample_count": "input_number.load_optimizer_1_cycle_sample_count",
    "input_datetime.dishwasher_cycle_start": "input_datetime.load_optimizer_1_cycle_start",
    "input_number.dishwasher_cycle_start_energy": "input_number.load_optimizer_1_cycle_start_energy",
    "input_number.dishwasher_peak_power": "input_number.load_optimizer_1_peak_power",
    "input_text.dishwasher_last_program": "input_text.load_optimizer_1_last_program",
    "input_number.dishwasher_last_runtime_minutes": "input_number.load_optimizer_1_last_runtime_minutes",
    "input_number.dishwasher_last_energy_kwh": "input_number.load_optimizer_1_last_energy_kwh",
    "input_datetime.dishwasher_last_finish": "input_datetime.load_optimizer_1_last_finish",
    "input_text.dishwasher_learning_database": "input_text.load_optimizer_1_learning_database",
    "input_text.dishwasher_learning_summary": "input_text.load_optimizer_1_learning_summary",
    "input_number.dishwasher_expected_runtime": "input_number.load_optimizer_1_expected_runtime",
    "input_number.dishwasher_expected_energy": "input_number.load_optimizer_1_expected_energy",
}


def _copy_state(source, target):
    value = state.get(source)
    if value in (None, "", "unknown", "unavailable"):
        return

    if target.startswith("input_text."):
        service.call("input_text", "set_value", entity_id=target, value=str(value)[:255])
    elif target.startswith("input_number."):
        try:
            service.call("input_number", "set_value", entity_id=target, value=float(value))
        except Exception:
            return
    elif target.startswith("input_boolean."):
        service.call("input_boolean", "turn_on" if value == "on" else "turn_off", entity_id=target)
    elif target.startswith("input_datetime."):
        service.call("input_datetime", "set_datetime", entity_id=target, datetime=str(value))


@service
def migrate_legacy_dishwasher_to_load_optimizer_1():
    for source, target in MAPPING.items():
        _copy_state(source, target)

