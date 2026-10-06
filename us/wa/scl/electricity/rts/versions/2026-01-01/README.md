# SCL Schedule RTS (Residential: Suburban Time-of-Use), 2026-01-01

Seattle City Light's optional residential time-of-use schedule for customers in the suburban jurisdictions City Light serves, Seattle Municipal Code 21.49.030.B as amended by Ordinance 127473. This version carries the ordinance column headed "Effective January 1, 2026".

**This filing uses `urpx:daysOfWeek`, proposed in [urpx-org/urpx#71](https://github.com/urpx-org/urpx/pull/71) and not in any URPX release. It does not validate against the v0.5.1 SHACL on that property**: `TimeBracketShape` is closed, so each bracket carrying `urpx:daysOfWeek` fails it. `dev/validate-with-base.py` excepts exactly those results under `DAYS_OF_WEEK_EXCEPTION`.

Every charge below is the unmultiplied rate, which a customer in Renton pays. The suburban franchise and tax multipliers and the Shoreline and Burien undergrounding charges are the modifier [`scl:residential-suburban`](../../../residential-suburban/versions/2026-01-01/), which takes its percentage of this filing's energy subtotal `scl:rts-2026-01-01-summary-energy` and of its Base Service Charge.

## Files

- `scl_rts_2026-01-01.pdf`: Ordinance 127473 as `Ord_127473.pdf` on clerk.seattle.gov. Schedule RTS is on page 11.
- `tariff.toml`: provenance, how the columns were read, holiday handling, deferrals.
- `rate-plan_scl_rts_2026-01-01.jsonld`: the URPX serialization.

## Rates

| Line | Ordinance | Carried |
| --- | --- | --- |
| Base Service Charge | 39.45 cents per meter per day | $0.3945 per day |
| Energy Peak (5-9pm Mon-Sat, not holidays) | 16.32 cents per kWh | $0.1632 per kWh |
| Energy Mid-Peak (6am-5pm and 9pm-12am Mon-Sat; 6am-12am Sundays and holidays) | 14.28 cents per kWh | $0.1428 per kWh |
| Energy Off-Peak (12am-6am every day) | 8.16 cents per kWh | $0.0816 per kWh |

Holidays are the six NERC holidays City Light names: New Year's Day, Memorial Day, Independence Day, Labor Day, Thanksgiving Day and Christmas Day. One falling on a Sunday is observed the following Monday; one falling on a Saturday stays on Saturday.
