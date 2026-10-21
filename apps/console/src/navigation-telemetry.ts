import { useEffect } from "react";
import { envoyerMesuresNavigation } from "./api";
import type { Metric } from "web-vitals";

export type RouteMesuree =
  | "workspace"
  | "assistant"
  | "analyses"
  | "knowledge"
  | "memory"
  | "architecture"
  | "observability"
  | "settings"
  | "guide"
  | "other";
export type MesureNavigation = {
  metric: "LCP" | "INP" | "CLS";
  route: RouteMesuree;
  value: number;
};
type Collecteurs = Pick<
  typeof import("web-vitals"),
  "onCLS" | "onINP" | "onLCP"
>;

export function routeMesuree(pathname: string): RouteMesuree {
  const segment = pathname.split("/")[1];
  const routes: Record<string, RouteMesuree> = {
    "": "workspace",
    assistant: "assistant",
    analyses: "analyses",
    runbooks: "knowledge",
    recherche: "knowledge",
    memoire: "memory",
    architecture: "architecture",
    observabilite: "observability",
    parametres: "settings",
    guide: "guide",
  };
  return Object.hasOwn(routes, segment) ? routes[segment] : "other";
}

// One lifetime per document. The SDK owns its observers and has no public
// disconnect API: callbacks are inert after closure; we remove only our listener.
// First-resolved anonymous sessions are excluded even after subsequent login.
export function creerTelemetrieNavigation(
  charger: () => Promise<Collecteurs> = () => import("web-vitals"),
  envoyer: (
    samples: MesureNavigation[],
  ) => Promise<void> = envoyerMesuresNavigation,
) {
  let monte = 0;
  let authentifie = false;
  let decide = false;
  let ferme = false;
  let route: RouteMesuree = "other";
  const mesures = new Map<MesureNavigation["metric"], MesureNavigation>();
  const recevoir = (metric: Metric) => {
    if (!monte || !authentifie || ferme) return;
    const name = metric.name;
    if (name !== "LCP" && name !== "INP" && name !== "CLS") return;
    if (
      !Number.isFinite(metric.value) ||
      metric.value < 0 ||
      metric.value > (name === "CLS" ? 100 : 300000)
    )
      return;
    // Deliberately reconstruct: no entries, DOM selectors, navigation URL, IDs,
    // attribution data or text may cross this boundary.
    mesures.set(name, { metric: name, route, value: metric.value });
  };
  const cacher = () => {
    if (document.visibilityState !== "hidden" || ferme) return;
    // SDK capture listeners finalize their measurements before this bubble
    // listener. A microtask also includes synchronous final report callbacks.
    queueMicrotask(() => {
      if (ferme) return;
      ferme = true;
      const samples = [...mesures.values()];
      mesures.clear();
      if (monte && authentifie && samples.length) {
        void envoyer(samples).catch(() => {});
      }
    });
  };
  return {
    monter() {
      if (monte++ === 0) window.addEventListener("visibilitychange", cacher);
      return () => {
        if (--monte === 0) {
          window.removeEventListener("visibilitychange", cacher);
          mesures.clear();
        }
      };
    },
    session(connecte: boolean | undefined, pathname: string) {
      if (connecte === undefined) return;
      authentifie = connecte;
      if (decide) {
        if (!connecte) {
          ferme = true;
          mesures.clear();
        }
        return;
      }
      decide = true;
      if (!connecte || document.visibilityState !== "visible") {
        ferme = true;
        return;
      }
      route = routeMesuree(pathname);
      void charger()
        .then((sdk) => {
          if (!monte || !authentifie || ferme || document.hidden) return;
          sdk.onLCP(recevoir);
          sdk.onINP(recevoir);
          sdk.onCLS(recevoir);
        })
        .catch(() => {
          ferme = true;
        });
    },
  };
}

const telemetrie = creerTelemetrieNavigation();
export function useNavigationTelemetry(
  connecte: boolean | undefined,
  route: string,
) {
  useEffect(() => telemetrie.monter(), []);
  useEffect(() => telemetrie.session(connecte, route), [connecte, route]);
}
