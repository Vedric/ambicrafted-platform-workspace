import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  Database,
  FileText,
  LoaderCircle,
  Plus,
  Search,
  Sparkles,
} from "lucide-react";
import { api, type Runbook } from "../api";
import { useToast, Erreur, Chargement, Vide, Titre, Markdown } from "../ui";

export function Bibliotheque() {
  const [recherche, setRecherche] = useState("");
  const q = useQuery({
    queryKey: ["runbooks", recherche],
    queryFn: () =>
      api<Runbook[]>("/runbooks?recherche=" + encodeURIComponent(recherche)),
  });
  return (
    <>
      <Titre
        surligne="MÉMOIRE OPÉRATIONNELLE"
        titre="Le savoir qui guide vos agents."
        texte="Des procédures lisibles, des sources vérifiables, une expertise qui se construit."
      >
        <Link className="btn primary" to="/runbooks/nouveau">
          <Plus size={17} /> Nouveau runbook
        </Link>
      </Titre>
      <div className="notice inline-notice">
        <Database size={19} />
        <span>
          Après une modification, réindexez la bibliothèque pour actualiser la
          recherche sémantique.
        </span>
        <Link to="/operations">
          Réindexer <ArrowRight size={14} />
        </Link>
      </div>
      <div className="toolbar standalone">
        <div className="search-input">
          <Search size={17} />
          <input
            aria-label="Rechercher un runbook"
            placeholder="Chercher dans les procédures…"
            value={recherche}
            onChange={(e) => setRecherche(e.target.value)}
          />
        </div>
        <span className="muted tiny">{q.data?.length ?? "—"} document(s)</span>
      </div>
      {q.isPending ? (
        <Chargement />
      ) : q.error ? (
        <Erreur erreur={q.error} />
      ) : !q.data?.length ? (
        <Vide
          titre="Aucun runbook trouvé."
          texte="Ajoutez une procédure ou essayez une autre recherche."
        />
      ) : (
        <div className="runbook-grid">
          {q.data.map((r) => (
            <Link
              className="panel runbook-card"
              to={"/runbooks/" + encodeURIComponent(r.nom)}
              key={r.nom}
            >
              <div className="runbook-card-top">
                <span className="tile-icon">
                  <BookOpen size={23} />
                </span>
                <ArrowRight size={18} />
              </div>
              <h2>{r.titre}</h2>
              <p>{r.extrait?.replace(/^#+\s*/gm, "").slice(0, 180)}…</p>
              <div className="runbook-card-foot">
                <span className="mono">{r.nom}</span>
                <span>{(r.octets / 1000).toFixed(1)} ko</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
export function Editeur() {
  const { nom } = useParams();
  const nouveau = nom === "nouveau";
  const [nomFichier, setNom] = useState(""),
    [contenu, setContenu] = useState(""),
    [empreinte, setEmpreinte] = useState(""),
    [edition, setEdition] = useState(nouveau),
    [charge, setCharge] = useState(false);
  const notifier = useToast(),
    navigate = useNavigate(),
    client = useQueryClient();
  const q = useQuery({
    queryKey: ["runbook", nom],
    queryFn: () => api<Runbook>("/runbooks/" + encodeURIComponent(nom!)),
    enabled: !nouveau,
  });
  useEffect(() => {
    setCharge(false);
    setEdition(nouveau);
    setContenu("");
    setEmpreinte("");
    setNom("");
  }, [nom, nouveau]);
  useEffect(() => {
    if (q.data && !charge) {
      setContenu(q.data.contenu || "");
      setEmpreinte(q.data.empreinte);
      setNom(q.data.nom);
      setCharge(true);
    }
  }, [q.data, charge]);
  const modifie = contenu !== (q.data?.contenu || "");
  useEffect(() => {
    if (!modifie) return;
    const avertir = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", avertir);
    return () => window.removeEventListener("beforeunload", avertir);
  }, [modifie]);
  const sauver = useMutation({
    mutationFn: () =>
      api<Runbook>(
        "/runbooks/" + encodeURIComponent(nouveau ? nomFichier : nom!),
        "PUT",
        { contenu, empreinte },
      ),
    onSuccess: (d) => {
      setEmpreinte(d.empreinte);
      client.setQueryData(["runbook", d.nom], d);
      client.invalidateQueries({ queryKey: ["runbooks"] });
      notifier(
        "Runbook enregistré. Réindexez pour actualiser la recherche sémantique.",
      );
      setEdition(false);
      if (nouveau) navigate("/runbooks/" + d.nom, { replace: true });
    },
  });
  if (!nouveau && q.isPending) return <Chargement />;
  if (q.error)
    return <Erreur erreur={q.error} recommencer={() => q.refetch()} />;
  return (
    <>
      <Link className="back-link" to="/runbooks">
        <ArrowLeft size={15} /> Bibliothèque
      </Link>
      <Titre
        surligne={nouveau ? "NOUVELLE PROCÉDURE" : "RUNBOOK"}
        titre={nouveau ? "Transmettez votre expertise." : q.data?.titre || nom!}
        texte="Une procédure claire aide l’agent. Sa pertinence reste une décision humaine."
      >
        <button className="btn" onClick={() => setEdition(!edition)}>
          {edition ? <BookOpen size={16} /> : <FileText size={16} />}{" "}
          {edition ? "Aperçu" : "Modifier"}
        </button>
        <button
          className="btn primary"
          onClick={() => sauver.mutate()}
          disabled={
            sauver.isPending || !contenu.trim() || (nouveau && !nomFichier)
          }
        >
          <Check size={17} /> Enregistrer
        </button>
      </Titre>
      {sauver.error && <Erreur erreur={sauver.error} />}
      <section className="panel editor-panel">
        {nouveau && (
          <div className="field">
            <label htmlFor="nom-runbook">Nom du fichier</label>
            <input
              id="nom-runbook"
              placeholder="ma-procedure.md"
              pattern="[a-zA-Z0-9][a-zA-Z0-9_-]*\.md"
              value={nomFichier}
              onChange={(e) => setNom(e.target.value)}
            />
          </div>
        )}
        {edition ? (
          <>
            <label htmlFor="contenu-runbook">Contenu Markdown</label>
            <textarea
              id="contenu-runbook"
              className="code-editor"
              rows={24}
              maxLength={8000}
              value={contenu}
              placeholder={
                "# Titre de la procédure\n\n## Symptômes\n\n## Prérequis\n\n## Diagnostic\n\n## Actions et conditions\n\n## Validation et retour arrière"
              }
              onChange={(e) => setContenu(e.target.value)}
            />
            <div className="field-foot">
              <span>Les modifications sont réservées à l’opérateur.</span>
              <span>{contenu.length} / 8 000</span>
            </div>
          </>
        ) : (
          <Markdown
            texte={
              contenu || "Commencez par rédiger une procédure dans l’éditeur."
            }
          />
        )}
      </section>
      {empreinte && (
        <p className="mono tiny muted break-all">SHA-256 · {empreinte}</p>
      )}
    </>
  );
}
export function Recherche() {
  const [q, setQ] = useState(""),
    [mode, setMode] = useState("texte");
  type Resultats = {
    mode: string;
    elements: (Runbook & {
      score?: number;
      donnees?: { fichier?: string; texte?: string; chemin_titres?: string };
    })[];
  };
  const recherche = useMutation({
    mutationFn: () =>
      api<Resultats>(`/recherche?q=${encodeURIComponent(q)}&mode=${mode}`),
  });
  return (
    <>
      <Titre
        surligne="EXPLORATION"
        titre="La bonne connaissance, au bon moment."
        texte="Retrouvez un passage exact ou explorez des procédures proches de votre situation."
      />
      <section className="panel search-panel">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            recherche.mutate();
          }}
        >
          <div className="segmented">
            <button
              type="button"
              className={mode === "texte" ? "selected" : ""}
              onClick={() => setMode("texte")}
            >
              <Search size={16} /> Texte exact
            </button>
            <button
              type="button"
              className={mode === "semantique" ? "selected" : ""}
              onClick={() => setMode("semantique")}
            >
              <Sparkles size={16} /> Sémantique locale
            </button>
          </div>
          <div className="search-row">
            <input
              aria-label="Votre recherche"
              required
              minLength={2}
              maxLength={500}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={
                mode === "texte"
                  ? "Ex. PostgreSQL, certificat, espace disque…"
                  : "Ex. Les requêtes attendent une connexion à la base…"
              }
            />
            <button className="btn primary" disabled={recherche.isPending}>
              {recherche.isPending ? (
                <LoaderCircle className="spin" size={18} />
              ) : (
                <Search size={18} />
              )}{" "}
              Rechercher
            </button>
          </div>
        </form>
        <p className="hint">
          La similarité indique une proximité de texte ; elle ne prouve pas
          qu’une procédure convient à votre incident.
        </p>
      </section>
      {recherche.error && <Erreur erreur={recherche.error} />}
      <div className="search-results">
        {recherche.data?.elements.map((r, i) => (
          <section className="panel search-result" key={i}>
            <div className="panel-heading">
              <Link
                to={
                  "/runbooks/" +
                  encodeURIComponent(r.nom || r.donnees?.fichier || "")
                }
              >
                <BookOpen size={18} />
                {r.titre || r.donnees?.fichier}
              </Link>
              {r.score !== undefined && (
                <span className="tag">SIMILARITÉ {r.score.toFixed(3)}</span>
              )}
            </div>
            <Markdown texte={r.extrait || r.donnees?.texte || ""} />
          </section>
        ))}
        {recherche.isSuccess && !recherche.data.elements.length && (
          <Vide
            titre="Aucun passage trouvé."
            texte="Essayez un terme plus large ou un autre mode de recherche."
          />
        )}
      </div>
    </>
  );
}
