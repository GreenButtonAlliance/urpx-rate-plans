# urpx-tariffs

A corpus of California utility electric tariffs converted to [URPX](https://github.com/urpx-org/urpx) JSON-LD.

This repo is a sibling of the URPX ontology repo and uses URPX to express each tariff in a machine-readable, validatable form. The goal is comprehensive coverage of California utilities — investor-owned (IOU), publicly-owned (POU), cooperative (coop), and community choice aggregator (CCA).

## Layout

See [LAYOUT.md](./LAYOUT.md) for the full conventions. In short:

```
ca/<class>/<utility>/<schedule>/versions/<effective-date>/
  tariff.toml                                    # per-filing manifest
  rate-plan_<utility>_<schedule>_<date>.jsonld   # URPX serialization
```

`<class>` is one of `iou`, `pou`, `coop`, `cca`. Source PDFs are **not** committed; each filing's manifest records the canonical URL and a sha256 so the original can be retrieved.

## Status

Initial corpus: top 5 PG&E residential tariffs (E-TOU-C, E-TOU-D, E-1, EV2, E-CARE). Tracking via beads in the URPX shadow repo.

## License

Each tariff is a public regulatory document. The URPX serializations and manifests in this repo are released under CC0.
