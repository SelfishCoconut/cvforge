import "@testing-library/jest-dom/vitest";

// jsdom has no ResizeObserver; Radix primitives (Switch) construct one on mount.
globalThis.ResizeObserver ??= class {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
};
