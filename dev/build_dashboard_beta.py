"""Build the optional storage-mode beta dashboard from shared chart templates."""

from copy import deepcopy
from pathlib import Path
from textwrap import dedent

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "homeassistant/dashboards/beta/load_optimizer_beta.yaml"


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def markdown(title, content):
    return {"type": "markdown", "title": title, "content": dedent(content).strip()}


def entities(title, instance, rows):
    return {"type": "entities", "title": title, "show_header_toggle": False,
        "entities": [{"entity": f"sensor.load_optimizer_{instance}_{key}", "name": name}
                     for key, name in rows]}


def section(*cards, span=1):
    return {"type": "grid", "column_span": span, "cards": list(cards)}


def view(title, path, icon, *sections):
    return {"title": title, "path": path, "icon": f"mdi:{icon}",
            "type": "sections", "max_columns": 3, "sections": list(sections)}


def build():
    full = yaml.safe_load((ROOT / "homeassistant/dashboards/full/load_optimizer_dashboard.yaml").read_text())
    learning = yaml.safe_load((ROOT / "homeassistant/dashboards/full/dishwasher_learning_insights.yaml").read_text())
    catalogue = deepcopy(next(card for card in walk(full) if card.get("title") == "Program Catalogue"))
    capabilities = deepcopy(next(card for card in walk(full) if card.get("title") == "Automation Capabilities"))
    forecast = deepcopy(next(card for card in walk(full) if card.get("header", {}).get("title") == "Dishwasher 1 - Cost Forecast"))
    forecast["grid_options"] = {"columns": "full"}
    forecast["apex_config"]["chart"]["height"] = 280
    price_cards = deepcopy(full["views"][0]["sections"][0]["cards"])
    for card in price_cards:
        if card.get("type") == "tile":
            card["grid_options"] = {"columns": 6}
        if card.get("type") == "custom:apexcharts-card":
            card["apex_config"]["chart"]["height"] = 280
            card["apex_config"]["tooltip"]["y"]["formatter"] = (
                "EVAL:function(value) { return Number(value).toFixed(2) + ' p/kWh'; }")

    next_wash = deepcopy(next(card for card in walk(full) if card.get("title") == "Next wash"))
    last_wash = markdown("Last wash", """
        {% set finish = states('sensor.load_optimizer_1_last_finish') %}
        {% set native = 'sensor.load_optimizer_1_orchestration_status' %}
        {% if as_datetime(finish, none) %}
        **{{ states('sensor.load_optimizer_1_last_program') }}**

        Finished {{ (as_datetime(finish) | as_local).strftime('%a %d %b %H:%M %Z') }}

        {{ states('sensor.load_optimizer_1_last_runtime') }} min / {{ states('sensor.load_optimizer_1_last_energy') }} kWh
        {% else %}
        No learned wash recorded.
        {% endif %}

        Scheduler result: **{{ state_attr(native, 'last_result') or 'Not recorded' }}**
    """)
    live_rows = [("cycle_state", "Cycle"), ("power", "Power"), ("total_runs", "Learned runs")]
    activity = section(next_wash, last_wash)
    overview = view("Overview", "overview", "home-lightning-bolt-outline",
        section(*price_cards, span=3), activity,
        section(entities("Dishwasher", 1, live_rows), entities("Washing machine", 2, live_rows)),
        section(entities("Robot vacuum", 3, live_rows), markdown("Charging", """
            [Charging Test Bench](/charging-test-bench)
        """)))

    schedule = markdown("Scheduling", """
        {% set entity = 'sensor.load_optimizer_1_automation_explanation' %}
        {% set blocks = state_attr(entity, 'blocker_messages') or [] %}
        {% set warnings = state_attr(entity, 'warning_messages') or [] %}
        {% set checks = (state_attr(entity, 'blockers') or []) + (state_attr(entity, 'warnings') or []) %}
        {% if not has_value(entity) %}
        Scheduling information unavailable.
        {% elif not blocks and not warnings and checks %}
        Readiness checks are pending. Review the integration details.
        {% elif not blocks and not warnings %}
        No outstanding checks reported.
        {% endif %}
        {% for message in blocks %}
        - {{ message }}
        {% endfor %}
        {% for message in warnings %}
        - {{ message }}
        {% endfor %}
    """)
    recommendation = markdown("Recommendation", """
        {% set entity = 'sensor.load_optimizer_1_overnight_recommendation' %}
        {% set start = state_attr(entity, 'start') %}
        {% set cost = state_attr(entity, 'cost_pence') | float(none) %}
        {% if has_value(entity) and states(entity) != 'not_ready' and as_datetime(start, none) %}
        **{{ state_attr(entity, 'program') or states(entity) }}**

        {{ (as_datetime(start) | as_local).strftime('%a %d %b %H:%M %Z') }}
        {% if is_number(cost) %}

        Estimated cost: **GBP {{ '%.2f' | format(cost / 100) }}**
        {% endif %}

        Recommendation only, not a queued wash.
        {% else %}
        No fully priced recommendation available.
        {% endif %}
    """)
    controls = {"type": "entities", "title": "Automatic modes", "show_header_toggle": False,
        "entities": [
            {"entity": "switch.load_optimizer_1_auto_mode_enabled", "name": "Schedule after loading (door rule)"},
            {"entity": "switch.load_optimizer_1_auto_negative_price_enabled", "name": "Profitable extra runs"},
        ]}
    manual = {"type": "entities", "title": "Manual programme", "show_header_toggle": False,
        "entities": [{"entity": "select.load_optimizer_1_override_program", "name": "Programme"}]}
    def command(name, entity, message, icon):
        return {"type": "button", "name": name, "icon": f"mdi:{icon}", "show_state": False,
                "tap_action": {"action": "perform-action", "perform_action": "button.press",
                    "target": {"entity_id": entity}, "confirmation": {"text": message}}}
    window = {"type": "entities", "title": "Overnight window", "show_header_toggle": False,
        "entities": [
            {"entity": "time.load_optimizer_1_overnight_start", "name": "Overnight start"},
            {"entity": "time.load_optimizer_1_overnight_end", "name": "Dishes ready by"},
            {"entity": "number.load_optimizer_1_door_open_minimum_minutes", "name": "Loading door-open minimum"},
        ]}
    window_help = deepcopy(next(card for card in walk(full) if card.get("title") == "Window settings"))
    dishwasher = view("Dishwasher", "dishwasher", "dishwasher",
        section(deepcopy(next_wash), schedule,
            command("Schedule one wash", "button.load_optimizer_1_request_overnight",
                "Authorise one wash inside the overnight window? The optimiser chooses the programme and start time.", "calendar-plus"),
            command("Start now", "button.load_optimizer_1_request_now",
                "Start a wash now using the optimiser's selected programme?", "play-circle"),
            command("Cancel pending schedule", "button.load_optimizer_1_cancel_schedule",
                "Cancel the pending request and permission? An active wash will continue.", "calendar-remove")),
        section(window, window_help, controls, recommendation,
            deepcopy(next(card for card in walk(full) if card.get("title") == "Cycle costs"))),
        section(entities("Appliance", 1, [("cycle_state", "Cycle"), ("power", "Power"),
            ("data_freshness", "Source freshness"), ("remote_activation_check", "Remote start")]),
            manual, command("Start selected programme", "button.load_optimizer_1_request_now_override",
                "Start the selected dishwasher programme now?", "play-circle-outline")),
        section(forecast, span=3))

    learned = deepcopy(next(card for card in walk(learning) if card.get("title") == "Learned Programs"))
    learned["title"] = "Dishwasher learning"
    learned["grid_options"] = {"columns": "full"}
    other_learning = [entities(title, instance, [("total_runs", "Learned runs"),
        ("cost_confidence", "Confidence"), ("last_finish", "Last finish")])
        for title, instance in (("Washing machine", 2), ("Robot vacuum", 3))]
    for card in other_learning:
        card["grid_options"] = {"columns": 6}
    catalogue["grid_options"] = {"columns": "full"}
    learning_view = view("Learning", "learning", "brain",
        section(learned, span=3),
        section(*other_learning, span=3),
        section(catalogue, span=3))

    events = markdown("Recent decisions", """
        {% set records = state_attr('sensor.load_optimizer_1_automation_explanation', 'recent_events') or [] %}
        {% if records %}
        | Home time | What happened | Programme |
        |---|---|---|
        {% for event in records[:12] -%}
        | {{ (as_datetime(event.timestamp) | as_local).strftime('%d %b %H:%M %Z') if as_datetime(event.timestamp, none) else 'Not recorded' }} | {{ (event.description | default('A scheduling record was saved.', true)) | replace('|', '/') | replace('\\n', ' ') }} | {{ (event.program | default('Not selected', true)) | replace('|', '/') | replace('\\n', ' ') }} |
        {% endfor -%}
        {% else %}
        No scheduling events recorded.
        {% endif %}
    """)
    native = markdown("Execution record", """
        {% set native = 'sensor.load_optimizer_1_orchestration_status' %}
        {% set snapshot = state_attr(native, 'last_start_decision_snapshot') %}
        {% set request = snapshot.get('request') if snapshot is mapping else none %}
        {% set quote = request.get('recommendation_quote') if request is mapping else none %}
        {% set alternatives = request.get('recommendation_alternatives') if request is mapping else none %}
        {% macro home_time(value) -%}
        {{ (as_datetime(value) | as_local).strftime('%a %d %b %H:%M %Z') if as_datetime(value, none) else 'Not recorded' }}
        {%- endmacro %}
        | Record | Value |
        |---|---|
        | Scheduler | {{ states(native) }} |
        | Last start | {{ home_time(state_attr(native, 'last_attempt')) }} |
        | Programme | {{ state_attr(native, 'last_program') or 'Not recorded' }} |
        | Manual recommendation estimate | {{ ('%.2f p' | format(quote.estimated_cost_pence)) if quote is mapping and quote.estimated_cost_pence is number else 'Not recorded' }} |
        {% if quote is mapping and quote.estimated_cost_pence is number -%}
        | Estimate window | {{ home_time(quote.start) }} to {{ home_time(quote.finish) }} |
        {% endif -%}
        | Result | {{ state_attr(native, 'last_result') or 'Not recorded' }} |
        | Detail | {{ (state_attr(native, 'last_message') or 'Not recorded') | replace('|', '/') | replace('\\n', ' ') }} |
        {% if alternatives is sequence and alternatives is not string and alternatives is not mapping and alternatives %}

        **Other programme estimates for this request**

        | Programme | Estimated cost | Estimate window |
        |---|---|---|
        {% for option in alternatives[:3] if option is mapping and option.estimated_cost_pence is number -%}
        | {{ option.program | replace('|', '/') | replace('\\n', ' ') }} | {{ '%.2f p' | format(option.estimated_cost_pence) }} | {{ home_time(option.start) }} to {{ home_time(option.finish) }} |
        {% endfor -%}
        {% endif %}
    """)
    capabilities["grid_options"] = {"columns": "full"}
    diagnostics = view("Diagnostics", "diagnostics", "stethoscope",
        section(native, entities("Sources", 1, [("status", "Optimizer"),
            ("data_freshness", "Data freshness"), ("tariff_horizon", "Published horizon")]),
            entities("Readiness", 1, [("overnight_readiness", "Overnight"),
                ("negative_price_readiness", "Free / negative price") ])),
        section(events, span=2), section(capabilities, span=3))
    return {"title": "Load Optimizer Beta", "views": [overview, dishwasher, learning_view, diagnostics]}


if __name__ == "__main__":
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(yaml.safe_dump(build(), sort_keys=False, allow_unicode=True, width=1000))
    print(OUTPUT)
