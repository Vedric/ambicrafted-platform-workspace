import { t, useI18n, LanguageSelector } from "./i18n";
import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import "@fontsource-variable/manrope";
import "@fontsource-variable/jetbrains-mono";
import "./style.css";
import "./premium.css";
import App from "./App";
import "./experience.css";
import "./aura-workspace.css";

const client = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 5000, refetchOnWindowFocus: true },
  },
});
function FatalError() {
  useI18n();
  return (
    <main className="fatal">
      <LanguageSelector />
      <h1>{t("Something interrupted your workspace.")}</h1>
      <p>{t("Your analyses are still safely stored on this device.")}</p>
      <button onClick={() => location.reload()}>{t("Reload workspace")}</button>
    </main>
  );
}
class FrontiereErreur extends React.Component<
  React.PropsWithChildren,
  { erreur: boolean }
> {
  state = { erreur: false };
  static getDerivedStateFromError() {
    return { erreur: true };
  }
  render() {
    return this.state.erreur ? <FatalError /> : this.props.children;
  }
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <FrontiereErreur>
      <QueryClientProvider client={client}>
        <BrowserRouter>
          <MotionConfig reducedMotion="user">
            <App />
          </MotionConfig>
        </BrowserRouter>
      </QueryClientProvider>
    </FrontiereErreur>
  </React.StrictMode>,
);
