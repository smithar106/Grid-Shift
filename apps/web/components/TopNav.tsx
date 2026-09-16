"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { getHealth } from "@/lib/api";
import { cx } from "@/components/ui";

const LINKS = [
  { href: "/", label: "Optimize" },
  { href: "/scenarios", label: "Scenarios" },
  { href: "/data", label: "Data" },
] as const;

type Status = { state: "checking" | "up" | "down"; detail: string };

/**
 * The API is reachable only through the Next.js proxy on the private network, so a
 * failure here is worth surfacing rather than letting every screen fail individually.
 */
function useApiStatus(): Status {
  const [status, setStatus] = useState<Status>({ state: "checking", detail: "Checking API" });

  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      try {
        const health = await getHealth();
        if (!cancelled) {
          setStatus({ state: "up", detail: `API ${health.version} · ${health.environment}` });
        }
      } catch {
        if (!cancelled) setStatus({ state: "down", detail: "API unreachable" });
      }
    };

    void check();
    const timer = setInterval(check, 60_000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  return status;
}

export function TopNav() {
  const pathname = usePathname();
  const status = useApiStatus();

  const dot =
    status.state === "up"
      ? "bg-gain"
      : status.state === "down"
        ? "bg-loss"
        : "bg-ink-faint";

  return (
    <header className="sticky top-0 z-10 border-b border-line bg-canvas">
      <div className="mx-auto flex h-12 max-w-[1440px] items-center gap-8 px-6">
        <Link href="/" className="text-sm font-semibold tracking-tight text-ink">
          GridShift
        </Link>

        <nav aria-label="Primary" className="flex items-center gap-1">
          {LINKS.map((link) => {
            const active =
              link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);

            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active ? "page" : undefined}
                className={cx(
                  "rounded-[3px] px-2 py-1 text-xs transition-colors",
                  active ? "text-ink" : "text-ink-muted hover:text-ink",
                )}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-2" title={status.detail}>
          <span className={cx("size-1.5 rounded-full", dot)} aria-hidden />
          <span className="text-[11px] text-ink-faint">{status.detail}</span>
        </div>
      </div>
    </header>
  );
}
