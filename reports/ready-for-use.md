# Filings with no self-disclosed deferrals

Filings whose JSON-LD contains no occurrence of `deferr*` / `not modeled` / `NOT modeled` / `TODO` / `follow-up` / `future work`. All SHACL-validate and have `tariff.toml` `[review].status = "draft"` (no filing has been promoted past draft yet).

23 of 46 filings (50%) qualify. See [`ready-for-use.edn`](./ready-for-use.edn) for the machine-readable form.

## By utility

### PG&E (IOU) — 7
| Schedule | Effective | Type |
|---|---|---|
| `e-1`     | 2026-03-01 | RatePlan |
| `e-tou-c` | 2026-03-01 | RatePlan |
| `e-tou-c` | 2026-03-27 | RatePlan (supersedes 2026-03-01) |
| `e-tou-d` | 2026-03-27 | RatePlan |
| `ev2`     | 2026-03-27 | RatePlan |
| `e-elec`  | 2026-01-01 | RatePlan |
| `e-elec`  | 2026-03-27 | RatePlan (supersedes 2026-01-01) |

### SCE (IOU) — 2
| Schedule | Effective | Type |
|---|---|---|
| `d`               | 2025-11-15 | RatePlan |
| `deed-restricted` | 2025-11-15 | RatePlanModifier |

### SDG&E (IOU) — 4
| Schedule | Effective | Type |
|---|---|---|
| `ev-tou-5` | 2026-04-01 | RatePlan |
| `tou-dr2`  | 2026-04-01 | RatePlan |
| `tou-elec` | 2026-04-01 | RatePlan |
| `dr-ses`   | 2026-04-01 | RatePlan |

### CPAU (POU) — 7
| Schedule | Effective | Type |
|---|---|---|
| `e-1`     | 2025-07-01 | RatePlan (URPX test-case template) |
| `e-1`     | 2025-09-01 | RatePlan |
| `e-1-tou` | 2026-01-01 | RatePlan |
| `e-2`     | 2025-07-01 | RatePlan |
| `e-eec-1` | 2025-09-01 | RatePlanModifier |
| `e-nse-1` | 2025-09-01 | RatePlanModifier |
| `e-hra`   | 2023-01-01 | RatePlanModifier |

### SMUD (POU) — 2
| Schedule | Effective | Type |
|---|---|---|
| `pev-credit` | 2025-06-20 | RatePlanModifier |
| `ssr`        | 2022-03-01 | RatePlanModifier |

### LADWP (POU) — 1
| Schedule | Effective | Type |
|---|---|---|
| `r-1a` | 2026-04-01 | RatePlan |

## Caveats

- **Heuristic, not proof.** This is a textual scan over the JSON-LD; it catches deferrals that the modeler explicitly wrote down. A gap that was modeled silently — extracted incompletely without a self-disclosing comment — wouldn't appear here.
- **Draft status.** Every entry has `[review].status = "draft"`. None has been formally reviewed, published, or marked superseded.
- **`EXCLUDED` is not a deferral.** SDG&E `dr-ses` 2026-04-01 contains the token `EXCLUDED` describing TRAC's structural exemption from the UDC for this schedule — that's a feature of the tariff, not modeling work that was set aside.
- **Supersession metadata is in-graph.** Where a filing supersedes a prior version (e.g. PG&E `e-tou-c` 2026-03-27 → 2026-03-01), the lineage is captured via `urpx:supersedes` in the JSON-LD; both versions remain in the corpus and are listed independently above.
