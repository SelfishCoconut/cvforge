import type { ReactNode } from "react";
import { Link, useLocation, useParams } from "react-router";
import { ApiError } from "../../api/client";
import type { ProposalRecord } from "../../api/types";
import { Time } from "../../ui/Time";
import { CommitPanel, CommitResult } from "./CommitPanel";
import { OperationCard } from "./OperationCard";
import { useProposalReview } from "./useProposalReview";
import { WRAP } from "../../ui/text";


function parseId(raw: string | undefined): number | null {
  return raw !== undefined && /^\d+$/.test(raw) ? Number(raw) : null;
}

function similarityWasUnavailable(state: unknown): boolean {
  return (state as { similarityAvailable?: unknown } | null)?.similarityAvailable === false;
}

function NotFound() {
  return <p className="mt-6 text-ink-muted">Proposal not found</p>;
}

/** The page heading until the proposal's own summary is known. */
function Placeholder({ children }: { children: ReactNode }) {
  return (
    <>
      <h1 className="text-3xl">Review proposal</h1>
      {children}
    </>
  );
}

function Header({ p }: { p: ProposalRecord }) {
  return (
    <header>
      <h1 className={`text-3xl ${WRAP}`}>{p.summary}</h1>
      <p className="mt-2 text-sm text-ink-muted">
        Proposal {p.id} · from {p.origin} · <Time iso={p.created_at} />
        {p.applied_at !== null && (
          <>
            {" "}
            · Committed <Time iso={p.applied_at} />
          </>
        )}
      </p>
    </header>
  );
}

/** One proposal under review: a card per operation and the commit gate. */
export function ReviewPage() {
  const id = parseId(useParams().id);
  // Per-proposal state (commit result, per-card errors) must not follow a route change.
  return <ReviewBody key={id ?? "invalid"} id={id} />;
}

function ReviewBody({ id }: { id: number | null }) {
  const location = useLocation();
  const r = useProposalReview(id);
  const { proposal, commit, committed } = r;

  let body;
  if (id === null) body = <Placeholder><NotFound /></Placeholder>;
  else if (proposal.isPending)
    body = (
      <Placeholder>
        <p className="mt-6 text-ink-muted">Loading proposal…</p>
      </Placeholder>
    );
  else if (proposal.isError) {
    const e = proposal.error;
    body = (
      <Placeholder>
        {e instanceof ApiError && e.status === 404 ? (
          <NotFound />
        ) : (
          <p role="alert" className={`mt-6 text-danger ${WRAP}`}>
            Could not load the proposal: {e.message}
          </p>
        )}
      </Placeholder>
    );
  } else {
    const p = proposal.data;
    const open = p.status === "open" && committed === null;
    const ops = [...p.operations].sort((a, b) => a.seq - b.seq);
    body = (
      <>
        <Header p={p} />
        {similarityWasUnavailable(location.state) && (
          <p className="mt-4 max-w-prose border-l-2 border-duplicate pl-3 text-sm">
            Similarity search was unavailable when this proposal was made; duplicates were not
            checked.
          </p>
        )}
        {committed !== null && <CommitResult result={committed} />}
        <div className="mt-8 space-y-6">
          {ops.map((op) => (
            <OperationCard
              key={op.id}
              op={op}
              proposalOpen={open}
              busy={r.reviewing}
              error={r.errors.get(op.id) ?? null}
              onDecide={(decision, edited) => r.decide(op.id, decision, edited)}
            />
          ))}
        </div>
        {open && (
          <CommitPanel
            ops={ops}
            open={open}
            pending={commit.isPending || r.reviewing}
            onCommit={() => commit.mutate()}
          />
        )}
        {commit.error !== null && (
          <p role="alert" className={`mt-3 text-sm text-danger ${WRAP}`}>
            {commit.error.message}
          </p>
        )}
      </>
    );
  }

  return (
    <div>
      <Link to="/review" className="text-sm text-accent hover:text-ink">
        ← All proposals
      </Link>
      <div className="mt-4">{body}</div>
    </div>
  );
}
