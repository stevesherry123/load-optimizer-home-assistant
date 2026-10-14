# Single Beta Branch

The owner approved consolidating the beta work, publishing a tested beta and
installing it on 14 October 2026. Stable `main` and release `v1.5.7` are not
promoted by this work. The canonical testing branch is now `beta/next`.

## Preserved Tips

| Superseded remote branch | Tip incorporated into beta/next |
| --- | --- |
| beta/tariff-analysis-v1.6 | fb5327737715b3804878d555630a95d200e8ce79 |
| beta/tariff-import-narrative-v1.7 | 91727ee5c1ee044dca383960125702bb70c674fb |
| docs/onboarding-clean-install | becd20478fd340310d9c5379d757786af0725605 |
| docs/physical-cycle-ledger-design | 0c81d5ecad8b7c4f9d217b0c2ae77aa6d4be51a0 |
| fix/negative-price-repeat-safety | f4cae7202b9c25cb2097e6e615a9bd89716dafc3 |
| fix/runtime-data-safety | 381306b386df260061ac2d64eb4b96dc5c26cde7 |

`f7a7b66` is the consolidation merge, preserving both parents and the original
commits. All six remote tips were verified unchanged and ancestors of the pushed
`beta/next` before deletion. Stacked PRs #4/#5 and repair PR #17 were closed and
replaced by [draft PR #18](https://github.com/stevesherry123/load-optimizer-home-assistant/pull/18).
Closing these superseded reviews is not stable promotion.

Eighteen local ancestor branches were also removed. Two unique prototype tips
remain recoverable through non-release archive tags before their local branches
were removed: `archive/tariff-intelligence-2026-10-09` and
`archive/negative-repeat-prototype-2026-10-14`. Only `main` and `beta/next` remain
locally and remotely. No installed release tag was moved or deleted.

## Still Experimental

Tariff analysis/import/narrative acceptance remains required before stable
promotion. AI remains optional and disabled unless the user enables it. The
physical-cycle quota ledger and guided editor remain designs, not implemented
features. The separate Octopus Intelligence app is not retired by cleanup.
