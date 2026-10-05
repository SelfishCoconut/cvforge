import { useLayoutEffect, useRef, type ReactNode } from "react";
import { Dialog, DialogContent } from "./Dialog";

/** Right-edge sheet placement; full width on phones, a fixed column from `sm` up. */
const RIGHT_EDGE = "right-0 top-0 h-dvh w-full sm:w-[28rem] rounded-none";

interface DrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The accessible name, rendered as the drawer heading. */
  title: string;
  /** The accessible description, rendered under the title. */
  description: string;
  children: ReactNode;
}

/** A modal sheet docked to the right edge. Focus is trapped; Escape closes and restores focus. */
export function Drawer({ open, onOpenChange, title, description, children }: DrawerProps) {
  // Opened from plain buttons rather than a DialogTrigger, so remember who had focus.
  const opener = useRef<HTMLElement | null>(null);
  useLayoutEffect(() => {
    if (open && document.activeElement instanceof HTMLElement) {
      opener.current = document.activeElement;
    }
  }, [open]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title={title}
        description={description}
        placement={RIGHT_EDGE}
        onCloseAutoFocus={(e) => {
          e.preventDefault();
          opener.current?.focus();
        }}
      >
        {children}
      </DialogContent>
    </Dialog>
  );
}
