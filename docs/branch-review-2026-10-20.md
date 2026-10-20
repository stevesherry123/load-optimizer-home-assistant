# Branch Review: 20 October 2026

The refreshed remote inventory contains three branches. No redundant remote
branches remain from the earlier consolidation.

| Branch | Purpose | Decision |
| --- | --- | --- |
| `main` | Stable, published integration line | Keep; do not promote experimental work implicitly. |
| `beta/next` | Shared tariff-analysis and appliance testing line | Keep until its outstanding acceptance gates are closed. |
| `feature/ev-charger-control` | Owner-only EV control and charging-test bench | Keep separate, as requested; physical vehicle acceptance is still outstanding. |

`beta/next` is an ancestor of the EV branch. That does not make it redundant:
deleting it would remove the separate non-EV testing line. Conversely, merging
the EV branch into it would distribute experimental charger-control code through
the shared beta line. Neither operation is part of configuration-form repairs.

There are two clean local checkouts, on `beta/next` and the EV branch. No local
branch can be removed while keeping both active checkouts intact.

## Next Consolidation

1. Carry the general configuration-editor and calendar-source repairs into the
   shared beta independently of the experimental EV controller, with validation.
2. Close the shared beta acceptance gates before approving stable promotion.
3. Merge and delete the EV branch only after vehicle setup and real charging
   acceptance are complete, or explicitly retire that experiment.

No release tag is moved, no version is incremented, and no HACS catalogue
submission is altered by this review.
