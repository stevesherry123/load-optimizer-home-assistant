# Load Optimizer Legacy Add-on

This directory contains the legacy Home Assistant add-on runtime.

New installations should use the HACS custom integration in
`custom_components/load_optimizer`. Existing add-on users can migrate learned
data with the `load_optimizer.import_legacy_state` integration service and then
stop and disable this add-on after validating the integration output.

See `DOCS.md` for historical add-on configuration and first-start guidance.
