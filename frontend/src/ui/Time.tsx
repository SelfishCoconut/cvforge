/** A machine-readable timestamp shown in the reader's locale. */
export function Time({ iso }: { iso: string }) {
  return (
    <time dateTime={iso}>
      {new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}
    </time>
  );
}
