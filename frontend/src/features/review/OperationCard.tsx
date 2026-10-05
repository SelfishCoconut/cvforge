import { useId } from "react";
import type { OperationRecord } from "../../api/types";
import { ClassificationBadge } from "../../ui/Badge";
import { allowedDecisions, type Decision } from "./actions";
import { EditOperationDialog } from "./EditOperationDialog";
import { Evidence } from "./Evidence";
import { explain, summarise } from "./explain";

const WRAP = "break-words [overflow-wrap:anywhere]";
const BUTTON =
  "rounded-sm px-4 py-1.5 text-sm font-medium ring-1 ring-inset disabled:cursor-not-allowed disabled:opacity-40";
const TONE: Record<Decision, string> = {
  accept: "bg-accent text-surface ring-accent",
  edit: "text-ink ring-line hover:bg-surface",
  reject: "text-danger ring-line hover:bg-surface",
};
const STATUS_TEXT: ReadonlyMap<string, string> = new Map([
  ["pending", "Awaiting review"],
  ["accepted", "Accepted"],
  ["edited", "Accepted with edits"],
  ["rejected", "Rejected"],
  ["applied", "Applied"],
]);

interface Props {
  op: OperationRecord;
  proposalOpen: boolean;
  /** A decision on this operation is in flight. */
  busy: boolean;
  /** The server's reason the last decision on this card failed. */
  error: string | null;
  /** Records a decision; resolves to null on success or the server's reason on failure. */
  onDecide: (decision: Decision, edited?: Record<string, unknown>) => Promise<string | null>;
}

function evidenceIdOf(payload: Record<string, unknown>): number | null {
  const id = payload["evidence_id"];
  return typeof id === "number" ? id : null;
}

function Payload({ label, value, open }: { label: string; value: unknown; open?: boolean }) {
  return (
    <details open={open} className="text-sm">
      <summary className="cursor-pointer text-ink-muted hover:text-ink">{label}</summary>
      <pre
        className={`mt-2 whitespace-pre-wrap rounded-sm bg-surface p-3 font-mono text-xs ${WRAP}`}
      >
        {JSON.stringify(value, null, 2)}
      </pre>
    </details>
  );
}

/**
 * One proposed operation: what it is, why it was classified as it was, the
 * evidence behind it, and the decisions `allowedDecisions` permits. All text
 * comes from untrusted documents and renders as text nodes only.
 */
export function OperationCard({ op, proposalOpen, busy, error, onDecide }: Props) {
  const headingId = useId();
  const decisions = allowedDecisions(op.status, proposalOpen);
  const edited = op.edited_payload !== null;

  return (
    <article aria-labelledby={headingId} className="rounded-sm bg-card p-5 ring-1 ring-line sm:p-6">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <ClassificationBadge value={op.classification} />
        <span className={`font-mono text-xs text-ink-muted ${WRAP}`}>{op.op_type}</span>
        <span className="ml-auto text-xs text-ink-muted">
          {STATUS_TEXT.get(op.status) ?? op.status}
        </span>
      </div>
      <h2 id={headingId} className={`mt-3 text-xl ${WRAP}`}>
        {summarise(op)}
      </h2>
      <p className="mt-1 text-sm text-ink-muted">{explain(op.classification, op.op_type)}</p>
      <div className="mt-4">
        <Evidence evidenceId={evidenceIdOf(op.edited_payload ?? op.payload)} />
      </div>
      {op.rationale && <p className={`mt-3 text-sm ${WRAP}`}>{op.rationale}</p>}
      <div className="mt-4 space-y-2">
        {edited && <Payload label="Edited payload" value={op.edited_payload} open />}
        <Payload label={edited ? "Original payload" : "Payload"} value={op.payload} />
      </div>
      {decisions.length > 0 && (
        <div className="mt-5 flex flex-wrap gap-3">
          {decisions.map((d) =>
            d === "edit" ? (
              <EditOperationDialog
                key={d}
                op={op}
                label={edited ? "Edit again" : "Edit"}
                describedBy={headingId}
                disabled={busy}
                className={`${BUTTON} ${TONE.edit}`}
                onSubmit={(payload) => onDecide("edit", payload)}
              />
            ) : (
              <button
                key={d}
                type="button"
                disabled={busy}
                aria-describedby={headingId}
                onClick={() => void onDecide(d)}
                className={`${BUTTON} ${TONE[d]}`}
              >
                {d === "accept" ? "Accept" : "Reject"}
              </button>
            ),
          )}
        </div>
      )}
      {error !== null && (
        <p role="alert" className={`mt-3 text-sm text-danger ${WRAP}`}>
          {error}
        </p>
      )}
    </article>
  );
}
