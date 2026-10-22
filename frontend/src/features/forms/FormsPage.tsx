import { useMutation } from "@tanstack/react-query";
import { useId, useState, type FormEvent } from "react";
import { api } from "../../api/client";
import type { FillResult, FormFieldState, FormSession } from "../../api/types";
import { WRAP } from "../../ui/text";

const BUTTON =
  "rounded-sm bg-accent px-5 py-2 font-medium text-surface disabled:cursor-not-allowed disabled:opacity-40";
const FIELD =
  "mt-1 block w-full max-w-prose rounded-sm border border-line bg-surface px-3 py-2";

/** Analyse an application form, review a suggested value per field, and fill what you confirm. */
export function FormsPage() {
  const urlId = useId();
  const cvId = useId();
  const [url, setUrl] = useState("");
  const [cv, setCv] = useState("");
  const [session, setSession] = useState<FormSession | null>(null);
  const start = useMutation({
    mutationFn: () => api.startFormFill(url.trim(), Number(cv)),
    onSuccess: setSession,
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    start.mutate();
  }

  return (
    <section>
      <h1 className="text-3xl">Forms</h1>
      <p className="mt-3 max-w-prose text-ink-muted">
        Give me an application form and the CV you are applying with. I suggest
        a value only where the CV states one, nothing is typed until you confirm
        it, and I never press submit.
      </p>
      <form onSubmit={onSubmit} className="mt-8 space-y-4">
        <div>
          <label htmlFor={urlId} className="block font-medium">
            Form address
          </label>
          <input
            id={urlId}
            type="url"
            required
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            className={FIELD}
          />
        </div>
        <div>
          <label htmlFor={cvId} className="block font-medium">
            CV number
          </label>
          <input
            id={cvId}
            type="number"
            min={1}
            required
            value={cv}
            onChange={(e) => setCv(e.target.value)}
            className={`${FIELD} max-w-40`}
          />
        </div>
        <button type="submit" disabled={start.isPending} className={BUTTON}>
          Analyse form
        </button>
        {start.isPending && (
          <p role="status" className="text-ink-muted">
            Reading the form…
          </p>
        )}
        {start.isError && (
          <p role="alert" className={`text-danger ${WRAP}`}>
            Could not analyse: {start.error.message}
          </p>
        )}
      </form>
      {session && <Session session={session} onChange={setSession} />}
    </section>
  );
}

function Session({
  session,
  onChange,
}: {
  session: FormSession;
  onChange: (s: FormSession) => void;
}) {
  const filled = session.status === "filled";
  const fill = useMutation({
    mutationFn: () => api.fillForm(session.id),
    onSuccess: () => onChange({ ...session, status: "filled" }),
  });
  const confirmed = session.fields.filter((f) => f.confirmed).length;
  return (
    <div className="mt-10">
      <h2 className={`text-xl ${WRAP}`}>{session.url}</h2>
      <ul className="mt-4 space-y-6">
        {session.fields.map((f) => (
          <FieldRow
            key={f.key}
            fillId={session.id}
            field={f}
            locked={filled}
            onChange={onChange}
          />
        ))}
      </ul>
      <div className="mt-8">
        <button
          type="button"
          className={BUTTON}
          disabled={confirmed === 0 || filled || fill.isPending}
          onClick={() => fill.mutate()}
        >
          Fill in browser
        </button>
        <p className="mt-2 text-sm text-ink-muted">
          {confirmed} {confirmed === 1 ? "field" : "fields"} confirmed. A
          browser window opens; review the form there and submit it yourself.
        </p>
        {fill.isPending && (
          <p role="status" className="mt-3 text-ink-muted">
            The browser is open. Close its window when you are done.
          </p>
        )}
        {fill.isError && (
          <p role="alert" className={`mt-3 text-danger ${WRAP}`}>
            Could not fill: {fill.error.message}
          </p>
        )}
        {fill.isSuccess && <Outcome result={fill.data} />}
      </div>
    </div>
  );
}

function Outcome({ result }: { result: FillResult }) {
  const skipped = Object.entries(result.skipped);
  return (
    <div role="status" className="mt-3">
      <p>
        Filled {result.filled.length}{" "}
        {result.filled.length === 1 ? "field" : "fields"}.
      </p>
      {skipped.length > 0 && (
        <ul className="mt-1 space-y-1 text-sm">
          {skipped.map(([key, reason]) => (
            <li key={key} className={WRAP}>
              Skipped {key}: {reason}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FieldRow({
  fillId,
  field,
  locked,
  onChange,
}: {
  fillId: number;
  field: FormFieldState;
  locked: boolean;
  onChange: (s: FormSession) => void;
}) {
  const id = useId();
  const [value, setValue] = useState(
    field.confirmed_value ?? field.suggested ?? "",
  );
  const confirm = useMutation({
    mutationFn: () => api.confirmFormField(fillId, field.key, value),
    onSuccess: onChange,
  });
  const withdraw = useMutation({
    mutationFn: () => api.withdrawFormField(fillId, field.key),
    onSuccess: onChange,
  });
  const skip = field.type === "password" || field.type === "file";
  const error = confirm.error ?? withdraw.error;
  return (
    <li className="border-t border-line pt-4">
      <label htmlFor={id} className={`block font-medium ${WRAP}`}>
        {field.label}
        {field.required && <span className="text-ink-muted"> (required)</span>}
      </label>
      <p className="mt-1 text-sm text-ink-muted">{field.reason}</p>
      {skip ? (
        <p className="mt-2 text-sm text-ink-muted">
          Fill this one yourself in the browser.
        </p>
      ) : (
        <>
          {field.options.length > 0 ? (
            <select
              id={id}
              value={value}
              disabled={locked || field.confirmed}
              onChange={(e) => setValue(e.target.value)}
              className={FIELD}
            >
              <option value="">Choose…</option>
              {field.options.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          ) : (
            <input
              id={id}
              value={value}
              disabled={locked || field.confirmed}
              onChange={(e) => setValue(e.target.value)}
              className={FIELD}
            />
          )}
          <div className="mt-2">
            {field.confirmed ? (
              <button
                type="button"
                disabled={locked || withdraw.isPending}
                onClick={() => withdraw.mutate()}
                className="underline underline-offset-4 disabled:opacity-40"
              >
                Withdraw {field.label}
              </button>
            ) : (
              <button
                type="button"
                disabled={locked || value.trim() === "" || confirm.isPending}
                onClick={() => confirm.mutate()}
                className="underline underline-offset-4 disabled:opacity-40"
              >
                Confirm {field.label}
              </button>
            )}
            {field.confirmed && (
              <span className="ml-3 text-sm text-ink-muted">Confirmed</span>
            )}
          </div>
        </>
      )}
      {error && (
        <p role="alert" className={`mt-2 text-sm text-danger ${WRAP}`}>
          {error.message}
        </p>
      )}
    </li>
  );
}
