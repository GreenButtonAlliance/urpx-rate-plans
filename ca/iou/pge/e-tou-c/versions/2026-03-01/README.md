# Worked example: PG&E E-TOU-C effective 2026-03-01

This directory exists to ground the conventions described in [`/LAYOUT.md`](../../../../../../LAYOUT.md) in a concrete example. The `tariff.toml` manifest is complete; the URPX JSON-LD will land here once the conversion in beads issue **URPX-4gn** is done.

When complete, this directory will contain:

- `tariff.toml` — present (manifest)
- `rate-plan_pge_e-tou-c_2026-03-01.jsonld` — pending (URPX serialization)
- `extracted/` — local-only (gitignored), MinerU intermediates

The source PDF is **not** committed; retrieve it from the URL in `tariff.toml` and verify against the recorded sha256.
