import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useId, useState, type FormEvent } from "react";
import { api } from "../../api/client";
import type { Provider, ProviderSettings, SettingsView } from "../../api/types";
import { Switch } from "../../ui/Switch";
import { WRAP } from "../../ui/text";

const PROVIDERS: readonly Provider[] = ["ollama", "anthropic", "openai"];
const EXTERNAL: readonly Provider[] = ["anthropic", "openai"];
const FIELD =
  "mt-1 block w-full rounded-sm border border-line bg-card px-2 py-1.5 text-ink";
const HELP = "mt-1 text-sm text-ink-muted";

interface Draft {
  provider: Provider;
  model: string;
  baseUrl: string;
  apiKeyEnv: string;
  allowExternal: boolean;
}

function toDraft(s: ProviderSettings): Draft {
  return {
    provider: s.provider,
    model: s.model,
    baseUrl: s.base_url ?? "",
    apiKeyEnv: s.api_key_env ?? "",
    allowExternal: s.allow_external,
  };
}

/** The persisted object with only the exposed fields replaced, so the rest round-trips. */
function merge(persisted: ProviderSettings, d: Draft): ProviderSettings {
  return {
    ...persisted,
    provider: d.provider,
    model: d.model,
    base_url: d.baseUrl.trim() || null,
    api_key_env: d.apiKeyEnv.trim() || null,
    allow_external: d.allowExternal,
  };
}

function same(a: ProviderSettings, b: ProviderSettings): boolean {
  return (
    a.provider === b.provider &&
    a.model === b.model &&
    (a.base_url ?? null) === (b.base_url ?? null) &&
    (a.api_key_env ?? null) === (b.api_key_env ?? null) &&
    a.allow_external === b.allow_external
  );
}

function Text({
  label,
  value,
  onChange,
  help,
  autoComplete,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  help?: React.ReactNode;
  autoComplete?: "off";
}) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="text-sm text-ink-muted">
        {label}
      </label>
      <input
        id={id}
        type="text"
        className={FIELD}
        value={value}
        autoComplete={autoComplete}
        spellCheck={false}
        onChange={(e) => onChange(e.target.value)}
      />
      {help && <p className={`${HELP} ${WRAP}`}>{help}</p>}
    </div>
  );
}

/**
 * The provider settings form. Editable state is local; the whole persisted
 * `ProviderSettings` is sent on save, so fields the form does not show are never reset.
 */
export function SettingsForm({ view }: { view: SettingsView }) {
  const client = useQueryClient();
  const persisted = view.settings;
  const [draft, setDraft] = useState<Draft>(() => toDraft(persisted));
  const providerId = useId();
  const switchId = useId();
  const save = useMutation({
    mutationFn: (s: ProviderSettings) => api.putSettings(s),
    onSuccess: (result) =>
      client.setQueryData<SettingsView>(["settings"], result),
  });

  const next = merge(persisted, draft);
  const dirty = !same(next, persisted);
  const edit = (patch: Partial<Draft>) => {
    if (!save.isPending) save.reset();
    setDraft({ ...draft, ...patch });
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (dirty && !save.isPending) save.mutate(next);
  };
  const external = EXTERNAL.includes(draft.provider);

  return (
    <form onSubmit={submit} className="mt-6 max-w-xl space-y-6">
      <div>
        <label htmlFor={providerId} className="text-sm text-ink-muted">
          Provider
        </label>
        <select
          id={providerId}
          className={FIELD}
          value={draft.provider}
          onChange={(e) => edit({ provider: e.target.value as Provider })}
        >
          {PROVIDERS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        {external && !draft.allowExternal && (
          <p className="mt-1 text-sm text-danger">
            External providers need 'Allow external' on.
          </p>
        )}
      </div>
      <Text
        label="Model"
        value={draft.model}
        onChange={(model) => edit({ model })}
      />
      <Text
        label="Base URL"
        value={draft.baseUrl}
        onChange={(baseUrl) => edit({ baseUrl })}
        help="Only used by Ollama. If it is not a local address, your text is sent to that host."
      />
      <Text
        label="API key variable name"
        value={draft.apiKeyEnv}
        autoComplete="off"
        onChange={(apiKeyEnv) => edit({ apiKeyEnv })}
        help={
          <>
            The <strong>name</strong> of an environment variable that holds your
            key — not the key itself. CVForge never asks for, stores or shows
            key values.
          </>
        }
      />
      <p className="text-sm text-ink-muted">
        {view.api_key_configured
          ? "An API key is configured"
          : "No API key found in the environment"}
      </p>
      <div>
        <div className="flex items-center gap-3">
          <Switch
            id={switchId}
            checked={draft.allowExternal}
            onCheckedChange={(allowExternal) => edit({ allowExternal })}
          />
          <label htmlFor={switchId}>Allow external</label>
        </div>
        {draft.allowExternal && (
          <p
            role="note"
            className="mt-2 rounded-sm border border-line bg-conflict-soft px-3 py-2 text-sm text-conflict"
          >
            While this is on, text from your conversations and documents is sent
            to the selected provider.
          </p>
        )}
      </div>
      <div className="flex items-center gap-4">
        <button
          type="submit"
          disabled={!dirty || save.isPending}
          className="rounded-sm bg-accent px-4 py-1.5 text-card disabled:opacity-50"
        >
          {save.isPending ? "Saving…" : "Save"}
        </button>
        {save.isSuccess && (
          <p role="status" className="text-sm text-new">
            Saved
          </p>
        )}
        {save.isError && (
          <p role="alert" className={`text-sm text-danger ${WRAP}`}>
            {save.error.message}
          </p>
        )}
      </div>
    </form>
  );
}
