# URPX Usage Report — Modeling four PG&E Residential Tariffs

**Author**: Donald Clark Jackson · `dcj@clark-communications.com`
**Date**: 2026-04-27
**Subject**: Initial-use experience with URPX, ahead of public launch
**Repos**:
- [grid-coordination/urpx-tariffs](https://github.com/grid-coordination/urpx-tariffs) — this report and the four PG&E filings
- [urpx-org/urpx](https://github.com/urpx-org/urpx) — the URPX ontology, SHACL shapes, and test cases
- [grid-coordination/clj-urpx](https://github.com/grid-coordination/clj-urpx) — the Clojure consumer library used to parse + resolve URPX rate plans

---

## 1. Context

This report captures our experience using URPX to model real California utility tariffs over a ~2-day window, ahead of URPX's public launch. We were granted early access and have been working alongside the URPX core team and [Fluxtailor](https://fluxtailor.com) — to whom we are very grateful. URPX is doing important, high-quality work in a domain that has long needed an open, machine-readable standard, and the goal of this report is to support that work: by sharing what we tried, what worked, and where our PG&E conversions surfaced opportunities to extend the vocabulary or strengthen the documentation. URPX's success is our success.

The exercise was concrete: convert the four most-used PG&E residential tariffs to URPX JSON-LD, validate them against the ontology and SHACL, and make them consumable by a downstream price-server library targeting OpenADR 3.

The chain of artifacts:

```
PG&E PDF tariff (CPUC sheet)
    │
    ▼  (this repo: urpx-tariffs)
URPX JSON-LD filing
    │
    ▼  (sibling repo: grid-coordination/clj-urpx)
Clojure data + SHACL-validated price resolution
    │
    ▼  (downstream: clj-price-server)
OpenADR 3 events / prices for VEN-clients
```

[`clj-urpx`](https://github.com/grid-coordination/clj-urpx) is also new — written in the same window. So we exercised both URPX (the standard) *and* a fresh consumer of it. Many findings here are URPX-flavored; some are clj-urpx-flavored. We've tried to keep them straight.

---

## 2. What was produced

Four PG&E residential tariffs, each as a single self-contained JSON-LD file:

| Schedule | Effective | File | Lines | SHACL | clj-urpx |
| --- | --- | --- | ---: | --- | --- |
| **E-1** (default non-TOU) | 2026-03-01 | [`ca/iou/pge/e-1/versions/2026-03-01/rate-plan_pge_e-1_2026-03-01.jsonld`](../ca/iou/pge/e-1/versions/2026-03-01/rate-plan_pge_e-1_2026-03-01.jsonld) | 738 | ✓ | ✓ resolves |
| **E-TOU-C** (default TOU, 4-9 p.m. all days) | 2026-03-01 | [`ca/iou/pge/e-tou-c/versions/2026-03-01/rate-plan_pge_e-tou-c_2026-03-01.jsonld`](../ca/iou/pge/e-tou-c/versions/2026-03-01/rate-plan_pge_e-tou-c_2026-03-01.jsonld) | 1020 | ✓ | ✓ resolves |
| **E-TOU-D** (alternative TOU, 5-8 p.m. weekday non-holiday) | 2026-03-27 | [`ca/iou/pge/e-tou-d/versions/2026-03-27/rate-plan_pge_e-tou-d_2026-03-27.jsonld`](../ca/iou/pge/e-tou-d/versions/2026-03-27/rate-plan_pge_e-tou-d_2026-03-27.jsonld) | 901 | ✓ | ✓ resolves |
| **EV2** (residential plug-in EV) | 2026-03-27 | [`ca/iou/pge/ev2/versions/2026-03-27/rate-plan_pge_ev2_2026-03-27.jsonld`](../ca/iou/pge/ev2/versions/2026-03-27/rate-plan_pge_ev2_2026-03-27.jsonld) | 634 | ✓ | ✓ resolves |

Each filing also carries a [`tariff.toml`](../ca/iou/pge/e-tou-c/versions/2026-03-01/tariff.toml) provenance manifest (canonical PDF URL, sha256, advice letter, regulatory authority, validation metadata) and a [`README.md`](../ca/iou/pge/e-tou-c/versions/2026-03-01/README.md) describing the URPX shape used and any known limitations.

### Conventions we landed on

The repo's [`LAYOUT.md`](../LAYOUT.md) documents these in detail; the load-bearing decisions:

- **One self-contained JSON-LD file per filing**, with `@graph` containing the `RatePlan` + nested `RatePlanVersion` plus any associated `RatePlanModifier` (with nested `RatePlanModifierVersion`) and supporting top-level resources (`ProgramEnrollment` for CARE/FERA). RDF graph-merge handles cross-file overlap if a consumer ever loads multiple filings.
- **Per-utility namespace** under `https://example.com/<utility>/` (placeholder URI; see Recommendation §6.4).
- **Sibling-modifier pattern**: the Vintaged-PCIA modifier ships in the same file as the base RatePlan and references it via `urpx:applicableToRatePlan`. SHACL accepts this in-graph linkage cleanly. Out-of-graph linkage is a separate pain point (see §4).
- **One conditional Price per "tier instance"** (income tier, vintage year, baseline-percent tier × season): we used `ApplicabilityGroup` with `hasInclusionConstraint` / `hasExclusionConstraint` keyed on a customer attribute IRI.

### Validation outputs (representative)

```
$ source ~/env/py/p3newa/bin/activate
$ pyshacl -s ../urpx/shacl/urpx-shacl.ttl \
          -e ../urpx/ontology/urpx-ontology.ttl \
          -df json-ld \
          ca/iou/pge/e-tou-c/versions/2026-03-01/rate-plan_pge_e-tou-c_2026-03-01.jsonld
Validation Report
Conforms: True
```

End-to-end resolution sanity, via clj-urpx 0.3.0:

```
=== E-TOU-D (dayType + holiday-inclusion check) ===
PASS Wed 2026-07-15 18:00 (non-holiday)        -> Summer Peak Period
PASS Sat 2026-07-04 18:00 (weekend)             -> Summer Off-Peak Period
PASS Mon 2026-05-25 18:00 (Memorial Day)        -> Winter Off-Peak Period
PASS Fri 2026-12-25 18:00 (Christmas Day)       -> Winter Off-Peak Period

=== E-1 (tier-stratified resolution check) ===
Conservation Incentive Adjustment -> 6 tier(s)
    tier 1 -0.04052M
    tier 2  0.04089M
    tier 3  0.04089M
    tier 4 -0.04052M
    tier 5  0.04089M
    tier 6  0.04089M
```

---

## 3. What worked well

These features fit our problem cleanly the first time, with no reach for upstream changes.

### 3.1 The hybrid `RatePlan` / `RatePlanVersion` model matches CPUC reality

A CPUC-regulated residential schedule has a stable identity (e.g. "E-TOU-C") that persists across decades, and a stream of immutable filings each effective on a specific date. The two-resource hybrid in URPX maps directly to that. We use the schedule code as the `RatePlan`'s persistent identifier and one `RatePlanVersion` per filing. The `urpx:effectiveDateTime` plus the `tariff.toml` advice-letter ID plus the recorded sha256 give a complete provenance trail back to the regulator's PDF.

### 3.2 SHACL closed shapes caught our errors fast

Every filing went through a tight `pyshacl --shapes urpx-shacl.ttl --ontology urpx-ontology.ttl --data-format json-ld` loop. Most errors we made were caught by SHACL inside seconds. Two notable catches:

- A `RatePlanModifierVersion` is the right host for `urpx:applicableToRatePlan`, not the `RatePlanModifier`. We tried it on the latter first and got a clean violation message ("Node X is closed. It cannot have value..."), which pointed us at the right shape.
- An `EligibilityRule` requires a `hasCustomerProfile` (or `hasServicePointProfile`). When we added a second EligibilityRule for EV2's annual usage cap and forgot the profile reference, SHACL flagged it immediately.

The closed-shape SHACL design caught us early and pointed us straight at the right fix each time — a clear win for the validation experience.

### 3.3 `ApplicabilityGroup` + inclusion/exclusion constraints scale

We used this pattern for three quite-different cases:

- **Income-tier base services charge** (3 conditional Prices): two prices use single inclusion constraints (CARE, FERA); the "everyone else" Tier 3 uses two exclusion constraints (NOT-CARE AND NOT-FERA). This N-1-exclusion pattern motivates urpx-org/urpx#9 (a default-tier or NOT-IN-set operator). (See §4.4.)
- **Vintage PCIA** (18 conditional Prices, one per departure-vintage gYear): each Price has one inclusion constraint with `constraintProperty` = a utility-namespaced datatype property and `constraintValue` = `xsd:gYear`. Verbose but uniform — easy to template.
- **EV2 annual usage cap** (one Condition with comparison operator): see §4.2.

### 3.4 `urpx:includeHolidays` / `urpx:includeNonHolidays`: exactly the right shape for E-TOU-D

This was the most pleasant find of the project. PG&E E-TOU-D's peak window is "5–8 p.m. Monday through Friday, NOT including holidays" — exactly the kind of conjunction that's clumsy to express in many tariff DSLs. URPX expresses it as two boolean properties on `TimeBracket`, and the modeling falls out:

```jsonld
{ "@type": "urpx:TimeBracket", "@id": "pge:time-bracket-summer-peak",
  "urpx:startTime": "17:00:00", "urpx:endTime": "20:00:00",
  "urpx:appliesInSeason": { "@id": "pge:season-summer" },
  "urpx:dayType":           { "@id": "urpx:weekdayDays" },
  "urpx:includeHolidays":   false,
  "urpx:includeNonHolidays": true }
```

A second TimeBracket with `dayType: weekdayDays` + `includeHolidays: true, includeNonHolidays: false` covers the off-peak case for holidays-on-weekdays. **An acknowledgement to the URPX team**: we initially missed these properties on a first read and started filing a "weekday-non-holiday" gap, which a parallel agent in [`urpx-org/urpx`](https://github.com/urpx-org/urpx) quickly pointed out was already covered. The features are well-designed and SHACL-conformant; the existing [test cases](https://github.com/urpx-org/urpx/tree/main/test-cases) happen to use only `urpx:allDays`, so a future test case demonstrating these properties (using a real schedule like E-TOU-D, or a synthetic example) would help others find them on their first pass.

### 3.5 `urpx:applicableToRatePlan` works when the modifier and base RatePlan share a graph

clj-urpx's recent `@graph`-unwrap support and our use of a single `@graph` per filing turn out to play well together: the Vintage-PCIA `RatePlanModifierVersion` can carry `urpx:applicableToRatePlan` pointing at the base `pge:e-tou-c`, and SHACL's class-check is satisfied because the linked RatePlan is fully defined in the same graph. The standalone [`pge-e-tou-c-vintage-pcia-2026-03-01`](https://github.com/urpx-org/urpx/tree/main/test-cases/pge-e-tou-c-vintage-pcia-2026-03-01) test case had to omit this link to validate; we don't, because we keep them together.

### 3.6 `urpx:timezoneIdentifier`

Adding `"urpx:timezoneIdentifier": "America/Los_Angeles"` to the `RatePlan` (and the `RatePlanModifier`) makes the price-server timezone-aware without external configuration. clj-urpx 0.3.0 reads it directly. This is a small property with outsized leverage.

---

## 4. Vocabulary gaps and proposed enhancements

URPX covers most of what we encountered out of the box. The items below describe places where these specific PG&E conversions reached the edge of the current vocabulary; each one is offered as constructive input — concrete tariff text that could inform a future enhancement. For each: the tariff text that triggered it, the expressivity gap, our interim workaround, and where it's tracked upstream.

### 4.1 Baseline-territory matrix (the big one)

**Tariff text** (PG&E E-1 and E-TOU-C, Special Condition 1): A 10-territory × 2-code (B basic / H all-electric) × 2-season (summer/winter) = 40-cell table giving the daily baseline allowance in kWh. The tier *rates* (baseline credit, CIA-baseline, CIA-overbaseline) are scalar — but the *boundaries* between tiers are functions of the customer's territory and code.

**Gap**: `urpx:ServiceTier` requires `xsd:decimal` literals for `lowerBound` and `upperBound`. There is no mechanism to parameterize the bound on customer attributes. To express the full matrix today, the modeler must enumerate every (territory, code, season) cell as its own ServiceTier and replicate every tier-conditional Price for every cell. For E-TOU-C this means 40 ServiceTiers + 120 Prices = ~200 entities; for E-1 (3 tiers × 2 seasons × 40 cells) ~240 entities.

**Workaround**: We produced each affected filing with **one cell modeled** (Territory P, Code B residential — the convention we established earlier in the [`pge-e-tou-c-baseline-tier-2026-03-01`](https://github.com/urpx-org/urpx/tree/main/test-cases/pge-e-tou-c-baseline-tier-2026-03-01) test case). The filing is correct for Territory-P/Code-B customers and incorrect (wrong tier boundaries → wrong CIA price selection) for everyone else. This is the right tradeoff *only* because the upstream issue is in flight — full enumeration would be obviated when it lands.

**Upstream**: [urpx-org/urpx#11](https://github.com/urpx-org/urpx/issues/11) (Parameterized matrix-valued tier bounds). Two of our four PG&E filings (E-TOU-C baseline-credit + CIA modifier, E-1 baseline expansion) carry one-cell representations awaiting this resolution.

This is the single biggest leverage point we found. **Recommendation**: prioritize.

### 4.2 Rolling-window aggregation + percent-of-baseline UoM in Conditions

**Tariff text** (PG&E EV2, Sheet 1):

> Customers taking service on this rate schedule cannot exceed 800% of their annual baseline allowance, measured as the total usage for the customer over the last 12 months divided by the total annual baseline allowance using the approved baseline allowances for those months. Customers ... in excess of 800 percent of baseline over 12 consecutive months [are] removed from Schedule EV2 and will be prohibited from taking service on any electric vehicle rate schedule for 12 months.

**Why it matters to us**: This isn't just regulatory text. A price-server emitting OpenADR 3 events to a VEN-client that knows its own cumulative usage state should be able to *surface this constraint* to the VEN. The VEN can then act on it (warn the user, throttle charging, recommend a switch). Without the constraint in the URPX file, the VEN has no signal.

**Gap**: URPX has the parts but they don't compose. `urpx:Condition` carries operator + value + description + `hasMetricSpecification`, and `urpx:IntervalAlignmentValue` exists with values like `rollingAligned`. But:

1. `IntervalAlignmentValue` isn't exposed on `Condition` or `MetricSpecification` (no place to attach "rolling 12 months" formally).
2. There's no `percentOfBaseline` in `urpx:UnitOfMeasureValue`, nor a generic "as percentage of <reference>" relation.

**Workaround**: An informal `urpx:Condition` with `conditionType: "annualUsageCapAsPercentOfBaseline"` (free string), `operator: lessThanOrEqualOperator`, `conditionValue: "800"`, full prose in `description`, and `hasMetricSpecification` pointing at the kWh energy metric. SHACL conforms. The conditionType string is the contract for any consumer that wants to interpret it. From [`ca/iou/pge/ev2/versions/2026-03-27/rate-plan_pge_ev2_2026-03-27.jsonld`](../ca/iou/pge/ev2/versions/2026-03-27/rate-plan_pge_ev2_2026-03-27.jsonld):

```jsonld
{ "@type": "urpx:Condition", "@id": "pge:condition-annual-usage-cap",
  "urpx:conditionType": "annualUsageCapAsPercentOfBaseline",
  "urpx:operator":      { "@id": "urpx:lessThanOrEqualOperator" },
  "urpx:conditionValue": "800",
  "urpx:hasMetricSpecification": { "@id": "pge:ms-energy" } }
```

**Suggested enhancement**: (a) attach `IntervalAlignmentValue` + `windowDuration` to `Condition`/`MetricSpecification`, and (b) add a `percentOfBaseline` UoM (or a generic ratio-of-reference relation). Once such vocabulary lands, EV2's annual usage cap can be re-expressed formally and the informal `conditionType` string retired.

### 4.3 `ServiceTier` upper-bound for "no upper bound"

A small ergonomic note. The over-baseline tier in E-1 has no upper bound — physically unbounded. URPX requires both `lowerBound` and `upperBound` decimals when ServiceTiers are used in this way. We used `"999999"` as a sentinel, matching the convention we established in the [`pge-e-tou-c-baseline-tier-2026-03-01`](https://github.com/urpx-org/urpx/tree/main/test-cases/pge-e-tou-c-baseline-tier-2026-03-01) test case. A formal "unbounded" indicator down the road — or treating an absent `upperBound` as positive infinity — would be a nice readability improvement when it fits the team's roadmap.

### 4.4 Default-tier ergonomics

Tariffs commonly express "Tier 3: customers who do not qualify for Tier 1 or Tier 2." Modeling this requires the Tier 3 Price to carry as many `hasExclusionConstraint`s as there are sibling tiers (in our case, two: NOT-CARE AND NOT-FERA). With three siblings it's three exclusions, with N siblings it's N-1. The pattern works correctly today; the maintenance impact scales with tier count, since adding a new sibling tier requires updating each default-tier Price.

We previously filed this upstream as [urpx-org/urpx#9](https://github.com/urpx-org/urpx/issues/9). The PG&E conversions reinforce the case: this came up in every PG&E residential filing we did.

### 4.5 Assistance-program category vocabulary

PG&E's Income Tier 2 is published as: "Customers either (a) FERA-enrolled, *or* (b) tenants in qualifying affordable-housing rentals." We model only the FERA branch in the current filings — expressing the second qualification path (a premises attribute, not a program enrollment) and a `urpx:moderateIncomeProgram` enum value for FERA's `programType` would let us cover the OR-path completely.

We previously filed this upstream as [urpx-org/urpx#10](https://github.com/urpx-org/urpx/issues/10). Every CA IOU residential schedule with FERA carries the same pattern, so the case strengthens with each conversion.

### 4.6 Initial-effective-date for long-lived schedules

`urpx:initialEffectiveDate` is required (`minCount 1`) on `RatePlan`. For a schedule like E-1 — in continuous use since at least the 1980s — the original effective date is not easily researchable, and successive restructurings (deregulation, baseline rule changes) raise the reasonable question of "which one do you mean?". We used **2001-01-01** as a placeholder for the post-restructuring modern E-1 era and noted the approximation in the README. A short docs guidance on choosing this date when historical specificity isn't recoverable would help future modelers handle long-lived schedules consistently.

### 4.7 Sheet-level base-charge unbundling: a fidelity decision worth documenting

PG&E publishes the daily base services charge in two ways: as a tier-total per income tier (3 numbers), AND as a 4-component breakdown (Distribution / PPP / Nuclear / NSGC × 3 tiers = 12 numbers, summing to the totals). URPX flexibly accepts either modeling — which is the right design call. We chose totals-only for all four filings (3 conditional Prices per filing), prioritizing readability over per-component visibility. A short docs note describing this kind of decision (with a worked example) would be helpful for first-time modelers, since each modeler currently makes the call independently.

---

## 5. Issues in `clj-urpx` (our consumer library) that these conversions surfaced

Worth highlighting because it's a clean demonstration of the URPX-data → consumer-library feedback loop. [`clj-urpx`](https://github.com/grid-coordination/clj-urpx) is our own library, written in the same window as the conversions; every commit is ours. The conversions **directly surfaced two specific issues** that hadn't been hit yet on synthetic test fixtures:

| Surfaced by | Description | Resolved |
| --- | --- | --- |
| E-TOU-D | `dayType` vocabulary mismatch with the URPX ontology (clj-urpx used `urpx:weekday`/`urpx:weekend`/`urpx:holiday`; the ontology defines `urpx:weekdayDays`/`urpx:weekendDays` and no `urpx:holiday`). Holiday-inclusion gates also weren't honored. | clj-urpx [`691acde`](https://github.com/grid-coordination/clj-urpx/commit/691acde68853ea2f4eec1202f9fdf414ff4f6f10) (0.2.0) |
| E-1 | `resolve-prices` exposed only one tier-Price per `PriceDefinition`, hiding the tier-stratified prices required for E-1's CIA structure | clj-urpx [`0d84c2d`](https://github.com/grid-coordination/clj-urpx/commit/0d84c2df7a50c8783d895ad0ca12c1ff018b23c6) (0.3.0) |

Both were straightforward to identify *because* the input was a real published tariff. clj-urpx's other 0.2.0 / 0.3.0 work (`urpx:timezoneIdentifier` reading, `@graph` auto-unwrap, RatePlanModifier overrides during resolution, opt-in timezone inference) was independent feature work but landed in the same window — the four filings benefit directly. Empirical pre/post evidence is in the conversion-session transcripts; for example, after the dayType + tier-stratified resolution fixes landed:

```
PASS Wed 2026-07-15 18:00 (non-holiday peak hour) -> Summer Peak Period
PASS Sat 2026-07-04 18:00 (weekend)               -> Summer Off-Peak Period
PASS Mon 2026-05-25 18:00 (Memorial Day, holiday) -> Winter Off-Peak Period
PASS Fri 2026-12-25 18:00 (Christmas, holiday)    -> Winter Off-Peak Period
PASS Tue 2026-12-22 18:00 (non-holiday peak hour) -> Winter Peak Period
PASS Sun 2026-12-20 18:00 (weekend)               -> Winter Off-Peak Period
PASS Wed 2026-07-15 10:00 (weekday morning)       -> Summer Off-Peak Period

E-1 CIA ledger: 6 tiers exposed, unit prices [-0.04052, 0.04089, 0.04089, -0.04052, 0.04089, 0.04089]
```

A modest takeaway worth sharing with the URPX team for launch planning: real tariff data flowing through a real consumer chain is uniquely effective at exposing assumptions. The existing [test cases](https://github.com/urpx-org/urpx/tree/main/test-cases) in the URPX repo are excellent fixtures; pairing them with end-to-end conversions of full tariffs (as we've been doing) seems to surface a complementary set of edge cases. If it would help, we're happy to keep contributing this kind of feedback.

---

## 6. Suggested upstream priorities, from our perspective

Offered as input to the team's roadmap, ranked by how often these came up in our PG&E conversions × leverage on cleanup. We trust the URPX team's overall prioritization and offer this purely as one consumer's view. URPX issue numbers from `urpx-org/urpx` referenced where known.

### 6.1 [urpx-org/urpx#11](https://github.com/urpx-org/urpx/issues/11) — Parameterized matrix-valued tier bounds

Hits every CA IOU residential schedule with a baseline structure. Without it, every such filing carries a one-cell-modeled disclaimer. Resolving this single issue unblocks the deferred work in two of our four PG&E filings (E-TOU-C baseline modifier and E-1 full matrix expansion).

**Note on `PriceSetAlternatives`**: URPX already has a vocabulary (`urpx:PriceSetAlternatives` / `urpx:ProfileAlternative` / `urpx:AlternativeDimension`) that organizes alternative price sets keyed on customer-profile dimensions like territory and code. We investigated whether it could replace the need for #11. It provides a clean discoverable shape for the matrix but does not reduce the per-cell entity count — 40 cells still produce ~200 entities, just better-organized. The leverage move is still parameterizing the bound itself based on customer attributes (#11), but adopting `PriceSetAlternatives` as the organizing structure for the eventual full enumeration would be an improvement over scattered ServiceTier definitions in the meantime.

### 6.2 Rolling-window aggregation + percent-of-baseline UoM in Conditions

Surfaced by EV2 but applies to many EV-charging programs, demand-response thresholds, and any tariff with a usage-history-based eligibility constraint. The gap blocks meaningful round-trip from URPX → OpenADR 3 events for these constraints. See §4.2 for the concrete tariff text and the suggested enhancement; happy to file a GitHub issue at the URPX team's request.

### 6.3 [urpx-org/urpx#9](https://github.com/urpx-org/urpx/issues/9) — Default-tier ("everyone else") ergonomics

N-1 exclusion is workable, with maintenance impact that scales with tier count. Our four filings together carry 12 N-1 expressions; that count grows linearly with both filings and tier count.

### 6.4 [urpx-org/urpx#10](https://github.com/urpx-org/urpx/issues/10) — Assistance-program category vocabulary

Blocks expressing CARE / FERA / affordable-housing-tenant qualification semantics fully. Affects every CA IOU (PG&E, SCE, SDG&E) plus the muni POU equivalents.

### 6.5 Documentation: self-contained-file pattern with `@graph`

Our convention of putting the `RatePlan` + `RatePlanModifier`(s) + `ProgramEnrollment`s in a single `@graph` per filing is not currently surfaced anywhere in URPX docs or test cases. It worked well for us and unlocked the in-graph `applicableToRatePlan` reference. **Recommendation**: add to the URPX tutorial.

### 6.6 Documentation: when a tariff is published at multiple levels of unbundling, which level should URPX modelers pick?

See §4.7. A short note in the docs would prevent every modeler from deriving the same trade-off independently.

### 6.7 Test case suggestion: showcase `urpx:includeHolidays` / `urpx:includeNonHolidays`

See §3.4. The URPX tutorial demonstrates these properties (in the TOU section), so the feature is documented. What's missing is a presence in the [`test-cases/`](https://github.com/urpx-org/urpx/tree/main/test-cases) corpus, which is what consumers tend to grep first when looking for "how URPX is used in practice." Adding a test case (e.g. PG&E E-TOU-D, or a synthetic example) there would catch readers like ourselves who reached for fixtures before reading the tutorial. Happy to contribute one if useful.

---

## 7. Closing

URPX held up well under genuine use. The vocabulary covered roughly 80% of what we encountered out of the box, and the remaining gaps (matrix tier bounds, rolling-window aggregation) are well-scoped and supported by concrete tariffs. Of the two upstream URPX gaps we surfaced during these conversions, one (the rolling-window / percent-of-baseline vocabulary) is genuinely new and was surfaced by EV2's annual usage cap; the other (a "weekday-non-holiday" gap) we mistakenly thought existed but was already covered by `urpx:includeHolidays` / `urpx:includeNonHolidays` — a useful illustration of how careful the URPX team has been in covering common cases.

A second pass through the URPX tutorial after writing this report turned up two more features we had missed and could profitably adopt: `urpx:HolidayCalendar` / `urpx:Holiday` for embedding the named PG&E holidays directly in our E-TOU-D filing (rather than relying on the consumer to supply a runtime predicate), and `urpx:PriceSetAlternatives` as an organizing structure for the eventual baseline-territory matrix expansion. We've added these to our local follow-up backlog. The pattern — URPX covers more than the existing fixture corpus suggests, and reading the tutorial pays dividends — is consistent with the false-alarm we filed earlier in the same window (the "weekday-non-holiday" gap mentioned above).

What we'd do next, if scope expands:

- **Other CA IOUs**: SCE and SDG&E publish residential tariffs with the same baseline-territory shape — they'll inherit any [urpx-org/urpx#11](https://github.com/urpx-org/urpx/issues/11) resolution cleanly.
- **Commercial schedules**: A-1, A-6, A-10, E-19, E-20 — different shape (TOU + demand charges instead of baseline tiers). Will surface a different set of vocabulary needs (likely demand charges, ratchets, etc.).
- **CA POUs**: SMUD, LADWP, CPAU. Different regulatory posture (city council instead of CPUC), different filing cadence, but the URPX core should fit.
- **Tariff modifiers** (NEM successor tariff, SmartRate, Medical Baseline, climate credit details): each is small individually but introduces URPX features we haven't yet exercised (probably `RatePlanModifier` patterns at scale).

We're happy to keep the [grid-coordination/urpx-tariffs](https://github.com/grid-coordination/urpx-tariffs) corpus growing as URPX evolves, and to keep contributing real-world feedback like this report — whatever's most useful to the team.

Sincere thanks to the URPX core team and [Fluxtailor](https://fluxtailor.com) for the early access, the careful design of the ontology and shapes, and the quick collaboration on issues during this window. URPX is the standard this domain has needed, and we're rooting for the launch.

— DCJ
