"""Constants for the Load Optimizer integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "load_optimizer"
MANUFACTURER = "Load Optimizer"
DEFAULT_NAME = "Load Optimizer"
DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)
DEFAULT_LEGACY_SCAN_INTERVAL = timedelta(seconds=60)

CONF_TARIFF_ENTITY = "tariff_entity"
CONF_TARIFF_TIMEZONE = "tariff_timezone"
CONF_TARIFF_PRICE_UNIT = "tariff_price_unit"
CONF_LOAD_TYPE = "load_type"
CONF_BATTERY_ENTITY = "battery_entity"
CONF_BATTERY_CAPACITY_ENTITY = "battery_capacity_entity"
CONF_TARGET_PERCENT_ENTITY = "target_percent_entity"
CONF_CONNECTION_STATUS_ENTITY = "connection_status_entity"
CONF_CHARGE_POWER_KW = "charge_power_kw"
CONF_CHARGER_EFFICIENCY = "charger_efficiency"
CONF_TARGET_PERCENT = "target_percent"
CONF_SLOT_MINUTES = "slot_minutes"
CONF_READY_BY = "ready_by"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_INSTANCES_YAML = "instances_yaml"
CONF_TARIFF_ENTITIES = "tariff_entities"
CONF_GREEN_WINDOW_ENTITY = "green_window_entity"
CONF_BLOCKED_WINDOW_ENTITY = "blocked_window_entity"
CONF_COST_SEARCH_HOURS = "cost_search_hours"
CONF_COST_FORECAST_HOURS = "cost_forecast_hours"
CONF_COST_FORECAST_INTERVAL = "cost_forecast_interval"
CONF_COST_CANDIDATE_INTERVAL = "cost_candidate_interval"
CONF_SCHEDULE_PREFERENCE_WEIGHT_PENCE = "schedule_preference_weight_pence"
CONF_PUBLISH_DIAGNOSTICS = "publish_diagnostics"
CONF_PUBLISH_PROFILE_DATA = "publish_profile_data"
CONF_PUBLISH_COST_FORECAST = "publish_cost_forecast"
CONF_PRICE_CAP_REGION = "price_cap_region"
CONF_PRICE_CAP_PAYMENT_METHOD = "price_cap_payment_method"
CONF_BOSCH_DEVICE_ID = "bosch_device_id"
CONF_BOSCH_POWER_SWITCH = "bosch_power_switch"
CONF_BOSCH_PROGRAM_SELECT = "bosch_program_select"
CONF_BOSCH_START_BUTTON = "bosch_start_button"
CONF_BOSCH_SELECTED_PROGRAM_SENSOR = "bosch_selected_program_sensor"
CONF_BOSCH_POWER_STATE_SENSOR = "bosch_power_state_sensor"
CONF_BOSCH_CONNECTED_SENSOR = "bosch_connected_sensor"
CONF_BOSCH_DOOR_SENSOR = "bosch_door_sensor"
CONF_BOSCH_REMOTE_CONTROL_SENSOR = "bosch_remote_control_sensor"
CONF_BOSCH_REMOTE_START_SENSOR = "bosch_remote_start_sensor"
CONF_BOSCH_OPERATION_STATE_SENSOR = "bosch_operation_state_sensor"

LOAD_TYPE_EV = "ev_charging"
LOAD_TYPE_LEARNED_APPLIANCE = "learned_appliance"
LOAD_TYPES = [LOAD_TYPE_EV, LOAD_TYPE_LEARNED_APPLIANCE]

PRICE_UNIT_PENCE = "p_per_kwh"
PRICE_UNIT_GBP = "gbp_per_kwh"
PRICE_UNITS = [PRICE_UNIT_PENCE, PRICE_UNIT_GBP]

PRICE_CAP_PAYMENT_DIRECT_DEBIT = "direct_debit"
PRICE_CAP_PAYMENT_STANDARD_CREDIT = "standard_credit"
PRICE_CAP_PAYMENT_PREPAYMENT = "prepayment"
PRICE_CAP_PAYMENT_METHODS = [
    PRICE_CAP_PAYMENT_DIRECT_DEBIT,
    PRICE_CAP_PAYMENT_STANDARD_CREDIT,
    PRICE_CAP_PAYMENT_PREPAYMENT,
]
OFGEM_REGIONS = [
    "North Western England",
    "North Eastern England",
    "Yorkshire",
    "Northern Scotland",
    "Southern England",
    "Southern Scotland",
    "Merseyside and Northern Wales",
    "London",
    "South Eastern England",
    "Eastern England",
    "East Midlands",
    "West Midlands",
    "South Western England",
    "Southern Wales",
    "Great Britain average",
]

DEFAULT_TARIFF_TIMEZONE = "Europe/London"
DEFAULT_TARIFF_PRICE_UNIT = PRICE_UNIT_PENCE
DEFAULT_PRICE_CAP_REGION = "Great Britain average"
DEFAULT_PRICE_CAP_PAYMENT_METHOD = PRICE_CAP_PAYMENT_DIRECT_DEBIT
DEFAULT_TARGET_PERCENT = 100.0
DEFAULT_CHARGER_EFFICIENCY = 0.9
DEFAULT_SLOT_MINUTES = 30
DEFAULT_LEGACY_SCAN_INTERVAL_SECONDS = 60

PLATFORMS = [
    "sensor",
    "binary_sensor",
    "button",
    "switch",
    "select",
    "datetime",
    "number",
    "text",
]
