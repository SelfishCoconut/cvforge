import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api } from "../../api/client";
import type { ProposalSummary } from "../../api/types";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../../ui/Tabs";
import { Time } from "../../ui/Time";

type Status = "open" | "committed";
const WRAP = "break-words [overflow-wrap:anywhere]";

function counts(p: ProposalSummary): string {
  if (p.status === "open") return `${p.pending_count} of ${p.operation_count} pending`;
  return `${p.operation_count} ${p.operation_count === 1 ? "operation" : "operations"}`;
}

function Row({ p }: { p: ProposalSummary }) {
  return (
    <li>
      <Link
        to={`/review/${p.id}`}
        className="group block py-4 hover:bg-card focus-visible:bg-card sm:px-3"
      >
        <span className={`block font-display text-lg group-hover:text-accent ${WRAP}`}>
          {p.summary}
        </span>
        <span className="mt-1 flex flex-wrap gap-x-3 text-sm text-ink-muted">
          <Time iso={p.applied_at ?? p.created_at} />
          <span>{counts(p)}</span>
        </span>
      </Link>
    </li>
  );
}

function Empty({ status }: { status: Status }) {
  if (status === "committed") return <p className="text-ink-muted">No committed proposals yet.</p>;
  return (
    <p className="text-ink-muted">
      Nothing to review. Tell the assistant something in{" "}
      <Link to="/chat" className="text-accent underline decoration-1 underline-offset-4">
        Chat
      </Link>
      .
    </p>
  );
}

function ProposalList({ status }: { status: Status }) {
  const q = useQuery({
    queryKey: ["proposals", status],
    queryFn: () => api.listProposals(status),
  });
  if (q.isPending) return <p className="text-ink-muted">Loading proposals…</p>;
  if (q.isError) {
    return (
      <p role="alert" className={`text-danger ${WRAP}`}>
        Could not load proposals: {q.error.message}
      </p>
    );
  }
  if (q.data.length === 0) return <Empty status={status} />;
  return (
    <ul className="divide-y divide-line">
      {q.data.map((p) => (
        <Row key={p.id} p={p} />
      ))}
    </ul>
  );
}

/** Proposals awaiting review, and those already committed. */
export function ReviewQueuePage() {
  return (
    <section className="max-w-3xl">
      <h1 className="text-3xl">Review queue</h1>
      <Tabs defaultValue="open" className="mt-8">
        <TabsList aria-label="Proposals">
          <TabsTrigger value="open">Open</TabsTrigger>
          <TabsTrigger value="committed">Committed</TabsTrigger>
        </TabsList>
        {(["open", "committed"] as const).map((s) => (
          <TabsContent key={s} value={s} className="mt-4">
            <ProposalList status={s} />
          </TabsContent>
        ))}
      </Tabs>
    </section>
  );
}
