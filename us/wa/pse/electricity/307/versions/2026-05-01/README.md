# PSE Schedule 307 (Residential Service Time-of-Use), 2026-05-01

Puget Sound Energy's optional residential time-of-use schedule, WN U-60 Electric Tariff G, with every supplemental schedule that prices it per kWh. In force from 2026-05-01 until 2026-10-01, when the 25th Revision of Sheet 129-B raised Schedule 129 from $0.007550 to $0.009204 per kWh.

## Files

- `pse_307_2026-05-01.pdf`: Schedule 307, sheets 307 through 307-C, as `elec_sch_307.pdf` on pse.com.
- `pse_<schedule>_<date>.pdf`: each supplemental schedule as PSE publishes it, dated by the sheet carrying the Schedule 307 rate. `pse_129_2025-10-01.pdf` is PSE's filing in UTC Docket UE-250648 (24th Revision of Sheet 129-B); `pse_129_2026-10-01.pdf` is the current schedule, whose 25th Revision bounds this version.
- `tariff.toml`: provenance (url and sha256 per PDF), the structure decision, holiday handling, deferrals.
- `rate-plan_pse_307_2026-05-01.jsonld`: the URPX serialization.

## Rates

| Line | Schedule, sheet | $/kWh |
| --- | --- | --- |
| Energy Charge, Winter Peak (weekdays 7-10am, 5-8pm, Oct-Mar) | 307, 307-A | 0.532445 |
| Energy Charge, Summer Peak (weekdays 5-8pm, Apr-Sep) | 307, 307-A | 0.335186 |
| Energy Charge, Off-Peak (all other hours, weekends, legal holidays) | 307, 307-A | 0.108197 |
| Greenhouse Gas Emissions Cap and Invest Adjustment | 111, 111-C | -0.012600 |
| same, Supplemental Rate | 111, 111-K | 0.002963 |
| Low Income Program | 129, 129-B (24th Rev.) | 0.007550 |
| Bill Discount Rate Rider | 129D, 129D-A | 0.002958 |
| Property Tax Tracker | 140, 140-B | 0.002010 |
| Energy Charge Credit Recovery Adjustment | 141A, 141A-A | 0.002010 |
| Colstrip Adjustment Rider | 141COL, 141COL-B | -0.001183 |
| Transportation Electrification Plan Adjustment Rider | 141TEP, 141TEP-A | 0.000520 |
| Targeted Exception Rate Adjustment | 141TEX, 141TEX-A | 0.000457 |
| Wildfire Prevention Tracker | 141WFP, 141WFP-A | 0.002246 |
| Revenue Decoupling Adjustment Mechanism | 142, 142-H | -0.000166 |
| Power Cost Adjustment Clause | 95, 95 | 0.035046 |
| same, Supplemental Rate | 95, 95-E.3 | 0.003673 |
| Electricity Conservation Service Rider | 120, 120 | 0.009409 |
| Residential and Farm Energy Exchange Benefit | 194, 194-A | -0.006648 |
| Federal Incentive Tracker | 95A, 95-G | -0.002378 |
| Clean Energy Implementation Tracker, Rates Not Subject to Refund, Participatory Funding Grants, Rates Subject to Refund, Temporary Customer Charge or Credit | 141CEI, 141N, 141PFG, 141R, 137 | 0.000000 |

Basic Charge: $7.49 per month single phase (three phase, $17.99, is deferred).

## Reconciliation against the Summary Sheet

The Summary of Total Current Prices, Residential Rate Schedules ("Effective Date 5/1/2026", https://www.pse.com/-/media/Project/PSE/Portal/Rate-documents/summ_elec_prices_2026_05_01.pdf, sha256 `baad3a1fab9ec26d2fa83d4cf152212a17bfc2680da260e777f4d19712f40462`) is derived from the schedules and is used only as a check.

| Cell | Schedule 307 | + Electricity Charge riders | = Summary "Total Electricity Charge" | + Additional charges | = Summary "Total per kWh" | Modeled marginal |
| --- | --- | --- | --- | --- | --- | --- |
| Winter Peak | 0.532445 | 0.006765 | 0.539210 | 0.039102 | 0.578312 | 0.578312 |
| Summer Peak | 0.335186 | 0.006765 | 0.341951 | 0.039102 | 0.381053 | 0.381053 |
| Off-Peak | 0.108197 | 0.006765 | 0.114962 | 0.039102 | 0.154064 | 0.154064 |

Residual 0.000000 in every cell. The modeled column is clj-urpx's marginal rate at a weekday instant in each period; no winter day falls inside 2026-05-01 to 2026-10-01, so the Winter Peak cell was resolved on a copy with `urpx:expirationDateTime` removed, at 2026-12-08 17:00 Pacific.
