# Architecture

## Topology

```
Browser
  │  HTTPS, same origin
  ▼
gridshift-web  (Next.js, Railway)
  │  /api/v1/* proxied over Railway's private network
  ▼
gridshift-api  (FastAPI + SciPy, Railway, no public domain)
  │
  ├──► Connectors   Open-Meteo, CSV
  ├──► Optimizer    SciPy linprog (HiGHS)
  └──► PostgreSQL   Railway, private
```

The browser only ever talks to the Next.js origin. The route handler at
`apps/web/app/api/v1/[...path]/route.ts` forwards to the API over the private network, so
the API has no public domain and there is no CORS surface to misconfigure. This is the
production architecture the PRD recommends.

## Layering

The dependency direction is one-way. Nothing in `app/optimization` imports the database,
the HTTP layer, or a connector.

```
app/routers/        HTTP. Translates requests, delegates, shapes responses.
app/services/       Application logic. Ingestion, scenario assembly, persistence, time.
app/optimization/   The model. Pure, solver-backed, dependency-free.
app/connectors/     External sources, normalized to the shared contract.
app/schemas/        Contracts. Enums, observations, ingestion reports, API payloads.
app/models/         SQLAlchemy tables.
```

The payoff is testability: the optimization engine is exercised with plain dataclasses and
no fixtures, database, or HTTP client, which is why it holds 100% branch coverage.

## Why these choices

**The optimization domain is not a Pydantic model.**
`OptimizationProblem` and `Workload` are frozen dataclasses. Pydantic wraps every error
raised in a validator in a generic `ValidationError`, which buries the specific reason a
problem is unusable. GridShift's whole proposition is that a rejection tells you what is
wrong, so the domain object raises `ProblemValidationError` with every reason attached.

**Timestamps go through a custom column type.**
SQLite does not preserve timezone information. Without `UtcDateTime`, a timestamp written
as aware UTC reads back naive, and every downstream comparison silently shifts by the local
offset. The type normalizes on bind and on read.

**Unparseable input is rejected, never repaired.**
Naive timestamps without a zone, duplicate hours, gaps, and unit mismatches are errors. The
ingestion service collects *every* issue and raises once, so a user fixes a file in one
pass rather than one error at a time.

**External failures are errors.**
A connector that cannot reach its upstream raises `UpstreamUnavailable`. It never
substitutes a synthetic value, because a fabricated number is indistinguishable from a real
one once it is in the database.

**The solver's answer is verified against the problem.**
After solving, the schedule is checked against every hard constraint. If any check fails the
result is downgraded to `numerical_error` rather than presented. The solver is not trusted
to be correct about the problem; the problem is used to check the solver.

**Optimization is synchronous, with bounded concurrency.**
A 24-hour solve takes single-digit milliseconds, so a job queue would add operational
surface for no user benefit. A semaphore caps simultaneous solves, because SciPy releases
the GIL only partially and an unbounded number would contend for CPU on a small instance.

**Ambiguity is an error.**
If two datasets supply electricity prices, the scenario builder refuses rather than picking
one. Guessing would make a result irreproducible without anyone noticing.

## Reproducibility

A run is reproducible because:

1. Every dataset carries a SHA-256 `checksum` of its canonical content. Identical input
   hashes identically.
2. A scenario records the dataset ids it used and a `snapshot_checksum` over them.
3. The baseline scheduler is deterministic — a total ordering and a greedy pass.
4. The LP has a unique optimal objective value. (The optimal *allocation* can be
   non-unique when prices tie; the objective value cannot.)
5. The result stores the solver name, status, variable and constraint counts, and solve
   time.

Nothing is overwritten in place. A re-upload creates a new dataset, so an old scenario can
always be re-derived from the snapshot it names.

## Persistence

| Table | Purpose |
| --- | --- |
| `facilities` | Site, location id, coordinates, capacity |
| `datasets` | One snapshot: source, status, metrics, checksum, row counts |
| `hourly_observations` | Canonical values **plus** the originals as supplied |
| `scenarios` | Objective, carbon price, dataset ids, snapshot checksum, status |
| `workloads` | Jobs: energy, release, deadline, power limit |
| `optimization_results` | Solver status, cost, emissions, baseline, diagnostics, assumptions |
| `hourly_allocations` | Per-job energy per hour |

`hourly_observations` stores both the canonical value (what the optimizer consumes) and the
`original_*` columns (what the user actually wrote). Without that, a result could not be
traced back to the file it came from.

## Frontend

Four screens, all client components that read through the same-origin proxy.

- **Overview** — setup state, facility, data coverage, latest result
- **Optimize** — inputs and results side by side, plus the trade-off frontier
- **Scenarios** — run, inspect, export, compare
- **Data** — facilities, dataset upload, weather

Design tokens live in `app/globals.css` and every colour resolves through them, so dark mode
is a single override block rather than a per-component concern. Chart colours are read from
the stylesheet at runtime via `useSyncExternalStore`, because SVG presentation attributes do
not support `var()`.

## Testing

| Suite | Count | Scope |
| --- | --- | --- |
| `tests/optimization/` | 84 | The model: feasibility, optimality, baseline, edge cases. 100% branch coverage. |
| `tests/test_csv_ingest.py` | 45 | Ingestion, unit canonicalization, DST, duplicates, gaps |
| `tests/test_api_*.py` | 60 | HTTP contracts and the end-to-end scenario flow |
| `tests/test_open_meteo.py` | 17 | Connector normalization, caching, failure modes |
| `tests/optimization/` coverage gate | — | CI fails below 90% |

CI runs Ruff, Mypy, Pytest (with the coverage gate), ESLint, `tsc`, Vitest, and a production
build for both applications.

## Known gaps

- **No authentication.** The deployment is single-tenant; every visitor sees the same
  scenarios. Adding auth is a prerequisite for multi-user use.
- **Capacity is constant.** `K[t]` is modelled per hour, but the API currently fills it from
  the facility rating. A per-hour capacity series is a data-model addition, not a solver
  change.
- **Uploads are capped in memory.** The API reads an 8 MB upload into memory. Large
  historical archives would need streaming.
- **Weather does not affect the objective.** It is retrieved and displayed only. A
  weather-to-cooling-load model is explicitly out of scope for v1.
