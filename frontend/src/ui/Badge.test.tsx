import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ClassificationBadge } from "./Badge";

const VALUES = ["new", "known", "duplicate", "conflict"] as const;

describe("ClassificationBadge", () => {
  it.each(VALUES)("renders the %s label as text", (value) => {
    render(<ClassificationBadge value={value} />);
    expect(screen.getByText(value)).toBeInTheDocument();
  });

  it("gives each classification a distinct colour class", () => {
    const classes = VALUES.map((value) => {
      const { container, unmount } = render(<ClassificationBadge value={value} />);
      const cls = (container.firstElementChild as HTMLElement).className;
      unmount();
      return cls;
    });
    expect(new Set(classes).size).toBe(VALUES.length);
    VALUES.forEach((value, i) => expect(classes[i]).toContain(`text-${value}`));
  });

  it("renders an unknown value as neutral raw text", () => {
    const { container } = render(<ClassificationBadge value="mystery" />);
    const el = container.firstElementChild as HTMLElement;
    expect(el).toHaveTextContent("mystery");
    for (const value of VALUES) expect(el.className).not.toContain(`text-${value}`);
    expect(el.className).toContain("text-ink-muted");
  });

  it.each(["constructor", "toString", "__proto__", "hasOwnProperty"])(
    "renders the inherited-property name %s as neutral text, not a prototype lookup",
    (value) => {
      const { container } = render(<ClassificationBadge value={value} />);
      const el = container.firstElementChild as HTMLElement;
      expect(el).toHaveTextContent(value);
      expect(el.className).toContain("text-ink-muted");
      expect(el.className).not.toMatch(/function|\[native code\]|\[object/);
    },
  );
});
