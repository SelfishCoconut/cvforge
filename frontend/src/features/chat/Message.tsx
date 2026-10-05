import { Link } from "react-router";
import type { Turn } from "./useChatStream";

function Assistant({ turn }: { turn: Extract<Turn, { role: "assistant" }> }) {
  const { proposalId, rejected, similarityAvailable, error, status, text } =
    turn;
  return (
    <div className="space-y-3">
      {text ? (
        <p className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
          {text}
        </p>
      ) : status === "streaming" ? (
        <p className="text-ink-muted" aria-label="Waiting for reply">
          …
        </p>
      ) : null}
      {similarityAvailable === false && (
        <p className="text-sm text-ink-muted">
          Similarity search was unavailable; possible duplicates were not
          checked.
        </p>
      )}
      {rejected.length > 0 && (
        <ul className="list-disc space-y-1 pl-5 text-sm text-ink-muted">
          {rejected.map((r, i) => (
            <li key={i} className="break-words [overflow-wrap:anywhere]">
              {r.item} — {r.reason}
            </li>
          ))}
        </ul>
      )}
      {proposalId != null && (
        <Link
          to={`/review/${proposalId}`}
          state={{ similarityAvailable }}
          className="inline-block border-b border-accent text-accent hover:text-ink"
        >
          Review proposal
        </Link>
      )}
      {status === "error" && (
        <p
          role="alert"
          className="text-sm text-danger break-words [overflow-wrap:anywhere]"
        >
          {error}
        </p>
      )}
    </div>
  );
}

/** One transcript turn. All text is rendered as text nodes, never as markup. */
export function Message({ turn }: { turn: Turn }) {
  if (turn.role === "user") {
    return (
      <div className="flex justify-end">
        <p className="max-w-[85%] whitespace-pre-wrap break-words rounded-sm bg-card px-4 py-2.5 ring-1 ring-inset ring-line [overflow-wrap:anywhere]">
          {turn.text}
        </p>
      </div>
    );
  }
  return (
    <div className="max-w-prose">
      <Assistant turn={turn} />
    </div>
  );
}
