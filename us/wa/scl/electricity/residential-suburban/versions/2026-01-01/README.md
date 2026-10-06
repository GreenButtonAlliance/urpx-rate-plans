# SCL residential suburban multipliers and undergrounding charges on Schedule RTS, 2026-01-01

The suburban franchise and tax multipliers and suburban undergrounding charges that Seattle Municipal Code 21.49.030 applies to Schedule RSS and, by 21.49.030.B, to Schedule RTS (Residential: Suburban Time-of-Use), as amended by Ordinance 127473. This version carries the multiplier column headed "Effective January 1, 2026" and composes with `scl:rts-2026-01-01`.

**This filing depends on [urpx-org/urpx#71](https://github.com/urpx-org/urpx/pull/71) through Schedule RTS**, whose brackets use `urpx:daysOfWeek`.

## Files

- `scl_residential-suburban_2026-01-01.pdf`: Ordinance 127473 as `Ord_127473.pdf` on clerk.seattle.gov. The multiplier table is on page 9, the undergrounding charges on pages 9 and 10.
- `tariff.toml`: provenance, how the tables were read, reconciliation against City Light's published prices.
- `rate-plan-modifier_scl_residential-suburban_2026-01-01.jsonld`: the URPX serialization.

## Rates

The customer's jurisdiction is a `urpx:ProfileAlternative`. The percentage increases every Schedule RTS charge, Base Service Charge included.

| Jurisdiction | Increase | Undergrounding, cents per kWh |
| --- | --- | --- |
| Burien | 8.00% | 0.50 (2 charges) |
| Unincorporated King County | 8.00% | none |
| Lake Forest Park | 8.04% | none |
| Normandy Park | 6.38% | none |
| SeaTac | 8.00% | none |
| Shoreline | 8.00% | 0.69 (5 charges) |
| Tukwila | 7.19% | none |

Renton customers take Schedule RTS unmultiplied, without this modifier. Shoreline's charges are North City 0.07, Aurora 1 0.17, Aurora 2 0.18, Aurora 3A 0.05 and Aurora 3B 0.22; Burien's are First Avenue South 1 0.37 and First Avenue South 2 0.13. Every customer in the city pays each of them. They are carried without the percentage increase.
