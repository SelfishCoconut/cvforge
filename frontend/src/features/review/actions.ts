/** A reviewer's decision on one operation, as the review endpoint accepts it. */
export type Decision = "accept" | "edit" | "reject";

/*
 * The single source of truth for what an operation card may offer.
 *
 * Each review replaces the previous decision, so `accept` on an `edited`
 * operation would silently discard the edit (plan audit F7). An edited
 * operation is already approved: it offers re-edit and reject, never accept.
 */
const OFFERS: ReadonlyMap<string, readonly Decision[]> = new Map([
  ["pending", ["accept", "edit", "reject"]],
  ["accepted", ["edit", "reject"]],
  ["edited", ["edit", "reject"]],
  ["rejected", ["accept", "edit"]],
]);

/**
 * The decisions a card may offer for an operation.
 *
 * @param status - The operation's review status.
 * @param proposalOpen - Whether the proposal is still open; a committed one is read-only.
 * @returns A fresh array; empty for a committed proposal, an applied or an unknown status.
 */
export function allowedDecisions(status: string, proposalOpen: boolean): Decision[] {
  if (!proposalOpen) return [];
  return [...(OFFERS.get(status) ?? [])];
}
