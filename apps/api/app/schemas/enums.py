"""Controlled vocabularies for GridShift data contracts.

Every value that crosses a module boundary is one of these literals, so the optimizer
and the UI can never disagree about what a string means.
"""

from __future__ import annotations

from enum import StrEnum


class Metric(StrEnum):
    """The physical quantity an observation measures."""

    ELECTRICITY_PRICE = "electricity_price"
    CARBON_INTENSITY = "carbon_intensity"
    FACILITY_LOAD = "facility_load"
    TEMPERATURE = "temperature"
    RELATIVE_HUMIDITY = "relative_humidity"


class Unit(StrEnum):
    """Supported units. Only units with an exact, lossless conversion are listed."""

    # Electricity price (currency is preserved, never converted)
    USD_PER_MWH = "USD/MWh"
    EUR_PER_MWH = "EUR/MWh"
    GBP_PER_MWH = "GBP/MWh"

    # Emissions intensity
    TONNES_CO2E_PER_MWH = "tCO2e/MWh"
    KG_CO2E_PER_MWH = "kgCO2e/MWh"

    # Energy over an interval
    MWH = "MWh"
    KWH = "kWh"

    # Weather
    CELSIUS = "degC"
    PERCENT = "%"


class DataSource(StrEnum):
    """Where an observation came from."""

    UPLOADED_CSV = "uploaded_csv"
    OPEN_METEO = "open_meteo"
    EIA = "eia"
    SYNTHETIC_SAMPLE = "synthetic_sample"


class DataStatus(StrEnum):
    """How much trust the observation deserves.

    `synthetic` is never produced implicitly. A connector that cannot reach its upstream
    must fail loudly rather than downgrade to synthetic values.
    """

    USER_SUPPLIED = "user_supplied"
    RETRIEVED = "retrieved"
    SYNTHETIC = "synthetic"


#: Which units are meaningful for each metric.
METRIC_UNITS: dict[Metric, frozenset[Unit]] = {
    Metric.ELECTRICITY_PRICE: frozenset({Unit.USD_PER_MWH, Unit.EUR_PER_MWH, Unit.GBP_PER_MWH}),
    Metric.CARBON_INTENSITY: frozenset({Unit.TONNES_CO2E_PER_MWH, Unit.KG_CO2E_PER_MWH}),
    Metric.FACILITY_LOAD: frozenset({Unit.MWH, Unit.KWH}),
    Metric.TEMPERATURE: frozenset({Unit.CELSIUS}),
    Metric.RELATIVE_HUMIDITY: frozenset({Unit.PERCENT}),
}

#: The unit each metric is converted to before it reaches the optimizer.
CANONICAL_UNITS: dict[Metric, Unit] = {
    Metric.ELECTRICITY_PRICE: Unit.USD_PER_MWH,
    Metric.CARBON_INTENSITY: Unit.TONNES_CO2E_PER_MWH,
    Metric.FACILITY_LOAD: Unit.MWH,
    Metric.TEMPERATURE: Unit.CELSIUS,
    Metric.RELATIVE_HUMIDITY: Unit.PERCENT,
}

#: Multiplicative factor taking a value in the given unit to the canonical unit.
#: Currencies are deliberately absent: converting currency would require an unsourced
#: FX assumption, so a dataset must use one currency throughout.
UNIT_SCALE: dict[Unit, float] = {
    Unit.KG_CO2E_PER_MWH: 1e-3,
    Unit.KWH: 1e-3,
}

#: Metrics whose value must never be negative.
NON_NEGATIVE_METRICS: frozenset[Metric] = frozenset(
    {
        Metric.CARBON_INTENSITY,
        Metric.FACILITY_LOAD,
        Metric.RELATIVE_HUMIDITY,
    }
)

#: Metrics whose currency must be consistent within a single dataset.
CURRENCY_METRICS: frozenset[Metric] = frozenset({Metric.ELECTRICITY_PRICE})
