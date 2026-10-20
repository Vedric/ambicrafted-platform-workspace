import { t, useI18n, number, countLabel } from "../i18n";
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
  useI18n();
  const [recherche, setRecherche] = useState("");
  const q = useQuery({
    queryKey: ["runbooks", recherche],
    queryFn: () =>
      api<Runbook[]>("/runbooks?recherche=" + encodeURIComponent(recherche)),
  });
  return (
    <>
      <Titre
        surligne={t("OPERATIONAL KNOWLEDGE")}
        titre="Runbooks"
        texte={t(
          "Give your agents clear procedures and evidence they can trace.",
        )}
      >
        <Link className="btn primary" to="/runbooks/nouveau">
          <Plus size={17} /> {t("New runbook")}
        </Link>
      </Titre>
      <div className="notice inline-notice">
        <Database size={19} />
        <span>
          {t("Reindex after editing a runbook to refresh semantic search.")}
        </span>
        <Link to="/operations">
          {t("Reindex runbooks")} <ArrowRight size={14} />
        </Link>
      </div>
      <div className="toolbar standalone">
        <div className="search-input">
          <Search size={17} />
          <input
            aria-label={t("Search runbooks")}
            placeholder={t("Search procedures…")}
            value={recherche}
            onChange={(e) => setRecherche(e.target.value)}
          />
        </div>
        <span className="muted tiny">
          {q.data ? countLabel(q.data.length, "document") : "—"}
        </span>
      </div>
      {q.isPending ? (
        <Chargement />
      ) : q.error ? (
        <Erreur erreur={q.error} />
      ) : !q.data?.length ? (
        <Vide
          titre={t("No runbooks found")}
          texte={t("Add a procedure or try a different search.")}
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
                <span>
                  {t("{count} kB", {
                    count: number(r.octets / 1000, {
                      minimumFractionDigits: 1,
                      maximumFractionDigits: 1,
                    }),
                  })}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
export function Editeur() {
  useI18n();
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
      notifier(t("Runbook saved. Reindex to refresh semantic search."));
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
        <ArrowLeft size={15} /> Runbooks
      </Link>
      <Titre
        surligne={nouveau ? t("NEW RUNBOOK") : "RUNBOOK"}
        titre={nouveau ? t("Create a runbook") : q.data?.titre || nom!}
        texte={t(
          "Write a clear, actionable procedure. You decide when it applies.",
        )}
      >
        <button className="btn" onClick={() => setEdition(!edition)}>
          {edition ? <BookOpen size={16} /> : <FileText size={16} />}{" "}
          {edition ? t("Preview") : t("Edit")}
        </button>
        <button
          className="btn primary"
          onClick={() => sauver.mutate()}
          disabled={
            sauver.isPending || !contenu.trim() || (nouveau && !nomFichier)
          }
        >
          <Check size={17} /> {t("Save runbook")}
        </button>
      </Titre>
      {sauver.error && <Erreur erreur={sauver.error} />}
      <section className="panel editor-panel">
        {nouveau && (
          <div className="field">
            <label htmlFor="nom-runbook">{t("File name")}</label>
            <input
              id="nom-runbook"
              placeholder="my-procedure.md"
              pattern="[a-zA-Z0-9][a-zA-Z0-9_\-]*\.md"
              value={nomFichier}
              onChange={(e) => setNom(e.target.value)}
            />
          </div>
        )}
        {edition ? (
          <>
            <label htmlFor="contenu-runbook">{t("Markdown content")}</label>
            <textarea
              id="contenu-runbook"
              className="code-editor"
              rows={24}
              maxLength={8000}
              value={contenu}
              placeholder={t(
                "# Procedure title\n\n## Symptoms\n\n## Prerequisites\n\n## Diagnosis\n\n## Actions and conditions\n\n## Validation and rollback",
              )}
              onChange={(e) => setContenu(e.target.value)}
            />
            <div className="field-foot">
              <span>{t("Only the operator can edit runbooks.")}</span>
              <span>
                {t("{count} / 8,000", { count: number(contenu.length) })}
              </span>
            </div>
          </>
        ) : (
          <Markdown
            texte={contenu || t("Start writing a procedure in the editor.")}
          />
        )}
      </section>
      {empreinte && (
        <p className="mono tiny muted break-all">
          {t("SHA-256 ·")} {empreinte}
        </p>
      )}
    </>
  );
}
export function Recherche() {
  useI18n();
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
        titre={t("Find the right guidance.")}
        texte={t(
          "Find an exact passage or explore procedures related to your situation.",
        )}
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
              <Search size={16} /> {t("Exact text")}
            </button>
            <button
              type="button"
              className={mode === "semantique" ? "selected" : ""}
              onClick={() => setMode("semantique")}
            >
              <Sparkles size={16} /> {t("Local semantic search")}
            </button>
          </div>
          <div className="search-row">
            <input
              aria-label={t("Search query")}
              required
              minLength={2}
              maxLength={500}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={
                mode === "texte"
                  ? t("e.g. PostgreSQL, certificate, disk space…")
                  : t("e.g. Requests are waiting for a database connection…")
              }
            />
            <button className="btn primary" disabled={recherche.isPending}>
              {recherche.isPending ? (
                <LoaderCircle className="spin" size={18} />
              ) : (
                <Search size={18} />
              )}{" "}
              {t("Search")}
            </button>
          </div>
        </form>
        <p className="hint">
          {t(
            "Similarity measures related text. Review each procedure before applying it to your incident.",
          )}
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
                <span className="tag">
                  {t("SIMILARITY")}{" "}
                  {number(r.score, {
                    minimumFractionDigits: 3,
                    maximumFractionDigits: 3,
                  })}
                </span>
              )}
            </div>
            <Markdown texte={r.extrait || r.donnees?.texte || ""} />
          </section>
        ))}
        {recherche.isSuccess && !recherche.data.elements.length && (
          <Vide
            titre={t("No matching passages")}
            texte={t("Try a broader term or switch search modes.")}
          />
        )}
      </div>
    </>
  );
}
