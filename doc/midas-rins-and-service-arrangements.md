<!-- SPDX-FileCopyrightText: 2026 Clark Communications Corporation -->
<!-- SPDX-License-Identifier: CDLA-Permissive-2.0 -->

# What a MIDAS RIN identifies

California's Market Informed Demand Automation Server publishes electricity prices keyed by a Rate Identification Number. A RIN is widely treated as naming a tariff. It does not. It names a **service arrangement**: a base rate plan composed with the particular overlays and supply arrangement a customer actually has.

That distinction decides where a RIN can be recorded in a URPX document, and getting it wrong produces assertions that validate cleanly and are false. This note sets out the evidence, because the point is not obvious and we got it wrong ourselves first.

Every figure below is derived from a snapshot of 5,207 MIDAS rate identifiers taken 2026-05-30, held at `reports/midas-coverage.json`.

## A rate plan has many RINs

PG&E's E-TOU-D is one rate plan. MIDAS publishes eighteen RINs for it:

```
USCA-PGPG-0200-0000  E-TOU-D                                   USCA-PGXX-0200-0000  E-TOU-D-CCA
USCA-PGPG-0201-0000  E-TOU-D-Smart Rate                        USCA-PGXX-0202-0000  E-TOU-D-CCA-CARE
USCA-PGPG-0202-0000  E-TOU-D-CARE                              USCA-PGXX-0203-0000  E-TOU-D-CCA-FERA
USCA-PGPG-0203-0000  E-TOU-D-FERA                              USCA-PGXX-0204-0000  E-TOU-D-CCA-Medical Baseline
USCA-PGPG-0204-0000  E-TOU-D-Medical Baseline                  USCA-PGXX-0210-0000  E-TOU-D-CCA-Medical Baseline-CARE
USCA-PGPG-0205-0000  E-TOU-D-Smart Rate-Medical Baseline       USCA-PGXX-0211-0000  E-TOU-D-CCA-Medical Baseline-FERA
USCA-PGPG-0206-0000  E-TOU-D-Smart Rate-CARE
USCA-PGPG-0207-0000  E-TOU-D-Smart Rate-FERA
USCA-PGPG-0208-0000  E-TOU-D-Smart Rate-CARE-Medical Baseline
USCA-PGPG-0209-0000  E-TOU-D-Smart Rate-FERA-Medical Baseline
USCA-PGPG-0210-0000  E-TOU-D-Medical Baseline-CARE
USCA-PGPG-0211-0000  E-TOU-D-Medical Baseline-FERA
```

They are the cross product of four independent facts about the customer: supply arrangement, discount program (none, CARE or FERA), medical baseline status, and Smart Rate enrollment. Overlays stack up to three deep. CARE and FERA never co-occur, which is correct: the programs are mutually exclusive.

A regulator identifying the plan would have issued one RIN. Eighteen exist because the published price differs by customer, and the RIN names the customer's arrangement.

## The four-character segment encodes the parties, not a price component

`USCA-PGXX-0200-0000` decomposes as country/state, a four-character party segment, a rate identifier, and a sub-identifier.

The party segment is two two-character codes. Measured across all 5,207 records:

- **The first pair is always the distribution utility.** It matches the utility on every record, 0 exceptions.
- **The second pair is the energy supplier.** Where it repeats the utility (`PGPG`, `SCSC`, `SDSD`) the utility supplies both delivery and generation: a bundled customer. Where it is `XX` the customer's generation comes from elsewhere, so the rate covers delivery only.

The evidence for the second half is asymmetric and worth stating precisely. Of 3,466 records whose second pair names the utility, **zero** carry CCA or Direct Access in their name. Of 1,741 records whose second pair is `XX`, 99 say CCA or DA explicitly and the rest carry no name at all. So `XX` is necessary for non-utility supply; the name field simply often does not say.

Only six segments occur: `PGPG`, `PGXX`, `SCSC`, `SCXX`, `SDSD`, `SDXX`. **No segment begins with `XX`.** A code such as `XXSD`, which would mean SDG&E supplying generation over another utility's wires, appears zero times.

## Why this forbids recording a RIN as a plan or modifier identifier

URPX v0.5.1 admits `urpx:hasIdentifier` on `RatePlan`, `RatePlanVersion`, `RatePlanModifier`, `RatePlanModifierVersion` and `OrganizationIdentity`. None of those is a composition. `urpx:RatePlan` is the plan identity, whose `skos:note` reads "The stable identifier. No pricing content"; `urpx:RatePlanVersion` is that identity's snapshot for a window.

So attaching `USCA-PGPG-0202-0000` to `pge:e-tou-d` would assert that the unmodified plan is identified by a code that identifies the plan plus CARE. Attaching it to the CARE modifier would assert that CARE alone is identified by a code that also names E-TOU-D. Both validate: `RatePlanIdentifierShape` and `RatePlanModifierIdentifierShape` are `sh:closed` over exactly `skos:notation`, `urpx:scheme` and `urpx:identifierJurisdiction`, so there is no slot in which to record what the identifier is scoped to.

This corpus therefore records RINs beside arrangements rather than inside filings, in `reports/rate-identifiers.{md,edn}`, keyed by the arrangement's intrinsic identity: base version IRI, sorted modifier version IRIs, sorted alternative selections.

## A RIN is an attestation, not an identity

An arrangement exists whether or not a RIN can be found for it. Deriving which tariff documents and features compose to produce the prices a given RIN covers is straightforward in some cases and intractable in others, and MIDAS itself is incomplete. A RIN is therefore recorded with its provenance: corroborated against the published feed, derived but uncorroborated, or unresolved. The third is a legitimate resting state.

Where a RIN is attached it asserts that our composition is the same thing the state means by that code. That claim is falsifiable and will occasionally be wrong, so what is recorded is how the correspondence was established, not only the value.

## What we got wrong

Two errors of our own, both from reading the second segment as a price component rather than as the energy supplier.

**Five SDG&E net-billing RINs of the form `USCA-XXSD-NB*` were recorded as a "Generation EEC" family.** No `XX`-first segment exists in MIDAS. The generation component is not published separately at all; where it is needed it must be derived by subtracting the delivery-only rate from the bundled rate, which is the method this corpus already records for SCE and then contradicted for SDG&E.

**Four PG&E RINs of the form `USCA-PGXX-*` were attached to prices serving bundled customers as well as CCA customers,** on the recorded reasoning that the underlying delivery values are identical. Equal prices do not make it the same arrangement. `PGXX` names the arrangement of a customer whose generation comes from elsewhere, and a bundled customer is not that customer even when the delivery charge matches.

Both errors were caught before the RINs were promoted into machine-readable identifiers, which is the practical argument for the rule above: prose that is wrong is a note to correct, and an identifier that is wrong is an assertion other systems act on.
