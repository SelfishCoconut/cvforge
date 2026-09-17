import { useEffect, useState } from "react";
import { fetchHealth, type Health } from "./api";

type BackendState =
  | { kind: "loading" }
  | { kind: "ok"; health: Health }
  | { kind: "error"; message: string };

export default function App() {
  const [backend, setBackend] = useState<BackendState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    fetchHealth()
      .then((health) => {
        if (!cancelled) setBackend({ kind: "ok", health });
      })
      .catch(() => {
        if (!cancelled) setBackend({ kind: "error", message: "backend unreachable" });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-dvh bg-surface text-ink">
      <header className="mx-auto flex max-w-3xl items-baseline justify-between px-6 py-10">
        <h1 className="font-display text-2xl tracking-tight">CVForge</h1>
        <StatusBadge backend={backend} />
      </header>
      <main className="mx-auto max-w-3xl px-6">
        <p className="max-w-prose text-ink-muted">
          A local-first knowledge base of everything you have done professionally — and
          the tailored, evidence-backed CVs it writes.
        </p>
      </main>
    </div>
  );
}

function StatusBadge({ backend }: { backend: BackendState }) {
  if (backend.kind === "loading") {
    return <span className="text-sm text-ink-muted">checking…</span>;
  }
  if (backend.kind === "error") {
    return <span className="text-sm text-danger">backend unreachable</span>;
  }
  return <span className="text-sm text-ink-muted">backend {backend.health.version}</span>;
}
