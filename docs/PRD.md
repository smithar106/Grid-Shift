# Product Requirements

## Problem

Data-center operators make several coupled decisions: when flexible computing should run,
how electricity prices and grid emissions intensity vary by hour, how much workload can move
without missing a deadline, and what the financial and environmental trade-offs are between
alternative schedules.

The relevant information is fragmented across energy data providers, weather services,
operational systems, and spreadsheets. GridShift combines those inputs into one analytical
model and produces an optimized workload schedule.

## Users

| User | Primary need |
| --- | --- |
| Data-center operations analyst | Identify lower-cost operating schedules |
| Energy procurement analyst | Model electricity cost exposure |
| Sustainability analyst | Compare energy-related emissions scenarios |
| Infrastructure researcher | Examine operational trade-offs |

This is a **decision-support** application. It is not a controller for physical
infrastructure.

## Core user story

> As a data-center operations analyst, I want to upload an hourly electricity demand
> profile, connect external energy data, specify operational constraints, and generate an
> optimized schedule, so I can quantify potential cost savings and emissions reductions
> without violating workload deadlines.

## MVP acceptance criteria

| # | Criterion | Status | Evidence |
| --- | --- | --- | --- |
| 1 | At least one functioning external API integration | **Done** | Open-Meteo connector, `tests/test_open_meteo.py` (17 tests) |
| 2 | CSV upload and validation | **Done** | `app/services/csv_ingest.py`, 48 tests |
| 3 | 24-hour optimization with a real solver | **Done** | SciPy `linprog` with HiGHS |
| 4 | Cost, carbon, and balanced optimization modes | **Done** | `ObjectiveMode`, parametrized tests |
| 5 | Capacity and deadline constraints enforced | **Done** | Structural + post-solve verification |
| 6 | Baseline versus optimized comparison | **Done** | Deterministic earliest-feasible baseline |
| 7 | Interactive hourly visualization | **Done** | Optimize screen, Recharts |
| 8 | Reproducible scenario results | **Done** | Content checksums, archived snapshots |
| 9 | Automated optimization tests | **Done** | 88 tests, 100% branch coverage of the model |
| 10 | One-command local startup | **Done** | `make setup && make api && make web` |

All ten are release requirements, not claims. The criterion most worth checking is #3: every
displayed result comes from the solver, and the post-solve verification step exists
specifically so that a solver answer which breaks a constraint is never presented as usable.

## In scope for v1

| Module | Functionality |
| --- | --- |
| Facility setup | Location, capacity, baseline load |
| Data ingestion | Weather API and CSV uploads |
| Energy data | Hourly prices and emissions factors from uploaded datasets |
| Optimization | Three objective modes |
| Constraints | Power limits, deadlines, workload completion |
| Dashboard | Hourly schedules, costs, emissions |
| Scenarios | Save and compare optimization runs |
| Export | CSV and JSON |
| Diagnostics | Solver status and infeasibility messages |

## Explicitly out of scope for v1

Real-time facility control, cloud-provider workload migration, battery dispatch,
electricity market bidding, demand-charge optimization, predictive modelling, and user
authentication.

These are future features, not MVP dependencies. Each is excluded because it would require
either a mixed-integer formulation, a data source GridShift does not have, or an
authentication model the MVP does not need.

## Deviations from the original specification

The project brief specified a stack that could not be deployed as described. These
deviations are recorded rather than silently absorbed.

| Original | Actual | Why |
| --- | --- | --- |
| Deploy to GitHub Pages | Deployed to Railway | Pages serves static files only. It cannot run FastAPI, PostgreSQL, or a Python solver. The brief was revised to Railway, which resolves the conflict and permits the full stack. |
| Docker Compose for local development | SQLite locally, PostgreSQL in production | Docker is not installed in the development environment. SQLAlchemy already abstracts the difference, so this removes a prerequisite without weakening the production topology. |
| Next.js frontend calling FastAPI directly | Next.js proxies `/api/v1/*` over Railway's private network | The brief's own recommendation. The API has no public domain, so there is no CORS surface. |
| Pydantic models for the problem definition | Frozen dataclasses | Pydantic wraps semantic validation errors in a generic `ValidationError`, which hides the reason a problem is unusable. The API layer still uses Pydantic for HTTP contracts. |
| `pandas` for CSV processing | Standard-library `csv` | Ingestion needs precise control over error reporting per row. `pandas` coerces types silently, which conflicts with the requirement to reject rather than repair. |
| Background job queue for optimization | Synchronous solve with a concurrency semaphore | A 24-hour solve takes single-digit milliseconds. The brief itself allows this: a queue is only warranted once solver time affects the user experience. |

## Success definition

> A user can load the sample facility, retrieve weather data, upload hourly energy inputs,
> run all three optimization modes, inspect the results, and export a reproducible scenario.

This is verified end to end against the production deployment. See the root
[`README.md`](../README.md) for the measured figures.

## Engineering requirements

| Area | Requirement | Status |
| --- | --- | --- |
| Correctness | Solver satisfies all constraints within numerical tolerance | Post-solve verification; violations downgrade the result |
| Reproducibility | Identical input snapshots produce equivalent results | Checksum tests; determinism tests |
| Reliability | External API errors produce actionable messages | `UpstreamUnavailable` with the upstream reason |
| Security | API keys stored in environment variables | No key required for Open-Meteo; `.env` is gitignored |
| Performance | 24-hour scenario solves in under 5 seconds | Measured at 1.3 ms (median of 7) |
| Accessibility | Keyboard-accessible controls and readable charts | Semantic tables, labelled controls, focus-visible rings |
| Testing | ≥90% coverage of optimization-domain code | 100% branch coverage, gated in CI |
| Documentation | Setup, architecture, equations, limitations | `docs/` |
| CI | Linting, type checks, and tests pass | GitHub Actions, both applications |

Performance and coverage figures are measured, not targets. The measured values are in the
root README.

## Limitations

GridShift models hypothetical workloads over a finite horizon. It does not control real data
centers, does not guarantee real electricity savings, and does not model battery dispatch,
demand charges, or non-preemptible jobs. Uploaded prices and carbon factors are treated as
supplied inputs; historical grid data is never presented as a forward-looking forecast.
