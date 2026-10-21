import { initI18n } from "@arba/i18n";
import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { AuthProvider } from "./auth/AuthProvider";
import { CelebrationProvider } from "./components/Celebrations";
import "./index.css";
import { queryClient } from "./lib/api";

initI18n();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <CelebrationProvider>
          <App />
        </CelebrationProvider>
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
