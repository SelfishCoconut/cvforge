const TONES: Record<string, string> = {
  new: "bg-new-soft text-new",
  known: "bg-known-soft text-known",
  duplicate: "bg-duplicate-soft text-duplicate",
  conflict: "bg-conflict-soft text-conflict",
};

const NEUTRAL = "bg-transparent text-ink-muted ring-1 ring-inset ring-line";

/**
 * A proposal classification shown as its text label on a tinted ground.
 * The label always carries the meaning; colour only reinforces it. Unknown
 * values render as neutral raw text.
 */
export function ClassificationBadge({ value }: { value: string }) {
  // Own keys only: an API string like "constructor" must not resolve through the prototype.
  const tone = Object.hasOwn(TONES, value) ? (TONES[value] ?? NEUTRAL) : NEUTRAL;
  return (
    <span
      className={`inline-flex items-center rounded-sm px-1.5 py-0.5 text-xs font-medium leading-none ${tone}`}
    >
      {value}
    </span>
  );
}
