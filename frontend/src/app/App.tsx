import { AppRoutes } from "./routes";
import { Shell } from "./Shell";

/** The application: the persistent shell around the routed page. */
export function App() {
  return (
    <Shell>
      <AppRoutes />
    </Shell>
  );
}
