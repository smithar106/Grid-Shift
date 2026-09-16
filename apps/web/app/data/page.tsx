"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  Alert,
  Button,
  Disclosure,
  EmptyState,
  Field,
  Input,
  Loading,
  PageHeader,
  Select,
  Table,
  TD,
  TH,
} from "@/components/ui";
import { createFacility, getWeather, listDatasets, listFacilities, uploadDataset } from "@/lib/api";
import {
  dayLabel,
  formatDateTime,
  formatInteger,
  formatNumber,
  metricLabel,
  shortChecksum,
} from "@/lib/format";
import type { Dataset, Facility, Weather } from "@/lib/types";

const BLANK_FACILITY = {
  name: "",
  location_id: "",
  latitude: "",
  longitude: "",
  timezone: "America/Los_Angeles",
  capacity_mw: "38",
};

export default function DataPage() {
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [form, setForm] = useState(BLANK_FACILITY);
  const [saving, setSaving] = useState(false);

  const fileInput = useRef<HTMLInputElement>(null);
  const [uploadFacility, setUploadFacility] = useState("");
  const [uploadTimezone, setUploadTimezone] = useState("");
  const [allowGaps, setAllowGaps] = useState(false);
  const [uploading, setUploading] = useState(false);

  const [weather, setWeather] = useState<Weather | null>(null);
  const [weatherError, setWeatherError] = useState<string | null>(null);
  const [loadingWeather, setLoadingWeather] = useState(false);

  const refresh = useCallback(async () => {
    const [facilityList, datasetList] = await Promise.all([listFacilities(), listDatasets()]);
    setFacilities(facilityList);
    setDatasets(datasetList);
    setUploadFacility((current) => current || facilityList[0]?.id || "");
  }, []);

  useEffect(() => {
    (async () => {
      try {
        await refresh();
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Could not load data");
      } finally {
        setLoading(false);
      }
    })();
  }, [refresh]);

  const submitFacility = async () => {
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const created = await createFacility({
        name: form.name,
        location_id: form.location_id,
        latitude: form.latitude ? Number(form.latitude) : null,
        longitude: form.longitude ? Number(form.longitude) : null,
        timezone: form.timezone,
        capacity_mw: Number(form.capacity_mw),
      });
      setForm(BLANK_FACILITY);
      setNotice(`Created facility ${created.name}.`);
      await refresh();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Could not create facility");
    } finally {
      setSaving(false);
    }
  };

  const submitUpload = async () => {
    const file = fileInput.current?.files?.[0];
    if (!file) {
      setError("Choose a CSV file first.");
      return;
    }
    setUploading(true);
    setError(null);
    setNotice(null);
    try {
      const dataset = await uploadDataset(file, {
        facilityId: uploadFacility || undefined,
        timezone: uploadTimezone || undefined,
        allowGaps,
      });
      setNotice(`Accepted ${dataset.rows_accepted} rows across ${dataset.metrics.length} metrics.`);
      if (fileInput.current) fileInput.current.value = "";
      await refresh();
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Upload rejected");
    } finally {
      setUploading(false);
    }
  };

  const loadWeather = async () => {
    const facility = facilities.find((item) => item.id === uploadFacility);
    if (!facility || facility.latitude === null || facility.longitude === null) {
      setWeatherError("This facility has no coordinates. Add them when creating a facility.");
      return;
    }
    setLoadingWeather(true);
    setWeatherError(null);
    try {
      setWeather(
        await getWeather({
          latitude: facility.latitude,
          longitude: facility.longitude,
          locationId: facility.location_id,
          forecastDays: 2,
        }),
      );
    } catch (weatherLoadError) {
      setWeather(null);
      setWeatherError(
        weatherLoadError instanceof Error ? weatherLoadError.message : "Weather unavailable",
      );
    } finally {
      setLoadingWeather(false);
    }
  };

  if (loading) return <Loading label="Loading data" />;

  return (
    <>
      <PageHeader
        title="Data"
        purpose="The facility and the hourly series the optimizer reads."
      />

      {error && (
        <div className="mb-4">
          <Alert tone="loss" title="Request failed">
            {error}
          </Alert>
        </div>
      )}
      {notice && (
        <div className="mb-4">
          <Alert tone="gain">{notice}</Alert>
        </div>
      )}

      <div className="flex flex-col gap-8">
        {/* --- 1. Facility ------------------------------------------------------- */}
        <section className="border-t border-line pt-4">
          <h2 className="mb-1 text-sm font-medium text-ink">Facility</h2>
          <p className="mb-3 text-xs text-ink-muted">
            The site whose capacity and timezone bound every schedule.
          </p>

          {facilities.length === 0 ? (
            <EmptyState>No facilities yet.</EmptyState>
          ) : (
            <Table>
              <thead>
                <tr>
                  <TH>Name</TH>
                  <TH>Location id</TH>
                  <TH align="right">Capacity</TH>
                  <TH>Timezone</TH>
                  <TH align="right">Coordinates</TH>
                  <TH>Created</TH>
                </tr>
              </thead>
              <tbody>
                {facilities.map((facility) => (
                  <tr key={facility.id}>
                    <TD>{facility.name}</TD>
                    <TD numeric>{facility.location_id}</TD>
                    <TD align="right" numeric>
                      {formatNumber(facility.capacity_mw, 0)} MW
                    </TD>
                    <TD>{facility.timezone}</TD>
                    <TD align="right" numeric>
                      {facility.latitude !== null && facility.longitude !== null
                        ? `${facility.latitude.toFixed(3)}, ${facility.longitude.toFixed(3)}`
                        : "—"}
                    </TD>
                    <TD>{formatDateTime(facility.created_at)}</TD>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}

          <div className="mt-4">
            <Disclosure title="Add a facility">
              <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-4">
                <Field label="Name" className="sm:col-span-2">
                  <Input
                    value={form.name}
                    onChange={(event) => setForm({ ...form, name: event.target.value })}
                    placeholder="Northern Virginia DC-1"
                  />
                </Field>
                <Field label="Location id">
                  <Input
                    value={form.location_id}
                    onChange={(event) => setForm({ ...form, location_id: event.target.value })}
                    placeholder="facility_001"
                  />
                </Field>
                <Field label="Capacity (MW)">
                  <Input
                    type="number"
                    min={0}
                    value={form.capacity_mw}
                    onChange={(event) => setForm({ ...form, capacity_mw: event.target.value })}
                  />
                </Field>
                <Field label="Latitude">
                  <Input
                    type="number"
                    step="0.0001"
                    value={form.latitude}
                    onChange={(event) => setForm({ ...form, latitude: event.target.value })}
                  />
                </Field>
                <Field label="Longitude">
                  <Input
                    type="number"
                    step="0.0001"
                    value={form.longitude}
                    onChange={(event) => setForm({ ...form, longitude: event.target.value })}
                  />
                </Field>
                <Field label="Timezone" className="sm:col-span-2">
                  <Input
                    value={form.timezone}
                    onChange={(event) => setForm({ ...form, timezone: event.target.value })}
                    placeholder="America/Los_Angeles"
                  />
                </Field>
                <div className="flex items-end">
                  <Button
                    variant="primary"
                    onClick={submitFacility}
                    disabled={saving || !form.name || !form.location_id}
                  >
                    {saving ? "Saving…" : "Create facility"}
                  </Button>
                </div>
              </div>
            </Disclosure>
          </div>
        </section>

        {/* --- 2. Datasets ------------------------------------------------------- */}
        <section className="border-t border-line pt-4">
          <h2 className="mb-1 text-sm font-medium text-ink">Datasets</h2>
          <p className="mb-3 text-xs text-ink-muted">
            Hourly CSV with columns <span className="font-mono">timestamp, metric, value, unit</span>.
            Optional: <span className="font-mono">location_id, timezone</span>.
          </p>

          {datasets.length === 0 ? (
            <EmptyState>No datasets uploaded yet.</EmptyState>
          ) : (
            <Table>
              <thead>
                <tr>
                  <TH>Metrics</TH>
                  <TH>Source</TH>
                  <TH align="right">Rows</TH>
                  <TH align="right">Hours</TH>
                  <TH>Coverage</TH>
                  <TH>Checksum</TH>
                  <TH>Retrieved</TH>
                </tr>
              </thead>
              <tbody>
                {datasets.map((dataset) => (
                  <tr key={dataset.id}>
                    <TD>{dataset.metrics.map(metricLabel).join(", ")}</TD>
                    <TD>{dataset.source.replace(/_/g, " ")}</TD>
                    <TD align="right" numeric>
                      {formatInteger(dataset.rows_accepted)}
                    </TD>
                    <TD align="right" numeric>
                      {dataset.series[0]?.hours ?? "—"}
                    </TD>
                    <TD>
                      {dataset.series.every((series) => series.is_contiguous) ? (
                        <span className="text-gain">contiguous</span>
                      ) : (
                        <span className="text-warn">has gaps</span>
                      )}
                    </TD>
                    <TD numeric>{shortChecksum(dataset.checksum)}</TD>
                    <TD>{formatDateTime(dataset.retrieved_at)}</TD>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}

          <div className="mt-4">
            <Disclosure title="Upload a dataset">
              <div className="grid gap-3 sm:grid-cols-3">
                <Field label="File" className="sm:col-span-2">
                  <input
                    ref={fileInput}
                    type="file"
                    accept=".csv,text/csv"
                    className="w-full text-xs text-ink-muted file:mr-2 file:rounded-[3px] file:border file:border-line-strong file:bg-panel file:px-2 file:py-1 file:text-xs file:text-ink"
                  />
                </Field>
                <Field label="Attach to facility">
                  <Select
                    value={uploadFacility}
                    onChange={(event) => setUploadFacility(event.target.value)}
                  >
                    <option value="">Unattached</option>
                    {facilities.map((facility) => (
                      <option key={facility.id} value={facility.id}>
                        {facility.name}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field
                  label="Default timezone"
                  hint="Only needed when timestamps carry no UTC offset."
                  className="sm:col-span-2"
                >
                  <Input
                    value={uploadTimezone}
                    onChange={(event) => setUploadTimezone(event.target.value)}
                    placeholder="America/Los_Angeles"
                  />
                </Field>
                <div className="flex items-end">
                  <Button variant="primary" onClick={submitUpload} disabled={uploading}>
                    {uploading ? "Validating…" : "Upload and validate"}
                  </Button>
                </div>
                <label className="flex items-center gap-2 text-xs text-ink-muted sm:col-span-3">
                  <input
                    type="checkbox"
                    className="accent-[var(--color-accent)]"
                    checked={allowGaps}
                    onChange={(event) => setAllowGaps(event.target.checked)}
                  />
                  Accept missing hours (recorded as warnings)
                </label>
              </div>
            </Disclosure>
          </div>
        </section>

        {/* --- 3. Weather -------------------------------------------------------- */}
        <section className="border-t border-line pt-4">
          <Disclosure title="Weather (context only)">
            <p className="mb-3 text-xs text-ink-muted">
              Retrieved from Open-Meteo for the selected facility. It does not enter the
              objective, so it cannot change a schedule.
            </p>

            <div className="flex flex-wrap items-end gap-3">
              <Field label="Facility" className="min-w-[200px]">
                <Select
                  value={uploadFacility}
                  onChange={(event) => setUploadFacility(event.target.value)}
                >
                  {facilities.map((facility) => (
                    <option key={facility.id} value={facility.id}>
                      {facility.name}
                    </option>
                  ))}
                </Select>
              </Field>
              <Button onClick={loadWeather} disabled={loadingWeather || !uploadFacility}>
                {loadingWeather ? "Fetching…" : "Fetch forecast"}
              </Button>
            </div>

            {weatherError && (
              <div className="mt-3">
                <Alert tone="warn">{weatherError}</Alert>
              </div>
            )}

            {weather && (
              <div className="mt-4">
                <Table>
                  <thead>
                    <tr>
                      <TH>Day</TH>
                      <TH align="right">Hour</TH>
                      <TH align="right">Temperature</TH>
                      <TH align="right">Humidity</TH>
                    </tr>
                  </thead>
                  <tbody>
                    {weather.points.slice(0, 24).map((point) => (
                      <tr key={point.timestamp_utc}>
                        <TD>{dayLabel(point.timestamp_utc)}</TD>
                        <TD align="right" numeric>
                          {point.timestamp_utc.slice(11, 16)}
                        </TD>
                        <TD align="right" numeric>
                          {point.temperature_c === null
                            ? "—"
                            : `${formatNumber(point.temperature_c)} °C`}
                        </TD>
                        <TD align="right" numeric>
                          {point.relative_humidity_pct === null
                            ? "—"
                            : `${formatNumber(point.relative_humidity_pct, 0)} %`}
                        </TD>
                      </tr>
                    ))}
                  </tbody>
                </Table>
                <p className="mt-2 text-[11px] text-ink-faint">
                  {weather.attribution}
                  {weather.from_cache ? " · served from cache" : ""}
                </p>
              </div>
            )}
          </Disclosure>
        </section>
      </div>
    </>
  );
}
