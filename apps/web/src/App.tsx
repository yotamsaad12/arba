import { useTranslation } from "react-i18next";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { useAuth } from "./auth/AuthProvider";
import { AppLayout } from "./components/Layout";
import { Spinner } from "./components/ui";
import { ImportPage } from "./pages/Import";
import { LandingPage } from "./pages/Landing";
import { LoginPage } from "./pages/Login";
import { NewProjectPage } from "./pages/NewProject";
import { ProjectPage } from "./pages/Project";
import { ProjectsPage } from "./pages/Projects";
import { RegisterPage } from "./pages/Register";
import { SettingsPage } from "./pages/Settings";
import { WhatsAppSimulatorPage } from "./pages/WhatsAppSimulator";

export function App() {
  const { t } = useTranslation();
  const { status } = useAuth();

  if (status === "loading") return <Spinner label={t("app.loading")} />;

  return (
    <BrowserRouter>
      {status === "anonymous" ? (
        <Routes>
          <Route index element={<LandingPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      ) : (
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<ProjectsPage />} />
            <Route path="/projects/new" element={<NewProjectPage />} />
            <Route path="/projects/:projectId" element={<ProjectPage />} />
            <Route path="/projects/:projectId/import" element={<ImportPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/dev/whatsapp" element={<WhatsAppSimulatorPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      )}
    </BrowserRouter>
  );
}
