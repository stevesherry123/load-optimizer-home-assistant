# Data Handling And Privacy

## Local Data

Load Optimizer reads the configured Home Assistant entities and stores learned
appliance profiles, run counters, requests and migration state in Home
Assistant's private `.storage` directory. Backups can contain these records.
Entities and dashboard attributes intentionally expose cycle timing and planning
details to users who have access to your Home Assistant instance. Home Assistant
Recorder and automations may retain them according to your own configuration.

The integration does not add analytics, telemetry, advertising, its own network
listener or a remote account. It does not require a Home Assistant access token
in its settings. Optional dashboard cards are separately installed frontend
dependencies, not part of this Python package's security review.

## External Connections

The regional benchmark fetches the public Ofgem page and its linked Everviz
tables over verified HTTPS. Those providers see a normal request, including your
public IP address and the integration User-Agent. Household entities, appliance
profiles, credentials and names are not included in these requests. The region
and payment selection are applied locally to the retrieved public table.

Appliance commands use existing Home Assistant services. Their integrations
(such as Home Connect) may use cloud services governed by their own policies.

The experimental beta's optional AI summary makes an explicit provider call only
when requested and complete analysis is available. It sends the compact tariff
analysis and relevant dates/windows to your configured HA AI Task provider,
not appliance profiles or HA credentials. Provider charges and its own retention
policy can apply. This is not a feature of the stable v1.5.7 release. Do not treat
an AI summary as an appliance command or an authoritative price forecast.

## Sharing Support Material

v1.5.7 diagnostic downloads use a positive allowlist of health/status information
and non-identifying numeric/boolean settings. They omit entry titles, raw YAML,
entity/device/source identifiers, location settings, battery state, schedules,
arbitrary errors and AI text. Local entity attributes remain useful for private
troubleshooting and are not equivalent to the redacted diagnostic download.

Older downloads may include private configuration: do not upload them publicly.
Event logging redacts credential keys and common embedded credential patterns,
but it cannot recognize every possible secret. Review logs and screenshots
before posting, and never paste tokens or full private YAML into public issues.

Importing memory is an administrator-only, explicit replacement operation, not
an automatic merge. Use a trusted source, finish captures and cancel queued
requests first. Invalid or oversized imports are rejected before persistence.
