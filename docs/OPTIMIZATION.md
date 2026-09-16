# The GridShift Optimization Model

This is the technical core of the project. Everything else — ingestion, the API, the
dashboard — exists to feed this model or to explain its output.

The central design principle: **every recommendation must be mathematically feasible,
reproducible, and traceable to its input data.**

## 1. Decision variables

Let the horizon be `T` hourly intervals. For each workload job `j` and hour `t`:

```
x[j,t] >= 0     energy committed to job j during hour t   (MWh)
```

A variable is created **only** for hours inside job `j`'s window `[r_j, d_j]`. The
constraint "no processing outside the window" is therefore structural — those variables
do not exist — rather than an extra row the solver could violate through rounding.

Fixed inputs:

| Symbol | Meaning | Unit |
| --- | --- | --- |
| `b[t]` | fixed facility load | MWh |
| `K[t]` | available electrical capacity | MW |
| `p[t]` | electricity price | USD/MWh |
| `c[t]` | emissions intensity | tCO2e/MWh |
| `W[j]` | energy job `j` must complete | MWh |
| `r[j]`, `d[j]` | release and deadline hour (inclusive) | index |
| `M[j]` | maximum processing power for job `j` | MW |
| `Δt` | interval length (1.0 for the hourly MVP) | hours |

Total consumption in hour `t`:

```
E[t] = b[t] + Σ_j x[j,t]
```

## 2. Objective functions

### Cost

```
minimize  Σ_t p[t] · E[t]
```

### Emissions

```
minimize  Σ_t c[t] · E[t]
```

### Balanced

```
minimize  Σ_t (p[t] + λ · c[t]) · E[t]
```

`λ` is an explicit **carbon price in USD per tonne CO₂e**. This is the reason balanced
mode is written this way: a naive `cost + emissions` objective would add dollars to
tonnes, which is dimensionally meaningless. Pricing carbon first makes every term a
currency amount.

The combined objective is *never* the number shown to the user. Cost and emissions are
always reported separately, because they are the two quantities the model is trading off.

## 3. Hard constraints

**1. Complete every workload**

```
Σ_{t=r_j}^{d_j} x[j,t] = W[j]        for every job j
```

**2. Respect electrical capacity**

```
b[t] + Σ_j x[j,t] ≤ K[t] · Δt        for every hour t
```

**3. Respect workload processing limits**

```
0 ≤ x[j,t] ≤ M[j] · Δt
```

**4. No processing outside the window** — enforced structurally (see §1).

## 4. Why a linear program

The model is continuous and linear, so it is solved as an LP. `x[j,t] ≥ 0` with an
equality and box constraints is a transportation-style problem; a mixed-integer solver
would be strictly more expensive for no benefit.

`scipy.optimize.linprog(method="highs")` is used. HiGHS is an open-source, actively
maintained solver, and it reports an explicit status for infeasibility rather than
failing silently.

Mixed-integer modelling becomes necessary only when the problem stops being linear:
binary activation, minimum run times, or non-preemptible jobs. Those are explicitly out
of scope for v1 and are the planned trigger for introducing OR-Tools.

### The constant term

`Σ_t w[t] · b[t]` does not depend on any decision variable, so it is dropped before
solving and added back afterwards. Without this the reported objective value would be the
*cost of the flexible work only*, not the cost of the schedule — which would understate
every number in the dashboard.

## 5. The baseline

A saving is only meaningful against a schedule that is itself valid. Comparing against a
schedule that violates a deadline would manufacture a benefit that does not exist.

GridShift uses a deterministic **earliest-feasible** baseline:

1. Order jobs by earliest deadline, then earliest release, then job id.
2. For each job in that order, allocate as much as possible in each hour from `r_j` to
   `d_j`, limited by the remaining headroom `K[t]·Δt − b[t]`, the job's own limit
   `M[j]·Δt`, and what the job still owes.

The ordering is total and the algorithm is greedy, so the same problem always produces
the same baseline.

If the greedy pass cannot complete every job, it raises `BaselineInfeasible` and **no
comparison is reported**. This is deliberate: an infeasible scenario has no valid
baseline, and inventing one would be dishonest. The result records that the baseline was
unavailable, and why.

Savings are computed as:

```
savings %  = (baseline − optimized) / baseline × 100
```

**Negative values are preserved.** Optimizing cost can raise emissions, and optimizing
emissions can raise cost. A dashboard that hid negative results would misrepresent the
trade-off the product exists to expose. When the baseline is zero the percentage is
undefined and is reported as absent rather than as `0%`.

## 6. Post-solve verification

The solver's answer is checked against every hard constraint before it is returned:
workload completion, capacity, per-job power limits, window containment, and
non-negativity. If any check fails, the result is downgraded to `numerical_error` and the
violations are attached.

The solver is not trusted to be correct about the problem; the problem is used to check
the solver.

## 7. Infeasibility

Infeasibility is reported, never worked around. GridShift distinguishes three cases:

| Situation | Reported as |
| --- | --- |
| A job cannot fit its own window: `W[j] > M[j] · (d_j − r_j + 1)` | `infeasible`, naming the job and both quantities |
| Jobs individually fit but compete for shared capacity | `infeasible`, from the solver status |
| Fixed load exceeds capacity in some hour | **problem error**, not infeasibility — no schedule of flexible work can repair it, because the fixed load cannot move |

The third case is a validation error because it is a data defect, not an optimization
outcome. Reporting it as "infeasible" would invite the user to adjust workloads that were
never the cause.

## 8. Assumptions and limitations

Every result carries its assumptions explicitly:

- Workloads are divisible and preemptible. No minimum run time, ramp, or activation cost.
- Baseline load is fixed and cannot be shifted.
- Capacity limits energy per hour to `K[t] · Δt`.
- Prices and carbon intensity are supplied inputs, **not forecasts**. Historical grid data
  is never presented as a forward-looking operational signal.
- The baseline is the deterministic earliest-feasible schedule described in §5.

Out of scope for v1: real-time facility control, cloud-provider workload migration,
battery dispatch, electricity market bidding, demand-charge optimization, predictive
modelling, and user authentication.

## 9. Reproducing a result

A scenario is reproducible because:

- The input snapshot is archived and identified by a content checksum; identical snapshots
  hash identically.
- The baseline is deterministic.
- The LP has a unique optimal objective value. (The optimal *allocation* can be
  non-unique when prices tie — the objective value is not.)
- The solver, its version, the variable and constraint counts, and the solve time are all
  recorded in the result diagnostics.

## 10. Measured performance

On the development machine (Apple silicon), with `SOLVER_TIME_LIMIT_SECONDS=5`:

| Scenario | Variables | Solve time |
| --- | --- | --- |
| 24 hours, 1 workload | 24 | ~4 ms |
| 24 hours, 10 workloads | 240 | ~4 ms |
| 168 hours, 100 workloads | 16,800 | ~84 ms |

The PRD's target is a 24-hour scenario in under 5 seconds; the observed figure is roughly
three orders of magnitude inside it. The solver time limit exists as a guardrail against
pathological inputs, not as a routine constraint.
