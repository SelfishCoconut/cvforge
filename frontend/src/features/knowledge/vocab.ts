import type { EntityKind, KnowledgeState } from "../../api/types";

/** The closed entity-kind vocabulary (spec §4.1), in display order. */
export const KINDS: readonly EntityKind[] = [
  "skill",
  "project",
  "organization",
  "role",
  "education",
  "credential",
  "achievement",
  "responsibility",
];

/** The closed knowledge-state vocabulary, in display order. */
export const STATES: readonly KnowledgeState[] = ["confirmed", "learning", "gap", "archived"];

/** Narrow a raw string (e.g. a query parameter) to a member of `allowed`, else undefined. */
export function pick<T extends string>(allowed: readonly T[], raw: string | null): T | undefined {
  return allowed.find((v) => v === raw);
}
