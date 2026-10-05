import { useId, useState, type FormEvent } from "react";
import type { OperationRecord } from "../../api/types";
import { Dialog, DialogClose, DialogContent, DialogTrigger } from "../../ui/Dialog";
import { effectivePayload } from "./explain";

interface Props {
  op: OperationRecord;
  /** "Edit", or "Edit again" for an operation that already carries an edit. */
  label: string;
  /** Id of the card heading, so the trigger is described by the operation it acts on. */
  describedBy: string;
  disabled: boolean;
  className: string;
  /** Records the edit; resolves to null on success or the server's reason on failure. */
  onSubmit: (payload: Record<string, unknown>) => Promise<string | null>;
}

function parseObject(text: string): Record<string, unknown> | string {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch (e) {
    return `Not valid JSON: ${(e as Error).message}`;
  }
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return "The payload must be a JSON object.";
  }
  return value as Record<string, unknown>;
}

/**
 * The Edit trigger and its dialog: the effective payload as editable JSON.
 * Invalid JSON or a non-object never reaches the server; a refused edit keeps
 * the dialog open with the typed text intact.
 */
export function EditOperationDialog({ op, label, describedBy, disabled, className, onSubmit }: Props) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const fieldId = useId();
  const errorId = useId();

  function onOpenChange(next: boolean) {
    if (next) {
      setText(JSON.stringify(effectivePayload(op), null, 2));
      setError(null);
    }
    setOpen(next);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const parsed = parseObject(text);
    if (typeof parsed === "string") {
      setError(parsed);
      return;
    }
    setSaving(true);
    const refusal = await onSubmit(parsed);
    setSaving(false);
    if (refusal === null) setOpen(false);
    else setError(refusal);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger disabled={disabled} aria-describedby={describedBy} className={className}>
        {label}
      </DialogTrigger>
      <DialogContent
        title="Edit operation"
        description="Edit the payload as JSON. Saving records your edit as the decision and replaces any earlier one."
      >
        <form onSubmit={(e) => void submit(e)} className="mt-5">
          <label htmlFor={fieldId} className="text-sm font-medium">
            Payload (JSON)
          </label>
          <textarea
            id={fieldId}
            rows={14}
            spellCheck={false}
            value={text}
            onChange={(e) => setText(e.target.value)}
            aria-invalid={error !== null}
            aria-describedby={error === null ? undefined : errorId}
            className="mt-2 block w-full resize-y rounded-sm border border-line bg-surface px-3 py-2 font-mono text-sm text-ink"
          />
          {error !== null && (
            <p
              id={errorId}
              role="alert"
              className="mt-2 text-sm text-danger break-words [overflow-wrap:anywhere]"
            >
              {error}
            </p>
          )}
          <div className="mt-5 flex justify-end gap-3">
            <DialogClose className="rounded-sm px-4 py-2 text-ink-muted ring-1 ring-inset ring-line hover:text-ink">
              Cancel
            </DialogClose>
            <button
              type="submit"
              disabled={saving}
              className="rounded-sm bg-accent px-5 py-2 font-medium text-surface disabled:cursor-not-allowed disabled:opacity-40"
            >
              Save edit
            </button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
