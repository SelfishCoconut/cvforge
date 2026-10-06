import * as RS from "@radix-ui/react-switch";
import type { ComponentProps } from "react";

/** An on/off switch (`role="switch"`); Space toggles it (Radix behaviour). */
export function Switch({
  className = "",
  ...props
}: ComponentProps<typeof RS.Root>) {
  return (
    <RS.Root
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border border-line bg-line transition-colors data-[state=checked]:border-accent data-[state=checked]:bg-accent ${className}`}
      {...props}
    >
      <RS.Thumb className="block size-4 translate-x-1 rounded-full bg-card shadow-sm transition-transform data-[state=checked]:translate-x-6" />
    </RS.Root>
  );
}
