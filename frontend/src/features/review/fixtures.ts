import type { EvidenceRecord, OperationRecord, ProposalRecord } from "../../api/types";

/** A synthetic operation; every field can be overridden. */
export function makeOp(over: Partial<OperationRecord> = {}): OperationRecord {
  return {
    id: 11,
    seq: 1,
    status: "pending",
    classification: "new",
    op_type: "create_entity",
    payload: { op_type: "create_entity", kind: "role", name: "Backend engineer", evidence_id: 40 },
    edited_payload: null,
    rationale: null,
    target_id: null,
    target_kind: null,
    ...over,
  };
}

/** A synthetic open proposal with id 5. */
export function makeProposal(over: Partial<ProposalRecord> = {}): ProposalRecord {
  return {
    id: 5,
    status: "open",
    summary: "Two facts about the Example Corp role",
    origin: "chat",
    source_id: 1,
    created_at: "2026-10-01T09:30:00Z",
    applied_at: null,
    operations: [makeOp()],
    ...over,
  };
}

/** A synthetic evidence span. */
export function makeEvidence(over: Partial<EvidenceRecord> = {}): EvidenceRecord {
  return {
    id: 40,
    excerpt: "I worked as a backend engineer at Example Corp.",
    locator: "message:1",
    source_id: 1,
    source_kind: "chat",
    source_label: "Chat message",
    ...over,
  };
}

/** A JSON `Response` with the given status. */
export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
