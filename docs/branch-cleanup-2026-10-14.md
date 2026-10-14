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
commits. Remove superseded remote branches only after `beta/next` is pushed and
ancestry is verified. Replace stacked PRs #4/#5 and repair PR #17 with one draft
beta-to-main review; closing a superseded PR is not stable promotion.

Local branches whose tips are already ancestors may also be removed. Preserve
any unique prototype tip under an explicitly non-release archive tag first.
Never move or delete an installed release tag to tidy branches.

## Still Experimental

Tariff analysis/import/narrative acceptance remains required before stable
promotion. AI remains optional and disabled unless the user enables it. The
physical-cycle quota ledger and guided editor remain designs, not implemented
features. The separate Octopus Intelligence app is not retired by cleanup.
