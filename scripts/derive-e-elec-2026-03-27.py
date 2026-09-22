#!/usr/bin/env python3
"""
Derive ca/iou/pge/e-elec/versions/2026-03-27/rate-plan_pge_e-elec_2026-03-27.jsonld
from the existing 2026-01-01 filing.

Reflects PG&E's reissue of E-ELEC under AL 7869-E / Decision D.26-03-013,
effective 2026-03-27 — the same advice letter that did E-TOU-C / E-TOU-D /
EV2's 2026-03-27 reissue (income-tiered base services charge introduced,
California Climate Credit removed).

Transformations:
  - RPV @id: pge:e-elec-2026-01-01 → pge:e-elec-2026-03-27
  - effectiveDateTime: 2026-03-27T00:00:00
  - hasRateCase: pge:rc-d-26-03-013 (replacing pge:rate-case-2025 / A2409015)
  - TariffPublication: TWO publications declared in @graph
      pge:al-7869-e — issues the new rate version (Sheet 2)
      pge:al-7846-e — issues most other sheets
  - Add 5 ProgramEnrollment instances (CARE/FERA/CCA/DA/TBS) to @graph
    (CARE/FERA needed for new income-tier ApplicabilityGroups; CCA/DA/TBS
    carried for parity with other PG&E filings even though E-ELEC's existing
    fixture didn't model vintage-PCIA)
  - Replace flat $0.49281/meter/day base services charge with 3 income-tier
    prices and ApplicabilityGroups (CARE inclusion, FERA inclusion, NOT-CARE-
    AND-NOT-FERA via BooleanOperationNode)
  - Update all energy rate values per Sheet 2 + Sheet 3 of the new PDF
  - Drop California Climate Credit (ledger, PriceDefinition, Price, household-
    count MetricInput) — Sheet 2 of the new PDF removes it
"""
import json
from pathlib import Path

ROOT = Path(str(Path(__file__).resolve().parent.parent))
SRC = ROOT / "ca/iou/pge/e-elec/versions/2026-01-01/rate-plan_pge_e-elec_2026-01-01.jsonld"
OUT = ROOT / "ca/iou/pge/e-elec/versions/2026-03-27/rate-plan_pge_e-elec_2026-03-27.jsonld"

# Sheet 3 unbundled per-kWh rates ($)
UNBUNDLED_RATES = {
    # by PriceDefinition @id → unitPrice
    "pge:pd-gen-summer-peak":           "0.26299",
    "pge:pd-gen-summer-part-peak":      "0.16388",
    "pge:pd-gen-summer-off-peak":       "0.11878",
    "pge:pd-gen-winter-peak":           "0.10086",
    "pge:pd-gen-winter-part-peak":      "0.08089",
    "pge:pd-gen-winter-off-peak":       "0.06754",
    "pge:pd-dist-summer-peak":          "0.23199",
    "pge:pd-dist-summer-part-peak":     "0.16922",
    "pge:pd-dist-summer-off-peak":      "0.15764",
    "pge:pd-dist-winter-peak":          "0.16261",
    "pge:pd-dist-winter-part-peak":     "0.16049",
    "pge:pd-dist-winter-off-peak":      "0.15998",
    "pge:pd-transmission":              "0.04638",
    "pge:pd-transmission-adj":          "0.00453",
    "pge:pd-reliability":               "0.00013",
    "pge:pd-public-purpose":            "0.00614",
    "pge:pd-nuclear":                   "-0.00002",
    "pge:pd-ctc":                       "0.00027",
    "pge:pd-energy-cost-recovery":      "0.00002",
    "pge:pd-wildfire-fund":             "0.00591",
    "pge:pd-new-sys-gen":               "0.00000",
    "pge:pd-wildfire-hardening":        "0.00391",
    "pge:pd-recovery-bond":             "0.00857",
    "pge:pd-recovery-bond-credit":      "-0.00857",
    "pge:pd-bundled-pcia":              "-0.01011",
}


def cn_equals_object(cn_id, prop_iri, value_iri):
    return {
        "@type": "urpx:ComparisonNode", "@id": cn_id,
        "urpx:operator": {"@id": "urpx:equalsOperator"},
        "urpx:leftOperand": {"@type": "urpx:ObjectOperandNode", "urpx:conditionProperty": {"@id": prop_iri}},
        "urpx:rightOperand": {"@type": "urpx:ObjectOperandNode", "urpx:referencesValue": {"@id": value_iri}},
    }


def cn_not_equals_object(cn_id, prop_iri, value_iri):
    n = cn_equals_object(cn_id, prop_iri, value_iri)
    n["urpx:operator"] = {"@id": "urpx:notEqualsOperator"}
    return n


def expr_single(cx_id, root_node):
    return {"@type": "urpx:ConditionExpression", "@id": cx_id, "urpx:rootNode": root_node}


def boolop(bn_id, op, operands, logic_expression=None):
    n = {
        "@type": "urpx:BooleanOperationNode", "@id": bn_id,
        "urpx:operator": {"@id": f"urpx:{op}Operator"},
        "urpx:operandNodes": operands,
    }
    if logic_expression:
        n["urpx:logicExpression"] = logic_expression
    return n


def main():
    data = json.loads(SRC.read_text())
    # Ensure xsd:date mapping for urpx:dateReceived (the 2026-01-01 source's
    # @context didn't have it because no entity used the property)
    ctx = data["@context"]
    if "urpx:dateReceived" not in ctx:
        ctx["urpx:dateReceived"] = {"@type": "xsd:date"}
    graph = data["@graph"]
    rate_plan = next(n for n in graph if n.get("@type") == "urpx:RatePlan")
    rpv = rate_plan["urpx:hasRatePlanVersion"]
    prog_enrollment = "urpx:hasProgramEnrollment"

    # ── 1. Add ProgramEnrollment instances + RateCase + TariffPublications ────
    new_entities = [
        {"@type": "urpx:ProgramEnrollment", "@id": "pge:program-care",
         "urpx:programName": "California Alternate Rates for Energy (CARE)",
         "urpx:programType": {"@id": "urpx:lowIncomeProgram"}},
        {"@type": "urpx:ProgramEnrollment", "@id": "pge:program-fera",
         "urpx:programName": "Family Electric Rate Assistance (FERA)"},
        {"@type": "urpx:ProgramEnrollment", "@id": "pge:program-cca",
         "urpx:programName": "Community Choice Aggregation (CCA)",
         "urpx:programType": {"@id": "urpx:communityChoiceAggregation"}},
        {"@type": "urpx:ProgramEnrollment", "@id": "pge:program-da",
         "urpx:programName": "Direct Access (DA)"},
        {"@type": "urpx:ProgramEnrollment", "@id": "pge:program-tbs",
         "urpx:programName": "Transitional Bundled Service (TBS)"},
        {"@type": "urpx:RateCase", "@id": "pge:rc-d-26-03-013",
         "urpx:caseNumber": "D.26-03-013",
         "urpx:name": "CPUC Decision D.26-03-013",
         "urpx:url": "https://docs.cpuc.ca.gov/PublishedDocs/Published/G000/M999/K999/26-03-013.PDF"},
        {"@type": "urpx:TariffPublication", "@id": "pge:al-7869-e",
         "urpx:name": "PG&E Advice Letter 7869-E",
         "urpx:filingNumber": "7869-E",
         "urpx:issuingAuthority": "California Public Utilities Commission",
         "urpx:publicationType": {"@id": "urpx:regulatoryFiling"},
         "urpx:description": "CPUC Decision D.26-03-013 — Sheet 2 reissue introducing income-tiered base services charge and removing California Climate Credit",
         "urpx:effectiveDate": "2026-03-27",
         "urpx:dateReceived": "2026-03-27",
         "urpx:hasRatePlan": {"@id": "pge:e-elec"}},
        {"@type": "urpx:TariffPublication", "@id": "pge:al-7846-e",
         "urpx:name": "PG&E Advice Letter 7846-E",
         "urpx:filingNumber": "7846-E",
         "urpx:issuingAuthority": "California Public Utilities Commission",
         "urpx:publicationType": {"@id": "urpx:regulatoryFiling"},
         "urpx:effectiveDate": "2026-03-01",
         "urpx:dateReceived": "2026-02-27",
         "urpx:hasRatePlan": {"@id": "pge:e-elec"}},
    ]
    # Drop the old RateCase (pge:rate-case-2025) since the rate update is under D.26-03-013
    # (Old fixture had pge:rate-case-2025 nested inside RPV; we'll regenerate below)
    # Keep the @graph clean — we'll prepend new entities and the existing RatePlan
    graph[:] = new_entities + [rate_plan]

    # ── 2. Update RPV: @id, effective date, hasRateCase ──────────────────────
    rpv["@id"] = "pge:e-elec-2026-03-27"
    rpv["urpx:effectiveDateTime"] = "2026-03-27T00:00:00"
    rpv["urpx:hasRateCase"] = {"@id": "pge:rc-d-26-03-013"}
    # Update the description to mention the AL 7869-E reissue
    rpv["urpx:description"] = (
        "Optional residential TOU schedule for customers with qualifying electric technologies "
        "(EV charging, energy storage, electric heat pump) or NBT enrollment. Reissued under PG&E "
        "Advice Letter 7869-E (CPUC Decision D.26-03-013) effective 2026-03-27. Substantive change "
        "from the 2026-01-01 version: income-tiered base services charge introduced (CARE/FERA/Tier-3 "
        "with same values as E-TOU-C / E-TOU-D / EV2 / E-1); California Climate Credit removed; "
        "minor energy-rate updates per Sheet 2 + Sheet 3."
    )
    # Update DataSourceReference's TariffBookReference leafEnd
    dsr = rpv.get("urpx:hasDataSourceReference", {})
    tbr = dsr.get("urpx:hasTariffBookReference", {})
    if tbr:
        tbr["urpx:leafStart"] = "61116-E"
        tbr["urpx:leafEnd"] = "61248-E"
    if "urpx:dateRetrieved" in dsr:
        dsr["urpx:dateRetrieved"] = "2026-04-29"

    # ── 3. Update energy rate values (loop over Prices in PriceSets) ─────────
    prices = rpv["urpx:hasPrices"]
    applied = set()
    for ps in prices.get("urpx:hasPriceSet", []):
        for p in ps.get("urpx:hasPrice", []):
            pd_ref = p.get("urpx:referencesPriceDefinition", {}).get("@id")
            if pd_ref in UNBUNDLED_RATES:
                p["urpx:unitPrice"] = UNBUNDLED_RATES[pd_ref]
                applied.add(pd_ref)
    # A key that matches no PriceDefinition leaves the source filing's value in
    # place and says nothing. That is how New System Generation shipped at the
    # 2026-01-01 value of $0.00792 when Sheet 3 prices $0.00000: the key read
    # "pge:pd-new-system-generation" and the PriceDefinition is
    # "pge:pd-new-sys-gen", so 24 of 25 updates applied and the 25th was silent.
    unapplied = sorted(set(UNBUNDLED_RATES) - applied)
    if unapplied:
        raise RuntimeError(
            "these UNBUNDLED_RATES keys matched no PriceDefinition, so their "
            "Sheet 3 values were not applied: " + ", ".join(unapplied))

    # ── 4. Drop California Climate Credit ────────────────────────────────────
    # 4a. Drop top-level Price
    prices["urpx:hasPrice"] = [
        p for p in prices.get("urpx:hasPrice", [])
        if p.get("@id") != "pge:price-climate-credit"
    ]
    # 4b. Drop the climate-credit Ledger
    pe = rpv["urpx:hasPlanElements"]
    bm = pe["urpx:hasBillingModel"]
    bm["urpx:hasLedger"] = [
        l for l in bm.get("urpx:hasLedger", [])
        if l.get("@id") != "pge:ledger-climate-credit"
    ]
    # 4c. Drop the climate-credit PriceDefinition
    bm["urpx:hasPriceDefinition"] = [
        pd for pd in bm.get("urpx:hasPriceDefinition", [])
        if pd.get("@id") != "pge:pd-climate-credit"
    ]
    # 4d. Drop the household-count MetricInput
    pe["urpx:hasMetricInput"] = [
        mi for mi in pe.get("urpx:hasMetricInput", [])
        if mi.get("@id") != "pge:mi-household-count"
    ]

    # ── 5. Replace flat base services charge with 3 income-tier ApplicabilityGroups ─
    # 5a. Drop the existing flat base-charge price (line ~1056 had unitPrice $0.49281)
    prices["urpx:hasPrice"] = [
        p for p in prices.get("urpx:hasPrice", [])
        if p.get("@id") != "pge:price-base-charge"  # may be named differently in source
        and p.get("urpx:referencesPriceDefinition", {}).get("@id") not in ("pge:pd-base-charge", "pge:pd-service")
    ]
    # 5b. Add 3 new income-tier prices to top-level hasPrice
    base_pd_id = "pge:pd-base-charge"
    # First ensure the base-charge PriceDefinition exists in BillingModel.hasPriceDefinition;
    # if the source had a different IRI for it, find the one whose ledger is the service ledger.
    # The existing fixture has a "pge:ledger-service" referencing mi-meter-count. The PD on it
    # would be the per-meter base charge. Find it.
    service_pd_id = None
    for pd in bm.get("urpx:hasPriceDefinition", []):
        if pd.get("urpx:referencesLedger", {}).get("@id") == "pge:ledger-service":
            service_pd_id = pd["@id"]
            # Update its name + chargeType + chargeCategory + billPortion to the income-tier base charge
            pd["urpx:name"] = "Base Services Charge"
            pd["urpx:chargeType"] = {"@id": "urpx:minimumBill"}
            pd["urpx:chargeCategory"] = {"@id": "urpx:serviceCharge"}
            pd["urpx:billPortion"] = {"@id": "urpx:bundledPortion"}
            pd["urpx:baseQuantity"] = "1"
            pd["urpx:hasCalculationMethod"] = {
                "@type": "urpx:CalculationMethod",
                "urpx:intervalDuration": "P1D",
            }
            break
    if service_pd_id is None:
        raise RuntimeError("Could not find service-ledger PriceDefinition")

    # Build the 3 income-tier prices
    def tier_price(price_id, name, unit_price, ag):
        return {
            "@type": "urpx:Price", "@id": price_id,
            "urpx:referencesPriceDefinition": {"@id": service_pd_id},
            "urpx:startDate": "2026-03-27",
            "urpx:name": name,
            "urpx:unitPrice": unit_price,
            "urpx:hasApplicabilityGroup": ag,
        }

    ag_tier_1 = {
        "@type": "urpx:ApplicabilityGroup",
        "@id": "pge:ag-base-charge-tier-1",
        "urpx:name": "Income Tier 1 — customer enrolled in CARE",
        "urpx:hasConditionExpression": expr_single(
            "pge:cx-tier-1",
            cn_equals_object("pge:cn-tier-1", prog_enrollment, "pge:program-care"),
        ),
    }
    ag_tier_2 = {
        "@type": "urpx:ApplicabilityGroup",
        "@id": "pge:ag-base-charge-tier-2",
        "urpx:name": "Income Tier 2 — customer enrolled in FERA",
        "urpx:hasConditionExpression": expr_single(
            "pge:cx-tier-2",
            cn_equals_object("pge:cn-tier-2", prog_enrollment, "pge:program-fera"),
        ),
    }
    ag_tier_3 = {
        "@type": "urpx:ApplicabilityGroup",
        "@id": "pge:ag-base-charge-tier-3",
        "urpx:name": "Income Tier 3 — customer not enrolled in CARE or FERA",
        "urpx:hasConditionExpression": expr_single(
            "pge:cx-tier-3",
            boolop("pge:bn-tier-3-and", "and", [
                cn_not_equals_object("pge:cn-tier-3-not-care", prog_enrollment, "pge:program-care"),
                cn_not_equals_object("pge:cn-tier-3-not-fera", prog_enrollment, "pge:program-fera"),
            ], logic_expression="hasProgramEnrollment != program-care AND hasProgramEnrollment != program-fera"),
        ),
    }
    new_tier_prices = [
        tier_price("pge:price-base-charge-tier-1",
                   "Base Services Charge — Income Tier 1 (CARE-eligible)", "0.19713", ag_tier_1),
        tier_price("pge:price-base-charge-tier-2",
                   "Base Services Charge — Income Tier 2 (FERA-eligible)", "0.39688", ag_tier_2),
        tier_price("pge:price-base-charge-tier-3",
                   "Base Services Charge — Income Tier 3 (no qualifying enrollment)", "0.79343", ag_tier_3),
    ]
    # Insert after the existing top-level hasPrice array (ordering matters less; just append)
    prices["urpx:hasPrice"] = list(prices["urpx:hasPrice"]) + new_tier_prices

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
