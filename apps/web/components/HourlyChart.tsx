"use client";

import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useChartColors } from "@/lib/useChartColors";
import { formatMoney, formatNumber, hourLabel } from "@/lib/format";
import type { HourlyPoint } from "@/lib/types";

/**
 * Hourly consumption split into fixed and flexible load, with the price that drove the
 * schedule overlaid. The point of the chart is to show *why* the flexible blocks landed
 * where they did, so price and consumption must be visible together.
 */
export function HourlyChart({ points }: { points: HourlyPoint[] }) {
  const colors = useChartColors();

  const data = points.map((point) => ({
    hour: hourLabel(point.timestamp_utc),
    fixed: point.baseline_load_mwh,
    flexible: point.optimized_flexible_mwh,
    price: point.price_usd_per_mwh,
    capacity: point.capacity_mwh,
  }));

  return (
    <div className="h-[280px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
          <CartesianGrid stroke={colors.line} vertical={false} />
          <XAxis
            dataKey="hour"
            tick={{ fill: colors.inkFaint, fontSize: 10 }}
            tickLine={false}
            axisLine={{ stroke: colors.line }}
            interval={1}
          />
          <YAxis
            yAxisId="energy"
            tick={{ fill: colors.inkFaint, fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            width={44}
            label={{
              value: "MWh",
              angle: -90,
              position: "insideLeft",
              fill: colors.inkFaint,
              fontSize: 10,
              offset: 12,
            }}
          />
          <YAxis
            yAxisId="price"
            orientation="right"
            tick={{ fill: colors.inkFaint, fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            width={52}
            label={{
              value: "USD/MWh",
              angle: 90,
              position: "insideRight",
              fill: colors.inkFaint,
              fontSize: 10,
              offset: 12,
            }}
          />
          <Tooltip
            contentStyle={{
              background: colors.panel,
              border: `1px solid ${colors.line}`,
              borderRadius: 3,
              fontSize: 12,
            }}
            labelStyle={{ color: colors.inkMuted }}
            formatter={(value, name) => {
              const numeric = typeof value === "number" ? value : Number(value ?? 0);
              return name === "Price"
                ? [formatMoney(numeric, true), String(name)]
                : [`${formatNumber(numeric)} MWh`, String(name)];
            }}
          />
          <Legend
            wrapperStyle={{ fontSize: 11, color: colors.inkMuted }}
            iconType="square"
            iconSize={9}
          />
          <Bar
            yAxisId="energy"
            dataKey="fixed"
            name="Fixed load"
            stackId="load"
            fill={colors.baseline}
          />
          <Bar
            yAxisId="energy"
            dataKey="flexible"
            name="Flexible (optimized)"
            stackId="load"
            fill={colors.accent}
          />
          <Line
            yAxisId="price"
            type="stepAfter"
            dataKey="price"
            name="Price"
            stroke={colors.inkMuted}
            strokeWidth={1.25}
            strokeDasharray="3 3"
            dot={false}
          />
          <Line
            yAxisId="energy"
            type="stepAfter"
            dataKey="capacity"
            name="Capacity"
            stroke={colors.inkFaint}
            strokeWidth={1}
            strokeDasharray="1 3"
            dot={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
