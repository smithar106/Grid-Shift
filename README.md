# GridShift — Open-Source Data Center Energy Optimization

Integrating public energy data, mathematical programming, and interactive analytics to model
cost and emissions trade-offs in flexible computing workloads.

GridShift is a decision-support application for data-center operations, energy procurement, and
sustainability analysts. It combines weather data, uploaded electricity prices and carbon
intensity, and explicit workload constraints into a single analytical model, then solves for a
lower-cost or lower-emission operating schedule.

> **Status:** under active development. Results shown by the deployed application are produced by
> a linear program; the repository does not yet claim measured production savings.

## What makes this different

The optimization engine is the product, not the dashboard. Every recommendation is:

- **Mathematically feasible** — produced by a linear program that enforces workload completion,
  electrical capacity, per-job processing limits, and release/deadline windows.
- **Reproducible** — each run archives an immutable snapshot of its inputs; identical snapshots
  produce equivalent results.
- **Traceable** — every metric records its source, units, and whether it was user-supplied,
  retrieved from an API, or synthetically generated.

## Architecture

```
Next.js dashboard ──► FastAPI service ──► Connectors (Open-Meteo, CSV)
  (Railway web)        (Railway api)   ──► Optimizer (SciPy HiGHS)
                                       ──► PostgreSQL (snapshots, scenarios, results)
```

Browser requests are same-origin: the Next.js server proxies `/api/v1/*` to the API over
Railway's private network, so the API is never publicly exposed.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for detail.

## The optimization model

For each workload job `j` and hour `t`, the decision variable `x[j,t] ≥ 0` is the energy (MWh)
committed to job `j` during hour `t`. Total facility consumption in hour `t` is
`E[t] = b[t] + Σ_j x[j,t]`, where `b[t]` is fixed baseline load.

| Mode | Objective |
| --- | --- |
| `cost` | `min Σ_t p[t] · E[t]` |
| `emissions` | `min Σ_t c[t] · E[t]` |
| `balanced` | `min Σ_t (p[t] + λ·c[t]) · E[t]` |

Subject to workload completion, capacity `b[t] + Σ_j x[j,t] ≤ K[t]`, processing limits
`0 ≤ x[j,t] ≤ M[j]`, and zero allocation outside each job's `[release, deadline]` window.
`λ` is an explicit carbon price in USD per tonne CO₂e.

The full formulation, solver choice, and baseline definition are documented in
[`docs/OPTIMIZATION.md`](docs/OPTIMIZATION.md).

## Quick start

Requires Python 3.11+ and Node 20+. No Docker needed — local development uses SQLite.

```bash
make setup      # create the venv and install both apps
make migrate    # create the local database
make dev        # prints the two commands to run
```

In two terminals:

```bash
make api        # FastAPI  → http://127.0.0.1:8000/docs
make web        # Next.js  → http://localhost:3000
```

## Testing

```bash
make test         # API (pytest) + web (vitest)
make lint         # ruff + eslint
make typecheck    # mypy + tsc
```

## Deployment

Both services deploy to Railway from this monorepo. See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## Limitations

GridShift models **hypothetical** workloads over a finite horizon. It does not control real data
centers, does not guarantee real electricity savings, and does not model battery dispatch,
demand charges, or non-preemptible jobs. Uploaded prices and carbon factors are treated as
user-supplied inputs — historical grid data is never presented as a forward-looking forecast.

## Data sources and licensing

See [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md).

## License

MIT — see [`LICENSE`](LICENSE).
