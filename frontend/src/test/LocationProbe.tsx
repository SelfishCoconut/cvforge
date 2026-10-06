import { useLocation } from "react-router";

/** Renders the current path and query so tests can assert URL state. */
export function LocationProbe() {
  const { pathname, search } = useLocation();
  return <output data-testid="location">{pathname + search}</output>;
}
