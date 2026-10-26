# HACS runtime and entity ownership review

The v1.5.9 patch addresses the three additional findings in HACS submission
11744, based on the stable v1.5.8 release rather than experimental EV work.

## Worker boundary

Calendar services and option normalization run before the executor. The legacy
calculation pass, including learning updates, recommendations, forecast, startup
repair and buffered publications, runs in one worker. Module-level legacy
adapters are protected by a process lock and rebound only within that worker.
Source reads and native control-state synthesis are marshalled back to HA's loop;
the worker never calls `states.async_set`. Notifications use the thread-safe
`hass.create_task`. Storage is saved on the loop after the worker completes.

The scan/import lock remains held when a scan's caller is cancelled: the scan
finishes and saves before cancellation is propagated. This prevents an executor
job from continuing to change memory after a reload/import assumes it has stopped.

## Maintenance outcomes

The three unregistered migration, legacy-add-on and recovery status states are no
longer written. Imports and recovery report through persistent notifications;
import without a learned-appliance runtime raises a service validation error.
The existing add-on retirement notification is retained. There are no shipped
dashboard references to the removed states; the migration guide is updated.

## Registry ownership

Migration only updates registry entries owned by this integration and config
entry. An occupied package-era ID causes a translated repair issue, not removal
of another integration's entity or state. A registered native alternative ID is
preserved across reloads. The user removes an obsolete template definition and
its remaining registry entry; after the target is free, reloading Load Optimizer
claims the intended ID and clears the repair. Learning memory is unaffected.

## Travelling browser regression

The optional full dashboard previously combined shifted timestamps with browser
time formatting. The patch preserves UTC instants after counteracting the chart
card's automatic server-profile offset, explicitly formats in the tariff zone,
and aligns day bounds and the Now marker to the same basis. Shipped JavaScript
is executed in New York, London and Tokyo browser timezones for both profile
preferences, one/two-day views and UK/US DST boundaries. The benchmark series is
checked against the same instants. A separate HA regression checks that a
25-hour current day is not mistaken for next-day rates.

Existing custom dashboard copies require the YAML changes to be applied; HACS
does not replace them automatically. No live HA/RPi deployment is part of this
review patch.
