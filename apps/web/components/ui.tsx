/**
 * Shared UI primitives.
 *
 * Deliberately sparse. GridShift is an analyst instrument, so hierarchy comes from
 * typography, alignment and rules rather than from cards, shadows and badges. A new
 * visual layer has to earn its place.
 */

import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

export function cx(...values: Array<string | false | null | undefined>): string {
  return values.filter(Boolean).join(" ");
}

// --- Layout ------------------------------------------------------------------------

export function Panel({
  title,
  action,
  children,
  description,
  className,
}: {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
  description?: string;
  className?: string;
}) {
  return (
    <section className={cx("border-t border-line pt-3", className)}>
      {(title || action) && (
        <header className="mb-3 flex items-baseline justify-between gap-4">
          <div>
            {title && (
              <h2 className="text-[11px] font-medium uppercase tracking-[0.08em] text-ink-muted">
                {title}
              </h2>
            )}
            {description && <p className="mt-1 text-xs text-ink-faint">{description}</p>}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function PageHeader({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <h1 className="text-lg font-medium tracking-tight text-ink">{title}</h1>
      {children && <div className="flex items-center gap-2">{children}</div>}
    </div>
  );
}

export function Columns({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("grid gap-8", className)}>{children}</div>;
}

// --- Controls ----------------------------------------------------------------------

type ButtonVariant = "primary" | "secondary" | "ghost";

export function Button({
  variant = "secondary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  const base =
    "inline-flex items-center justify-center gap-1.5 rounded-[3px] px-2.5 py-1.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45";
  const variants: Record<ButtonVariant, string> = {
    primary: "bg-accent text-white hover:bg-accent-hover",
    secondary: "border border-line-strong text-ink hover:bg-sunken",
    ghost: "text-ink-muted hover:bg-sunken hover:text-ink",
  };
  return <button className={cx(base, variants[variant], className)} {...props} />;
}

/**
 * A labelled control.
 *
 * The control is wrapped *inside* the `<label>` rather than referenced by `htmlFor`, so
 * the association is implicit and cannot be forgotten. Several call sites render a label
 * without an id, which produced controls that looked labelled but were announced as
 * unlabelled by a screen reader.
 */
export function Field({
  label,
  hint,
  error,
  children,
  className,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={cx("flex flex-col gap-1", className)}>
      <span className="text-[11px] font-medium uppercase tracking-[0.06em] text-ink-muted">
        {label}
      </span>
      {children}
      {error ? (
        <span className="text-xs text-loss">{error}</span>
      ) : hint ? (
        <span className="text-xs text-ink-faint">{hint}</span>
      ) : null}
    </label>
  );
}

const controlClass =
  "w-full rounded-[3px] border border-line-strong bg-panel px-2 py-1.5 text-sm text-ink placeholder:text-ink-faint disabled:opacity-50";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cx(controlClass, className)} {...props} />;
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cx(controlClass, "pr-7", className)} {...props}>
      {children}
    </select>
  );
}

// --- Data display ------------------------------------------------------------------

export function Table({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cx("overflow-x-auto", className)}>
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  );
}

export function TH({
  children,
  align = "left",
  className,
}: {
  children?: ReactNode;
  align?: "left" | "right";
  className?: string;
}) {
  return (
    <th
      scope="col"
      className={cx(
        "border-b border-line-strong pb-1.5 pr-4 text-[10px] font-medium uppercase tracking-[0.07em] text-ink-faint last:pr-0",
        align === "right" ? "text-right" : "text-left",
        className,
      )}
    >
      {children}
    </th>
  );
}

export function TD({
  children,
  align = "left",
  numeric = false,
  className,
  colSpan,
}: {
  children?: ReactNode;
  align?: "left" | "right";
  numeric?: boolean;
  className?: string;
  colSpan?: number;
}) {
  return (
    <td
      colSpan={colSpan}
      className={cx(
        "border-b border-line py-1.5 pr-4 align-top text-ink last:pr-0",
        align === "right" ? "text-right" : "text-left",
        numeric && "tnum font-mono text-[13px]",
        className,
      )}
    >
      {children}
    </td>
  );
}

export function DefinitionList({ items }: { items: Array<{ term: string; value: ReactNode }> }) {
  return (
    <dl className="grid grid-cols-[minmax(7rem,auto)_1fr] gap-x-6 gap-y-1.5 text-sm">
      {items.map((item) => (
        <div key={item.term} className="contents">
          <dt className="text-ink-muted">{item.term}</dt>
          <dd className="text-ink">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** A single figure. No card, no icon, no coloured badge. */
export function Stat({
  label,
  value,
  detail,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: "neutral" | "gain" | "loss" | "warn";
}) {
  const toneClass = {
    neutral: "text-ink",
    gain: "text-gain",
    loss: "text-loss",
    warn: "text-warn",
  }[tone];
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] uppercase tracking-[0.06em] text-ink-muted">{label}</span>
      <span className={cx("tnum font-mono text-xl leading-tight", toneClass)}>{value}</span>
      {detail && <span className="text-xs text-ink-faint">{detail}</span>}
    </div>
  );
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "gain" | "loss" | "warn" | "accent" }) {
  const toneClass = {
    neutral: "border-line-strong text-ink-muted",
    gain: "border-gain/40 text-gain",
    loss: "border-loss/40 text-loss",
    warn: "border-warn/40 text-warn",
    accent: "border-accent/40 text-accent",
  }[tone];
  return (
    <span
      className={cx(
        "inline-block rounded-[3px] border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-[0.06em]",
        toneClass,
      )}
    >
      {children}
    </span>
  );
}

export function Alert({
  tone = "neutral",
  title,
  children,
}: {
  tone?: "neutral" | "gain" | "loss" | "warn";
  title?: string;
  children: ReactNode;
}) {
  const border = {
    neutral: "border-line-strong",
    gain: "border-gain/50",
    loss: "border-loss/50",
    warn: "border-warn/50",
  }[tone];
  return (
    <div className={cx("border-l-2 py-1.5 pl-3 text-sm", border)} role={tone === "loss" ? "alert" : undefined}>
      {title && <p className="font-medium text-ink">{title}</p>}
      <div className="text-ink-muted">{children}</div>
    </div>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="py-6 text-sm text-ink-faint">{children}</p>;
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <p className="py-6 text-sm text-ink-faint" role="status" aria-live="polite">
      {label}…
    </p>
  );
}
