import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  BookOpen,
  Bot,
  Database,
  ExternalLink,
  Gauge,
  GitBranch,
  LockKeyhole,
  Search,
  ShieldCheck,
  SquareTerminal,
  Wrench,
} from "lucide-react";
import { api, date, type Analyse, type Journal, type Sante } from "../api";
import { Erreur, Chargement, Vide, Titre, Modal } from "../ui";

export function SantePage() {
  const q = useQuery({
    queryKey: ["sante"],
    queryFn: () => api<Sante>("/sante"),
    refetchInterval: 15000,
  });
  return (
    <>
      <Titre
        surligne="ÉCOSYSTÈME LOCAL"
        titre="Chaque composant, à sa place."
        texte="Disponibilité mesurée, modèles installés et état de la mémoire vectorielle."
      >
        <button
          className="btn"
          onClick={() => q.refetch()}
          disabled={q.isFetching}
        >
          <Activity size={17} /> Actualiser
        </button>
      </Titre>
      {q.isPending ? (
        <Chargement />
      ) : q.error ? (
        <Erreur erreur={q.error} />
      ) : (
        <>
          <div className="service-grid">
            {q.data!.services.map((s) => (
              <section className="panel service-card" key={s.id}>
                <div className="runbook-card-top">
                  <span className="tile-icon">
                    <Database size={23} />
                  </span>
                  <span
                    className={
                      "badge " + (s.ok ? "status-complet" : "status-erreur")
                    }
                  >
                    <i />
                    {s.ok ? "Disponible" : "Indisponible"}
                  </span>
                </div>
                <h2>{s.nom}</h2>
                <p>
                  Temps de réponse{" "}
                  <strong className="mono">{s.latence_ms} ms</strong>
                </p>
                {s.lien && (
                  <a
                    className="text-button"
                    href={s.lien}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Ouvrir la console <ExternalLink size={14} />
                  </a>
                )}
              </section>
            ))}
          </div>
          <div className="dashboard-grid">
            <section className="panel">
              <div className="panel-heading">
                <h2>Modèles présents sur le poste</h2>
                <Bot size={18} />
              </div>
              <div className="model-list">
                {q.data!.modeles.length ? (
                  q.data!.modeles.map((m) => (
                    <div key={m.nom}>
                      <span className="tile-icon">
                        <Bot size={18} />
                      </span>
                      <strong>{m.nom}</strong>
                      <small>{(m.taille / 1e9).toFixed(1)} Go</small>
                    </div>
                  ))
                ) : (
                  <p className="muted">Inventaire indisponible.</p>
                )}
              </div>
            </section>
            <section className="panel instruction-card">
              <span className="tile-icon">
                <Database size={23} />
              </span>
              <h2>Mémoire des runbooks</h2>
              <div className="big-number">
                {q.data!.index.points ?? "—"}
                <small>fragments</small>
              </div>
              <p>
                Collection active : <code>runbooks-current</code>
              </p>
              <p>État : {q.data!.index.statut || "indisponible"}</p>
              <Link className="text-button" to="/operations">
                Actualiser l’index <ArrowRight size={14} />
              </Link>
            </section>
          </div>
        </>
      )}
    </>
  );
}
export function Observabilite() {
  const q = useQuery({
    queryKey: ["observabilite"],
    queryFn: () =>
      api<{
        cibles: {
          nom: string;
          sante: string;
          dernier_scrape: string;
          duree_s: number;
        }[];
        journal: Journal[];
      }>("/observabilite"),
    refetchInterval: 15000,
  });
  return (
    <>
      <Titre
        surligne="OBSERVABILITÉ"
        titre="Comprendre ce qui se passe."
        texte="Métriques collectées et journal des opérations, sans contenu d’alerte dans les événements."
      >
        <a
          className="btn primary"
          href="http://localhost:3000/d/plateforme-sre"
          target="_blank"
          rel="noopener noreferrer"
        >
          <Gauge size={17} /> Ouvrir Grafana <ExternalLink size={14} />
        </a>
      </Titre>
      {q.isPending ? (
        <Chargement />
      ) : q.error ? (
        <Erreur erreur={q.error} />
      ) : (
        <>
          <section className="panel">
            <div className="panel-heading">
              <h2>Collecte Prometheus</h2>
              <span className="tag">{q.data!.cibles.length} CIBLES</span>
            </div>
            <div className="targets">
              {q.data!.cibles.length ? (
                q.data!.cibles.map((c) => (
                  <div key={c.nom}>
                    <span
                      className={
                        "health-dot " +
                        (c.sante === "up" ? "healthy" : "unhealthy")
                      }
                    />
                    <strong>{c.nom}</strong>
                    <span>
                      {c.sante === "up" ? "Collecte active" : "À vérifier"}
                    </span>
                    <small>{date(c.dernier_scrape)}</small>
                    <code>{Math.round(c.duree_s * 1000)} ms</code>
                  </div>
                ))
              ) : (
                <Vide
                  titre="Aucune cible disponible."
                  texte="Vérifiez le service Prometheus dans la page Santé."
                />
              )}
            </div>
          </section>
          <section className="panel">
            <div className="panel-heading">
              <h2>Journal d’activité</h2>
              <span className="muted tiny">60 événements les plus récents</span>
            </div>
            <div className="audit-list">
              {q.data!.journal.map((j) => (
                <div key={j.id}>
                  <span className="audit-icon">
                    <GitBranch size={15} />
                  </span>
                  <div>
                    <strong>
                      {j.action.replaceAll(".", " · ").replaceAll("_", " ")}
                    </strong>
                    <small>
                      {j.acteur}
                      {j.reference ? " · " + j.reference.slice(0, 24) : ""}
                    </small>
                  </div>
                  <time>{date(j.date)}</time>
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </>
  );
}
const operations = [
  {
    id: "verifier",
    titre: "Vérifier la plateforme",
    texte: "Contrôler la configuration et les services nécessaires au moteur.",
    icone: Activity,
    bouton: "Lancer la vérification",
  },
  {
    id: "indexer",
    titre: "Actualiser la mémoire",
    texte:
      "Recalculer les fragments et publier un nouvel index de recherche atomiquement.",
    icone: Database,
    bouton: "Réindexer les runbooks",
  },
  {
    id: "sauvegarder",
    titre: "Créer une sauvegarde",
    texte:
      "Sauvegarder les données et la configuration dans le stockage privé local.",
    icone: ArrowDownToLine,
    bouton: "Sauvegarder maintenant",
  },
  {
    id: "tester-restauration",
    titre: "Tester la restauration",
    texte:
      "Vérifier la dernière sauvegarde dans des conteneurs temporaires isolés.",
    icone: ShieldCheck,
    bouton: "Tester la sauvegarde",
  },
];
export function Operations() {
  const [operation, setOperation] = useState<string | null>(null),
    navigate = useNavigate();
  const lancer = useMutation({
    mutationFn: (id: string) => api<Analyse>("/operations/" + id, "POST"),
    onSuccess: (d) => navigate("/analyses/" + d.id),
  });
  return (
    <>
      <Titre
        surligne="EXPLOITATION"
        titre="Une plateforme qui se maintient."
        texte="Des opérations définies, supervisées et suivies dans votre historique."
      />
      <div className="service-grid operations-grid">
        {operations.map((o) => (
          <section className="panel operation-card" key={o.id}>
            <span className="tile-icon">
              <o.icone size={24} />
            </span>
            <h2>{o.titre}</h2>
            <p>{o.texte}</p>
            <button className="btn" onClick={() => setOperation(o.id)}>
              {o.bouton}
              <ArrowRight size={16} />
            </button>
          </section>
        ))}
      </div>
      <div className="notice inline-notice">
        <ShieldCheck size={20} />
        <span>
          Les opérations partagent une file bornée avec les analyses. Les
          sauvegardes peuvent contenir des données confidentielles ; elles
          restent sur ce poste.
        </span>
      </div>
      {operation && (
        <Modal
          titre={operations.find((o) => o.id === operation)!.titre}
          fermer={() => setOperation(null)}
        >
          <p>{operations.find((o) => o.id === operation)!.texte}</p>
          <p className="muted">
            L’opération sera ajoutée à la file et son résultat apparaîtra dans
            les analyses.
          </p>
          {lancer.error && <Erreur erreur={lancer.error} />}
          <div className="form-actions">
            <button className="btn" onClick={() => setOperation(null)}>
              Retour
            </button>
            <button
              className="btn primary"
              disabled={lancer.isPending}
              onClick={() => lancer.mutate(operation)}
            >
              Confirmer le lancement <ArrowRight size={16} />
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
export function Agents() {
  const q = useQuery({
    queryKey: ["outils"],
    queryFn: () =>
      api<{
        outils: { nom: string; description: string; lecture_seule: boolean }[];
      }>("/outils"),
  });
  return (
    <>
      <Titre
        surligne="AGENTS & OUTILS"
        titre="Des rôles précis. Un objectif commun."
        texte="Une chaîne de spécialistes locaux coordonnée par un graphe, avec validation humaine."
      />
      <div className="agents-flow">
        {[
          {
            nom: "Extraction",
            role: "Comprendre le signal",
            texte:
              "Structure les symptômes et signale les instructions suspectes.",
            icon: Search,
          },
          {
            nom: "Triage",
            role: "Qualifier la situation",
            texte: "Propose une classification et une urgence à vérifier.",
            icon: Activity,
          },
          {
            nom: "Investigation",
            role: "Confronter aux sources",
            texte: "Consulte les runbooks via MCP dans un budget borné.",
            icon: BookOpen,
          },
          {
            nom: "Supervision",
            role: "Vous laisser décider",
            texte: "Contrôle les sources et attend votre approbation.",
            icon: ShieldCheck,
          },
        ].map((a, i) => (
          <section className="panel agent-card" key={a.nom}>
            <span className="agent-number">0{i + 1}</span>
            <span className="tile-icon">
              <a.icon size={24} />
            </span>
            <h2>{a.nom}</h2>
            <strong>{a.role}</strong>
            <p>{a.texte}</p>
            <span className="tag">
              {i === 3 ? "CODE + HUMAIN" : "ALIAS LOCAL"}
            </span>
          </section>
        ))}
      </div>
      <section className="panel">
        <div className="panel-heading">
          <h2>Outils & connecteurs autorisés</h2>
          <span className="tag">MCP LOCAL</span>
        </div>
        {q.isPending ? (
          <Chargement />
        ) : q.error ? (
          <Erreur erreur={q.error} />
        ) : (
          <div className="tools-grid">
            {q.data!.outils.map((o) => (
              <div key={o.nom}>
                <span className="tile-icon">
                  <Wrench size={18} />
                </span>
                <div>
                  <strong>{o.nom}</strong>
                  <p>{o.description}</p>
                  <span className="tiny muted">
                    {o.lecture_seule
                      ? "Lecture seule"
                      : "Action explicite de l’opérateur"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
      <div className="notice inline-notice">
        <LockKeyhole size={20} />
        <span>
          Les rôles d’analyse partagent un moteur local séquentiel. Aucun agent
          ne peut approuver son propre diagnostic ni exécuter une remédiation.
        </span>
      </div>
    </>
  );
}
export function Parametres() {
  const q = useQuery({
    queryKey: ["parametres"],
    queryFn: () =>
      api<{
        version: string;
        acces: string;
        alias: string;
        file_max: number;
        retention_jours: number;
        duree_session_heures: number;
      }>("/parametres"),
  });
  const [mot, setMot] = useState(""),
    [confirmation, setConfirmation] = useState("");
  const client = useQueryClient();
  const changer = useMutation({
    mutationFn: () => api("/auth/mot-de-passe", "PUT", { valeur: mot }),
    onSuccess: () => {
      setMot("");
      setConfirmation("");
      client.clear();
      location.assign("/");
    },
  });
  return (
    <>
      <Titre
        surligne="VOTRE ESPACE"
        titre="Pensé pour vous. Maîtrisé par vous."
        texte="Sécurité locale, préférences de session et accès depuis le terminal."
      />
      <div className="dashboard-grid">
        <section className="panel settings-panel">
          <h2>
            <LockKeyhole size={19} /> Accès & confidentialité
          </h2>
          {q.isPending ? (
            <Chargement />
          ) : q.error ? (
            <Erreur erreur={q.error} />
          ) : (
            <dl>
              <dt>Version</dt>
              <dd>{q.data!.version}</dd>
              <dt>Mode d’accès</dt>
              <dd>{q.data!.acces}</dd>
              <dt>Alias d’analyse</dt>
              <dd>{q.data!.alias}</dd>
              <dt>Capacité de la file</dt>
              <dd>{q.data!.file_max} tâches</dd>
              <dt>Durée de session</dt>
              <dd>{q.data!.duree_session_heures} heures</dd>
              <dt>Rétention des analyses</dt>
              <dd>{q.data!.retention_jours} jours</dd>
            </dl>
          )}
          <p className="hint">
            Le thème se règle en haut de l’écran. Les animations respectent la
            préférence « réduire les mouvements » du système.
          </p>
        </section>
        <section className="panel settings-panel">
          <h2>
            <ShieldCheck size={19} /> Mot de passe de l’interface
          </h2>
          <p>
            Vous pouvez aussi ouvrir une session depuis le CLI sans saisir de
            mot de passe.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              changer.mutate();
            }}
          >
            <label htmlFor="nouveau-mdp">Nouveau mot de passe</label>
            <input
              id="nouveau-mdp"
              type="password"
              autoComplete="new-password"
              minLength={14}
              maxLength={128}
              required
              value={mot}
              onChange={(e) => setMot(e.target.value)}
            />
            <label htmlFor="confirmer-mdp">Confirmation</label>
            <input
              id="confirmer-mdp"
              type="password"
              autoComplete="new-password"
              required
              value={confirmation}
              onChange={(e) => setConfirmation(e.target.value)}
            />
            <p className="hint">
              14 caractères minimum. L’enregistrement révoque les sessions
              existantes.
            </p>
            {changer.error && <Erreur erreur={changer.error} />}
            <button
              className="btn primary"
              disabled={
                changer.isPending || mot.length < 14 || mot !== confirmation
              }
            >
              Enregistrer & reconnecter
            </button>
          </form>
        </section>
      </div>
      <section className="panel settings-panel">
        <h2>
          <SquareTerminal size={20} /> La même plateforme, depuis votre
          terminal.
        </h2>
        <p>
          Depuis le dossier du projet. Les alertes sont lues sur l’entrée
          standard et ne figurent pas dans la liste des processus.
        </p>
        <div className="cli-examples">
          <code>./plateforme ouvrir</code>
          <span>Ouvrir une session dans l’interface</span>
          <code>./plateforme statut</code>
          <span>Vérifier les services locaux</span>
          <code>./plateforme analyses lister</code>
          <span>Retrouver les analyses</span>
          <code>./plateforme --help</code>
          <span>Consulter toutes les commandes</span>
        </div>
      </section>
    </>
  );
}
