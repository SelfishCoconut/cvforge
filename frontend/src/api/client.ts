import type {
  Committed,
  EdgeRecord,
  EntityKind,
  EntityRecord,
  EvidenceRecord,
  KnowledgeState,
  ProposalRecord,
  ProposalSummary,
  ProviderSettings,
  ProvenanceRecord,
  SettingsView,
} from "./types";

/** A non-2xx response, or `status` 0 when the backend could not be reached. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface Health {
  status: string;
  version: string;
}

async function errorMessage(response: Response): Promise<string> {
  const fallback = `HTTP ${response.status}`;
  try {
    const body: unknown = await response.json();
    const detail = (body as { detail?: unknown } | null)?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((d) => (d as { msg?: unknown } | null)?.msg)
        .filter((m): m is string => typeof m === "string");
      if (msgs.length > 0) return msgs.join("; ");
    }
  } catch {
    // body was not JSON; use the status fallback
  }
  return fallback;
}

async function send(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let response: Response;
  try {
    response = await fetch(path, { ...init, headers });
  } catch {
    throw new ApiError(0, "backend unreachable");
  }
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response));
  return response;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  return (await (await send(path, init)).json()) as T;
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
}

function query(params: Record<string, string | undefined>): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined) qs.set(k, v);
  const s = qs.toString();
  return s ? `?${s}` : "";
}

/** Typed access to the CVForge backend. */
export const api = {
  health: () => request<Health>("/api/health"),
  listProposals: (status?: "open" | "committed") =>
    request<ProposalSummary[]>(`/api/proposals${query({ status })}`),
  getProposal: (id: number) => request<ProposalRecord>(`/api/proposals/${id}`),
  reviewOperation: (
    proposalId: number,
    opId: number,
    decision: "accept" | "edit" | "reject",
    editedPayload?: Record<string, unknown>,
  ) =>
    post<ProposalRecord>(`/api/proposals/${proposalId}/operations/${opId}/review`, {
      decision,
      edited_payload: editedPayload,
    }),
  commitProposal: (id: number) => post<Committed>(`/api/proposals/${id}/commit`),
  getEvidence: (id: number) => request<EvidenceRecord>(`/api/evidence/${id}`),
  listEntities: (f?: { kind?: EntityKind; state?: KnowledgeState }) =>
    request<EntityRecord[]>(`/api/entities${query({ kind: f?.kind, state: f?.state })}`),
  getEntity: (id: number) => request<EntityRecord>(`/api/entities/${id}`),
  getEdges: (id: number) => request<EdgeRecord[]>(`/api/entities/${id}/edges`),
  getProvenance: (kind: "entity" | "edge", id: number) =>
    request<ProvenanceRecord[]>(`/api/provenance/${kind}/${id}`),
  getSettings: () => request<SettingsView>("/api/settings"),
  putSettings: (s: ProviderSettings) =>
    request<SettingsView>("/api/settings", { method: "PUT", body: JSON.stringify(s) }),
  streamChat: (text: string, conversationId: number | null, signal?: AbortSignal) =>
    send("/api/chat/messages/stream", {
      method: "POST",
      headers: { Accept: "application/x-ndjson" },
      body: JSON.stringify({ text, conversation_id: conversationId }),
      ...(signal ? { signal } : {}),
    }),
};
