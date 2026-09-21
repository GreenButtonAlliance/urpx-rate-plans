#!/usr/bin/env python3
"""
the project tracker: extract the 3 CPAU residential modifier-only filings as
standalone urpx:RatePlanModifier filings.

Source: ca/pou/cpau/e-1/versions/2025-09-01/rate-plan_cpau_e-1_2025-09-01.jsonld
        (multi-source @graph that bundles cpau:e-1 base + cpau:e-hra +
         cpau:e-eec-1 + cpau:e-nse-1)

Output (3 new filings):
  ca/pou/cpau/e-hra/versions/2023-01-01/rate-plan-modifier_cpau_e-hra_2023-01-01.jsonld
  ca/pou/cpau/e-eec-1/versions/2025-09-01/rate-plan-modifier_cpau_e-eec-1_2025-09-01.jsonld
  ca/pou/cpau/e-nse-1/versions/2025-09-01/rate-plan-modifier_cpau_e-nse-1_2025-09-01.jsonld

Each output is a standalone @graph containing only the modifier subtree.

Per-modifier substantive transforms:
  - Strip urpx:applicableToRatePlan (was {"@id": "cpau:e-1"} in the source
    multi-source filing; fine there because the base RatePlan IS in the
    same @graph; here we strip per the urpx-org/urpx#23 workaround for
    standalone modifier filings — same pattern as CPAU E-2-G/E-4-G/E-7-G).
  - Strip urpx:applicableToRatePlanVersion (the project tracker retrofit added this
    on 2026-04-30; same standalone-modifier cross-graph identity issue).
  - Update urpx:hasDataSourceReference to point at the canonical
    paloalto.gov URL (rather than the placeholder file:// URI inherited
    from the URPX-team-authored source).
  - DataSourceReference dateRetrieved = 2026-04-30; matches when we
    fetched the modifier PDFs into the new filing dirs today.
"""
import json
import copy
from pathlib import Path

ROOT = Path(str(Path(__file__).resolve().parent.parent))
SRC  = ROOT / "ca/pou/cpau/e-1/versions/2025-09-01/rate-plan_cpau_e-1_2025-09-01.jsonld"

# (modifier @id, output filing dir relative to ROOT, source-PDF URL, source-PDF filename)
MODIFIER_TARGETS = [
    ("cpau:e-hra",
     "ca/pou/cpau/e-hra/versions/2023-01-01/rate-plan-modifier_cpau_e-hra_2023-01-01.jsonld",
     "https://www.paloalto.gov/files/assets/public/v/3/utilities/rates-schedules-for-utilities/e-hra-effective-2023-01-01.pdf",
     "e-hra-effective-2023-01-01.pdf"),
    ("cpau:e-eec-1",
     "ca/pou/cpau/e-eec-1/versions/2025-09-01/rate-plan-modifier_cpau_e-eec-1_2025-09-01.jsonld",
     "https://www.paloalto.gov/files/assets/public/v/6/utilities/rates-schedules-for-utilities/residential-utility-rates/e-eec-1-effective-2025-09-01.pdf",
     "e-eec-1-effective-2025-09-01.pdf"),
    ("cpau:e-nse-1",
     "ca/pou/cpau/e-nse-1/versions/2025-09-01/rate-plan-modifier_cpau_e-nse-1_2025-09-01.jsonld",
     "https://www.paloalto.gov/files/assets/public/v/6/utilities/rates-schedules-for-utilities/residential-utility-rates/e-nse-1-effective-2025-09-01.pdf",
     "e-nse-1-effective-2025-09-01.pdf"),
]


def strip_cross_graph_props(obj):
    """In the modifier subtree, remove applicableToRatePlan and
    applicableToRatePlanVersion (the cross-graph-identity workaround for
    standalone modifier filings — pending urpx-org/urpx#23)."""
    if isinstance(obj, dict):
        for k in ("urpx:applicableToRatePlan", "urpx:applicableToRatePlanVersion"):
            obj.pop(k, None)
        for v in obj.values():
            strip_cross_graph_props(v)
    elif isinstance(obj, list):
        for x in obj:
            strip_cross_graph_props(x)


def update_data_source_reference(obj, url, filename):
    """In the modifier subtree, update any urpx:DataSourceReference to
    point at the canonical paloalto.gov URL (rather than the placeholder
    file:// URI inherited from the URPX-team-authored source)."""
    if isinstance(obj, dict):
        if obj.get("@type") == "urpx:DataSourceReference":
            obj["urpx:url"] = url
            obj["urpx:fileName"] = filename
            obj["urpx:dateRetrieved"] = "2026-04-30"
            obj.setdefault("urpx:dataSourceType", {"@id": "urpx:utilityWebsiteSource"})
            obj.setdefault("urpx:mediaType", {"@id": "urpx:applicationPdf"})
        for v in obj.values():
            update_data_source_reference(v, url, filename)
    elif isinstance(obj, list):
        for x in obj:
            update_data_source_reference(x, url, filename)


def main():
    src = json.loads(SRC.read_text())
    context = copy.deepcopy(src["@context"])
    # Source @context lacks a urpx:dateRetrieved → xsd:date mapping; the
    # multi-source filing didn't use that property. Our extracted modifier
    # DSRs do, so add the mapping.
    if "urpx:dateRetrieved" not in context:
        context["urpx:dateRetrieved"] = {"@type": "xsd:date"}

    for rpm_id, out_path, pdf_url, pdf_filename in MODIFIER_TARGETS:
        rpm = next((n for n in src["@graph"]
                    if n.get("@type") == "urpx:RatePlanModifier" and n.get("@id") == rpm_id),
                   None)
        if rpm is None:
            print(f"  ✗ {rpm_id} not found in source")
            continue

        # Deep-copy so mutations don't leak back to src
        rpm_out = copy.deepcopy(rpm)
        strip_cross_graph_props(rpm_out)
        update_data_source_reference(rpm_out, pdf_url, pdf_filename)

        # Wrap in standalone @graph
        doc = {"@context": context, "@graph": [rpm_out]}

        out = ROOT / out_path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        print(f"  ✓ wrote {out_path} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
