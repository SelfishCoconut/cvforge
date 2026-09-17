export interface Health {
  status: string;
  version: string;
}

/** Ask the backend whether it is serving, and which version is running. */
export async function fetchHealth(): Promise<Health> {
  const response = await fetch("/api/health");
  if (!response.ok) {
    throw new Error(`health check failed with status ${response.status}`);
  }
  return (await response.json()) as Health;
}
