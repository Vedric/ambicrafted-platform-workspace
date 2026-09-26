import { useEffect, useState } from "react";
import {
  Link,
  NavLink,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
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
    titre: "ESPACE DE TRAVAIL",
    liens: [
      { chemin: "/", nom: "Vue d’ensemble", icone: LayoutDashboard },
      { chemin: "/assistant", nom: "Assistant vocal", icone: AudioLines },
      { chemin: "/analyses", nom: "Analyses", icone: Workflow },
      { chemin: "/approbations", nom: "Approbations", icone: ShieldCheck },
    ],
  },
  {
    titre: "CONNAISSANCES",
    liens: [
      { chemin: "/runbooks", nom: "Bibliothèque", icone: BookOpen },
      { chemin: "/recherche", nom: "Recherche", icone: Search },
    ],
  },
  {
    titre: "PLATEFORME",
    liens: [
      { chemin: "/agents", nom: "Agents & outils", icone: Bot },
      { chemin: "/sante", nom: "Santé & modèles", icone: Activity },
      { chemin: "/observabilite", nom: "Observabilité", icone: Gauge },
      { chemin: "/operations", nom: "Opérations", icone: Wrench },
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
let echange: Promise<unknown> | null = null;
export default function App() {
  const client = useQueryClient();
  const [toast, setToast] = useState<{
    message: string;
    erreur: boolean;
  } | null>(null);
  const [ticketErreur, setTicketErreur] = useState<Error | null>(null);
  const [theme, setTheme] = useState(
    () => localStorage.getItem("ambicrafted-theme") || "dark",
  );
  const session = useQuery({
    queryKey: ["session"],
    queryFn: () => api<Session>("/auth"),
    retry: false,
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("ambicrafted-theme", theme);
  }, [theme]);
  useEffect(() => {
    const ticket = new URLSearchParams(location.hash.slice(1)).get("session");
    if (ticket && !echange) {
      history.replaceState(null, "", location.pathname + location.search);
      echange = api("/auth/connexion", "POST", { ticket })
        .then(() => client.invalidateQueries({ queryKey: ["session"] }))
        .catch((e) => setTicketErreur(e));
    }
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
    <ToastContext.Provider value={notifier}>
      {session.isPending ? (
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
        />
      ) : (
        <AccueilPublic
          motDePasse={session.data?.mot_de_passe || false}
          erreur={ticketErreur}
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
              aria-label="Fermer la notification"
              onClick={() => setToast(null)}
            >
              <X size={16} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </ToastContext.Provider>
  );
}
function AccueilPublic({
  motDePasse,
  erreur,
}: {
  motDePasse: boolean;
  erreur: Error | null;
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
        <span className="private-label">
          <LockKeyhole size={14} /> Espace privé · Local
        </span>
      </header>
      <main className="landing-main">
        <div className="landing-copy">
          <div className="eyebrow">
            <span className="live-dot" /> L’INTELLIGENCE, SOUS VOTRE CONTRÔLE
          </div>
          <h1>
            Votre astreinte.
            <br />
            <span>
              Une longueur
              <br />
              d’avance.
            </span>
          </h1>
          <p className="landing-lead">
            De l’alerte à la décision, un espace agentique qui relie vos
            connaissances, vos outils et votre expertise.
          </p>
          <div className="landing-tags">
            <span>
              <ShieldCheck size={16} /> Données locales
            </span>
            <span>
              <GitBranch size={16} /> Décisions traçables
            </span>
            <span>
              <AudioLines size={16} /> Dialogue vocal
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
                <label htmlFor="connexion-privee">Retrouver votre espace</label>
                <div className="login-row">
                  <input
                    id="connexion-privee"
                    type="password"
                    autoComplete="current-password"
                    placeholder="Votre mot de passe"
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
                    <span>Entrer</span>
                  </button>
                </div>
              </form>
            ) : (
              <>
                <strong>Bienvenue dans votre espace de travail.</strong>
                <p>Ouvrez une session sécurisée depuis votre terminal.</p>
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
              Connexion depuis le terminal <ChevronDown size={14} />
            </button>
            {instructions && (
              <p className="hint">
                Dans le dossier du projet, exécutez{" "}
                <code>./plateforme ouvrir</code>. Un lien à usage unique ouvre
                votre session. Pour configurer un mot de passe :{" "}
                <code>./plateforme mot-de-passe</code>.
              </p>
            )}
          </div>
        </div>
        <Orbit />
      </main>
      <footer className="landing-footer">
        <span>
          AM B I C R A F T E D <b> / </b> MISSION CONTROL
        </span>
        <span>Conçu pour décider. Avec vous.</span>
      </footer>
    </div>
  );
}
function Cadre({
  theme,
  changerTheme,
}: {
  theme: string;
  changerTheme: () => void;
}) {
  const [mobile, setMobile] = useState(false),
    [palette, setPalette] = useState(false);
  const client = useQueryClient(),
    lieu = useLocation(),
    notifier = useToast();
  const titre =
    liens.find((l) => l.chemin === lieu.pathname)?.nom ||
    (lieu.pathname.startsWith("/analyses/")
      ? "Détail de l’analyse"
      : lieu.pathname.startsWith("/runbooks/")
        ? "Runbook"
        : "Paramètres");
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
      <Link className="brand-link" to="/" aria-label="Ambicrafted, accueil">
        <Logo />
      </Link>
      <div className="workspace-switch">
        <span className="workspace-avatar">A</span>
        <div>
          <strong>Mon espace privé</strong>
          <small>Poste local</small>
        </div>
        <LockKeyhole size={15} />
      </div>
      <nav aria-label="Navigation principale">
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
                <l.icone size={18} />
                <span>{l.nom}</span>
                {l.chemin === "/assistant" && (
                  <span className="nav-new">VOIX</span>
                )}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <div className="local-card">
          <span className="live-dot" />
          <strong>Votre IA reste ici.</strong>
          <p>Inférence locale. Vous gardez la main.</p>
        </div>
        <NavLink className="nav-link" to="/parametres">
          <Settings2 size={18} /> Paramètres & aide
        </NavLink>
        <div className="operator">
          <div className="operator-avatar">VO</div>
          <div>
            <strong>Vous</strong>
            <small>Opérateur local</small>
          </div>
          <button
            className="icon-button"
            aria-label="Déconnexion"
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
        Aller au contenu
      </a>
      <aside className="sidebar">{sidebar}</aside>
      {mobile && (
        <Modal titre="Navigation" fermer={() => setMobile(false)}>
          <div className="mobile-nav">{sidebar}</div>
        </Modal>
      )}
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              aria-label="Ouvrir le menu"
              onClick={() => setMobile(true)}
            >
              <Menu size={22} />
            </button>
            <span>Espace de travail</span>
            <ChevronRight size={14} />
            <strong>{titre}</strong>
          </div>
          <div className="topbar-actions">
            <button
              className="command-button"
              aria-label="Accès rapide"
              onClick={() => setPalette(true)}
            >
              <Search size={16} />
              <span>Accès rapide</span>
              <kbd>⌘ K</kbd>
            </button>
            <span className="private-pill">
              <LockKeyhole size={13} /> PRIVÉ
            </span>
            <button
              className="icon-button"
              onClick={changerTheme}
              aria-label={
                theme === "dark"
                  ? "Activer le thème clair"
                  : "Activer le thème sombre"
              }
            >
              {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            </button>
          </div>
        </header>
        <main id="contenu" className="content" tabIndex={-1}>
          <motion.div
            key={lieu.pathname}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.22 }}
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
                    titre="Cette page n’existe pas."
                    texte="Retrouvez votre espace de travail."
                  >
                    <Link className="btn primary" to="/">
                      Retour à l’accueil
                    </Link>
                  </Vide>
                }
              />
            </Routes>
          </motion.div>
          <footer className="app-footer">
            <span>
              Ambicrafted <b> / </b> Intelligence locale, décision humaine.
            </span>
            <Link to="/parametres">
              Documentation CLI <ArrowRight size={12} />
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
    <Modal titre="Aller à…" fermer={fermer}>
      <div className="search-input">
        <Search size={18} />
        <input
          aria-label="Chercher une page"
          autoFocus
          placeholder="Une page, un outil, une action…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>
      <div className="palette-results">
        {[
          ...liens,
          {
            chemin: "/analyses/nouvelle",
            nom: "Nouvelle analyse",
            icone: Plus,
          },
        ]
          .filter((l) =>
            l.nom.toLocaleLowerCase("fr").includes(q.toLocaleLowerCase("fr")),
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
        Tab pour parcourir · Entrée pour ouvrir · Échap pour fermer
      </p>
    </Modal>
  );
}
