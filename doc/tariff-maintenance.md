<!-- SPDX-FileCopyrightText: 2026 Clark Communications Corporation -->
<!-- SPDX-License-Identifier: CDLA-Permissive-2.0 -->

# Keeping the corpus current

A tariff corpus is a sample of a stream. Utilities file continuously; this repository captures a document now and then. Every gap in `reports/version-continuity.md` is the arithmetic of that: the sample rate is slower than the filing rate.

Measured 2026-09-22: every filing's source was last checked between 116 and 260 days ago, median 145. Eight gaps totalling 572 days follow from that, and from the fact that nobody is watching in between.

## A gap report is a post-mortem

By the time a gap appears, a consumer already cannot price that period. Worse, until the superseded version carries `urpx:expirationDateTime` the gap is invisible: the old filing answers anyway, with rates that stopped applying, and nothing says so. Bounding converts a silent wrong answer into a visible absence, which is strictly better and still not prevention.

So the gap list is the backlog, not the alarm.

## Why the corpus cannot forecast its own maintenance

The obvious idea is to project the next filing from observed intervals between versions. It fails twice over, and the reasons are worth stating so nobody builds it.

**Filings are not periodic.** They are events: a general rate case concludes, the Commission issues a decision, a cost-recovery balancing account is trued up, a fuel adjustment lands. Intervals between the filings this corpus happens to hold run 161, 45 and 125 days for SCE and 14, 62, 59 and 26 for PG&E. Some implement a Commission decision and arrive when that decision does (AL 7869-E carries D.26-03-013); others are utility-initiated and arrive on the utility's own timetable. There is no period to fit, so a model that assumes one is wrong before it sees any data.

**And the data would be the wrong data anyway.** Version effective dates record when *we captured* a filing, not when the utility made one. Estimating filing cadence from them estimates this repository's sampling rate. The medians come out at 517 days for CPAU, 570 for SMUD and 6,421 for LADWP: facts about our history, not about any utility's behaviour.

So the polling schedule is regular precisely because the filings are not. You cannot time a check to an event you cannot predict; you check often enough that any event is caught soon after it happens. The only genuine forward signal is an effective date a utility has already published, which is the next section.

## What the source actually offers

Each `utility.toml` already records the canonical discovery URLs (six for SCE, five for SDG&E, and so on), and each `tariff.toml` records its source `url`, `sha256` and `retrieved_on`. That is enough for a polling loop:

1. **Re-fetch** each canonical URL and compare `sha256` against the manifest. Unchanged means nothing to do, and is the common case.
2. **When it changes**, read the sheet headers. Each carries its own revision number, the number it cancels, its advice letter and its effective date. Comparing the live sheet numbers against the ones in the filing we hold says exactly which of our filings is now behind.
3. **Read the effective dates forward.** An advice letter's effective date is usually in the future when the sheet is published, so this is the one genuine forecast available: not an extrapolation, a date the utility has already committed to.

Lead time is real but short and uneven. AL 5654-E was submitted 2025-10-16 for a 2025-11-15 effective date, thirty days. AL 5725-E was submitted 2025-12-30 for 2026-01-01, two days. So polling buys small gaps rather than no gaps, and the realistic target is a sampling interval short enough that any gap is a few weeks rather than a few months.

## Why a missed filing is backlog and not a firedrill

Superseded sheets stay published. `us/ca/sce/utility.toml` records the per-year historical archive, and the other utilities keep equivalents. A gap discovered today can be closed by fetching a document that still exists, on whatever schedule suits, and the result is as correct as it would have been if captured on the day.

That is what makes this safe to run as a queue rather than an incident. Nothing is lost by noticing late, provided the corpus does not meanwhile assert something false about the period it missed. Bounding is what buys that.

## What each piece is for

| Piece | Answers | Prevents a gap? |
| --- | --- | --- |
| `urpx:expirationDateTime` on superseded versions | when a version stopped applying | No. Makes the absence visible instead of silently wrong. |
| `reports/version-continuity.md` gaps | which periods we cannot price | No. It is the backfill queue. |
| `reports/version-continuity.md` overlaps | two versions in force at once | Not a gap; a modeling error. Fails the gate. |
| Source age column | how long since we looked | Partly. The only leading indicator available offline. |
| Polling the discovery URLs | what changed upstream, and when it takes effect | Yes. The only thing here that does. |

## Sketch: the loop that would do this

The loop itself does not belong in this repository. This repository is the corpus; the scraper is a service with a schedule, a queue and a failure mode of its own. What belongs here is the sketch and the obligations it places on the corpus, so that when the loop is built it does not need this repository to change shape.

```
  cron (daily or weekly)
    |
    v
  for each utility.toml discovery URL
    fetch -> sha256
    |
    +-- unchanged -> record the check, done.       <- the common case
    |
    +-- changed   -> parse sheet headers:
                       own revision no.
                       cancelled revision no.
                       advice letter
                       effective date            <- often in the future
                     diff against the sheets our filings hold
                     |
                     v
                   enqueue one work item per affected schedule
```

A work item is small and self-describing: the utility, the schedule, the new sheet numbers, the sheets they cancel, the advice letter, the effective date, and the URL and digest of the document. It carries a date the change takes effect, which is what lets the queue be prioritized rather than drained in order: an item effective next week outranks one effective next quarter.

Draining an item is the existing §9 workflow in `LAYOUT.md`, which already ends with bounding the filing the new one supersedes. The queue supplies the trigger and the provenance; nothing about modeling changes.

Two properties worth designing in from the start. The loop must be **idempotent**, because a weekly cron over an unchanged page is the normal case and must cost nothing and enqueue nothing. And an item must be **closeable as "no model change"**, because many reissues touch only special-condition sheets; recording that we looked and decided nothing was needed is what stops the same sheet being re-queued forever.

## What the corpus owes that loop

Most of it is already here, which is the point of writing this down now rather than later.

- **Discovery URLs**, in each `utility.toml`. Present for all six utilities.
- **A digest per source**, in each `tariff.toml` as `source.sha256`, so "has it changed" is one comparison. Present.
- **A last-checked date**, as `source.retrieved_on`. Present, and surfaced in `reports/version-continuity.md` so staleness is visible without a fetch.
- **The sheet numbers a filing holds.** NOT present. Today they can only be recovered by re-parsing the committed PDF, which the loop can do but should not have to. Recording the live sheet revisions per filing in `tariff.toml` would let the diff happen against the manifest alone. That is the one addition this loop would want.
- **A statement of what a filing ends.** Partly present: `urpx:expirationDateTime` gives the date. The cancellation itself, which is what the source states and what the loop reads, has nowhere to go. See `LAYOUT.md` §10.

## What a consumer owes it

A consumer has to be able to ask a time-scoped question and get a refusal rather than a guess. clj-urpx supplies the mechanism: `urpx.index/versions-by-plan` offers every version of a plan, and the resolver takes the one in force at the instant or refuses by name.

One defect to fix before relying on that, found while writing this. Version windows are compared in wall-clock terms, against `(.toLocalDateTime zdt)`, so the answer depends on the caller's timezone rather than on the instant. Asked for `sce:d-2025-11-15` at one real moment expressed two ways, `2025-12-31T20:00-08:00` prices at 0.32062 and the identical instant as `2026-01-01T04:00Z` refuses with `:outside-version-window`. A horizon walk in UTC would therefore change version up to eight hours early at every boundary.

The fix is available without touching the corpus, because a document already states its own zone. `urpx:timezoneIdentifier` is present on all 72 filings, carried on the `urpx:RatePlan` in 39 and the `urpx:RatePlanModifier` in 41, so both halves of a composition can be zoned rather than only the base. A version reaches it through the `urpx:forRatePlan` / `urpx:forRatePlanModifier` link it is already required to carry, which is the same link `urpx.index/versions-by-plan` keys on, so the plan node is in hand wherever the window is built. Parsing is not the obstacle; `ZonedDateTime/parse` throws on the corpus's naive form and `LocalDateTime/parse` plus `.atZone` does not. Writing offsets into the corpus instead would work for a single instant but bakes a resolved offset in place of a zone, and would have to be recomputed across daylight saving.

## What a consumer should do

Refuse rather than publish. A price server asked for a price in an uncovered period should say it cannot answer, not fall back to the nearest version it holds. clj-urpx already behaves this way once the bounds are present: `urpx.index/versions-by-plan` offers every version of a plan and the resolver takes the one in force at the instant, or refuses by name.

That is the whole payoff of bounding. Without it the same request returns a number, and the number is wrong.
