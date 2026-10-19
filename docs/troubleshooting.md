# Troubleshooting

Start with the affected device's entities and attributes in **Developer tools >
States**. Installing through HACS does not configure sources or enable starting.
Do not work around missing data by assuming a device is safe to run.

## Configuration Review

Malformed appliance YAML, duplicate IDs/keys/policies, non-finite numbers,
invalid scheduling fields and ambiguous quoted permission flags are rejected
before saving. The form keeps the submitted values; correct the indicated field
and review again. Remove legacy `reset_instance_ids` instructions from an
ordinary appliance setup/edit. An existing appliance's ID is its learning
association, not a display label to rename.

The review can warn about missing/unavailable entities or wrong W/kWh units
without blocking setup. Fix the source integration or use correctly converted
template sensors; the integration does not convert appliance units for you.
Cancelling the review leaves the saved configuration unchanged. A known active
capture or queued request blocks saving changed sources: wait for completion,
or explicitly cancel only the request if that is your intent. No wash is stopped
and no request is cancelled automatically by this form.

## Learning And Recommendations

| Symptom / state | Meaning and next check |
| --- | --- |
| Integration is absent from Add integration | Restart HA after HACS download, then refresh the browser. Check HA logs if it still fails. |
| `configuration_required` | Appliance definitions are missing or unusable. Check the Instances YAML list and power sensor reference. |
| Runtime `ready`, but no cost recommendation | Runtime health is not tariff or policy readiness. Inspect the appliance's `_cost_status` attributes. |
| Power / energy `unavailable` | Verify the source entity exists and has a numeric value in W / kWh. Do not paste a switch or raw kW / Wh values. |
| Cycle remains `running` | It may still be above the activity threshold or waiting for low-power finish scans. Check the actual appliance and its source readings. |
| Count has not increased immediately | Allow the finish scans. Check `_last_discarded_cycle` for short, interrupted or poor-quality captures; rejected captures do not increment learning. |
| Learned as `Default` | No usable programme source was captured. Configure an actual programme sensor if available; otherwise use an explicit `Default` recommendation policy. |
| `tariff_not_configured` | Configure a forecast entity or additional rates events. A current-price sensor alone is insufficient. |
| `no_eligible_programs` | Check explicit programme policies first. Also inspect programme diagnostics for cooldowns, time constraints, blocked windows and unpriced candidates. |
| `insufficient_profile` | No usable completed power profile yet. Check capture quality and finish a normal cycle. Do not fabricate learning to clear it. |
| Price appears 100 times too large / small | Check `gbp_per_kwh` versus `p_per_kwh`, then compare the published current price with your supplier. Avoid double conversion. |
| Tomorrow absent | Check the supplier's next-day rates event attributes. Publishing time varies; complete coverage is needed for each candidate cycle. |

For ID `1`, the prefix is `sensor.load_optimizer_1`. Useful attributes include
the catalogue's `programs`, cost status `program_diagnostics` and the tariff
horizon's coverage information. An entity state and its reason may differ:
inspect both rather than treating every `not_ready` as the same fault.

Confidence measures the learned profile's amount and consistency of data. More
repeatable valid cycles generally improve it, but a fixed number of runs does
not guarantee 100%. Recommendation eligibility and automatic-start confidence
are separate checks.

## Dishwasher Starts

- **`shadow`:** native control is inactive. Completing learning or filling control
  references does not activate it. Follow the fresh-install
  [control guide](dishwasher-control.md), or the separate legacy migration guide.
- **Recommendation visible, no wash queued:** a plan is not a start request.
  Check ownership, the two automatic opt-ins and Automatic Scheduling's reason.
- **Queued but not started:** inspect queued time, last attempt, connection,
  door, remote-start permission, operation state and confidence. Do not press
  another button to test unless you intend a real wash.
- **Manual programme absent:** check the configured live Home Connect programme
  selector and its supported options. Manual selection does not use automatic
  cooldowns, but still requires a physically ready appliance.
- **Free/negative programme absent:** check its explicit negative-price policy,
  run allowance, usable pricing and window fit. A promotional calendar does not
  enrol you in an offer. Stable v1.5.7 does not turn calendar events into zero
  prices. The beta.9 Power Up feature requires an explicit eligible-account
  `free_window_entity`; see [free-electricity calendar pricing](power-up-pricing.md).
  An unavailable calendar supplies no promotional price, while Power Down
  remains a no-run constraint. Include the exact installed version.
- **Dishwasher has its own start timer:** beta.9 distinguishes Bosch
  `DelayedStart` from washing and protects that timer from optimizer commands.
  The next explanation update explicitly shows it as waiting, not washing,
  alongside any separate optimizer request. Change the timer on the appliance
  if that is your intent; a manual override does not bypass this safety check.
- **A particular programme is cooling down:** the next dashboard-template
  update lists its automatic eligibility time. An explicit selected-programme
  manual request bypasses programme cooldowns, not connection, door, operation
  state or remote-start checks. The automatic 30-minute retry interval is a
  different limit and is identified separately.

Disable automatic modes and cancel pending requests if you need to investigate
without a scheduled start. This does not stop an already running wash.

## EV Planning

Inspect the EV Status entity's `reason` attribute:

| Reason | Next check |
| --- | --- |
| `missing_battery_percent` / `missing_battery_capacity` | Correct numeric sensor references, percent and usable kWh. |
| `vehicle_not_connected` | Check explicit text connection status, including unknown/unavailable. See the binary-status adapter in the EV guide. |
| `no_tariff_periods` / `tariff_error` | Inspect future-rate attributes and price-unit settings. |
| `insufficient_tariff_coverage` | Not enough whole charging slots before the deadline. Recheck the deadline, charging power and available rates. |
| `invalid_charging_inputs` / other `invalid_*` | Check finite numbers, efficiency as a fraction, percent bounds and units. |
| `target_already_met` | Normal result: no slots are required and charge-now stays off. |

An EV plan does not prove a charger is receiving commands. Built-in planning is
advisory; this integration does not install a charger controller.

## Dashboards And Support

Use the [one-appliance starter dashboard](dashboard.md#start-with-one-appliance)
first. Entity-not-found errors usually mean a mismatched appliance ID or copied
EV name. Rich chart errors can also mean ApexCharts Card is not installed.
Unknown cost values before learning are not missing entities. Keep customised
dashboard files outside `custom_components/` so HACS updates cannot replace them.

For a [GitHub issue](https://github.com/stevesherry123/load-optimizer-home-assistant/issues),
include the exact integration release, HA version, load type, expected and actual
result, relevant state/reason and reproduction steps. Download diagnostics from
the integration/device page, review the contents and share only redacted data.
Use [private reporting](../SECURITY.md) for suspected security problems. Never
attach tokens, full configuration, private backups or unreviewed screenshots.
