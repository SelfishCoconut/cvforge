import type { OperationRecord } from "../../api/types";

/* ADR-0009's table: what accepting an operation of each classification does. */
const SENTENCES: ReadonlyMap<string, string> = new Map([
  ["new", "Nothing stored covers this; accepting creates or changes rows."],
  [
    "known",
    "The same thing is already recorded; accepting adds this evidence to the existing record.",
  ],
  [
    "duplicate",
    "A differently named record is probably the same thing; accepting links to that record.",
  ],
  [
    "conflict",
    "The same field or edge is recorded with a different value; accepting replaces the stored value and keeps the old one as history.",
  ],
]);

/**
 * One sentence explaining what accepting an operation does (ADR-0009).
 *
 * @param classification - The operation's classification; any string is tolerated.
 * @param _opType - The operation type; the table is keyed by classification alone today.
 * @returns The sentence, or "Unclassified operation." for an unknown classification.
 */
export function explain(classification: string, _opType: string): string {
  return SENTENCES.get(classification) ?? "Unclassified operation.";
}

/**
 * Whether a proposal can be committed, and if not, why.
 *
 * @param ops - The proposal's operations.
 * @param proposalOpen - Whether the proposal is still open.
 * @returns `ok` plus a human reason when it is false.
 */
export function canCommit(
  ops: OperationRecord[],
  proposalOpen: boolean,
): { ok: boolean; reason?: string } {
  if (!proposalOpen) return { ok: false, reason: "This proposal is already committed." };
  const pending = ops.filter((o) => o.status === "pending").length;
  if (pending > 0) {
    return {
      ok: false,
      reason: `${pending} ${pending === 1 ? "operation" : "operations"} still pending`,
    };
  }
  if (!ops.some((o) => o.status === "accepted" || o.status === "edited")) {
    return { ok: false, reason: "Accept or edit at least one operation." };
  }
  return { ok: true };
}
