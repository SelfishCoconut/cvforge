import * as RT from "@radix-ui/react-tabs";
import type { ComponentProps } from "react";

/** The tabs root; arrow keys move between triggers (Radix behaviour). */
export const Tabs = RT.Root;

/** The row of tab triggers, ruled underneath. */
export function TabsList({ className = "", ...props }: ComponentProps<typeof RT.List>) {
  return <RT.List className={`flex gap-6 border-b border-line ${className}`} {...props} />;
}

/** One tab; the selected one carries the accent underline. */
export function TabsTrigger({ className = "", ...props }: ComponentProps<typeof RT.Trigger>) {
  return (
    <RT.Trigger
      className={`-mb-px border-b-2 border-transparent pb-2 text-ink-muted hover:text-ink data-[state=active]:border-accent data-[state=active]:text-ink ${className}`}
      {...props}
    />
  );
}

/** The panel for one tab. */
export const TabsContent = RT.Content;
