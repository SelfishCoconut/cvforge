import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { FillResult, FormFieldState, FormSession } from "../../api/types";
import { renderApp } from "../../test-utils";
import { fakeApi } from "../review/fakeApi";
import { json } from "../review/fixtures";
import { FormsPage } from "./FormsPage";

afterEach(() => vi.unstubAllGlobals());

const START = "POST /api/forms/fills";
const FILL = "POST /api/forms/fills/4/fill";
const YEARS = "PUT /api/forms/fills/4/fields/f1";
const YEARS_WITHDRAW = "DELETE /api/forms/fills/4/fields/f1";

function field(over: Partial<FormFieldState>): FormFieldState {
  return {
    key: "f1",
    label: "Years of experience",
    type: "text",
    required: true,
    options: [],
    suggested: "6",
    claim_ids: [1],
    reason: "6 years of roles on the CV.",
    confirmed: false,
    confirmed_value: null,
    ...over,
  };
}

function session(
  fields: FormFieldState[],
  status: "analyzed" | "filled" = "analyzed",
) {
  return {
    id: 4,
    application_id: null,
    cv_id: 1,
    url: "https://x.test/apply",
    status,
    fields,
  } satisfies FormSession;
}

const FIELDS = [
  field({}),
  field({
    key: "f2",
    label: "Level",
    type: "select",
    required: false,
    options: ["jr", "sr"],
    suggested: null,
    reason: "No stored fact answers this; fill it in manually.",
  }),
  field({
    key: "f3",
    label: "Password",
    type: "password",
    suggested: null,
    reason: "Never.",
  }),
];

async function analyse(user = userEvent.setup()) {
  await user.type(
    screen.getByLabelText("Form address"),
    "https://x.test/apply",
  );
  await user.type(screen.getByLabelText("CV number"), "1");
  await user.click(screen.getByRole("button", { name: "Analyse form" }));
  await screen.findByText("https://x.test/apply");
  return user;
}

describe("FormsPage", () => {
  it("explains itself and starts from an address and a CV", async () => {
    const api = fakeApi({ [START]: [json(session(FIELDS))] });
    renderApp(<FormsPage />);
    expect(
      screen.getByRole("heading", { level: 1, name: "Forms" }),
    ).toBeInTheDocument();
    await analyse();
    expect(api.bodyOf(START)).toEqual({
      url: "https://x.test/apply",
      cv_id: 1,
    });
    expect(screen.getByLabelText(/Years of experience/)).toHaveValue("6");
    expect(screen.getByText("6 years of roles on the CV.")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Fill in browser" }),
    ).toBeDisabled();
  });

  it("leaves a password to the user and offers a select's options", async () => {
    fakeApi({ [START]: [json(session(FIELDS))] });
    renderApp(<FormsPage />);
    await analyse();
    expect(
      screen.getByText("Fill this one yourself in the browser."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Confirm Password" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: "sr" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Confirm Level" }),
    ).toBeDisabled();
  });

  it("confirms an edited value, then withdraws it", async () => {
    const confirmed = [
      field({ confirmed: true, confirmed_value: "7" }),
      ...FIELDS.slice(1),
    ];
    const api = fakeApi({
      [START]: [json(session(FIELDS))],
      [YEARS]: [json(session(confirmed))],
      [YEARS_WITHDRAW]: [json(session(FIELDS))],
    });
    renderApp(<FormsPage />);
    const user = await analyse();
    const input = screen.getByLabelText(/Years of experience/);
    await user.clear(input);
    await user.type(input, "7");
    await user.click(
      screen.getByRole("button", { name: "Confirm Years of experience" }),
    );
    await screen.findByText("Confirmed");
    expect(api.bodyOf(YEARS)).toEqual({ value: "7" });
    expect(screen.getByText(/1 field confirmed/)).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "Withdraw Years of experience" }),
    );
    await waitFor(() =>
      expect(screen.queryByText("Confirmed")).not.toBeInTheDocument(),
    );
  });

  it("fills only after a confirmation, reports skips, and then locks", async () => {
    const confirmed = [
      field({ confirmed: true, confirmed_value: "6" }),
      ...FIELDS.slice(1),
    ];
    const result: FillResult = {
      filled: ["f1"],
      skipped: { f2: "the page changed" },
    };
    fakeApi({
      [START]: [json(session(confirmed))],
      [FILL]: [json(result)],
    });
    renderApp(<FormsPage />);
    const user = await analyse();
    await user.click(screen.getByRole("button", { name: "Fill in browser" }));
    expect(await screen.findByText("Filled 1 field.")).toBeInTheDocument();
    expect(
      screen.getByText("Skipped f2: the page changed"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Fill in browser" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Withdraw Years of experience" }),
    ).toBeDisabled();
  });

  it("says why a fill, a confirmation or the analysis failed", async () => {
    const confirmed = [field({ confirmed: true, confirmed_value: "6" })];
    fakeApi({
      [START]: [
        json({ detail: "no fillable form was found on that page" }, 422),
        json(session(confirmed)),
      ],
      [FILL]: [json({ detail: "no browser" }, 422)],
      [YEARS_WITHDRAW]: [json({ detail: "already filled" }, 409)],
    });
    renderApp(<FormsPage />);
    const user = userEvent.setup();
    await user.type(
      screen.getByLabelText("Form address"),
      "https://x.test/apply",
    );
    await user.type(screen.getByLabelText("CV number"), "1");
    await user.click(screen.getByRole("button", { name: "Analyse form" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "no fillable form",
    );

    await user.click(screen.getByRole("button", { name: "Analyse form" }));
    await screen.findByText("https://x.test/apply");
    await user.click(
      screen.getByRole("button", { name: "Withdraw Years of experience" }),
    );
    expect(await screen.findByText("already filled")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Fill in browser" }));
    expect(
      await screen.findByText(/Could not fill: no browser/),
    ).toBeInTheDocument();
  });
});
