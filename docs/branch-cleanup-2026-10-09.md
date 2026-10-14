# Branch Cleanup: 9 October 2026

Reviewed all 18 remote branches and their open/merged pull requests. Removed 14
branch references whose tips were proven ancestors of retained main/beta work,
and one superseded early prototype after preserving its exact tip in an annotated
archive tag. Remote deletions checked the expected SHA to avoid removing a branch
that changed during the review. No commits, release tags, learning data, live HA
configuration or open beta pull requests were removed.

## Retained

- `main`: stable product, current release v1.5.7.
- `beta/tariff-analysis-v1.6`: draft PR #4 with its analysis promotion gates.
- `beta/tariff-import-narrative-v1.7`: draft PR #5 stacked on analysis; current
  prerelease v1.7.0-beta.5. Separate AI/import gates remain incomplete.

These two betas are not parallel installations of the integration. Both remain
because deterministic analysis can be reviewed/promoted independently of its
import/AI extension. Cleanup does not promote either to stable.

## Retired References

| Remote branch removed | Preserved tip | Retained history |
| --- | --- | --- |
| `beta/ev-options-v1.5.2` | `5f80033a8b8f9571d6b5155e68359ce31a932098` | `main` |
| `beta/native-entities-v1.3` | `2d9ecbc12e40384e37bef9b74b2c0019662ca9c4` | `main` |
| `beta/native-orchestration-v1.4` | `85bfbb0e116dd4df42a3d45b399364e154d7e827` | `main` |
| `beta/overnight-diagnostics-v1.5.3` | `97f1ef6cb95fbf0cdb44b9915f153730ccde401e` | `main` |
| `beta/publication-readiness-v1.5.1` | `ee212d53f53dd6ffb477ff393aca02fa0adfe5b4` | `main` |
| `beta/tariff-intelligence-v1.5` | `74154a4bc277daca31b495c275e033a8a02cfc49` | `main` |
| `beta/v1.4.2-hardening` | `05904420c53f638e8235cfe53fdd13222dd7d68a` | `main` |
| `feature/price-benchmark-tile-colours` | `f0b34a37b8434ac7b8ca5edd7a71a24aedba0d72` | `main` |
| `fix/dashboard-and-options` | `c6ddc3db351fd42f6926f849b1c2e889578cfb3d` | `main` |
| `fix/minimum-ha-device-links` | `590860488f006fe8deb6a325c28515eee5a855e4` | `main` |
| `fix/startup-confidence-v1.5.4` | `4a49c66e554ee79a0d3966872124df82548e0fcd` | `main` |
| `hotfix/options-flow-compatibility` | `d0b2b50fe291ad5cdb9d2064ef546533956ccdd2` | `main` |
| `security/beta-v1.7.0-beta.5` | `72a7469b0a2c67e7e909da37303a6c49e610b5e0` | `beta/tariff-import-narrative-v1.7` |
| `security/publication-v1.5.7` | `e57cc937b1319114747b07c7f04747e6ac6fe1cc` | `main` |
| `feature/tariff-intelligence` | `eb35e601615e4c6d7b220886166bbe5ff7057e74` | `archive/tariff-intelligence-2026-10-09` |

The early `feature/tariff-intelligence` prototype included planning commits
subsequently cherry-picked and an earlier benchmark/options implementation
superseded by the tested stable code. Its exact history is recoverable from
`archive/tariff-intelligence-2026-10-09`, targeting
`eb35e601615e4c6d7b220886166bbe5ff7057e74`. The archive tag has no GitHub release
and is not advertised by HACS as an update. All published release tags remain
unchanged. Merged pull requests still retain their discussion and audit trail.

Only remote repository branch references were pruned. Local branches/checkouts
belonging to other work were left alone. The separate personal-fork HACS branch
`add-load-optimizer-v1.5.7` remains intact while catalogue PR #11744 is open.

