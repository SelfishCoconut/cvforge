import { Link, Navigate, Route, Routes } from "react-router";
import { ChatPage } from "../features/chat/ChatPage";
import { EntityPage } from "../features/knowledge/EntityPage";
import { KnowledgePage } from "../features/knowledge/KnowledgePage";
import { ReviewPage } from "../features/review/ReviewPage";
import { ReviewQueuePage } from "../features/review/ReviewQueuePage";
import { SettingsPage } from "../features/settings/SettingsPage";

/** Every client-side route of the SPA; unknown paths render a not-found page. */
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/chat" replace />} />
      <Route path="/chat" element={<ChatPage />} />
      <Route path="/review" element={<ReviewQueuePage />} />
      <Route path="/review/:id" element={<ReviewPage />} />
      <Route path="/knowledge" element={<KnowledgePage />} />
      <Route path="/knowledge/:id" element={<EntityPage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}

function NotFound() {
  return (
    <section className="max-w-prose">
      <h1 className="text-3xl">Page not found</h1>
      <p className="mt-3 text-ink-muted">Nothing lives at this address.</p>
      <p className="mt-6">
        <Link
          to="/chat"
          className="text-accent underline decoration-1 underline-offset-4 hover:decoration-2"
        >
          Go to chat
        </Link>
      </p>
    </section>
  );
}
