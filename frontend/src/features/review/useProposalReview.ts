import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError } from "../../api/client";
import type { Committed, ProposalRecord } from "../../api/types";
import type { Decision } from "./actions";

interface ReviewVars {
  opId: number;
  decision: Decision;
  edited?: Record<string, unknown>;
}

function messageOf(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/**
 * Data and actions for reviewing one proposal. A review answers with the
 * whole updated proposal, which replaces the cached one. After any 409 the
 * proposal is refetched so the page never offers a stale Commit.
 */
export function useProposalReview(id: number | null) {
  const client = useQueryClient();
  const key = ["proposal", id] as const;
  const [errors, setErrors] = useState<ReadonlyMap<number, string>>(new Map());
  const [committed, setCommitted] = useState<Committed | null>(null);

  const proposal = useQuery({
    queryKey: key,
    queryFn: () => api.getProposal(id as number),
    enabled: id !== null,
  });

  const refetchIfConflict = (e: Error) => {
    if (e instanceof ApiError && e.status === 409) void client.invalidateQueries({ queryKey: key });
  };

  const review = useMutation<ProposalRecord, Error, ReviewVars>({
    mutationFn: (v) =>
      api.reviewOperation(id as number, v.opId, v.decision, v.edited),
    onSuccess: (data) => client.setQueryData(key, data),
    onError: refetchIfConflict,
  });

  const commit = useMutation<Committed, Error, void>({
    mutationFn: () => api.commitProposal(id as number),
    onSuccess: (data) => {
      setCommitted(data);
      void client.invalidateQueries({ queryKey: key });
      void client.invalidateQueries({ queryKey: ["proposals"] });
    },
    onError: refetchIfConflict,
  });

  const setError = (opId: number, message: string | null) =>
    setErrors((prev) => {
      const next = new Map(prev);
      if (message === null) next.delete(opId);
      else next.set(opId, message);
      return next;
    });

  /** Records a decision; resolves to null on success or the server's reason. */
  async function decide(
    opId: number,
    decision: Decision,
    edited?: Record<string, unknown>,
  ): Promise<string | null> {
    try {
      await review.mutateAsync({ opId, decision, ...(edited ? { edited } : {}) });
      setError(opId, null);
      return null;
    } catch (e) {
      const message = messageOf(e);
      setError(opId, message);
      return message;
    }
  }

  return {
    proposal,
    decide,
    errors,
    busyOpId: review.isPending ? review.variables.opId : null,
    commit,
    committed,
  };
}
