import type { EdgeRecord, EntityRecord, ProvenanceRecord } from "../api/types";

/** A synthetic entity with id 3. */
export function makeEntity(over: Partial<EntityRecord> = {}): EntityRecord {
  return {
    id: 3,
    kind: "skill",
    name: "Python",
    normalized_name: "python",
    state: "confirmed",
    summary: "General-purpose programming language.",
    attributes: {},
    first_seen_at: "2026-09-01T10:00:00Z",
    updated_at: "2026-09-02T10:00:00Z",
    ...over,
  };
}

/** A synthetic edge 7 from entity 3 to entity 4. */
export function makeEdge(over: Partial<EdgeRecord> = {}): EdgeRecord {
  return {
    id: 7,
    src_id: 3,
    dst_id: 4,
    rel: "used_in",
    note: null,
    confidence: null,
    started_at: null,
    ended_at: null,
    ...over,
  };
}

/** A synthetic provenance record. */
export function makeProvenance(over: Partial<ProvenanceRecord> = {}): ProvenanceRecord {
  return {
    assertion_id: 1,
    source_id: 2,
    source_kind: "chat",
    source_label: "Chat 2026-09-01",
    locator: "message:4",
    excerpt: "I used Python daily at Example Corp.",
    field: null,
    value: null,
    ...over,
  };
}
