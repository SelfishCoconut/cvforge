import { useId } from "react";
import type { Committed, OperationRecord } from "../../api/types";
import { canCommit } from "./explain";

interface Props {
  ops: OperationRecord[];
  open: boolean;
  pending: boolean;
  onCommit: () => void;
}

/** The commit gate: disabled, with its reason visible, until the proposal can be committed. */
export function CommitPanel({ ops, open, pending, onCommit }: Props) {
  const reasonId = useId();
  const gate = canCommit(ops, open);
  return (
    <section
      aria-label="Commit"
      className="sticky bottom-0 mt-10 border-t border-line bg-surface pb-2 pt-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p id={reasonId} className="text-sm text-ink-muted">
          {gate.reason ?? "Ready to commit. Rejected operations are discarded."}
        </p>
        <button
          type="button"
          disabled={!gate.ok || pending}
          aria-describedby={gate.reason === undefined ? undefined : reasonId}
          onClick={onCommit}
          className="rounded-sm bg-accent px-5 py-2 font-medium text-surface disabled:cursor-not-allowed disabled:opacity-40"
        >
          Commit
        </button>
      </div>
    </section>
  );
}

/** What a successful commit did, including entities still awaiting similarity indexing. */
export function CommitResult({ result }: { result: Committed }) {
  const applied = result.applied_operation_ids.length;
  const unindexed = result.index_pending.length;
  return (
    <div className="mt-6 space-y-2">
      <p role="status" className="font-medium">
        Committed: {applied} {applied === 1 ? "operation" : "operations"} applied.
      </p>
      {unindexed > 0 && (
        <p className="text-sm text-ink-muted">
          {unindexed} {unindexed === 1 ? "entity is" : "entities are"} not yet searchable for
          similarity; they will be indexed later.
        </p>
      )}
    </div>
  );
}
