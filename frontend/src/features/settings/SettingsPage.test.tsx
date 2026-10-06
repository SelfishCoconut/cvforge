import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProviderSettings, SettingsView } from "../../api/types";
import { renderApp } from "../../test-utils";
import { fakeApi } from "../review/fakeApi";
import { json } from "../review/fixtures";
import { SettingsPage } from "./SettingsPage";

const GET = "GET /api/settings";
const PUT = "PUT /api/settings";

afterEach(() => vi.unstubAllGlobals());

function settings(over: Partial<ProviderSettings> = {}): ProviderSettings {
  return {
    provider: "ollama",
    model: "qwen3.6:27b",
    base_url: "http://127.0.0.1:11434",
    api_key_env: null,
    allow_external: false,
    embedding_provider: "ollama",
    embedding_model: "nomic-embed-text",
    similarity_threshold: 0.91,
    ...over,
  };
}

function view(
  over: Partial<ProviderSettings> = {},
  configured = false,
): SettingsView {
  return { settings: settings(over), api_key_configured: configured };
}

const NOTE =
  "While this is on, text from your conversations and documents is sent to the selected provider.";
const HINT = "External providers need 'Allow external' on.";

describe("SettingsPage", () => {
  it("shows loading, then the persisted settings", async () => {
    fakeApi({ [GET]: [json(view())] });
    renderApp(<SettingsPage />);
    expect(
      screen.getByRole("heading", { level: 1, name: "Settings" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Loading settings/)).toBeInTheDocument();
    expect(await screen.findByLabelText("Provider")).toHaveValue("ollama");
    expect(screen.getByLabelText("Model")).toHaveValue("qwen3.6:27b");
    expect(screen.getByLabelText("Base URL")).toHaveValue(
      "http://127.0.0.1:11434",
    );
    expect(screen.getByLabelText("API key variable name")).toHaveValue("");
    expect(
      screen.getByRole("switch", { name: "Allow external" }),
    ).not.toBeChecked();
    expect(
      screen.getByText("No API key found in the environment"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
    expect(screen.queryByText(HINT)).not.toBeInTheDocument();
  });

  it("shows an explicit error when the initial load fails", async () => {
    fakeApi({ [GET]: [json({ detail: "db locked" }, 500)] });
    renderApp(<SettingsPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not load settings: db locked",
    );
    expect(screen.queryByLabelText("Provider")).not.toBeInTheDocument();
  });

  it("reports a configured key as a status line only", async () => {
    fakeApi({ [GET]: [json(view({ api_key_env: "MY_KEY" }, true))] });
    renderApp(<SettingsPage />);
    expect(
      await screen.findByText("An API key is configured"),
    ).toBeInTheDocument();
  });

  it("treats the key field as a variable name and never renders a key", async () => {
    const fake = "sk-ant-FAKE-NOT-A-REAL-KEY";
    fakeApi({ [GET]: [json(view({ api_key_env: fake }, true))] });
    renderApp(<SettingsPage />);
    const field = await screen.findByLabelText("API key variable name");
    expect(field).toHaveAttribute("type", "text");
    expect(field).toHaveAttribute("autocomplete", "off");
    expect(field).toHaveValue(fake);
    expect(document.querySelectorAll("input[type=password]")).toHaveLength(0);
    expect(document.querySelectorAll("[name=api_key]")).toHaveLength(0);
    expect(document.querySelectorAll("input[name*=key i]")).toHaveLength(0);
    expect(screen.queryByText(fake, { exact: false })).not.toBeInTheDocument(); // value only, never page text
    expect(
      screen.getByText(/CVForge never asks for, stores or shows key values\./),
    ).toHaveTextContent(
      "The name of an environment variable that holds your key — not the key itself. CVForge never asks for, stores or shows key values.",
    );
  });

  it("warns when allow external is on, and sends it on save", async () => {
    const api = fakeApi({
      [GET]: [json(view())],
      [PUT]: [json(view({ allow_external: true }))],
    });
    renderApp(<SettingsPage />);
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("switch", { name: "Allow external" }),
    );
    expect(screen.getByRole("note")).toHaveTextContent(NOTE);
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Saved");
    expect(api.bodyOf(PUT)).toMatchObject({ allow_external: true });
  });

  it("hints, without blocking, when an external provider is chosen with external off", async () => {
    const api = fakeApi({
      [GET]: [json(view())],
      [PUT]: [json(view({ provider: "anthropic" }))],
    });
    renderApp(<SettingsPage />);
    const user = userEvent.setup();
    await user.selectOptions(
      await screen.findByLabelText("Provider"),
      "anthropic",
    );
    expect(screen.getByText(HINT)).toBeInTheDocument();
    const save = screen.getByRole("button", { name: "Save" });
    expect(save).toBeEnabled();
    await user.click(save);
    await waitFor(() => expect(api.calls(PUT)).toHaveLength(1));
  });

  it("shows the server's refusal and leaves the persisted settings unchanged", async () => {
    const detail =
      "anthropic is an external provider; set allow_external to use it (NFR-01)";
    fakeApi({ [GET]: [json(view())], [PUT]: [json({ detail }, 422)] });
    renderApp(<SettingsPage />);
    const user = userEvent.setup();
    await user.selectOptions(
      await screen.findByLabelText("Provider"),
      "anthropic",
    );
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(detail);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  });

  it("round-trips the whole object, including fields the form does not expose", async () => {
    const api = fakeApi({
      [GET]: [json(view())],
      [PUT]: [json(view({ model: "llama3" }))],
    });
    renderApp(<SettingsPage />);
    const user = userEvent.setup();
    const model = await screen.findByLabelText("Model");
    await user.clear(model);
    await user.type(model, "llama3");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("status");
    expect(api.bodyOf(PUT)).toEqual(settings({ model: "llama3" }));
  });

  it("sends empty optional fields as null", async () => {
    const api = fakeApi({
      [GET]: [json(view({ api_key_env: "OLD" }))],
      [PUT]: [json(view())],
    });
    renderApp(<SettingsPage />);
    const user = userEvent.setup();
    await user.clear(await screen.findByLabelText("API key variable name"));
    await user.clear(screen.getByLabelText("Base URL"));
    await user.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("status");
    expect(api.bodyOf(PUT)).toMatchObject({
      api_key_env: null,
      base_url: null,
    });
  });

  it("refreshes the key status from the response", async () => {
    fakeApi({
      [GET]: [json(view())],
      [PUT]: [json(view({ api_key_env: "MY_KEY" }, true))],
    });
    renderApp(<SettingsPage />);
    const user = userEvent.setup();
    await user.type(
      await screen.findByLabelText("API key variable name"),
      "MY_KEY",
    );
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(
      await screen.findByText("An API key is configured"),
    ).toBeInTheDocument();
  });

  it("disables Save while unchanged and while pending", async () => {
    let release: (r: Response) => void = () => undefined;
    fakeApi({
      [GET]: [json(view())],
      [PUT]: [() => new Promise<Response>((r) => (release = r))],
    });
    renderApp(<SettingsPage />);
    const user = userEvent.setup();
    const save = await screen.findByRole("button", { name: "Save" });
    expect(save).toBeDisabled();
    await user.type(screen.getByLabelText("Model"), "x");
    expect(save).toBeEnabled();
    await user.click(save);
    expect(
      await screen.findByRole("button", { name: "Saving…" }),
    ).toBeDisabled();
    release(json(view({ model: "qwen3.6:27bx" })));
    expect(await screen.findByRole("status")).toHaveTextContent("Saved");
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("clears the Saved note once the form is edited again", async () => {
    fakeApi({ [GET]: [json(view())], [PUT]: [json(view({ model: "a" }))] });
    renderApp(<SettingsPage />);
    const user = userEvent.setup();
    const model = await screen.findByLabelText("Model");
    await user.clear(model);
    await user.type(model, "a");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("status");
    await user.type(model, "b");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("alerts on a network failure", async () => {
    fakeApi({ [GET]: [json(view())], [PUT]: [new TypeError("down")] });
    renderApp(<SettingsPage />);
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Model"), "x");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "backend unreachable",
    );
  });

  it("toggles the switch with Space and submits with Enter in a text input", async () => {
    const api = fakeApi({
      [GET]: [json(view())],
      [PUT]: [json(view({ allow_external: true }))],
    });
    renderApp(<SettingsPage />);
    const user = userEvent.setup();
    const sw = await screen.findByRole("switch", { name: "Allow external" });
    sw.focus();
    await user.keyboard(" ");
    expect(sw).toBeChecked();
    await user.click(screen.getByLabelText("Model"));
    await user.keyboard("{Enter}");
    await screen.findByRole("status");
    expect(api.calls(PUT)).toHaveLength(1);
    expect(api.bodyOf(PUT)).toMatchObject({ allow_external: true });
  });
});
