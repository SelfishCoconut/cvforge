import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { api, ApiError } from "../../api/client";
import type { EdgeRecord, EntityRecord } from "../../api/types";
import { WhyDrawer } from "./WhyDrawer";
import { WRAP } from "../../ui/text";

const LINK = "text-accent underline decoration-1 underline-offset-4";
const WHY_BUTTON =
  "rounded-sm text-sm text-accent underline decoration-1 underline-offset-4 hover:text-ink";

function NotFound() {
  return (
    <section className="max-w-3xl">
      <h1 className="text-3xl">Entity not found</h1>
      <p className="mt-4">
        <Link to="/knowledge" className={LINK}>
          Back to knowledge
        </Link>
      </p>
    </section>
  );
}

function Attributes({ attributes }: { attributes: Record<string, unknown> }) {
  const entries = Object.entries(attributes);
  if (entries.length === 0) return null;
  return (
    <dl className="mt-6 grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
      {entries.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className={`text-ink-muted ${WRAP}`}>{k}</dt>
          <dd className={WRAP}>{typeof v === "string" ? v : JSON.stringify(v)}</dd>
        </div>
      ))}
    </dl>
  );
}

/** The display name of an entity, or a placeholder until (or unless) it loads. */
function useEntityName(id: number): string {
  const q = useQuery({
    queryKey: ["entity", id],
    queryFn: () => api.getEntity(id),
    retry: false,
  });
  return q.data ? q.data.name : `Entity ${id}`;
}

function EndName({ id }: { id: number }) {
  const name = useEntityName(id);
  return (
    <Link to={`/knowledge/${id}`} className={`${LINK} ${WRAP}`}>
      {name}
    </Link>
  );
}

function End({ id, current, name }: { id: number; current: number; name: string }) {
  if (id === current) return <span className={`font-medium ${WRAP}`}>{name}</span>;
  return <EndName id={id} />;
}

function EdgeRow({
  edge,
  entity,
  onWhy,
}: {
  edge: EdgeRecord;
  entity: EntityRecord;
  onWhy: (edgeId: number) => void;
}) {
  const otherId = edge.src_id === entity.id ? edge.dst_id : edge.src_id;
  const otherName = useEntityName(otherId);
  return (
    <li className="py-3">
      <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <End id={edge.src_id} current={entity.id} name={entity.name} />
        <span className="text-ink-muted">→</span>
        <span className="font-mono text-sm text-ink-muted">{edge.rel}</span>
        <span className="text-ink-muted">→</span>
        <End id={edge.dst_id} current={entity.id} name={entity.name} />
        <button
          type="button"
          aria-label={`Why: ${edge.rel} ${otherName}`}
          className={`ml-auto ${WHY_BUTTON}`}
          onClick={() => onWhy(edge.id)}
        >
          why?
        </button>
      </p>
      {edge.note && <p className={`mt-1 text-sm text-ink-muted ${WRAP}`}>{edge.note}</p>}
      {edge.confidence !== null && (
        <p className="mt-1 text-sm text-ink-muted">confidence {edge.confidence}</p>
      )}
    </li>
  );
}

function Edges({ entity, onWhy }: { entity: EntityRecord; onWhy: (edgeId: number) => void }) {
  const q = useQuery({
    queryKey: ["edges", entity.id],
    queryFn: () => api.getEdges(entity.id),
  });
  let body;
  if (q.isPending) body = <p className="text-ink-muted">Loading relationships…</p>;
  else if (q.isError) {
    body = (
      <p role="alert" className={`text-danger ${WRAP}`}>
        Could not load relationships: {q.error.message}
      </p>
    );
  } else if (q.data.length === 0)
    body = <p className="text-ink-muted">No relationships recorded.</p>;
  else {
    body = (
      <ul className="divide-y divide-line">
        {q.data.map((e) => (
          <EdgeRow key={e.id} edge={e} entity={entity} onWhy={onWhy} />
        ))}
      </ul>
    );
  }
  return (
    <section className="mt-10" aria-labelledby="edges-h">
      <h2 id="edges-h" className="text-xl">
        Relationships
      </h2>
      <div className="mt-3">{body}</div>
    </section>
  );
}

function Detail({ entity }: { entity: EntityRecord }) {
  const [why, setWhy] = useState<{
    kind: "entity" | "edge";
    id: number;
  } | null>(null);
  // Remember the last target so the closing drawer keeps its content while animating out.
  const [last, setLast] = useState<{ kind: "entity" | "edge"; id: number }>({
    kind: "entity",
    id: entity.id,
  });
  const show = (kind: "entity" | "edge", id: number) => {
    setLast({ kind, id });
    setWhy({ kind, id });
  };
  return (
    <section className="max-w-3xl">
      <h1 className={`text-3xl ${WRAP}`}>{entity.name}</h1>
      <p className="mt-2 flex gap-x-3 text-sm text-ink-muted">
        <span>{entity.kind}</span>
        <span>{entity.state}</span>
      </p>
      {entity.summary && <p className={`mt-4 ${WRAP}`}>{entity.summary}</p>}
      <Attributes attributes={entity.attributes ?? {}} />
      <p className="mt-6">
        <button type="button" className={WHY_BUTTON} onClick={() => show("entity", entity.id)}>
          Why do we know this?
        </button>
      </p>
      <Edges entity={entity} onWhy={(id) => show("edge", id)} />
      <WhyDrawer
        kind={last.kind}
        id={last.id}
        open={why !== null}
        onOpenChange={(o) => {
          if (!o) setWhy(null);
        }}
      />
    </section>
  );
}

function Loaded({ id }: { id: number }) {
  const q = useQuery({
    queryKey: ["entity", id],
    queryFn: () => api.getEntity(id),
    retry: false,
  });
  if (q.isPending) return <p className="text-ink-muted">Loading entity…</p>;
  if (q.isError) {
    if (q.error instanceof ApiError && q.error.status === 404) return <NotFound />;
    return (
      <p role="alert" className={`text-danger ${WRAP}`}>
        Could not load entity: {q.error.message}
      </p>
    );
  }
  return <Detail key={q.data.id} entity={q.data} />;
}

/** Read-only detail for one entity: attributes, relationships and the "why?" evidence drawer. */
export function EntityPage() {
  const { id } = useParams();
  const n = Number(id);
  if (!/^\d+$/.test(id ?? "") || !Number.isSafeInteger(n)) return <NotFound />;
  return <Loaded id={n} />;
}
