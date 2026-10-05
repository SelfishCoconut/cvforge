import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router";
import { api } from "../../api/client";
import type { EntityRecord } from "../../api/types";
import { KINDS, pick, STATES, WRAP } from "./vocab";

const SELECT = "mt-1 block rounded-sm border border-line bg-card px-2 py-1.5 text-sm text-ink";

function Filter({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: readonly string[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="text-sm text-ink-muted">
      {label}
      <select className={SELECT} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">All</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  );
}

function Row({ e }: { e: EntityRecord }) {
  return (
    <li>
      <Link
        to={`/knowledge/${e.id}`}
        className="group block py-4 hover:bg-card focus-visible:bg-card sm:px-3"
      >
        <span className={`block font-display text-lg group-hover:text-accent ${WRAP}`}>
          {e.name}
        </span>
        <span className="mt-1 flex gap-x-3 text-sm text-ink-muted">
          <span>{e.kind}</span>
          <span>{e.state}</span>
        </span>
      </Link>
    </li>
  );
}

/** Read-only list of knowledge entities, filterable by kind and state via the URL. */
export function KnowledgePage() {
  const [params, setParams] = useSearchParams();
  const kind = pick(KINDS, params.get("kind"));
  const state = pick(STATES, params.get("state"));
  const q = useQuery({
    queryKey: ["entities", kind ?? null, state ?? null],
    queryFn: () => api.listEntities({ kind, state }),
  });

  const set = (key: "kind" | "state") => (v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(key, v);
    else next.delete(key);
    setParams(next);
  };

  return (
    <section className="max-w-3xl">
      <h1 className="text-3xl">Knowledge</h1>
      <div className="mt-6 flex flex-wrap gap-4">
        <Filter label="Kind" value={kind ?? ""} options={KINDS} onChange={set("kind")} />
        <Filter label="State" value={state ?? ""} options={STATES} onChange={set("state")} />
      </div>
      <div className="mt-6">
        {q.isPending && <p className="text-ink-muted">Loading entities…</p>}
        {q.isError && (
          <p role="alert" className={`text-danger ${WRAP}`}>
            Could not load entities: {q.error.message}
          </p>
        )}
        {q.isSuccess && q.data.length === 0 && <p className="text-ink-muted">No entities match.</p>}
        {q.isSuccess && q.data.length > 0 && (
          <ul className="divide-y divide-line">
            {q.data.map((e) => (
              <Row key={e.id} e={e} />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
