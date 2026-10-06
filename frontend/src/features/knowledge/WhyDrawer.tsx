import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "../../api/client";
import type { ProvenanceRecord } from "../../api/types";
import { Drawer } from "../../ui/Drawer";
import { WRAP } from "./vocab";

interface WhyDrawerProps {
  kind: "entity" | "edge";
  id: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function formatValue(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value);
}

function Assertion({ p }: { p: ProvenanceRecord }) {
  return (
    <li className="py-4">
      <p className={`text-sm text-ink-muted ${WRAP}`}>
        {p.source_kind} · {p.source_label}
      </p>
      <blockquote
        className={`mt-2 border-l-2 border-line pl-4 font-display text-lg leading-snug whitespace-pre-wrap ${WRAP}`}
      >
        {p.excerpt}
      </blockquote>
      <p className={`mt-1 font-mono text-xs text-ink-muted ${WRAP}`}>{p.locator}</p>
      {p.field !== null && (
        <p className={`mt-2 text-sm ${WRAP}`}>
          <span className="text-ink-muted">{p.field}</span>: {formatValue(p.value)}
        </p>
      )}
    </li>
  );
}

function Body({ kind, id, open }: Omit<WhyDrawerProps, "onOpenChange">) {
  const q = useQuery({
    queryKey: ["provenance", kind, id],
    queryFn: () => api.getProvenance(kind, id),
    enabled: open,
    retry: false,
  });
  if (q.isPending) return <p className="mt-4 text-ink-muted">Loading evidence…</p>;
  if (q.isError) {
    if (q.error instanceof ApiError && q.error.status === 404) {
      return <p className="mt-4 text-ink-muted">No evidence is recorded for this item.</p>;
    }
    return (
      <p role="alert" className={`mt-4 text-danger ${WRAP}`}>
        Could not load evidence: {q.error.message}
      </p>
    );
  }
  return (
    <ul className="mt-4 divide-y divide-line">
      {q.data.map((p) => (
        <Assertion key={p.assertion_id} p={p} />
      ))}
    </ul>
  );
}

/** Side drawer listing the stored assertions (source, locator, literal excerpt) behind an item. */
export function WhyDrawer({ kind, id, open, onOpenChange }: WhyDrawerProps) {
  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title="Why do we know this?"
      description={`Evidence recorded for this ${kind}.`}
    >
      <Body kind={kind} id={id} open={open} />
    </Drawer>
  );
}
