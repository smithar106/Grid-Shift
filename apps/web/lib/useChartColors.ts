"use client";

import { useSyncExternalStore } from "react";

/**
 * Resolve design tokens to concrete colours for SVG.
 *
 * SVG presentation attributes do not support `var()`, so Recharts needs real values.
 * Reading them from the stylesheet keeps the tokens as the single source of truth and
 * lets the charts follow the colour scheme without duplicating the palette.
 *
 * The stylesheet is external state, so this subscribes to it with
 * `useSyncExternalStore` rather than mirroring it into React state in an effect. The
 * cached snapshot keeps `getSnapshot` referentially stable, which the store contract
 * requires.
 */

const TOKENS = {
  accent: "--color-accent",
  baseline: "--color-baseline",
  ink: "--color-ink",
  inkMuted: "--color-ink-muted",
  inkFaint: "--color-ink-faint",
  line: "--color-line",
  gain: "--color-gain",
  loss: "--color-loss",
  panel: "--color-panel",
} as const;

export type ChartColors = Record<keyof typeof TOKENS, string>;

const FALLBACKS: ChartColors = {
  accent: "#b45309",
  baseline: "#a8a29e",
  ink: "#1b1a17",
  inkMuted: "#6a675f",
  inkFaint: "#97938b",
  line: "#e5e3de",
  gain: "#15803d",
  loss: "#b91c1c",
  panel: "#ffffff",
};

function readColors(): ChartColors {
  if (typeof document === "undefined") return FALLBACKS;
  const styles = getComputedStyle(document.documentElement);
  const resolved = { ...FALLBACKS };
  for (const [key, token] of Object.entries(TOKENS) as Array<[keyof ChartColors, string]>) {
    const value = styles.getPropertyValue(token).trim();
    if (value) resolved[key] = value;
  }
  return resolved;
}

const listeners = new Set<() => void>();
let snapshot: ChartColors = FALLBACKS;
let subscribed = false;

function publish(): void {
  snapshot = readColors();
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);

  if (!subscribed && typeof window !== "undefined") {
    subscribed = true;
    window
      .matchMedia("(prefers-color-scheme: dark)")
      .addEventListener("change", publish);
  }

  // The tokens are only readable once the stylesheet has applied on the client.
  if (typeof document !== "undefined") publish();

  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot(): ChartColors {
  return snapshot;
}

function getServerSnapshot(): ChartColors {
  return FALLBACKS;
}

export function useChartColors(): ChartColors {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
