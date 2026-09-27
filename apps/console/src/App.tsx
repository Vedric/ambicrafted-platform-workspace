import { AmbientAudioProvider, AmbientAudioControl } from "./AmbientAudio";
import { t, useI18n, LanguageSelector, systemText } from "./i18n";
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import {
  Link,
  NavLink,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AnimatePresence,
  LayoutGroup,
  MotionConfig,
  motion,
} from "motion/react";
import {
  Activity,
  ArrowRight,
  AudioLines,
  BookOpen,
  Bot,
  Check,
  Compass,
  ClipboardCheck,
  ChevronDown,
  ChevronRight,
  Gauge,
  GitBranch,
  LayoutDashboard,
  LoaderCircle,
  LockKeyhole,
  LogOut,
  Menu,
  Network,
  Moon,
  Pause,
  Play,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  SquareTerminal,
  Sun,
  Triangle,
  Workflow,
  Wrench,
  X,
  XCircle,
} from "lucide-react";
import { api, definirCsrf, type Session } from "./api";
import WelcomeVoice from "./WelcomeVoice";
import { WelcomeUpdates } from "./WelcomeUpdates";
import { ExperiencePreferences } from "./ExperiencePreferences";
import { ScrollExperience } from "./ScrollExperience";
const Missions = lazy(() =>
  import("./pages/missions").then((module) => ({ default: module.Missions })),
);
import { Preparation } from "./pages/preparation";
import "./architecture.css";
import {
  ToastContext,
  useToast,
  Erreur,
  Chargement,
  Vide,
  Modal,
  MotionPreference,
  useReducedMotionPreference,
} from "./ui";
const VueEnsemble = lazy(() =>
  import("./pages/vue-ensemble").then((module) => ({
    default: module.VueEnsemble,
  })),
);
const Analyses = lazy(() =>
  import("./pages/analyses").then((module) => ({ default: module.Analyses })),
);
const NouvelleAnalyse = lazy(() =>
  import("./pages/analyses").then((module) => ({
    default: module.NouvelleAnalyse,
  })),
);
const DetailAnalyse = lazy(() =>
  import("./pages/analyses").then((module) => ({
    default: module.DetailAnalyse,
  })),
);
import { Bibliotheque, Editeur, Recherche } from "./pages/bibliotheque";
import {
  SantePage,
  Observabilite,
  Operations,
  Agents,
  Parametres,
} from "./pages/plateforme";

const Memory = lazy(() => import("./pages/memory"));
const Assistant = lazy(() => import("./ConversationWorkspace"));
const UserGuide = lazy(() =>
  import("./pages/guide").then((module) => ({ default: module.UserGuide })),
);
const Architecture = lazy(() =>
  import("./pages/architecture").then((module) => ({
    default: module.Architecture,
  })),
);

export {
  useToast,
  Erreur,
  Chargement,
  Vide,
  Titre,
  Badge,
  Markdown,
  Modal,
} from "./ui";

function readPreference(key: string, fallback: string): string {
  try {
    return localStorage.getItem(key) || fallback;
  } catch {
    return fallback;
  }
}
function savePreference(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* Keep the active in-memory preference. */
  }
}

const navigation = [
  {
    get titre() {
      return t("WORKSPACE");
    },
    liens: [
      {
        chemin: "/",
        get nom() {
          return t("Overview");
        },
        icone: LayoutDashboard,
      },
      {
        chemin: "/missions",
        get nom() {
          return t("Missions");
        },
        icone: Compass,
      },
      {
        chemin: "/assistant",
        get nom() {
          return t("AURA · Voice assistant");
        },
        icone: AudioLines,
      },
      {
        chemin: "/analyses",
        get nom() {
          return t("Analyses");
        },
        icone: Workflow,
      },
      {
        chemin: "/approbations",
        get nom() {
          return t("Approvals");
        },
        icone: ShieldCheck,
      },
    ],
  },
  {
    get titre() {
      return t("KNOWLEDGE");
    },
    liens: [
      { chemin: "/runbooks", nom: "Runbooks", icone: BookOpen },
      {
        chemin: "/memoire",
        get nom() {
          return t("Memory graph");
        },
        icone: Network,
      },
      {
        chemin: "/recherche",
        get nom() {
          return t("Search");
        },
        icone: Search,
      },
      {
        chemin: "/guide",
        get nom() {
          return t("User guide");
        },
        icone: BookOpen,
      },
    ],
  },
  {
    get titre() {
      return t("PLATFORM");
    },
    liens: [
      {
        chemin: "/agents",
        get nom() {
          return t("Agents & tools");
        },
        icone: Bot,
      },
      {
        chemin: "/architecture",
        get nom() {
          return t("Architecture");
        },
        icone: Network,
      },
      {
        chemin: "/preparation",
        get nom() {
          return t("Readiness");
        },
        icone: ClipboardCheck,
      },
      {
        chemin: "/sante",
        get nom() {
          return t("System health");
        },
        icone: Activity,
      },
      {
        chemin: "/observabilite",
        get nom() {
          return t("Observability");
        },
        icone: Gauge,
      },
      {
        chemin: "/operations",
        get nom() {
          return t("Operations");
        },
        icone: Wrench,
      },
    ],
  },
];
const liens = navigation.flatMap((g) => g.liens);
function Logo({ compact = false }: { compact?: boolean }) {
  useI18n();
  return (
    <div className="brand">
      <span className="brand-icon">
        <Triangle size={23} />
        <i />
      </span>
      {!compact && (
        <span>
          ambicrafted<span className="brand-sub">{t("AGENTIC WORKSPACE")}</span>
        </span>
      )}
    </div>
  );
}
export default function App() {
  useI18n();
  const currentRoute = useLocation();
  const client = useQueryClient();
  const [ticket] = useState(() =>
    new URLSearchParams(location.hash.slice(1)).get("session"),
  );
  const [ticketPending, setTicketPending] = useState(Boolean(ticket));
  const exchange = useRef<Promise<unknown> | null>(null);
  const [toast, setToast] = useState<{
    message: string;
    erreur: boolean;
  } | null>(null);
  const [ticketErreur, setTicketErreur] = useState<Error | null>(null);
  const [theme, setTheme] = useState(() =>
    readPreference("ambicrafted-theme", "dark"),
  );
  const [animations, setAnimations] = useState(
    () => readPreference("ambicrafted-motion", "enabled") !== "paused",
  );
  const [density, setDensity] = useState(() =>
    readPreference("ambicrafted-density", "comfortable") === "compact"
      ? "compact"
      : "comfortable",
  );
  useEffect(() => {
    document.documentElement.dataset.density = density;
    savePreference("ambicrafted-density", density);
  }, [density]);
  const reduced = useReducedMotionPreference();
  const motionEnabled = animations && !reduced;
  useEffect(() => {
    const value = animations ? "enabled" : "paused";
    document.documentElement.dataset.motion = value;
    savePreference("ambicrafted-motion", value);
  }, [animations]);
  useEffect(() => {
    const update = () => {
      document.documentElement.dataset.visible = document.hidden
        ? "hidden"
        : "visible";
    };
    update();
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);
  const session = useQuery({
    queryKey: ["session"],
    queryFn: () => api<Session>("/auth"),
    // A signed-out response started before the cookie exchange must never
    // overwrite the newly authenticated session, even on a slow connection.
    enabled: !ticketPending,
    retry: false,
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    savePreference("ambicrafted-theme", theme);
  }, [theme]);
  useEffect(() => {
    if (!ticket) return;
    let active = true;
    history.replaceState(null, "", location.pathname + location.search);
    // Keep one exchange across StrictMode's extra effect setup/cleanup cycle.
    exchange.current ??= api("/auth/connexion", "POST", { ticket });
    void exchange.current
      .then(() => {
        if (active) return client.invalidateQueries({ queryKey: ["session"] });
      })
      .catch((error: Error) => {
        if (active) setTicketErreur(error);
      })
      .finally(() => {
        if (active) setTicketPending(false);
      });
    return () => {
      active = false;
    };
  }, [client, ticket]);
  useEffect(() => {
    const expirer = () => {
      definirCsrf(null);
      client.cancelQueries();
      client.removeQueries({ predicate: (q) => q.queryKey[0] !== "session" });
      client.setQueryData<Session>(["session"], (ancien) => ({
        connecte: false,
        csrf: null,
        mot_de_passe: ancien?.mot_de_passe || false,
      }));
      client.invalidateQueries({ queryKey: ["session"] });
    };
    window.addEventListener("session-expiree", expirer);
    return () => window.removeEventListener("session-expiree", expirer);
  }, [client]);
  useEffect(() => {
    definirCsrf(session.data?.csrf || null);
  }, [session.data]);
  useEffect(() => {
    // Enter each workspace at its heading, including sign-in from a scrolled
    // welcome page. Query filters and in-page anchors preserve their position.
    if (window.scrollX || window.scrollY)
      window.scrollTo({ top: 0, left: 0, behavior: "instant" });
  }, [currentRoute.pathname, session.data?.connecte]);
  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(null), 6000);
      return () => clearTimeout(t);
    }
  }, [toast]);
  const notifier = (message: string, erreur = false) =>
    setToast({ message, erreur });
  return (
    <ExperiencePreferences.Provider
      value={{
        theme,
        setTheme,
        animations,
        setAnimations,
        density,
        setDensity,
      }}
    >
      <AmbientAudioProvider>
        <MotionPreference.Provider value={animations}>
          <ScrollExperience routeKey={currentRoute.pathname} />
          <MotionConfig reducedMotion={motionEnabled ? "never" : "always"}>
            <ToastContext.Provider value={notifier}>
              {ticketPending || session.isPending ? (
                <Chargement />
              ) : session.isError ? (
                <main className="fatal">
                  <Logo />
                  <Erreur
                    erreur={session.error}
                    recommencer={() => session.refetch()}
                  />
                </main>
              ) : !session.data?.connecte &&
                currentRoute.pathname === "/guide" ? (
                <div className="public-guide">
                  <header className="public-guide-header">
                    <Link to="/welcome" aria-label={t("Ambicrafted home")}>
                      <Logo />
                    </Link>
                    <LanguageSelector />
                    <Link className="btn" to="/welcome">
                      {t("Enter workspace")}
                      <ArrowRight size={16} />
                    </Link>
                  </header>
                  <main className="page-scene">
                    <Suspense fallback={<Chargement />}>
                      <UserGuide />
                    </Suspense>
                  </main>
                </div>
              ) : session.data?.connecte &&
                currentRoute.pathname !== "/welcome" ? (
                <Cadre
                  theme={theme}
                  changerTheme={() =>
                    setTheme(theme === "dark" ? "light" : "dark")
                  }
                  animations={animations}
                  motionEnabled={motionEnabled}
                  changerAnimations={() => setAnimations((value) => !value)}
                />
              ) : (
                <AccueilPublic
                  connecte={session.data?.connecte || false}
                  motDePasse={session.data?.mot_de_passe || false}
                  erreur={ticketErreur}
                  animations={animations}
                  changerAnimations={() => setAnimations((value) => !value)}
                  theme={theme}
                  changerTheme={() =>
                    setTheme(theme === "dark" ? "light" : "dark")
                  }
                />
              )}
              <AnimatePresence>
                {toast && (
                  <motion.div
                    role={toast.erreur ? "alert" : "status"}
                    className={"toast " + (toast.erreur ? "toast-error" : "")}
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 16 }}
                  >
                    {toast.erreur ? <XCircle size={20} /> : <Check size={20} />}
                    <span>{systemText(toast.message)}</span>
                    <button
                      aria-label={t("Dismiss notification")}
                      onClick={() => setToast(null)}
                    >
                      <X size={16} />
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>
            </ToastContext.Provider>
          </MotionConfig>
        </MotionPreference.Provider>
      </AmbientAudioProvider>
    </ExperiencePreferences.Provider>
  );
}
function AnimationControl({
  enabled,
  toggle,
}: {
  enabled: boolean;
  toggle: () => void;
}) {
  useI18n();
  const reduced = useReducedMotionPreference();
  const label = enabled ? t("Pause animations") : t("Enable animations");
  return (
    <button
      className="icon-button motion-control"
      onClick={toggle}
      aria-label={label}
      title={reduced ? t("Reduced motion is enabled on your device") : label}
      data-system-reduced={reduced}
    >
      {enabled ? <Pause size={16} /> : <Play size={16} />}
    </button>
  );
}
function AccueilPublic({
  connecte = false,
  motDePasse,
  erreur,
  animations,
  changerAnimations,
  theme,
  changerTheme,
}: {
  connecte?: boolean;
  motDePasse: boolean;
  erreur: Error | null;
  animations: boolean;
  changerAnimations: () => void;
  theme: string;
  changerTheme: () => void;
}) {
  const { language } = useI18n();
  useEffect(() => {
    document.title = "Ambicrafted · " + t("AGENTIC WORKSPACE");
  }, [language]);
  const [mot, setMot] = useState("");
  const [instructions, setInstructions] = useState(false);
  const client = useQueryClient();
  const connexion = useMutation({
    mutationFn: () => api("/auth/connexion", "POST", { mot_de_passe: mot }),
    onSuccess: () => {
      setMot("");
      client.invalidateQueries({ queryKey: ["session"] });
    },
  });
  return (
    <div className="landing">
      <header className="landing-header">
        <Logo />
        <div className="landing-controls">
          <LanguageSelector />
          <span className="private-label">
            <LockKeyhole size={14} /> {t("PRIVATE WORKSPACE")}
          </span>
          <AmbientAudioControl />
          <AnimationControl enabled={animations} toggle={changerAnimations} />
          <button
            className="icon-button"
            onClick={changerTheme}
            aria-label={
              theme === "dark"
                ? t("Switch to light theme")
                : t("Switch to dark theme")
            }
          >
            {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </div>
      </header>
      <main className="landing-main">
        <div className="landing-copy reveal-copy">
          <div className="eyebrow">
            <span className="live-dot" />{" "}
            {t("YOUR PRIVATE AGENTIC OPERATING SPACE")}
          </div>
          <h1>
            {t("Intelligence.")}
            <br />
            <span>{t("Within reach.")}</span>
            <em>{t("Entirely yours.")}</em>
          </h1>
          <p className="landing-lead">
            {t(
              "Orchestrate investigations. Explore your knowledge. Talk to AURA. One immersive workspace, powered locally and guided by you.",
            )}
          </p>
          <div className="landing-tags">
            <span>
              <ShieldCheck size={16} /> {t("Local by design")}
            </span>
            <span>
              <GitBranch size={16} /> {t("Evidence-led decisions")}
            </span>
            <span>
              <AudioLines size={16} /> {t("Meet AURA")}
            </span>
          </div>
          {(erreur || connexion.error) && (
            <Erreur erreur={erreur || connexion.error} />
          )}
          <div className="landing-entry">
            {connecte ? (
              <Link to="/" className="btn primary">
                {t("Rejoin workspace")} <ArrowRight size={18} />
              </Link>
            ) : (
              <a href="#workspace-access" className="btn primary">
                {t("Enter workspace")} <ArrowRight size={18} />
              </a>
            )}
          </div>
          {!connecte && (
            <div className="login-card" id="workspace-access" tabIndex={-1}>
              {motDePasse ? (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    connexion.mutate();
                  }}
                >
                  <label htmlFor="connexion-privee">{t("Welcome back")}</label>
                  <div className="login-row">
                    <input
                      id="connexion-privee"
                      type="password"
                      autoComplete="current-password"
                      placeholder={t("Enter your password")}
                      value={mot}
                      onChange={(e) => setMot(e.target.value)}
                      required
                      maxLength={128}
                    />
                    <button
                      className="btn primary"
                      disabled={connexion.isPending}
                    >
                      {connexion.isPending ? (
                        <LoaderCircle className="spin" size={18} />
                      ) : (
                        <ArrowRight size={18} />
                      )}
                      <span>{t("Enter workspace")}</span>
                    </button>
                  </div>
                </form>
              ) : (
                <>
                  <strong>{t("Your workspace, one command away.")}</strong>
                  <p>{t("Open a secure session from your terminal.")}</p>
                  <div className="command-line">
                    <SquareTerminal size={18} />
                    <code>./plateforme ouvrir</code>
                  </div>
                </>
              )}
              <button
                className="text-button"
                onClick={() => setInstructions(!instructions)}
              >
                {t("Sign in from your terminal")} <ChevronDown size={14} />
              </button>
              {instructions && (
                <p className="hint">
                  {t("From the project directory, run")}{" "}
                  <code>./plateforme ouvrir</code>
                  {t(
                    ". A single-use link opens your session. To set up a password, run",
                  )}{" "}
                  <code>./plateforme mot-de-passe</code>.
                </p>
              )}
            </div>
          )}
        </div>
        <WelcomeVoice connected={connecte} />
      </main>
      <section
        className="landing-principles"
        aria-label={t("Workspace principles")}
      >
        <div>
          <span>01</span>
          <div>
            <strong>{t("Connected thinking.")}</strong>
            <p>{t("Knowledge and tools, in one considered workspace.")}</p>
          </div>
          <BookOpen size={21} />
        </div>
        <div>
          <span>02</span>
          <div>
            <strong>{t("Considered action.")}</strong>
            <p>{t("From an alert to a proposal you can actually review.")}</p>
          </div>
          <GitBranch size={21} />
        </div>
        <div>
          <span>03</span>
          <div>
            <strong>{t("Entirely your space.")}</strong>
            <p>{t("Local inference. A human at every decision.")}</p>
          </div>
          <ShieldCheck size={21} />
        </div>
      </section>
      <WelcomeUpdates />
      <div className="landing-marquee" aria-hidden="true">
        <div className="marquee-track">
          {[0, 1].map((copy) => (
            <span key={copy}>
              {[
                t("Missions"),
                t("Knowledge"),
                t("Agents & tools"),
                t("Human oversight"),
                "AURA",
              ].map((label) => (
                <span key={label}>
                  {label}
                  <i>✦</i>
                </span>
              ))}
            </span>
          ))}
        </div>
      </div>
      <footer className="landing-footer">
        <span>
          AM B I C R A F T E D <b> / </b> {t("MISSION CONTROL")}
        </span>
        <span>{t("Built for clarity. Designed for you.")}</span>
      </footer>
    </div>
  );
}
function Cadre({
  theme,
  changerTheme,
  animations,
  changerAnimations,
  motionEnabled,
}: {
  theme: string;
  changerTheme: () => void;
  animations: boolean;
  changerAnimations: () => void;
  motionEnabled: boolean;
}) {
  useI18n();
  const [mobile, setMobile] = useState(false),
    [palette, setPalette] = useState(false);
  const client = useQueryClient(),
    lieu = useLocation(),
    notifier = useToast();
  const titre =
    liens.find((l) => l.chemin === lieu.pathname)?.nom ||
    (lieu.pathname.startsWith("/analyses/")
      ? t("Analysis details")
      : lieu.pathname.startsWith("/runbooks/")
        ? "Runbook"
        : t("Settings & help"));
  useEffect(() => {
    setMobile(false);
    document.title = titre + " · Ambicrafted";
    // A route may be fully cached; revalidate the session even when it needs no data fetch.
    void client.invalidateQueries({ queryKey: ["session"] });
  }, [lieu.pathname, titre]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setPalette((v) => !v);
      }
      if (e.key === "Escape") setMobile(false);
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);
  const sortir = async () => {
    try {
      await api("/auth/deconnexion", "POST");
      client.clear();
      location.assign("/");
    } catch (e) {
      notifier((e as Error).message, true);
    }
  };
  const sidebar = (
    <>
      <Link
        className="brand-link"
        to="/welcome"
        aria-label={t("Ambicrafted home")}
      >
        <Logo />
      </Link>
      <div className="workspace-switch">
        <span className="workspace-avatar">{t("A")}</span>
        <div>
          <strong>{t("Personal workspace")}</strong>
          <small>{t("Private environment")}</small>
        </div>
        <LockKeyhole size={15} />
      </div>
      <nav aria-label={t("Main navigation")}>
        {navigation.map((g) => (
          <div className="nav-group" key={g.titre}>
            <div className="nav-caption">{g.titre}</div>
            {g.liens.map((l) => (
              <NavLink
                key={l.chemin}
                to={l.chemin}
                end={l.chemin === "/"}
                className={({ isActive }) =>
                  "nav-link " + (isActive ? "active" : "")
                }
              >
                {({ isActive }) => (
                  <>
                    {isActive && (
                      <motion.span
                        className="nav-active-plate"
                        layoutId="active-navigation"
                        transition={{
                          type: "spring",
                          stiffness: 440,
                          damping: 38,
                        }}
                        aria-hidden="true"
                      />
                    )}
                    <l.icone size={18} />
                    <span>{l.nom}</span>
                    {l.chemin === "/assistant" && (
                      <span className="nav-new">{t("VOICE")}</span>
                    )}
                  </>
                )}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <div className="local-card">
          <span className="live-dot" />
          <strong>{t("PRIVATE COMPUTE / HUMAN CONTROL")}</strong>
          <p>{t("Local inference. Always in your control.")}</p>
        </div>
        <NavLink className="nav-link" to="/parametres">
          <Settings2 size={18} /> {t("Settings & help")}
        </NavLink>
        <div className="operator">
          <div className="operator-avatar">{t("YOU")}</div>
          <div>
            <strong>{t("You")}</strong>
            <small>{t("Local operator")}</small>
          </div>
          <button
            className="icon-button"
            aria-label={t("Sign out")}
            onClick={sortir}
          >
            <LogOut size={17} />
          </button>
        </div>
      </div>
    </>
  );
  return (
    <div className="app-shell">
      <a className="skip-link" href="#contenu">
        {t("Skip to content")}
      </a>
      <aside className="sidebar">
        <LayoutGroup id="desktop-navigation">{sidebar}</LayoutGroup>
      </aside>
      {mobile && (
        <Modal titre="Navigation" fermer={() => setMobile(false)}>
          <div className="mobile-nav">
            <LayoutGroup id="mobile-navigation">{sidebar}</LayoutGroup>
          </div>
        </Modal>
      )}
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              aria-label={t("Open navigation")}
              onClick={() => setMobile(true)}
            >
              <Menu size={22} />
            </button>
            <span>{t("Workspace")}</span>
            <ChevronRight size={14} />
            <strong>{titre}</strong>
          </div>
          <div className="topbar-actions">
            <LanguageSelector />
            <button
              className="command-button"
              aria-label={t("Open command menu")}
              onClick={() => setPalette(true)}
            >
              <Search size={16} />
              <span>{t("Command center")}</span>
              <kbd>⌘ K</kbd>
            </button>
            <span className="private-pill">
              <LockKeyhole size={13} /> {t("PRIVATE")}
            </span>
            <AmbientAudioControl />
            <AnimationControl enabled={animations} toggle={changerAnimations} />
            <button
              className="icon-button"
              onClick={changerTheme}
              aria-label={
                theme === "dark"
                  ? t("Switch to light theme")
                  : t("Switch to dark theme")
              }
            >
              {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            </button>
          </div>
        </header>
        <main id="contenu" className="content" tabIndex={-1}>
          <motion.div
            className="page-scene"
            key={lieu.pathname}
            initial={motionEnabled ? { opacity: 0, y: 14 } : false}
            animate={{ opacity: 1, y: 0 }}
            transition={{
              duration: motionEnabled ? 0.42 : 0,
              ease: [0.22, 1, 0.36, 1],
            }}
          >
            <Suspense fallback={<Chargement />}>
              <Routes>
                <Route path="/" element={<VueEnsemble />} />
                <Route path="/missions" element={<Missions />} />
                <Route path="/memoire" element={<Memory />} />
                <Route path="/preparation" element={<Preparation />} />
                <Route path="/architecture" element={<Architecture />} />
                <Route path="/guide" element={<UserGuide />} />
                <Route path="/analyses" element={<Analyses />} />
                <Route
                  path="/analyses/nouvelle"
                  element={<NouvelleAnalyse />}
                />
                <Route path="/analyses/:id" element={<DetailAnalyse />} />
                <Route
                  path="/approbations"
                  element={<Analyses approbations />}
                />
                <Route path="/runbooks" element={<Bibliotheque />} />
                <Route path="/runbooks/:nom" element={<Editeur />} />
                <Route path="/recherche" element={<Recherche />} />
                <Route path="/sante" element={<SantePage />} />
                <Route path="/observabilite" element={<Observabilite />} />
                <Route path="/operations" element={<Operations />} />
                <Route path="/agents" element={<Agents />} />
                <Route path="/parametres" element={<Parametres />} />
                <Route path="/assistant" element={<Assistant />} />
                <Route
                  path="*"
                  element={
                    <Vide
                      titre={t("This page is off the map.")}
                      texte={t("Let’s get you back to your workspace.")}
                    >
                      <Link className="btn primary" to="/">
                        {t("Back to overview")}
                      </Link>
                    </Vide>
                  }
                />
              </Routes>
            </Suspense>
          </motion.div>
          <footer className="app-footer">
            <span>
              {t("Ambicrafted")} <b> / </b>{" "}
              {t("Local intelligence. Human decisions.")}
            </span>
            <Link to="/parametres">
              {t("CLI reference")} <ArrowRight size={12} />
            </Link>
          </footer>
        </main>
      </div>
      {palette && <Palette fermer={() => setPalette(false)} />}
    </div>
  );
}
function Palette({ fermer }: { fermer: () => void }) {
  useI18n();
  const [q, setQ] = useState("");
  const navigate = useNavigate();
  return (
    <Modal titre={t("Go anywhere")} fermer={fermer}>
      <div className="search-input">
        <Search size={18} />
        <input
          aria-label={t("Search pages")}
          autoFocus
          placeholder={t("Find a page, a tool, your next move…")}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>
      <div className="palette-results">
        {[
          ...liens,
          {
            chemin: "/parametres",
            nom: t("Settings & CLI reference"),
            icone: Settings2,
          },
          {
            chemin: "/analyses/nouvelle",
            nom: t("New analysis"),
            icone: Plus,
          },
        ]
          .filter((l) =>
            l.nom.toLocaleLowerCase().includes(q.toLocaleLowerCase("en")),
          )
          .map((l) => (
            <button
              key={l.chemin}
              onClick={() => {
                navigate(l.chemin);
                fermer();
              }}
            >
              <l.icone size={19} />
              {l.nom}
              <ArrowRight size={16} />
            </button>
          ))}
      </div>
      <p className="hint">
        {t("Tab to browse · Enter to open · Esc to close")}
      </p>
    </Modal>
  );
}
