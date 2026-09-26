import { useEffect, useRef, useState } from "react";
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
  ChevronDown,
  ChevronRight,
  Gauge,
  GitBranch,
  LayoutDashboard,
  LoaderCircle,
  LockKeyhole,
  LogOut,
  Menu,
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
import Assistant from "./Assistant";
import {
  ToastContext,
  useToast,
  Erreur,
  Chargement,
  Vide,
  Modal,
  Orbit,
  MotionPreference,
  useReducedMotionPreference,
} from "./ui";
import { VueEnsemble } from "./pages/vue-ensemble";
import { Analyses, NouvelleAnalyse, DetailAnalyse } from "./pages/analyses";
import { Bibliotheque, Editeur, Recherche } from "./pages/bibliotheque";
import {
  SantePage,
  Observabilite,
  Operations,
  Agents,
  Parametres,
} from "./pages/plateforme";

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

const navigation = [
  {
    titre: "WORKSPACE",
    liens: [
      { chemin: "/", nom: "Overview", icone: LayoutDashboard },
      { chemin: "/assistant", nom: "Voice assistant", icone: AudioLines },
      { chemin: "/analyses", nom: "Analyses", icone: Workflow },
      { chemin: "/approbations", nom: "Approvals", icone: ShieldCheck },
    ],
  },
  {
    titre: "KNOWLEDGE",
    liens: [
      { chemin: "/runbooks", nom: "Runbooks", icone: BookOpen },
      { chemin: "/recherche", nom: "Search", icone: Search },
    ],
  },
  {
    titre: "PLATFORM",
    liens: [
      { chemin: "/agents", nom: "Agents & tools", icone: Bot },
      { chemin: "/sante", nom: "System health", icone: Activity },
      { chemin: "/observabilite", nom: "Observability", icone: Gauge },
      { chemin: "/operations", nom: "Operations", icone: Wrench },
    ],
  },
];
const liens = navigation.flatMap((g) => g.liens);
function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <div className="brand">
      <span className="brand-icon">
        <Triangle size={23} />
        <i />
      </span>
      {!compact && (
        <span>
          ambicrafted<span className="brand-sub">AGENTIC WORKSPACE</span>
        </span>
      )}
    </div>
  );
}
export default function App() {
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
  const [theme, setTheme] = useState(
    () => localStorage.getItem("ambicrafted-theme") || "dark",
  );
  const [animations, setAnimations] = useState(
    () => localStorage.getItem("ambicrafted-motion") !== "paused",
  );
  const reduced = useReducedMotionPreference();
  const motionEnabled = animations && !reduced;
  useEffect(() => {
    const value = animations ? "enabled" : "paused";
    document.documentElement.dataset.motion = value;
    localStorage.setItem("ambicrafted-motion", value);
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
    localStorage.setItem("ambicrafted-theme", theme);
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
    if (toast) {
      const t = setTimeout(() => setToast(null), 6000);
      return () => clearTimeout(t);
    }
  }, [toast]);
  const notifier = (message: string, erreur = false) =>
    setToast({ message, erreur });
  return (
    <MotionPreference.Provider value={animations}>
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
          ) : session.data?.connecte ? (
            <Cadre
              theme={theme}
              changerTheme={() => setTheme(theme === "dark" ? "light" : "dark")}
              animations={animations}
              motionEnabled={motionEnabled}
              changerAnimations={() => setAnimations((value) => !value)}
            />
          ) : (
            <AccueilPublic
              motDePasse={session.data?.mot_de_passe || false}
              erreur={ticketErreur}
              animations={animations}
              changerAnimations={() => setAnimations((value) => !value)}
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
                <span>{toast.message}</span>
                <button
                  aria-label="Dismiss notification"
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
  );
}
function AnimationControl({
  enabled,
  toggle,
}: {
  enabled: boolean;
  toggle: () => void;
}) {
  const label = enabled ? "Pause animations" : "Enable animations";
  return (
    <button
      className="icon-button motion-control"
      onClick={toggle}
      aria-label={label}
      title={label}
    >
      {enabled ? <Pause size={16} /> : <Play size={16} />}
    </button>
  );
}
function AccueilPublic({
  motDePasse,
  erreur,
  animations,
  changerAnimations,
}: {
  motDePasse: boolean;
  erreur: Error | null;
  animations: boolean;
  changerAnimations: () => void;
}) {
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
          <span className="private-label">
            <LockKeyhole size={14} /> PRIVATE WORKSPACE
          </span>
          <AnimationControl enabled={animations} toggle={changerAnimations} />
        </div>
      </header>
      <main className="landing-main">
        <div className="landing-copy reveal-copy">
          <div className="eyebrow">
            <span className="live-dot" /> INTELLIGENCE. WITH INTENTION.
          </div>
          <h1>
            Your next move.
            <br />
            <span>
              Already
              <br />
              in focus.
            </span>
          </h1>
          <p className="landing-lead">
            Turn signals into understanding. A private agentic workspace that
            connects your knowledge, your tools, and your next decision.
          </p>
          <div className="landing-tags">
            <span>
              <ShieldCheck size={16} /> Local by design
            </span>
            <span>
              <GitBranch size={16} /> Evidence-led decisions
            </span>
            <span>
              <AudioLines size={16} /> Voice enabled
            </span>
          </div>
          {(erreur || connexion.error) && (
            <Erreur erreur={erreur || connexion.error} />
          )}
          <div className="login-card">
            {motDePasse ? (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  connexion.mutate();
                }}
              >
                <label htmlFor="connexion-privee">Welcome back</label>
                <div className="login-row">
                  <input
                    id="connexion-privee"
                    type="password"
                    autoComplete="current-password"
                    placeholder="Enter your password"
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
                    <span>Enter workspace</span>
                  </button>
                </div>
              </form>
            ) : (
              <>
                <strong>Your workspace, one command away.</strong>
                <p>Open a secure session from your terminal.</p>
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
              Sign in from your terminal <ChevronDown size={14} />
            </button>
            {instructions && (
              <p className="hint">
                From the project directory, run <code>./plateforme ouvrir</code>
                . A single-use link opens your session. To set up a password,
                run <code>./plateforme mot-de-passe</code>.
              </p>
            )}
          </div>
        </div>
        <Orbit />
      </main>
      <section className="landing-principles" aria-label="Workspace principles">
        <div>
          <span>01</span>
          <div>
            <strong>Connected thinking.</strong>
            <p>Knowledge and tools, in one considered workspace.</p>
          </div>
          <BookOpen size={21} />
        </div>
        <div>
          <span>02</span>
          <div>
            <strong>Considered action.</strong>
            <p>From an alert to a proposal you can actually review.</p>
          </div>
          <GitBranch size={21} />
        </div>
        <div>
          <span>03</span>
          <div>
            <strong>Entirely your space.</strong>
            <p>Local inference. A human at every decision.</p>
          </div>
          <ShieldCheck size={21} />
        </div>
      </section>
      <footer className="landing-footer">
        <span>
          AM B I C R A F T E D <b> / </b> MISSION CONTROL
        </span>
        <span>Built for clarity. Designed for you.</span>
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
  const [mobile, setMobile] = useState(false),
    [palette, setPalette] = useState(false);
  const client = useQueryClient(),
    lieu = useLocation(),
    notifier = useToast();
  const titre =
    liens.find((l) => l.chemin === lieu.pathname)?.nom ||
    (lieu.pathname.startsWith("/analyses/")
      ? "Analysis details"
      : lieu.pathname.startsWith("/runbooks/")
        ? "Runbook"
        : "Settings & help");
  useEffect(() => {
    setMobile(false);
    document.title = titre + " · Ambicrafted";
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
      <Link className="brand-link" to="/" aria-label="Ambicrafted home">
        <Logo />
      </Link>
      <div className="workspace-switch">
        <span className="workspace-avatar">A</span>
        <div>
          <strong>Personal workspace</strong>
          <small>Private environment</small>
        </div>
        <LockKeyhole size={15} />
      </div>
      <nav aria-label="Main navigation">
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
                      <span className="nav-new">VOICE</span>
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
          <strong>Your intelligence. Your space.</strong>
          <p>Local inference. Always in your control.</p>
        </div>
        <NavLink className="nav-link" to="/parametres">
          <Settings2 size={18} /> Settings & help
        </NavLink>
        <div className="operator">
          <div className="operator-avatar">YOU</div>
          <div>
            <strong>You</strong>
            <small>Local operator</small>
          </div>
          <button
            className="icon-button"
            aria-label="Sign out"
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
        Skip to content
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
              aria-label="Open navigation"
              onClick={() => setMobile(true)}
            >
              <Menu size={22} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>{titre}</strong>
          </div>
          <div className="topbar-actions">
            <button
              className="command-button"
              aria-label="Open command menu"
              onClick={() => setPalette(true)}
            >
              <Search size={16} />
              <span>Quick search</span>
              <kbd>⌘ K</kbd>
            </button>
            <span className="private-pill">
              <LockKeyhole size={13} /> PRIVATE
            </span>
            <AnimationControl enabled={animations} toggle={changerAnimations} />
            <button
              className="icon-button"
              onClick={changerTheme}
              aria-label={
                theme === "dark"
                  ? "Switch to light theme"
                  : "Switch to dark theme"
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
            <Routes>
              <Route path="/" element={<VueEnsemble />} />
              <Route path="/analyses" element={<Analyses />} />
              <Route path="/analyses/nouvelle" element={<NouvelleAnalyse />} />
              <Route path="/analyses/:id" element={<DetailAnalyse />} />
              <Route path="/approbations" element={<Analyses approbations />} />
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
                    titre="This page is off the map."
                    texte="Let’s get you back to your workspace."
                  >
                    <Link className="btn primary" to="/">
                      Back to overview
                    </Link>
                  </Vide>
                }
              />
            </Routes>
          </motion.div>
          <footer className="app-footer">
            <span>
              Ambicrafted <b> / </b> Local intelligence. Human decisions.
            </span>
            <Link to="/parametres">
              CLI reference <ArrowRight size={12} />
            </Link>
          </footer>
        </main>
      </div>
      {palette && <Palette fermer={() => setPalette(false)} />}
    </div>
  );
}
function Palette({ fermer }: { fermer: () => void }) {
  const [q, setQ] = useState("");
  const navigate = useNavigate();
  return (
    <Modal titre="Go anywhere" fermer={fermer}>
      <div className="search-input">
        <Search size={18} />
        <input
          aria-label="Search pages"
          autoFocus
          placeholder="Find a page, a tool, your next move…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>
      <div className="palette-results">
        {[
          ...liens,
          {
            chemin: "/analyses/nouvelle",
            nom: "New analysis",
            icone: Plus,
          },
        ]
          .filter((l) =>
            l.nom.toLocaleLowerCase("en").includes(q.toLocaleLowerCase("en")),
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
      <p className="hint">Tab to browse · Enter to open · Esc to close</p>
    </Modal>
  );
}
