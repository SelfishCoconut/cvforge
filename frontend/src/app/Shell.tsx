import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link, NavLink } from "react-router";
import { api } from "../api/client";

const NAV = [
  { to: "/chat", label: "Chat" },
  { to: "/review", label: "Review" },
  { to: "/knowledge", label: "Knowledge" },
  { to: "/settings", label: "Settings" },
] as const;

function navClass({ isActive }: { isActive: boolean }): string {
  const base =
    "inline-block border-b-2 pb-1 pt-2 text-[0.9375rem] transition-colors hover:text-ink";
  return isActive
    ? `${base} border-accent text-ink`
    : `${base} border-transparent text-ink-muted hover:border-line`;
}

function BackendStatus() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  if (health.isPending) return <span className="text-ink-muted">checking backend…</span>;
  if (health.isError) return <span className="text-danger">backend unreachable</span>;
  return <span className="text-ink-muted">backend {health.data.version}</span>;
}

/** Persistent chrome: skip link, masthead with primary navigation, main region, status footer. */
export function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col bg-surface text-ink">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:bg-card focus:px-3 focus:py-2 focus:text-ink focus:ring-1 focus:ring-line"
      >
        Skip to content
      </a>
      <header className="border-b border-line">
        <div className="mx-auto flex max-w-5xl flex-wrap items-end justify-between gap-x-10 gap-y-2 px-4 pt-6 sm:px-8 sm:pt-8">
          <Link to="/chat" className="pb-3 font-display text-2xl leading-none text-ink">
            CVForge
          </Link>
          <nav aria-label="Primary" className="-mb-px w-full sm:w-auto">
            <ul className="flex gap-6 sm:gap-8">
              {NAV.map((item) => (
                <li key={item.to}>
                  <NavLink to={item.to} className={navClass}>
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      </header>
      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-5xl flex-1 px-4 py-10 sm:px-8">
        {children}
      </main>
      <footer className="border-t border-line">
        <div className="mx-auto max-w-5xl px-4 py-4 text-sm sm:px-8">
          <BackendStatus />
        </div>
      </footer>
    </div>
  );
}
