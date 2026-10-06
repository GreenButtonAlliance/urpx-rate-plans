# PSE Schedule 327 (Residential Service Time-of-Use with Super Off-Peak), 2026-10-01

Puget Sound Energy's optional residential time-of-use schedule with a super off-peak period, WN U-60 Electric Tariff G, with every supplemental schedule that prices it per kWh. In force from 2026-10-01, the effective date of the 25th Revision of Sheet 129-B (Schedule 129, $0.009204 per kWh). Every other rate is unchanged from the 2026-05-01 version.

## Files

- `pse_327_2026-10-01.pdf`: Schedule 327, sheets 327 through 327-C, as `elec_sch_327.pdf` on pse.com.
- `pse_<schedule>_<date>.pdf`: each supplemental schedule as PSE publishes it, dated by the sheet carrying the Schedule 327 rate. These are the files committed beside Schedule 307, which prints the same rate on the same line.
- `tariff.toml`: provenance (url and sha256 per PDF), the structure decision, holiday handling, deferrals.
- `rate-plan_pse_327_2026-10-01.jsonld`: the URPX serialization.

## Rates

| Line | Schedule, sheet | $/kWh |
| --- | --- | --- |
| Energy Charge, Winter Peak (weekdays 7-10am, 5-8pm, Oct-Mar) | 327, 327-A | 0.503575 |
| Energy Charge, Winter Off-Peak (weekdays 10am-5pm, 8-11pm; weekends and legal holidays 7am-11pm) | 327, 327-A | 0.127088 |
| Energy Charge, Summer Peak (weekdays 7-10am, 5-8pm, Apr-Sep) | 327, 327-A | 0.271839 |
| Energy Charge, Summer Off-Peak (weekdays 10am-5pm, 8-11pm; weekends and legal holidays 7am-11pm) | 327, 327-A | 0.122055 |
| Energy Charge, Super Off-Peak (11pm-7am daily, year round) | 327, 327-A | 0.075542 |
| Greenhouse Gas Emissions Cap and Invest Adjustment | 111, 111-C | -0.012600 |
| same, Supplemental Rate | 111, 111-K | 0.002963 |
| Low Income Program | 129, 129-B (25th Rev.) | 0.009204 |
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

The Summary of Total Current Prices, Residential Rate Schedules ("Effective Date 10/1/2026", https://www.pse.com/-/media/Project/PSE/Portal/Rate-documents/summ_elec_prices_2026_10_01.pdf, sha256 `ab6cee5420ef21fb8d644eeeb2defdfa9b303d11f35beec3d7ddd9ec23092193`) is derived from the schedules and is used only as a check. Its Schedule 327 page labels the Basic Charge row "SCH 317"; the amounts are sheet 327-A's.

| Cell | Schedule 327 | + Electricity Charge riders | = Summary "Total Electricity Charge" | + Additional charges | = Summary "Total per kWh" | Modeled marginal |
| --- | --- | --- | --- | --- | --- | --- |
| Winter Peak | 0.503575 | 0.008419 | 0.511994 | 0.039102 | 0.551096 | 0.551096 |
| Winter Off-Peak | 0.127088 | 0.008419 | 0.135507 | 0.039102 | 0.174609 | 0.174609 |
| Summer Peak | 0.271839 | 0.008419 | 0.280258 | 0.039102 | 0.319360 | 0.319360 |
| Summer Off-Peak | 0.122055 | 0.008419 | 0.130474 | 0.039102 | 0.169576 | 0.169576 |
| Super Off-Peak | 0.075542 | 0.008419 | 0.083961 | 0.039102 | 0.123063 | 0.123063 |

Residual 0.000000 in every cell. The modeled column is clj-urpx's marginal rate at 2026-12-08 17:00 and 2026-12-08 11:00 (Winter Peak and Off-Peak), 2027-07-14 17:00 and 11:00 (Summer Peak and Off-Peak) and 2026-12-08 03:00 (Super Off-Peak) Pacific.
