# EV Options Beta

Branch: `beta/ev-options-v1.5.2`, based on the stable publication preparation.
It does not include or promote the v1.6/v1.7 tariff-intelligence branches.

Implemented: the EV entry's Configure menu offers EV charging settings and
Price-cap benchmark. Setup and editing share one schema. Saved options override
setup values; optional target/connection references and the ready-by deadline
can be cleared, including references originally saved in entry data.
Required entities, charge power, fallback target, efficiency and slot length
are prefilled. Ready by is a daily local `HH:MM` deadline, not an ISO datetime.
Saving does not replace the entry, reset learning or enable charger control.

174 unit tests pass locally. The minimum-HA import/schema job checks actual
Home Assistant selectors, retained numeric defaults, optional-reference clearing
and rejected numeric/deadline values. This does not yet claim a live UI test.

## Live Acceptance Before Promotion

1. On a dedicated beta installation, record the EV entry/entity identities,
   options and current advisory plan. Do not replace the owner's v1.7 deployment
   with this older feature branch merely to test an options editor.
2. Open Configure on an EV entry; confirm only EV and benchmark sections appear.
3. Change target/power and benchmark independently. Confirm each section retains
   the other's values and updates the plan after the existing reload listener.
4. Clear optional references, including ones originally in entry data. Confirm
   the numeric fallback target and cleared local deadline take effect.
5. Reload/restart and confirm entry and entity IDs, options and advisory behavior.
6. Confirm learned-appliance options and stored learning are unchanged. Test a
   downgrade with the new options present; options must not enable control.

Merge only after these checks pass. Propagate the editor into the analysis/import
branches without discarding their independently verified history stores.
