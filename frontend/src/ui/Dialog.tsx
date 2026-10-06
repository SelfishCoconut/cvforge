import * as RD from "@radix-ui/react-dialog";
import type { ReactNode } from "react";

/** The dialog root; controls open state. */
export const Dialog = RD.Root;
/** The element that opens the dialog; focus returns to it on close. */
export const DialogTrigger = RD.Trigger;
/** Closes the dialog when activated. */
export const DialogClose = RD.Close;

/** Centred modal placement; a drawer passes its own placement classes. */
export const CENTRED =
  "left-1/2 top-1/2 w-[min(42rem,calc(100vw-2rem))] max-h-[calc(100dvh-2rem)] -translate-x-1/2 -translate-y-1/2";

interface DialogContentProps {
  /** The accessible name, rendered as the dialog heading. */
  title: string;
  /** The accessible description, rendered under the title. */
  description: string;
  /** Placement and size classes; defaults to a centred modal. */
  placement?: string;
  /** Overrides where focus goes on close, for triggers that are not a `DialogTrigger`. */
  onCloseAutoFocus?: (event: Event) => void;
  children: ReactNode;
}

/**
 * Modal content in a portal over a dimmed overlay. Focus is trapped inside,
 * Escape closes, and focus returns to the trigger (Radix behaviour).
 */
export function DialogContent({
  title,
  description,
  placement = CENTRED,
  onCloseAutoFocus,
  children,
}: DialogContentProps) {
  return (
    <RD.Portal>
      <RD.Overlay className="fixed inset-0 bg-ink/40" />
      <RD.Content
        onCloseAutoFocus={onCloseAutoFocus}
        className={`fixed ${placement} overflow-y-auto rounded-sm bg-card p-6 text-ink shadow-lg ring-1 ring-line`}
      >
        <RD.Title className="text-2xl">{title}</RD.Title>
        <RD.Description className="mt-2 text-sm text-ink-muted">{description}</RD.Description>
        {children}
      </RD.Content>
    </RD.Portal>
  );
}
