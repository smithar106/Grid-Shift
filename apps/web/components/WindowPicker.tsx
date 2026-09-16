"use client";

import { Select } from "@/components/ui";

/**
 * Pick a workload window in day-and-hour terms.
 *
 * The optimizer works in hour indices, but a two-week horizon makes "release hour 187"
 * meaningless to a person. Days and clock hours are how an operator actually thinks about
 * a maintenance window.
 */

const HOURS_PER_DAY = 24;

function toParts(hour: number): { day: number; hourOfDay: number } {
  return { day: Math.floor(hour / HOURS_PER_DAY), hourOfDay: hour % HOURS_PER_DAY };
}

function fromParts(day: number, hourOfDay: number, horizonHours: number): number {
  return Math.min(day * HOURS_PER_DAY + hourOfDay, horizonHours - 1);
}

function formatClock(hourOfDay: number): string {
  return `${String(hourOfDay).padStart(2, "0")}:00`;
}

export function WindowPicker({
  horizonHours,
  release_hour,
  deadline_hour,
  onChange,
}: {
  horizonHours: number;
  release_hour: number;
  deadline_hour: number;
  onChange: (next: { release_hour: number; deadline_hour: number }) => void;
}) {
  const dayCount = Math.max(1, Math.ceil(horizonHours / HOURS_PER_DAY));
  const start = toParts(release_hour);
  const end = toParts(deadline_hour);

  const days = Array.from({ length: dayCount }, (_, index) => index);
  const hours = Array.from({ length: HOURS_PER_DAY }, (_, index) => index);

  const setStart = (day: number, hourOfDay: number) => {
    const next = fromParts(day, hourOfDay, horizonHours);
    // Keep the window valid: a start after the deadline would be rejected by the API.
    onChange({
      release_hour: next,
      deadline_hour: Math.max(next, deadline_hour),
    });
  };

  const setEnd = (day: number, hourOfDay: number) => {
    const next = fromParts(day, hourOfDay, horizonHours);
    onChange({
      release_hour: Math.min(release_hour, next),
      deadline_hour: next,
    });
  };

  const spanDays = Math.max(1, Math.round(((deadline_hour - release_hour + 1) / HOURS_PER_DAY) * 10) / 10);

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
      <span className="flex items-center gap-1.5">
        <span className="text-[11px] uppercase tracking-[0.06em] text-ink-faint">from</span>
        <Select
          aria-label="Window start day"
          className="w-auto py-1"
          value={start.day}
          onChange={(event) => setStart(Number(event.target.value), start.hourOfDay)}
        >
          {days.map((day) => (
            <option key={day} value={day}>
              Day {day + 1}
            </option>
          ))}
        </Select>
        <Select
          aria-label="Window start hour"
          className="w-auto py-1"
          value={start.hourOfDay}
          onChange={(event) => setStart(start.day, Number(event.target.value))}
        >
          {hours.map((hour) => (
            <option key={hour} value={hour}>
              {formatClock(hour)}
            </option>
          ))}
        </Select>
      </span>

      <span className="flex items-center gap-1.5">
        <span className="text-[11px] uppercase tracking-[0.06em] text-ink-faint">to</span>
        <Select
          aria-label="Window end day"
          className="w-auto py-1"
          value={end.day}
          onChange={(event) => setEnd(Number(event.target.value), end.hourOfDay)}
        >
          {days.map((day) => (
            <option key={day} value={day}>
              Day {day + 1}
            </option>
          ))}
        </Select>
        <Select
          aria-label="Window end hour"
          className="w-auto py-1"
          value={end.hourOfDay}
          onChange={(event) => setEnd(end.day, Number(event.target.value))}
        >
          {hours.map((hour) => (
            <option key={hour} value={hour}>
              {formatClock(hour)}
            </option>
          ))}
        </Select>
      </span>

      <span className="tnum font-mono text-[11px] text-ink-faint">{spanDays}d window</span>
    </div>
  );
}
