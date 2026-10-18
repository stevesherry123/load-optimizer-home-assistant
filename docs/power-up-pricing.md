# Free-Electricity Calendar Pricing

Status: implemented on beta/next; not yet installed in the owner's beta.8.

In learned-appliance tariff settings, set **Free-electricity calendars (Power
Up)** to the calendar provided for an account eligible for those sessions:

```yaml
free_window_entity: calendar.octopus_energy_YOUR_ACCOUNT_octoplus_power_up
blocked_window_entity: calendar.octopus_energy_YOUR_ACCOUNT_octoplus_power_down
```

The optional `free_window_entity` setting also supports comma-separated calendars
and an explicit per-appliance override in the appliance document. It defaults to
blank; a green/low-carbon calendar never implies free energy. Use a separate
blocked-window calendar for Power Down. The provider documents these calendars
in [Octoplus entities](https://bottlecapdave.github.io/HomeAssistant-OctopusEnergy/entities/octoplus/).

Only successfully queried, timed events with explicit timezone offsets grant a
0 p/kWh planning override. An unavailable source, failed query or invalid event
grants no free pricing; normal estimates fall back to contracted prices. An
empty or cancelled event list removes the override even if the calendar's
current-event attributes are stale. Calendar failures are exposed through
`free_window_source_ready`; a fresh failure blocks an automatic free-price start.

The override splits existing tariff periods precisely at event boundaries. It
does not fill missing-rate gaps or change the underlying Octopus feed, raw
historical tariff analysis, standing charges or billing records. Any part of a
cycle outside the event retains the contracted price. All effective rates
inside the event are set to zero as a planning assumption, including negative
contracted rates; raw negative rates remain intact in the source history.
This is an appliance scheduling estimate, not confirmation of an account credit.

Explicit manual special-price controls take precedence over calendar pricing.
Power Down/no-run windows, readiness, cooldowns, programme permissions and cycle
limits still apply. Automatic free-price commands fetch calendar events again
and reprice the requested programme immediately before attempting a start.

## Delayed Starts

For the native appliance-1 dishwasher, its configured Bosch operation sensor is
used for capture when no explicit learning state sensor is set. Other appliances
keep their existing power-based behavior. An explicit `DelayedStart` reports
`scheduled`, never starts learning from standby spikes, and clears an unconfirmed
false capture without incrementing learning. The actual running transition
starts a fresh capture. Optimiser commands cannot replace a pending native
delayed start.

The owner's 18 October read-only audit confirmed Bosch `DelayedStart`, zero
programme progress and low standby power while the old power-only capture
reported running. The exact triggering power sample was not retained by Recorder.
The false capture cleared naturally before the manually scheduled wash. A
verified 14:00-15:00 BST Power Up was applied through the existing native manual
price controls; the effective price reached zero without a restart or appliance
command. Permanent calendar and delayed-start fixes still require idle-time
deployment; they were not hot-patched into the active capture.
