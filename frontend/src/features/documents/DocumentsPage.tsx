import { useMutation } from "@tanstack/react-query";
import { useId, useState, type ChangeEvent } from "react";
import { Link } from "react-router";
import { api } from "../../api/client";
import type { DocumentView, ExtractionView } from "../../api/types";
import { WRAP } from "../../ui/text";

const ACCEPT = ".pdf,.docx,.md,.txt";

/** Upload a document, then have the model propose the facts it states, each with its quote. */
export function DocumentsPage() {
  const inputId = useId();
  const [uploaded, setUploaded] = useState<DocumentView[]>([]);
  const upload = useMutation({
    mutationFn: (file: File) => api.uploadDocument(file),
    onSuccess: (doc) => setUploaded((docs) => [doc, ...docs]),
  });

  function onPick(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) upload.mutate(file);
  }

  return (
    <section>
      <h1 className="text-3xl">Documents</h1>
      <p className="mt-3 max-w-prose text-ink-muted">
        Upload a CV, certificate or notes. I read the text, propose the facts it states with the
        passage that supports each one, and nothing is saved until you review it.
      </p>
      <div className="mt-8">
        <label htmlFor={inputId} className="block font-medium">
          Document
        </label>
        <input
          id={inputId}
          type="file"
          accept={ACCEPT}
          onChange={onPick}
          disabled={upload.isPending}
          className="mt-2 block w-full max-w-prose text-sm file:mr-4 file:rounded-sm file:border-0 file:bg-accent file:px-4 file:py-2 file:text-surface"
        />
        <p className="mt-1 text-sm text-ink-muted">
          PDF, DOCX, Markdown or plain text, up to 20 MiB.
        </p>
        {upload.isPending && <p className="mt-3 text-ink-muted">Uploading…</p>}
        {upload.isError && (
          <p role="alert" className={`mt-3 text-danger ${WRAP}`}>
            Could not upload: {upload.error.message}
          </p>
        )}
      </div>
      {uploaded.length > 0 && (
        <ul className="mt-10 space-y-8">
          {uploaded.map((doc) => (
            <DocumentItem key={doc.source_id} doc={doc} />
          ))}
        </ul>
      )}
    </section>
  );
}

function DocumentItem({ doc }: { doc: DocumentView }) {
  const extract = useMutation({
    mutationFn: () => api.extractDocument(doc.source_id),
  });
  return (
    <li className="border-t border-line pt-4">
      <h2 className={`text-xl ${WRAP}`}>{doc.filename}</h2>
      <p className="mt-1 text-sm text-ink-muted">
        {doc.pages} {doc.pages === 1 ? "page" : "pages"}, {doc.characters.toLocaleString("en")}{" "}
        characters
      </p>
      <div className="mt-3">
        <button
          type="button"
          onClick={() => extract.mutate()}
          disabled={extract.isPending || extract.isSuccess}
          className="rounded-sm bg-accent px-5 py-2 font-medium text-surface disabled:cursor-not-allowed disabled:opacity-40"
        >
          Extract facts
        </button>
      </div>
      {extract.isPending && (
        <p role="status" className="mt-3 text-ink-muted">
          Reading the document. A local model can take several minutes.
        </p>
      )}
      {extract.isError && (
        <p role="alert" className={`mt-3 text-danger ${WRAP}`}>
          Could not extract: {extract.error.message}
        </p>
      )}
      {extract.isSuccess && <Outcome result={extract.data} />}
    </li>
  );
}

function Outcome({ result }: { result: ExtractionView }) {
  const count = result.proposal.operations.length;
  return (
    <div className="mt-3" role="status">
      {result.proposal.id === null ? (
        <p>No facts were found in this document.</p>
      ) : (
        <p>
          Proposed {count} {count === 1 ? "change" : "changes"}.{" "}
          <Link
            to={`/review/${result.proposal.id}`}
            className="text-accent underline decoration-1 underline-offset-4 hover:decoration-2"
          >
            Review them
          </Link>
        </p>
      )}
      {!result.similarity_available && (
        <p className="mt-2 text-sm text-ink-muted">
          Duplicate detection was unavailable, so similar entries are not flagged.
        </p>
      )}
      {result.rejected.length > 0 && (
        <div className="mt-3">
          <p className="text-sm text-ink-muted">Left out, with the reason:</p>
          <ul className="mt-1 space-y-1 text-sm">
            {result.rejected.map((r, i) => (
              <li key={i} className={WRAP}>
                {r.item}: {r.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
