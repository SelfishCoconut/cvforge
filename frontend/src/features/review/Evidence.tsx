import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { WRAP } from "../../ui/text";


/** The cited evidence excerpt, fetched by id. Untrusted text: rendered as text nodes only. */
export function Evidence({ evidenceId }: { evidenceId: number | null }) {
  const q = useQuery({
    queryKey: ["evidence", evidenceId],
    queryFn: () => api.getEvidence(evidenceId as number),
    enabled: evidenceId !== null,
  });
  if (evidenceId === null) return <p className="text-sm text-ink-muted">No evidence cited</p>;
  if (q.isPending) return <p className="text-sm text-ink-muted">Loading evidence…</p>;
  if (q.isError) return <p className="text-sm text-ink-muted">Evidence unavailable</p>;
  return (
    <figure className="border-l-2 border-line pl-4">
      <blockquote className={`whitespace-pre-wrap font-display text-lg leading-snug ${WRAP}`}>
        {q.data.excerpt}
      </blockquote>
      <figcaption className={`mt-1 text-xs text-ink-muted ${WRAP}`}>
        {q.data.source_label} · {q.data.locator}
      </figcaption>
    </figure>
  );
}
