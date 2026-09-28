import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import {
  FileText,
  History,
  Image,
  Paperclip,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";
import Assistant, { type Message } from "./Assistant";
import { api, date, savedDialogue } from "./api";
import { t, useI18n } from "./i18n";
import { Chargement, Erreur, Modal } from "./ui";

type Attachment = {
  id: string;
  nom: string;
  kind: "text" | "image";
  truncated: boolean;
  characters?: number;
};
type Thread = {
  id: string;
  titre: string;
  maj_le: string;
  messages: Message[];
  total_messages: number;
  pieces: Attachment[];
};

export default function ConversationWorkspace() {
  useI18n();
  const client = useQueryClient();
  const [parameters] = useSearchParams();
  const [history, setHistory] = useState(false),
    [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [thread, setThread] = useState<Thread | null>(null);
  const [viewKey, setViewKey] = useState(() => crypto.randomUUID());
  const [selected, setSelected] = useState<string[]>([]);
  const [loading, setLoading] = useState(false),
    [error, setError] = useState<Error | null>(null);
  const [deleting, setDeleting] = useState<Thread | null>(null);
  const current = useRef<Thread | null>(null);
  const drafts = useRef(new Map<string, string>());
  const pending = useRef<Promise<Thread> | null>(null);
  const version = useRef(0);
  const file = useRef<HTMLInputElement>(null);
  const lastOperation = useRef<{
    text: string;
    id: string;
    conversation: string;
    pieces: string;
    language: string;
    vocal: boolean;
  } | null>(null);
  const controller = useRef<AbortController | null>(null);
  const list = useQuery({
    queryKey: ["conversations", search, page],
    queryFn: ({ signal }) =>
      api<{ elements: Thread[]; total: number }>(
        `/conversations?recherche=${encodeURIComponent(search)}&page=${page}`,
        "GET",
        undefined,
        signal,
      ),
    enabled: history,
    retry: false,
  });
  useEffect(
    () => () => {
      version.current++;
      controller.current?.abort();
    },
    [],
  );
  useEffect(() => {
    const id = parameters.get("conversation");
    if (id && /^[a-f0-9-]{36}$/.test(id)) void open(id);
  }, [parameters]);

  function reset() {
    version.current++;
    controller.current?.abort();
    current.current = null;
    pending.current = null;
    lastOperation.current = null;
    setThread(null);
    setSelected([]);
    setError(null);
    setLoading(false);
    setViewKey(crypto.randomUUID());
  }
  async function ensure(signal?: AbortSignal): Promise<Thread> {
    if (current.current) return current.current;
    if (pending.current) return pending.current;
    const generation = version.current;
    pending.current = api<Thread>("/conversations", "POST", {}, signal)
      .then((created) => {
        if (generation !== version.current)
          throw new DOMException("Cancelled", "AbortError");
        current.current = created;
        setThread(created);
        void client.invalidateQueries({ queryKey: ["conversations"] });
        return created;
      })
      .finally(() => {
        if (generation === version.current) pending.current = null;
      });
    return pending.current;
  }
  async function open(id: string) {
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    setLoading(true);
    setError(null);
    try {
      const loaded = await api<Thread>(
        `/conversations/${id}`,
        "GET",
        undefined,
        request.signal,
      );
      if (request.signal.aborted) return;
      version.current++;
      current.current = loaded;
      pending.current = null;
      lastOperation.current = null;
      setThread(loaded);
      setSelected(
        loaded.total_messages === 0
          ? loaded.pieces.map((piece) => piece.id)
          : [],
      );
      setViewKey(crypto.randomUUID());
      setHistory(false);
    } catch (cause) {
      if (!request.signal.aborted) setError(cause as Error);
    } finally {
      if (!request.signal.aborted) setLoading(false);
    }
  }
  async function upload(attachment: File) {
    if (attachment.size > 8 * 1024 * 1024) {
      setError(new Error(t("Each attachment must be at most 8 MiB.")));
      return;
    }
    setLoading(true);
    setError(null);
    const generation = version.current;
    const request = new AbortController();
    controller.current = request;
    try {
      const active = await ensure(request.signal);
      const content = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onerror = () =>
          reject(new Error(t("The file could not be read.")));
        reader.onload = () =>
          resolve(String(reader.result).split(",")[1] || "");
        reader.readAsDataURL(attachment);
      });
      if (generation !== version.current) return;
      const added = await api<Attachment>(
        `/conversations/${active.id}/pieces`,
        "POST",
        { nom: attachment.name, contenu: content },
        request.signal,
      );
      if (generation !== version.current) return;
      const next = { ...active, pieces: [...active.pieces, added] };
      current.current = next;
      setThread(next);
      setSelected((previous) => [...previous, added.id]);
    } catch (cause) {
      if (generation === version.current && !request.signal.aborted)
        setError(cause as Error);
    } finally {
      if (generation === version.current) setLoading(false);
      if (file.current) file.current.value = "";
    }
  }
  async function remove(attachment: Attachment) {
    if (!current.current) return;
    const active = current.current,
      generation = version.current;
    setLoading(true);
    setError(null);
    try {
      await api(
        `/conversations/${active.id}/pieces/${attachment.id}`,
        "DELETE",
      );
      if (generation !== version.current) return;
      const next = {
        ...active,
        pieces: active.pieces.filter((item) => item.id !== attachment.id),
      };
      current.current = next;
      setThread(next);
      setSelected((previous) => previous.filter((id) => id !== attachment.id));
    } catch (cause) {
      if (generation === version.current) setError(cause as Error);
    } finally {
      if (generation === version.current) setLoading(false);
    }
  }

  return (
    <>
      <div className="conversation-toolbar">
        <button className="btn" onClick={() => setHistory(true)}>
          <History size={17} />
          {t("Conversation history")}
        </button>
        <span>
          {thread?.titre && thread.titre !== "New conversation"
            ? thread.titre
            : t("New conversation")}
        </span>
        <span className="tag">{t("SAVED LOCALLY")}</span>
      </div>
      {error && <Erreur erreur={error} />}
      {thread && thread.total_messages > 100 && (
        <p className="hint">
          {t(
            "Showing the latest 100 messages. AURA receives only a bounded recent context.",
          )}
        </p>
      )}
      <Assistant
        key={viewKey}
        initialMessages={thread?.messages || []}
        externalBusy={loading}
        initialDraft={drafts.current.get(thread?.id || viewKey) || ""}
        onDraftChange={(draft) => {
          const key = current.current?.id || viewKey;
          if (draft) drafts.current.set(key, draft);
          else drafts.current.delete(key);
        }}
        onNew={reset}
        sendMessage={async (text, language, signal, onText, vocal = false) => {
          const generation = version.current;
          const active = await ensure(signal);
          const previous = lastOperation.current,
            pieces = JSON.stringify(selected);
          const retry =
            previous?.text === text &&
            previous.conversation === active.id &&
            previous.pieces === pieces &&
            previous.language === language;
          const operation = retry ? previous.id : crypto.randomUUID();
          // Retry the exact uncertain operation, including its reply mode. A
          // spoken turn retried via Send must not duplicate an already saved pair.
          const spoken = retry ? previous.vocal : vocal;
          lastOperation.current = {
            id: operation,
            text,
            conversation: active.id,
            pieces,
            language,
            vocal: spoken,
          };
          const result = await savedDialogue(
            active.id,
            {
              message: text,
              langue: language,
              ...(spoken ? { vocal: true } : {}),
              pieces: selected,
              operation_id: operation,
            },
            signal,
            onText,
          );
          if (generation === version.current) {
            lastOperation.current = null;
            const next = {
              ...current.current!,
              titre:
                active.titre === "New conversation"
                  ? text.slice(0, 80)
                  : active.titre,
              total_messages: active.total_messages + 2,
            };
            current.current = next;
            setThread(next);
            void client.invalidateQueries({ queryKey: ["conversations"] });
          }
          return result;
        }}
        composerExtra={
          <>
            <div className="attachment-toolbar">
              <button
                type="button"
                className="btn"
                disabled={loading || (thread?.pieces.length || 0) >= 8}
                onClick={() => file.current?.click()}
              >
                <Paperclip size={16} />
                {loading
                  ? t("Reading document…")
                  : t("Attach a document or image")}
              </button>
              <span className="hint">
                {t("8 MiB per file · up to 8 files · 2 images per message")}
              </span>
            </div>
            <input
              ref={file}
              type="file"
              hidden
              aria-label={t("Attach a document or image")}
              accept=".txt,.md,.csv,.json,.yaml,.yml,.log,.py,.ts,.tf,.sh,.xml,.pdf,.docx,.xlsx,.pptx,.png,.jpg,.jpeg,.webp"
              onChange={(event) => {
                const attachment = event.target.files?.[0];
                if (attachment) void upload(attachment);
              }}
            />
            {!!thread?.pieces.length && (
              <div className="attachment-list">
                {thread.pieces.map((attachment) => (
                  <div className="attachment-chip" key={attachment.id}>
                    <label>
                      <input
                        type="checkbox"
                        checked={selected.includes(attachment.id)}
                        disabled={loading}
                        onChange={(event) =>
                          setSelected((previous) =>
                            event.target.checked
                              ? [...previous, attachment.id]
                              : previous.filter((id) => id !== attachment.id),
                          )
                        }
                      />
                      {attachment.kind === "image" ? (
                        <Image size={17} />
                      ) : (
                        <FileText size={17} />
                      )}
                      <span>
                        {attachment.nom}
                        {attachment.truncated && (
                          <small>{t("Partial extraction")}</small>
                        )}
                      </span>
                    </label>
                    <button
                      type="button"
                      className="icon-button"
                      disabled={loading}
                      aria-label={t("Remove attachment {name}", {
                        name: attachment.nom,
                      })}
                      onClick={() => void remove(attachment)}
                    >
                      <X size={15} />
                    </button>
                  </div>
                ))}
              </div>
            )}
            <p className="hint">
              {t(
                "Select the sources to include in this message. Text, PDF, Word, Excel, PowerPoint and images stay local. Extracts are bounded; formulas and macros are never executed.",
              )}
            </p>
          </>
        }
      />
      {history && (
        <Modal
          titre={t("Conversation history")}
          fermer={() => setHistory(false)}
        >
          <p>
            {t(
              "Search your local messages. Conversations expire after 30 days without activity. Separate client environments remain necessary.",
            )}
          </p>
          <label className="history-search">
            <Search size={17} />
            <input
              aria-label={t("Search conversations")}
              value={search}
              maxLength={100}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
              placeholder={t("Search conversations")}
            />
          </label>
          <button
            className="btn"
            onClick={() => {
              reset();
              setHistory(false);
            }}
          >
            <Plus size={16} />
            {t("New conversation")}
          </button>
          {list.isPending ? (
            <Chargement />
          ) : list.error ? (
            <Erreur erreur={list.error} />
          ) : (
            <div className="history-list">
              {list.data.elements.length ? (
                list.data.elements.map((item) => (
                  <div key={item.id}>
                    <button
                      disabled={loading}
                      onClick={() => void open(item.id)}
                    >
                      <strong>{item.titre}</strong>
                      <time>{date(item.maj_le)}</time>
                    </button>
                    <button
                      className="icon-button"
                      aria-label={t("Delete conversation {name}", {
                        name: item.titre,
                      })}
                      onClick={() => {
                        setDeleting(item);
                        setHistory(false);
                      }}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))
              ) : (
                <p>{t("No saved conversations found.")}</p>
              )}
            </div>
          )}
          <div className="history-pagination">
            <button
              className="btn"
              disabled={page === 1}
              onClick={() => setPage(page - 1)}
            >
              {t("Previous")}
            </button>
            <span>{page}</span>
            <button
              className="btn"
              disabled={page * 50 >= (list.data?.total || 0)}
              onClick={() => setPage(page + 1)}
            >
              {t("Next")}
            </button>
          </div>
        </Modal>
      )}
      {deleting && (
        <Modal
          titre={t("Delete saved conversation")}
          fermer={() => setDeleting(null)}
        >
          <p>
            {t(
              "Delete this conversation and its extracted attachments from active storage? Existing backups have their own retention policy.",
            )}
          </p>
          <strong>{deleting.titre}</strong>
          <div className="modal-actions">
            <button className="btn" onClick={() => setDeleting(null)}>
              {t("Cancel")}
            </button>
            <button
              className="btn danger"
              disabled={loading}
              onClick={async () => {
                setLoading(true);
                try {
                  await api(`/conversations/${deleting.id}`, "DELETE");
                  if (current.current?.id === deleting.id) reset();
                  setDeleting(null);
                  void client.invalidateQueries({
                    queryKey: ["conversations"],
                  });
                } catch (cause) {
                  setError(cause as Error);
                } finally {
                  setLoading(false);
                }
              }}
            >
              {t("Delete conversation")}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
