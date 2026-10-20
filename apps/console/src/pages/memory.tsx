import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Database, Link2, Plus, Search, Trash2 } from "lucide-react";
import { api, date } from "../api";
import { t, useI18n } from "../i18n";
import { Chargement, Erreur, Modal, Titre } from "../ui";

type Note = {
  id: string;
  titre: string;
  contenu: string;
  source: string;
  scope: string;
  type: "fact" | "decision" | "question" | "preference";
  maj_le: string;
};
const empty = {
  titre: "",
  contenu: "",
  source: "",
  type: "fact" as Note["type"],
};

export default function Memory() {
  useI18n();
  const cache = useQueryClient();
  const navigate = useNavigate();
  const [scope, setScope] = useState("personal");
  const [search, setSearch] = useState("");
  const [form, setForm] = useState(false),
    [draft, setDraft] = useState(empty);
  const [selected, setSelected] = useState<Note | null>(null),
    [remove, setRemove] = useState<Note | null>(null);
  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<Error | null>(null);
  const validScope = /^[a-z0-9][a-z0-9_-]{0,63}$/.test(scope);
  const status = useQuery({
    queryKey: ["memory-status"],
    queryFn: ({ signal }) =>
      api<{ ready: boolean; notes: number | null }>(
        "/memoire/statut",
        "GET",
        undefined,
        signal,
      ),
    retry: false,
  });
  const notes = useQuery({
    queryKey: ["memory", scope, search],
    enabled: validScope && !!status.data?.ready,
    queryFn: ({ signal }) =>
      api<{ notes: Note[]; limit: number }>(
        `/memoire?scope=${encodeURIComponent(scope)}&recherche=${encodeURIComponent(search)}`,
        "GET",
        undefined,
        signal,
      ),
    retry: false,
  });
  const links = useQuery({
    queryKey: ["memory-links", selected?.id, scope],
    enabled: !!selected,
    queryFn: ({ signal }) =>
      api<{ liens: string[] }>(
        `/memoire/${selected!.id}?scope=${encodeURIComponent(scope)}`,
        "GET",
        undefined,
        signal,
      ),
    retry: false,
  });
  async function mutate(action: () => Promise<unknown>, finish: () => void) {
    setBusy(true);
    setError(null);
    try {
      await action();
      finish();
      await cache.invalidateQueries({
        predicate: (query) => String(query.queryKey[0]).startsWith("memory"),
      });
    } catch (cause) {
      setError(cause as Error);
    } finally {
      setBusy(false);
    }
  }
  async function discuss(note: Note) {
    let conversation: { id: string } | undefined;
    try {
      conversation = await api<{ id: string }>("/conversations", "POST", {
        titre: note.titre.slice(0, 100),
      });
      await api(`/conversations/${conversation.id}/memoire`, "POST", {
        scope: note.scope,
        identifiant: note.id,
      });
      navigate(`/assistant?conversation=${conversation.id}`);
    } catch (cause) {
      if (conversation)
        await api(`/conversations/${conversation.id}`, "DELETE").catch(
          () => {},
        );
      throw cause;
    }
  }
  return (
    <>
      <Titre
        surligne={t("LOCAL GRAPH MEMORY")}
        titre={t("Keep useful context connected.")}
        texte={t(
          "Capture decisions, observations and open questions in your dedicated Neo4j memory. Every note has a source and an explicit scope.",
        )}
        children={
          <button
            className="btn primary"
            disabled={!status.data?.ready || !validScope}
            onClick={() => {
              setError(null);
              setForm(true);
            }}
          >
            <Plus size={16} />
            {t("Add memory note")}
          </button>
        }
      />
      <section className="panel memory-boundary">
        <Database size={22} />
        <div>
          <strong>
            {status.data?.ready
              ? t("Dedicated Neo4j connected")
              : t("Dedicated Neo4j unavailable")}
          </strong>
          <p>
            {t(
              "Notes are operator context, not verified evidence or execution permissions. Scope filters prevent accidental mixing; use separate platform instances for separate clients.",
            )}
          </p>
          {!status.data?.ready && (
            <code>
              uv run --locked --project apps/control-api python -m
              plateforme.installer_memoire
            </code>
          )}
        </div>
      </section>
      {error && !form && !selected && !remove && <Erreur erreur={error} />}
      {status.error && <Erreur erreur={status.error} />}
      <div className="memory-controls">
        <label>
          {t("Memory scope")}
          <input
            value={scope}
            maxLength={64}
            pattern="[a-z0-9][a-z0-9_\-]{0,63}"
            onChange={(event) => {
              setScope(event.target.value);
              setSelected(null);
              setTarget("");
            }}
          />
        </label>
        <label>
          <Search size={16} />
          {t("Search memory")}
          <input
            value={search}
            maxLength={200}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
      </div>
      {!validScope && (
        <p role="alert">
          {t(
            "Use lowercase letters, digits, underscores or hyphens for a scope.",
          )}
        </p>
      )}
      {notes.error ? (
        <Erreur erreur={notes.error} />
      ) : notes.isFetching ? (
        <Chargement />
      ) : (
        <div className="memory-grid">
          {notes.data?.notes.map((note) => (
            <article className="panel" key={note.id}>
              <div className="memory-note-header">
                <span className="tag">
                  {t(
                    note.type === "fact"
                      ? "Observation"
                      : note.type === "decision"
                        ? "Decision"
                        : note.type === "question"
                          ? "Open question"
                          : "Preference",
                  )}
                </span>
                <button
                  className="icon-button"
                  aria-label={t("Delete memory note {name}", {
                    name: note.titre,
                  })}
                  onClick={() => {
                    setError(null);
                    setRemove(note);
                  }}
                >
                  <Trash2 size={16} />
                </button>
              </div>
              <h2>{note.titre}</h2>
              <p className="memory-content">{note.contenu}</p>
              <p className="hint">
                {t("Source")}: {note.source}
              </p>
              <time>{date(note.maj_le)}</time>
              <button
                className="text-button"
                onClick={() => {
                  setError(null);
                  setSelected(note);
                  setTarget("");
                }}
              >
                <Link2 size={16} />
                {t("View and connect context")}
              </button>
            </article>
          ))}
        </div>
      )}
      {notes.data?.notes.length === 0 && (
        <p>
          {t(
            "No notes in this scope yet. Add a sourced observation or a decision worth keeping.",
          )}
        </p>
      )}
      {notes.data && (
        <p className="hint">
          {t(
            "At most 100 matching notes are shown. Narrow your search to find older context.",
          )}
        </p>
      )}
      {form && (
        <Modal
          titre={t("Add memory note")}
          fermer={() => {
            if (!busy) setForm(false);
          }}
        >
          {error && <Erreur erreur={error} />}
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void mutate(
                () => api("/memoire", "POST", { ...draft, scope }),
                () => {
                  setForm(false);
                  setDraft(empty);
                },
              );
            }}
          >
            <p>
              {t("Memory scope")}: <strong>{scope}</strong>
            </p>
            <label>
              {t("Title")}
              <input
                required
                maxLength={120}
                value={draft.titre}
                onChange={(event) =>
                  setDraft({ ...draft, titre: event.target.value })
                }
              />
            </label>
            <label>
              {t("Note type")}
              <select
                value={draft.type}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    type: event.target.value as Note["type"],
                  })
                }
              >
                <option value="fact">{t("Observation")}</option>
                <option value="decision">{t("Decision")}</option>
                <option value="question">{t("Open question")}</option>
                <option value="preference">{t("Preference")}</option>
              </select>
            </label>
            <label>
              {t("Context")}
              <textarea
                required
                maxLength={4000}
                rows={7}
                value={draft.contenu}
                onChange={(event) =>
                  setDraft({ ...draft, contenu: event.target.value })
                }
              />
            </label>
            <label>
              {t("Source")}
              <input
                required
                maxLength={500}
                value={draft.source}
                onChange={(event) =>
                  setDraft({ ...draft, source: event.target.value })
                }
              />
            </label>
            <p className="hint">
              {t(
                "Record a document reference, an analysis ID or the origin of this observation. Do not store passwords or credentials.",
              )}
            </p>
            <button className="btn primary" disabled={busy}>
              {t("Save note")}
            </button>
          </form>
        </Modal>
      )}
      {selected && (
        <Modal
          titre={selected.titre}
          fermer={() => {
            if (!busy) setSelected(null);
          }}
        >
          {error && <Erreur erreur={error} />}
          <p className="memory-content">{selected.contenu}</p>
          <button
            className="btn primary"
            disabled={busy}
            onClick={() =>
              void mutate(
                () => discuss(selected),
                () => setSelected(null),
              )
            }
          >
            {t("Use this context with AURA")}
          </button>
          <h3>{t("Connected context")}</h3>
          {links.error ? (
            <Erreur erreur={links.error} />
          ) : links.isPending ? (
            <Chargement />
          ) : (
            <ul>
              {links.data.liens.map((id) => (
                <li key={id}>
                  {notes.data?.notes.find((item) => item.id === id)?.titre ||
                    id}
                </li>
              ))}
            </ul>
          )}
          <label>
            {t("Connect another note")}
            <select
              aria-label={t("Connect another note")}
              value={target}
              onChange={(event) => setTarget(event.target.value)}
            >
              <option value="">{t("Select a note")}</option>
              {notes.data?.notes
                .filter((note) => note.id !== selected.id)
                .map((note) => (
                  <option key={note.id} value={note.id}>
                    {note.titre}
                  </option>
                ))}
            </select>
          </label>
          <button
            className="btn"
            disabled={!target || busy}
            onClick={() =>
              void mutate(
                () =>
                  api("/memoire/liens", "POST", {
                    scope,
                    origine: selected.id,
                    destination: target,
                  }),
                () => setTarget(""),
              )
            }
          >
            <Link2 size={16} />
            {t("Connect notes")}
          </button>
        </Modal>
      )}
      {remove && (
        <Modal
          titre={t("Delete memory note")}
          fermer={() => {
            if (!busy) setRemove(null);
          }}
        >
          {error && <Erreur erreur={error} />}
          <p>
            {t(
              "Delete this note and its graph links? Conversation copies and backups have separate retention.",
            )}
          </p>
          <strong>{remove.titre}</strong>
          <button
            className="btn danger"
            disabled={busy}
            onClick={() =>
              void mutate(
                () =>
                  api(
                    `/memoire/${remove.id}?scope=${encodeURIComponent(remove.scope)}`,
                    "DELETE",
                  ),
                () => setRemove(null),
              )
            }
          >
            {t("Delete note")}
          </button>
        </Modal>
      )}
    </>
  );
}
