# Data Sources

GridShift is deliberately explicit about where every number comes from. An observation
carries its `source` and its `data_status`, and the API never substitutes synthetic values
for a failed retrieval.

## Status vocabulary

| `data_status` | Meaning |
| --- | --- |
| `user_supplied` | Provided by the operator via CSV. Authoritative for that facility. |
| `retrieved` | Fetched from an external API, with the retrieval time recorded. |
| `synthetic` | Generated for demonstration. Never produced implicitly. |

## Supported sources

### CSV upload (MVP, authoritative)

The primary input. GridShift needs an hourly electricity price series and an hourly carbon
intensity series; a facility load series is optional and defaults to zero.

Required columns: `timestamp`, `metric`, `value`, `unit`.
Optional columns: `location_id`, `timezone`.

```csv
timestamp,location_id,metric,value,unit
2026-09-16T00:00:00Z,facility_001,electricity_price,28.01,USD/MWh
2026-09-16T00:00:00Z,facility_001,carbon_intensity,0.2001,tCO2e/MWh
2026-09-16T00:00:00Z,facility_001,facility_load,14.0,MWh
```

Accepted metrics: `electricity_price`, `carbon_intensity`, `facility_load`, `temperature`,
`relative_humidity`. Common aliases (`price`, `load`, `emissions_factor`) are recognized.

Accepted units and their canonical targets:

| Metric | Accepted units | Canonical |
| --- | --- | --- |
| `electricity_price` | `USD/MWh`, `EUR/MWh`, `GBP/MWh` | unchanged |
| `carbon_intensity` | `tCO2e/MWh`, `kgCO2e/MWh` | `tCO2e/MWh` |
| `facility_load` | `MWh`, `kWh` | `MWh` |

**Currencies are never converted.** Converting would require an unsourced FX rate, so a
dataset must use one currency throughout; mixing them is rejected.

### Open-Meteo (MVP, context only)

Hourly temperature and relative humidity forecasts.

- Endpoint: `https://api.open-meteo.com/v1/forecast`
- Authentication: none
- Cost: free hosted tier, non-commercial use
- Published limit: 10,000 calls per day
- Attribution: **required** — "Weather data by Open-Meteo.com", CC BY 4.0
- Documentation: <https://open-meteo.com/en/docs>

Responses are cached in-process for 15 minutes (`CACHE_TTL_SECONDS`). The cache stores the
raw response body, not the parsed objects, so the archived payload remains evidence of what
the upstream actually said.

**Weather does not enter the optimization objective.** It is retrieved and displayed
alongside the schedule. It would affect the objective only through an explicit, documented
weather-to-cooling-load model, which is out of scope for v1. The API states this in every
response (`affects_objective: false`) so the dashboard cannot imply otherwise.

### U.S. Energy Information Administration (planned, phase 2)

Historical hourly electricity demand, generation, and interchange.

- Endpoint: `https://api.eia.gov/v2/`
- Authentication: free API key, required
- Documentation: <https://www.eia.gov/opendata/>

**Why EIA is not the v1 price feed.** EIA publishes *historical operating data*. It does not
provide a facility's forward-looking electricity tariff, and it does not provide a marginal
emissions forecast. Presenting historical grid data as a live operational signal would
misrepresent it, so v1 labels uploaded prices and carbon factors as supplied inputs and
does not imply they are forecasts.

### Synthetic sample data

GridShift has no access to proprietary data-center telemetry, so the shipped sample is
synthetic and labelled as such.

- Generator: `apps/api/scripts/generate_sample_data.py`
- Output: `data/synthetic/sample_facility_24h.csv`, `sample_facility_168h.csv`
- Seeder: `apps/api/scripts/seed_sample.py`

The profile has a morning ramp and an evening peak, so the earliest-feasible baseline is
genuinely suboptimal. A flat curve would make every objective agree and would hide whether
the comparison works.

The generator uses a fixed start date and no random seed, so the published CSV is stable and
the README's figures can be reproduced exactly.

## Validation rules

An upload is rejected unless all of the following hold:

- A required column is present, with an accepted metric and a unit valid for that metric.
- Every value is a finite number; `NaN`, `inf`, and `1,5` are rejected.
- `carbon_intensity`, `facility_load`, and `relative_humidity` are non-negative.
  Electricity prices **may** be negative — negative prices are a real market condition.
- Timestamps are ISO 8601. Naive timestamps require a `timezone` column or a form
  timezone; an IANA name is required.
- No duplicate hours, and no missing hours unless gaps are explicitly allowed.
- One currency throughout a price series.

Validation reports every problem at once rather than failing on the first.

### Daylight saving

DST is handled explicitly rather than by ignoring it:

- An **ambiguous** local time (the repeated hour when clocks go back) is resolved by
  occurrence order, so both 01:00 local hours survive as distinct UTC instants. A 25-hour
  day is ingested as 25 hours.
- A **nonexistent** local time (the hour skipped when clocks go forward) is rejected,
  because no real instant corresponds to it.

Timestamps are normalized to UTC and the original timezone is preserved as provenance.

## Licensing and attribution

| Source | License / terms |
| --- | --- |
| Open-Meteo | CC BY 4.0 — attribution required |
| EIA Open Data | Public domain (U.S. Government work) |
| Synthetic sample | MIT, as part of this repository |
| User uploads | Belong to the user; GridShift claims no rights |

GridShift itself is MIT licensed. See [`../LICENSE`](../LICENSE).
