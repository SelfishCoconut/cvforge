import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { WRAP } from "../knowledge/vocab";
import { SettingsForm } from "./SettingsForm";

/** LLM provider settings: which model runs, and whether text may leave this machine. */
export function SettingsPage() {
  const q = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });
  return (
    <section>
      <h1 className="text-3xl">Settings</h1>
      {q.isPending && <p className="mt-6 text-ink-muted">Loading settings…</p>}
      {q.isError && (
        <p role="alert" className={`mt-6 text-danger ${WRAP}`}>
          Could not load settings: {q.error.message}
        </p>
      )}
      {q.isSuccess && <SettingsForm view={q.data} />}
    </section>
  );
}
