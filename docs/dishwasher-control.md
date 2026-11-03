# Optional Home Connect Dishwasher Control

This is for a **fresh installation** with a Home Connect dishwasher. It is not
needed for learning or recommendations. Legacy-package users must instead follow
[orchestration migration](native-orchestration-migration.md) to avoid competing
controllers.

The current controller targets appliance ID **`1`**. If a different appliance
already owns that ID, do not rename IDs or move learning just to follow this
guide. Generic selectable control targets are future work.

## Learn Before Enabling Control

Use [`examples/home-connect-dishwasher.yaml`](examples/home-connect-dishwasher.yaml)
as the Instances YAML list for a new dishwasher hub. Replace the source IDs and
example `Eco50` programme with your supported programme. Power and energy may
come from a monitoring plug; programme and operation-state sources come from
Home Connect.

Run a wash normally on the machine. Confirm its learned count increases, the
programme appears in the catalogue, and its policy permits normal recommendations.
The example deliberately disallows negative-price runs.

## Configure The Controller

Open **Settings > Devices & services > Load Optimizer > Configure > Dishwasher
control (optional)**. Supply all references from your own installation:

| Field | Reference |
| --- | --- |
| Home Connect device ID | HA device-registry ID for the Home Connect dishwasher, not its serial number or Load Optimizer device ID. The device URL in Settings > Devices & services > Devices contains this ID. |
| Power switch | Home Connect power control, not the metering plug. |
| Program selector | Home Connect supported-programme `select` entity. |
| Start button | Home Connect start-programme button. |
| Selected program sensor | Selected Home Connect programme. |
| Power state sensor | Home Connect power state. |
| Connected sensor | Connection status. |
| Door sensor | Open/closed status. |
| Remote control sensor | Whether remote control is allowed. |
| Remote start sensor | Whether remote starting is allowed. |
| Operation state sensor | Home Connect operation state. |

Saving these fields **does not activate control**. Confirm both
`switch.load_optimizer_1_auto_mode_enabled` and
`switch.load_optimizer_1_auto_negative_price_enabled` remain **off**, with no
queued request, before activating.

As an administrator, open **Developer tools > Actions**, choose
`load_optimizer.activate_native_orchestration` and perform it with no fields.
Older HA versions call the tab **Services**. Fresh installations need no
migration preparation or legacy package. Missing references produce an error
rather than partial activation.

Check `sensor.load_optimizer_1_orchestration_status`: it should leave `shadow`
and its `active` attribute become true. With no pending request and both automatic
modes off, activation alone does not start a wash. Ownership and automatic modes
are independent gates.

## Supervised Manual Test

Only do this when you intend to run a real wash. Load the machine, enable the
manufacturer's remote-start permission, and close the door. Check remote
activation status and safety warnings first.

On a dashboard with dishwasher controls, select a supported programme in
**Manual Override Program**, then press **Start Selected Program Now**. This is
a real command, not a simulation. Manual selections bypass automatic programme
cooldowns and learning-confidence filtering, not connection, closed-door,
remote-start or already-running checks.

Verify the actual operation starts, then completion, the incremented learning
count and the recorded outcome. A queued request is not proof that Home Connect
accepted a command. The small starter dashboard has no start buttons; use the
larger template or the device's corresponding select/button entities.

## Opt Into Automatic Modes Separately

Normal automatic washing requires an observed door opening followed by closure.
This door-based mode is optional and off by default. An explicit scheduling
request authorises one normal wash without enabling the door-based mode.
The door must remain open for at least **two minutes** by default. Configure
**Door Open Minimum** on the dishwasher device
(`number.load_optimizer_1_door_open_minimum_minutes`, 0.5-60 minutes).
Shorter openings do not create a new normal-wash permission. This is a loading
heuristic, not proof of dirty dishes. Initial/restored states, interrupted door
telemetry and openings during a running wash do not qualify. A short reopening
does not revoke an existing permission; the closed-door safety check still applies.

### Script And Voice Requests

[`examples/dishwasher-scripts.yaml`](examples/dishwasher-scripts.yaml) contains
three optional scripts: **Schedule dishwasher**, **Start dishwasher now** and
**Cancel dishwasher schedule**. Its contents are a `scripts.yaml` mapping; merge
them into your existing scripts configuration rather than overwriting it.
Replace the button IDs if your registered IDs differ.

The schedule and start-now scripts hand programme selection to the optimiser,
using eligible learned programmes rather than the manual override selection.
An active native controller is required. In the unreleased development build,
**Schedule dishwasher** persists permission for one wash even when a priced plan
is not yet available. Missing prices produce a Home Assistant notification; when
complete data returns, planning resumes inside the original window. A cancelled
or expired request is never revived. **Start dishwasher now** still needs a ready
recommendation, unless using the separate selected-programme override.
Cancellation clears the pending request and normal door-based permission; it
does not stop a running wash or disable separately opted-in negative-price runs.
An explicit script request does not require a qualifying door opening, but all
physical safety checks remain enforced.

Scripts can be exposed through your existing Alexa/Home Assistant connection;
optional Alexa routines can provide your chosen phrases. Load Optimizer does
not configure Alexa, install these scripts, or send voice announcements itself.

### Automatic Modes

- **Automatic mode:** normal overnight scheduling. Requires a suitable policy,
  confidence, window and physical readiness. Recommendation permission alone
  does not enable automatic starts.
- **Automatic free / negative-price mode:** separate opt-in, also requiring
  `allow_negative_price_run: true` for each permitted programme. Review your
  release's behaviour, run limits and non-energy costs first. Leave it off
  during initial onboarding.

For a negative-enabled programme, set `maximum_runs_per_window` deliberately:
`1` allows one run of that programme per continuous free/negative window;
the default `0` means **unlimited**, not disabled. A positive-price gap creates
a new window. This limit is separate from normal programme cooldowns.

Promotional events do not automatically alter tariff prices or enrol you in an
offer. Free/negative scheduling needs usable zero/negative rates or an explicit
special-price overlay. Water, detergent and wear can outweigh electricity
credits; a negative electricity estimate is not guaranteed whole-cycle profit.
The unreleased development build requires strictly positive whole-cycle net
benefit for extra runs. See [operating costs](operating-costs.md) for the cost
fields, zero-return behaviour and dashboard breakdown.

To stop automatic scheduling, turn both modes off and cancel queued requests
separately. To relinquish ownership, call
`load_optimizer.deactivate_native_orchestration`; this clears pending native
requests but does not stop an already running wash. Legacy installations may
have captured package automations re-enabled, so use their migration guide.

For waiting or failed starts, see [troubleshooting](troubleshooting.md). Never
remove safety or missing-data checks to force a request through.

### Overnight Window (Unreleased Development Build)

The dishwasher device exposes **Overnight Start**
(`time.load_optimizer_1_overnight_start`) and **Dishes Ready By**
(`time.load_optimizer_1_overnight_end`). New defaults are **21:00–07:00**, using
the configured tariff timezone. Existing explicit appliance YAML window settings
are retained until overridden using these controls. Changes to defaults apply
to subsequent requests; they cannot move an existing authorised window.

The optimiser chooses the cheapest eligible programme and start that finishes
inside the window. If none fits completely, it chooses the cheapest eligible
cycle that **starts inside the window**, allowing completion afterwards. The
start boundary is inclusive and the end boundary exclusive: a request ending at
07:00 cannot start at 07:00 or later. A cheaper midday start is never substituted.
The explanation sensor exposes the authorised window, expected finish and
`late_finish` flag.

All candidate cycles need complete tariff coverage, including their late-finishing
portion. Explicit no-run periods, configured hard finish constraints and physical
safety gates still apply. Replanning can change programme and timing until the
short pre-start freeze; a final source and window check also runs before commands.
Normal wash permission takes priority over separately enabled opportunistic runs.
Scheduling again while a normal request exists retains the same wash and window.

These changes are development work, not an installed or published update.
