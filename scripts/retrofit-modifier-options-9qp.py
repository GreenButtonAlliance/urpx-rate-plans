#!/usr/bin/env python3
"""
Retrofit the project tracker: add Decision #084/#090 modifier-coupling properties to
all corpus filings with embedded RatePlanModifiers.

Adds (in-place):
  - RatePlanVersion.hasModifierOptions          → [RatePlanModifier @ids]
  - RatePlanVersion.hasModifierVersionOptions   → [RatePlanModifierVersion @ids]
  - RatePlanModifierVersion.applicableToRatePlanVersion → local RPV @id

Skips standalone modifier filings (E-2-G / E-4-G / E-7-G) — they have the
same SHACL closed-world cross-graph issue as applicableToRatePlan
(urpx-org/urpx#23) and would fail validation.

Each filing's structure:
  @graph[*] urpx:RatePlan
            └─ hasRatePlanVersion [urpx:RatePlanVersion]
                └─ (any nested location) urpx:RatePlanModifier
                                          └─ hasRatePlanModifierVersion
                                              [urpx:RatePlanModifierVersion]

Mechanics: walk the @graph, find the RPV node and all RPM nodes.
For each RPM, find its RPMV. Set the three properties.
"""
import json
from pathlib import Path

ROOT = Path(str(Path(__file__).resolve().parent.parent))

FILINGS = [
    "ca/iou/pge/e-1/versions/2026-03-01/rate-plan_pge_e-1_2026-03-01.jsonld",
    "ca/iou/pge/e-tou-c/versions/2026-03-01/rate-plan_pge_e-tou-c_2026-03-01.jsonld",
    "ca/iou/pge/e-tou-c/versions/2026-03-27/rate-plan_pge_e-tou-c_2026-03-27.jsonld",
    "ca/iou/pge/e-tou-d/versions/2026-03-27/rate-plan_pge_e-tou-d_2026-03-27.jsonld",
    "ca/iou/pge/ev2/versions/2026-03-27/rate-plan_pge_ev2_2026-03-27.jsonld",
    "ca/pou/cpau/e-1/versions/2025-07-01/rate-plan_cpau_e-1_2025-07-01.jsonld",
    "ca/pou/cpau/e-1/versions/2025-09-01/rate-plan_cpau_e-1_2025-09-01.jsonld",
    "ca/pou/cpau/e-1-tou/versions/2026-01-01/rate-plan_cpau_e-1-tou_2026-01-01.jsonld",
]


def find_rpv(node):
    if isinstance(node, dict):
        if node.get("@type") == "urpx:RatePlanVersion":
            return node
        for v in node.values():
            r = find_rpv(v)
            if r: return r
    elif isinstance(node, list):
        for x in node:
            r = find_rpv(x)
            if r: return r


def find_rpms(node, found=None):
    if found is None: found = []
    if isinstance(node, dict):
        if node.get("@type") == "urpx:RatePlanModifier":
            found.append(node)
        for v in node.values():
            find_rpms(v, found)
    elif isinstance(node, list):
        for x in node:
            find_rpms(x, found)
    return found


def get_rpmv(rpm):
    """RatePlanModifier.hasRatePlanModifierVersion can be single or list."""
    v = rpm.get("urpx:hasRatePlanModifierVersion")
    if isinstance(v, list):
        # If multiple versions, retrofit each. For our corpus all RPMs have one.
        return v
    elif isinstance(v, dict):
        return [v]
    return []


def retrofit(path):
    p = ROOT / path
    doc = json.loads(p.read_text())

    rpv = find_rpv(doc)
    if not rpv:
        print(f"  NO RPV in {path}")
        return False
    rpv_id = rpv["@id"]

    rpms = find_rpms(doc)
    if not rpms:
        print(f"  NO RPMs in {path}")
        return False

    rpm_ids = [rpm["@id"] for rpm in rpms]
    rpmv_ids = []
    for rpm in rpms:
        for rpmv in get_rpmv(rpm):
            rpmv_ids.append(rpmv["@id"])
            # Set applicableToRatePlanVersion on each RPMV
            existing = rpmv.get("urpx:applicableToRatePlanVersion")
            new_val = {"@id": rpv_id}
            if existing is None:
                rpmv["urpx:applicableToRatePlanVersion"] = new_val
            elif isinstance(existing, dict):
                if existing.get("@id") != rpv_id:
                    rpmv["urpx:applicableToRatePlanVersion"] = [existing, new_val]
            elif isinstance(existing, list):
                if not any(e.get("@id") == rpv_id for e in existing):
                    existing.append(new_val)

    # Set hasModifierOptions and hasModifierVersionOptions on the RPV
    rpv["urpx:hasModifierOptions"] = [{"@id": x} for x in rpm_ids] if len(rpm_ids) > 1 else {"@id": rpm_ids[0]}
    rpv["urpx:hasModifierVersionOptions"] = [{"@id": x} for x in rpmv_ids] if len(rpmv_ids) > 1 else {"@id": rpmv_ids[0]}

    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    print(f"  ✓ {path}: RPV={rpv_id} → {len(rpm_ids)} RPM(s), {len(rpmv_ids)} RPMV(s)")
    return True


def main():
    for f in FILINGS:
        retrofit(f)


if __name__ == "__main__":
    main()
