"use client";

import {
  CartesianGrid,
  Label,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";

import { useChartColors } from "@/lib/useChartColors";
import { formatMoney, formatNumber } from "@/lib/format";
import type { TradeoffCurve } from "@/lib/types";

/**
 * The cost/emissions frontier across carbon prices.
 *
 * Each point is a full solve, so this is the model's own trade-off rather than a
 * smoothed illustration. The baseline is drawn as a reference so the reader can see
 * immediately which region is an improvement on business as usual.
 */
export function TradeoffScatter({ curve }: { curve: TradeoffCurve }) {
  const colors = useChartColors();

  const data = curve.points.map((point) => ({
    cost: point.total_cost_usd,
    emissions: point.total_emissions_tco2e,
    carbonPrice: point.carbon_price_usd_per_tco2e,
  }));

  const baseline =
    curve.baseline_total_cost_usd !== null &&
    curve.baseline_total_emissions_tco2e !== null
      ? {
          cost: curve.baseline_total_cost_usd,
          emissions: curve.baseline_total_emissions_tco2e,
        }
      : null;

  const allCosts = [
    ...data.map((d) => d.cost),
    ...(baseline ? [baseline.cost] : []),
  ];
  const allEmissions = [
    ...data.map((d) => d.emissions),
    ...(baseline ? [baseline.emissions] : []),
  ];

  const pad = (values: number[]) => {
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || Math.max(1, Math.abs(max) * 0.1);
    return [min - span * 0.12, max + span * 0.12] as const;
  };

  const [costMin, costMax] = pad(allCosts);
  const [emissionsMin, emissionsMax] = pad(allEmissions);

  /**
   * Axis ticks must be precise enough to distinguish the points. A frontier can span a
   * fraction of a tonne, and rounding to integers would label every tick identically.
   */
  const moneyTicks = (min: number, max: number) => {
    const span = max - min;
    if (span >= 20_000)
      return (value: number) => `$${Math.round(value / 1000)}k`;
    if (span >= 2_000)
      return (value: number) => `$${(value / 1000).toFixed(1)}k`;
    return (value: number) => `$${Math.round(value)}`;
  };

  const numberTicks = (min: number, max: number) => {
    const span = max - min;
    if (span >= 20) return (value: number) => value.toFixed(0);
    if (span >= 2) return (value: number) => value.toFixed(1);
    if (span >= 0.2) return (value: number) => value.toFixed(2);
    return (value: number) => value.toFixed(3);
  };

  const costTick = moneyTicks(costMin, costMax);
  const emissionTick = numberTicks(emissionsMin, emissionsMax);

  // Identical carbon prices can yield identical schedules, so report distinct points.
  const distinct = new Set(
    data.map((point) => `${point.cost}|${point.emissions}`),
  ).size;

  return (
    <div className="flex flex-col gap-2">
      <div className="h-[280px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 8, right: 24, bottom: 24, left: 8 }}>
            <CartesianGrid stroke={colors.line} />
            <XAxis
              type="number"
              dataKey="cost"
              domain={[costMin, costMax]}
              tickCount={5}
              tick={{ fill: colors.inkFaint, fontSize: 10 }}
              tickLine={false}
              axisLine={{ stroke: colors.line }}
              tickFormatter={costTick}
            >
              <Label
                value="Modelled cost (USD)"
                position="insideBottom"
                offset={-16}
                fill={colors.inkFaint}
                fontSize={10}
              />
            </XAxis>
            <YAxis
              type="number"
              dataKey="emissions"
              domain={[emissionsMin, emissionsMax]}
              tickCount={5}
              tick={{ fill: colors.inkFaint, fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              width={60}
              tickFormatter={emissionTick}
            >
              <Label
                value="Modelled emissions (tCO2e)"
                angle={-90}
                position="insideLeft"
                fill={colors.inkFaint}
                fontSize={10}
                offset={14}
              />
            </YAxis>
            <ZAxis range={[70, 70]} />
            <Tooltip
              contentStyle={{
                background: colors.panel,
                border: `1px solid ${colors.line}`,
                borderRadius: 3,
                fontSize: 12,
              }}
              content={({ payload }) => {
                const point = payload?.[0]?.payload as
                  | { cost: number; emissions: number; carbonPrice?: number }
                  | undefined;
                if (!point) return null;
                return (
                  <div
                    className="rounded-[3px] border px-2 py-1.5 text-xs"
                    style={{
                      background: colors.panel,
                      borderColor: colors.line,
                    }}
                  >
                    {point.carbonPrice !== undefined && (
                      <div style={{ color: colors.inkMuted }}>
                        Carbon price {formatMoney(point.carbonPrice)}
                      </div>
                    )}
                    <div style={{ color: colors.ink }}>
                      {formatMoney(point.cost)} cost
                    </div>
                    <div style={{ color: colors.ink }}>
                      {formatNumber(point.emissions, 2)} tCO2e
                    </div>
                  </div>
                );
              }}
            />

            {baseline && (
              <ReferenceLine
                x={baseline.cost}
                stroke={colors.baseline}
                strokeDasharray="3 3"
                label={{
                  value: "Baseline",
                  position: "insideTopLeft",
                  fill: colors.inkFaint,
                  fontSize: 10,
                }}
              />
            )}
            {baseline && (
              <ReferenceLine
                y={baseline.emissions}
                stroke={colors.baseline}
                strokeDasharray="3 3"
              />
            )}

            <Scatter
              name="Frontier"
              data={data}
              fill={colors.accent}
              line={{ stroke: colors.accent, strokeWidth: 1 }}
              shape="circle"
            />
            {baseline && (
              <Scatter
                name="Baseline"
                data={[baseline]}
                fill={colors.baseline}
                shape="square"
                legendType="square"
              />
            )}
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      <p className="text-[11px] text-ink-faint">
        {curve.points.length} carbon prices solved · {distinct} distinct outcome
        {distinct === 1 ? "" : "s"}. Dashed lines mark the earliest-feasible
        baseline.
      </p>
    </div>
  );
}
