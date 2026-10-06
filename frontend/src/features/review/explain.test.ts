import { describe, expect, it } from "vitest";
import type { OperationRecord } from "../../api/types";
import { canCommit, explain, summarise } from "./explain";

function op(status: string, id = 1): OperationRecord {
  return {
    id,
    seq: id,
    status,
    classification: "new",
    op_type: "create_entity",
    payload: {},
    edited_payload: null,
    rationale: null,
    target_id: null,
    target_kind: null,
  };
}

describe("canCommit", () => {
  it("canCommit is false with a pending operation and says how many", () => {
    expect(canCommit([op("accepted", 1), op("pending", 2), op("pending", 3)], true)).toEqual({
      ok: false,
      reason: "2 operations still pending",
    });
    expect(canCommit([op("accepted", 1), op("pending", 2)], true)).toEqual({
      ok: false,
      reason: "1 operation still pending",
    });
  });

  it("canCommit is false when nothing is accepted or edited", () => {
    expect(canCommit([op("rejected", 1), op("rejected", 2)], true)).toEqual({
      ok: false,
      reason: "Accept or edit at least one operation.",
    });
    expect(canCommit([], true).ok).toBe(false);
  });

  it("canCommit is true with >=1 accepted/edited and 0 pending", () => {
    expect(canCommit([op("accepted", 1), op("rejected", 2)], true)).toEqual({ ok: true });
    expect(canCommit([op("edited", 1)], true)).toEqual({ ok: true });
  });

  it("canCommit is false once the proposal is no longer open", () => {
    expect(canCommit([op("accepted", 1)], false)).toEqual({
      ok: false,
      reason: "This proposal is already committed.",
    });
  });
});

describe("explain", () => {
  it("explain covers the four classifications and never throws on an unknown one", () => {
    expect(explain("new", "create_entity")).toBe(
      "Nothing stored covers this; accepting creates or changes rows.",
    );
    expect(explain("known", "create_entity")).toBe(
      "The same thing is already recorded; accepting adds this evidence to the existing record.",
    );
    expect(explain("duplicate", "create_entity")).toBe(
      "A differently named record is probably the same thing; accepting links to that record.",
    );
    expect(explain("conflict", "set_field")).toBe(
      "The same field or edge is recorded with a different value; accepting replaces the stored value and keeps the old one as history.",
    );
    for (const odd of ["", "mystery", "constructor", "__proto__", "toString"]) {
      expect(explain(odd, "create_entity")).toBe("Unclassified operation.");
    }
  });
});

describe("summarise", () => {
  it("joins the humanised op type with the payload name", () => {
    expect(summarise(op("pending"))).toBe("Create entity");
    expect(summarise({ ...op("pending"), payload: { name: "Backend engineer" } })).toBe(
      "Create entity: Backend engineer",
    );
  });

  it("falls back to the field, prefers the edited payload, and ignores non-string values", () => {
    const base = { ...op("edited"), op_type: "update_field" };
    expect(summarise({ ...base, payload: { field: "end_date" } })).toBe("Update field: end_date");
    expect(
      summarise({ ...base, payload: { name: "Old" }, edited_payload: { name: "New" } }),
    ).toBe("Update field: New");
    expect(summarise({ ...base, payload: { name: 3, field: "" } })).toBe("Update field");
    expect(summarise({ ...base, op_type: "" })).toBe("Operation");
  });
});
