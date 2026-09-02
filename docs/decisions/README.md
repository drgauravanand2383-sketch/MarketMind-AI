# Architecture Decision Records

One file per significant decision, numbered `NNNN-short-slug.md`. Each
records the context, the decision(s), the consequences, and the
alternatives that were weighed and rejected — enough that someone
reading it later understands *why*, not just *what*.

Decisions that are inseparable from a single subsystem may instead be
recorded inline in that subsystem's `docs/architecture/*.md` (as the
Global Market Intelligence "approved decisions" in §2 of its own doc
are); this directory is for decisions worth surfacing on their own.

| # | Decision |
|---|----------|
| [0001](0001-global-market-trailing-return-windows.md) | Global Market Intelligence: extended trailing-return windows (24H … 5Y) |
| [0002](0002-asset-aware-price-precision.md) | Magnitude-aware price precision for historical series (FX / low-priced assets) |
