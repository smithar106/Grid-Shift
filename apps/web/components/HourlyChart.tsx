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

import { isDaily, toBuckets } from "@/lib/buckets";
import { useChartColors } from "@/lib/useChartColors";
import { formatMoney, formatNumber } from "@/lib/format";
import type { HourlyPoint } from "@/lib/types";

/**
 * Where the load lands, against the price that drove it.
 *
 * The chart adapts to the horizon: hourly bars up to four days, daily totals beyond that.
 * A fortnight of hourly bars is an unreadable smear, and at that scale the useful question
 * is which days took the work, not which hour.
 */
export function HourlyChart({ points }: { points: HourlyPoint[] }) {
  const colors = useChartColors();
  const buckets = toBuckets(points);
  const daily = isDaily(points);

  const unit = daily ? "MWh/day" : "MWh";
  const priceLabel = daily ? "Avg price" : "Price";

  return (
    <div className="h-[280px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={buckets} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
          <CartesianGrid stroke={colors.line} vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: colors.inkFaint, fontSize: 10 }}
            tickLine={false}
            axisLine={{ stroke: colors.line }}
            interval="preserveStartEnd"
            minTickGap={24}
          />
          <YAxis
            yAxisId="energy"
            tick={{ fill: colors.inkFaint, fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            width={48}
            label={{
              value: unit,
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
              return name === priceLabel
                ? [formatMoney(numeric, true), String(name)]
                : [`${formatNumber(numeric)} ${daily ? "MWh" : "MWh"}`, String(name)];
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
            type={daily ? "monotone" : "stepAfter"}
            dataKey="price"
            name={priceLabel}
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
