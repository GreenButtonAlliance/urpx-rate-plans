# Generators and extractors

The scripts that produced data in this corpus. They are published so the data is reproducible: a filing whose prices were emitted by a script should ship the script that emitted them.

They are working tools, not a supported library. Each was written for one filing or one batch, they are not idempotent in general, and several are superseded by later ones. Read the script before running it.

## Conventions

- Run them from the repository root; they resolve the corpus relative to their own location.
- Scripts that read source data living outside this repository (bulk rate sheets, downloaded ZIPs) take its location from `URPX_SOURCE_DATA`.
- `build-midas-coverage-report.py` calls the CPUC MIDAS API and reads `MIDAS_USERNAME` and `MIDAS_PASSWORD` from the environment. No credentials are stored here.

## What is here

| Prefix | Purpose |
| --- | --- |
| `build-cpau-*` | Emit a CPAU filing's JSON-LD from its extracted tariff tables |
| `build-pge-nbt-*`, `extract-nbt-*`, `extract-sdge-nbt-*` | Net Billing Tariff export-compensation prices, per vintage and per cell |
| `build-midas-coverage-report.py` | Cross-reference corpus prices against CPUC MIDAS rate identifiers |
| `tag-pge-nbt-prices-with-midas-rins.py` | Retroactively attach MIDAS RINs to already-emitted prices |
| `derive-*`, `retrofit-*`, `extract-cpau-modifiers-*` | One-off derivations and retrofits applied to existing filings |
| `migrate-*-v020.py` | Historical: the v0.1.x to v0.2.0 vocabulary migration |

The v0.2.x to v0.5.1 migration is `dev/migrate-v051.py`, which is tooling rather than a generator and lives with the validators.
