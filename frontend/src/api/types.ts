import type { components } from "./schema";

type S = components["schemas"];

export type ProposalRecord = S["ProposalRecord"];
export type OperationRecord = S["OperationRecord"];
export type ProposalSummary = S["ProposalSummary"];
export type EvidenceRecord = S["EvidenceRecord"];
export type EntityRecord = S["EntityRecord"];
export type EdgeRecord = S["EdgeRecord"];
export type ProvenanceRecord = S["ProvenanceRecord"];
export type SettingsView = S["SettingsView"];
export type ProviderSettings = S["ProviderSettings"];
export type Committed = S["Committed"];
export type EntityKind = S["EntityKind"];
export type KnowledgeState = S["KnowledgeState"];
export type ProposalView = S["ProposalView"];
export type RejectedView = S["RejectedView"];

/** One line of the `/api/chat/messages/stream` NDJSON response. */
export type ChatEvent =
  | { type: "delta"; text: string }
  | {
      type: "proposal";
      conversation_id: number;
      message_id: number;
      proposal: ProposalView;
      rejected: RejectedView[];
      similarity_available: boolean;
    }
  | { type: "done" }
  | { type: "error"; message: string };
