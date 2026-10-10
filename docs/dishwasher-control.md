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

To stop automatic scheduling, turn both modes off and cancel queued requests
separately. To relinquish ownership, call
`load_optimizer.deactivate_native_orchestration`; this clears pending native
requests but does not stop an already running wash. Legacy installations may
have captured package automations re-enabled, so use their migration guide.

For waiting or failed starts, see [troubleshooting](troubleshooting.md). Never
remove safety or missing-data checks to force a request through.
