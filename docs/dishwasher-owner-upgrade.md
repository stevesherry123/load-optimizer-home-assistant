# Owner dishwasher upgrade candidate

The owner candidate applies the dishwasher changes from draft PR #27 to EV
trial commit `70dafaf`. It retains the trial controller, storage format,
configuration flow and dashboard. The public dishwasher candidate remains a
separate branch based on shared beta.

Before installing, match the live integration files to a reviewed source build.
A beta.9 version label alone cannot distinguish the owner trial revisions.
Confirm all appliance captures are idle, no request is pending and EV control
is off with no owned charging session. Preserve the existing code, Home
Assistant configuration and learning data in a restorable backup.

After a planned restart, check loaded entries, entity IDs, learned-run counts,
optional mode settings and the EV trial dashboard. Check the new dishwasher
window entities and inspect one recommendation before authorising a wash.
Keep customised dashboards and trial packages with the existing configuration.
If any entry fails to load or state differs unexpectedly, restore the matching
source and configuration backup before resuming control.
