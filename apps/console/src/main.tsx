import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import "@fontsource-variable/manrope";
import "@fontsource-variable/jetbrains-mono";
import "./style.css";
import App from "./App";

const client = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 5000, refetchOnWindowFocus: true },
  },
});
class FrontiereErreur extends React.Component<
  React.PropsWithChildren,
  { erreur: boolean }
> {
  state = { erreur: false };
  static getDerivedStateFromError() {
    return { erreur: true };
  }
  render() {
    return this.state.erreur ? (
      <main className="fatal">
        <h1>L’interface a rencontré une erreur.</h1>
        <p>Vos analyses restent conservées sur ce poste.</p>
        <button onClick={() => location.reload()}>Recharger l’interface</button>
      </main>
    ) : (
      this.props.children
    );
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
