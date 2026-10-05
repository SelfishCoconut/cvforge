import { describe, expect, it } from "vitest";
import { allowedDecisions, type Decision } from "./actions";

describe("allowedDecisions", () => {
  it("an edited operation is already approved: offers re-edit and reject, never accept", () => {
    expect(allowedDecisions("edited", true)).toEqual(["edit", "reject"]);
  });

  it("offers nothing once the proposal is committed", () => {
    for (const s of ["pending", "accepted", "edited", "rejected", "applied"]) {
      expect(allowedDecisions(s, false)).toEqual([]);
    }
  });

  it.each<[string, Decision[]]>([
    ["pending", ["accept", "edit", "reject"]],
    ["accepted", ["edit", "reject"]],
    ["rejected", ["accept", "edit"]],
    ["applied", []],
    ["weird", []],
    ["constructor", []],
  ])("status %s on an open proposal offers %j", (status, expected) => {
    expect(allowedDecisions(status, true)).toEqual(expected);
  });

  it("returns a fresh array each call so callers cannot corrupt the table", () => {
    const first = allowedDecisions("pending", true);
    first.push("accept");
    expect(allowedDecisions("pending", true)).toEqual(["accept", "edit", "reject"]);
  });
});
