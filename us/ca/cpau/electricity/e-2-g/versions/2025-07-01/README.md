# CPAU E-2-G — effective 2025-07-01

City of Palo Alto Utilities **Schedule E-2-G: Residential Master-Metered and Small Non-Residential Green Power Electric Service**. A `urpx:RatePlanModifier` on the [CPAU E-2 base](../../e-2/versions/2025-07-01/) that adds a **Palo Alto Green Charge of \$0.0075/kWh** to small commercial / master-metered multi-family customers participating in the Palo Alto Green Program under the **100% Renewable Option**.

## Files

- `cpau_e-2-g_2025-07-01.pdf` — source PDF (sha256 in `tariff.toml`)
- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan-modifier_cpau_e-2-g_2025-07-01.jsonld` — URPX rate-plan-modifier serialization (top-level `urpx:RatePlanModifier`)

## What this modifier does

Per Section C of the published Schedule E-2-G, two options are available within the Palo Alto Green Program:

| Option | Per-kWh adder | Per-block charge |
|---|---:|---:|
| **100% Renewable Option** (modeled in v1) | \$0.0075 / kWh | — |
| **1000 kWh Block Purchase Option** (deferred — see follow-up) | — | \$7.50 / 1000 kWh block |

The 100% Renewable customer's energy bill = base E-2 unbundled rates + \$0.0075/kWh on top of every kWh consumed. The Block Purchase Option works differently — customer designates discrete blocks of green energy at a flat per-block charge while paying base rates for actual consumption — and has a different MetricInput shape (per-block discrete purchase vs continuous per-kWh consumption); deferred to a follow-up bd issue.

## Eligibility (Section A)

The customer must:
1. Qualify for E-2 Service (per the E-2 eligibility rules)
2. Elect to participate in the Palo Alto Green Program

Captured in the modifier's `RatePlanModifierVersion.description` text. The structural linkage to the E-2 base (`urpx:applicableToRatePlan`) is **omitted** pending [`urpx-org/urpx#23`](https://github.com/urpx-org/urpx/issues/23) — see "Modeling notes" below.

## Standalone modifier filing

This is one of the **first three standalone modifier filings** in this corpus (alongside sibling CPAU E-2-G / E-4-G / E-7-G — all filed together). Prior modifier modeling has been embedded in base RatePlan `@graph`s (e.g. PG&E vintage PCIA, CPAU E-1 2025-09-01 multi-source). The standalone shape lets each modifier sit in its own filing directory with its own `tariff.toml` provenance — appropriate when the modifier has a customer-segmented opt-in (Palo Alto Green Program) rather than always-applicable to the base.

The top-level entity is `urpx:RatePlanModifier`; the JSON-LD filename uses the `rate-plan-modifier_*` convention (vs `rate-plan_*` for base RatePlans).

## Modeling notes

Two URPX-team / clj-urpx threads were in flight while building this filing:

1. **`urpx-org/urpx#23`** — *how should a standalone modifier filing express `applicableToRatePlan` when the base RatePlan is in a separate file?* SHACL closed-world validation can't see the base RatePlan declaration across files, so setting `applicableToRatePlan = {"@id": "cpau:e-2"}` reports a class-membership violation. **Path taken**: omit `applicableToRatePlan` and describe the relationship in prose, matching the URPX-team's standalone-modifier test case pattern (`pge-e-tou-c-vintage-pcia-2026-03-01`). Retrofit once the URPX team responds with the intended pattern.

2. **clj-urpx** — loader support for standalone `RatePlanModifier` filings. Originally `core/load-rate-plan` expected a top-level `urpx:RatePlan`; modifier-only filings need a parallel `core/load-rate-plan-modifier` entry point. **Resolved** in `clj-urpx@994f2e7`; the filing now load+coerce+validates end-to-end.

3. **Composer** — combining a base RatePlan + modifier(s) into a single bill calculation is deferred until `urpx-org/urpx#23` converges on the consumer convention. The validate harness reports `resolve N/A — modifier requires base composition` for modifier filings.

## Provenance

DCJ-authored, generated from scratch by `scripts/build-cpau-e-2-g-2025-07-01.py` on 2026-04-30. Source PDF retrieved from paloalto.gov via curl_cffi.

## Validation

```
dev/shacl.sh --utility cpau
```

End-to-end via clj-urpx: `clojure -M:validate` reports `load+coerce ✓ (resolve N/A — modifier requires base composition)` — Malli-validates against the `urpx.schema/RatePlanModifier` schema; resolve-prices is correctly skipped pending the base+modifier composer.
