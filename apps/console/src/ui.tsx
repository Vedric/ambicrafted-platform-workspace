import {
  createContext,
  useContext,
  useEffect,
  useRef,
  type ReactNode,
} from "react";
import {
  Bot,
  Database,
  ExternalLink,
  LoaderCircle,
  ShieldCheck,
  Triangle,
  Workflow,
  X,
  XCircle,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { statuts } from "./api";

export const ToastContext = createContext<
  (message: string, erreur?: boolean) => void
>(() => {});
export const useToast = () => useContext(ToastContext);
export function Erreur({
  erreur,
  recommencer,
}: {
  erreur: Error | null;
  recommencer?: () => void;
}) {
  return (
    <div className="error-box" role="alert">
      <XCircle size={20} />
      <div>
        <strong>Nous n’avons pas pu terminer cette action.</strong>
        <p>{erreur?.message || "Ressource indisponible."}</p>
        {recommencer && (
          <button className="btn small" onClick={recommencer}>
            Réessayer
          </button>
        )}
      </div>
    </div>
  );
}
export function Chargement() {
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" size={22} />
      <span>Chargement de votre espace…</span>
    </div>
  );
}
export function Vide({
  titre,
  texte,
  children,
}: {
  titre: string;
  texte: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Workflow size={28} />
      </div>
      <h3>{titre}</h3>
      <p>{texte}</p>
      {children}
    </div>
  );
}
export function Titre({
  surligne,
  titre,
  texte,
  children,
}: {
  surligne: string;
  titre: string;
  texte: string;
  children?: ReactNode;
}) {
  return (
    <div className="page-title">
      <div>
        <div className="eyebrow">{surligne}</div>
        <h1>{titre}</h1>
        <p>{texte}</p>
      </div>
      {children && <div className="title-actions">{children}</div>}
    </div>
  );
}
export function Badge({ statut }: { statut: string }) {
  return (
    <span className={"badge status-" + statut}>
      <i />
      {statuts[statut] || statut}
    </span>
  );
}
export function Markdown({ texte }: { texte: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          img: ({ alt }) => <span>{alt}</span>,
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
              <ExternalLink size={12} />
            </a>
          ),
        }}
      >
        {texte}
      </ReactMarkdown>
    </div>
  );
}
export function Modal({
  titre,
  children,
  fermer,
}: {
  titre: string;
  children: ReactNode;
  fermer: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
    ref.current
      ?.querySelector<HTMLInputElement>('input:not([type="checkbox"]),textarea')
      ?.focus();
    return () => ref.current?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      onCancel={fermer}
      onClick={(e) => {
        if (e.target === e.currentTarget) fermer();
      }}
      aria-label={titre}
    >
      <div className="modal-head">
        <h2>{titre}</h2>
        <button className="icon-button" onClick={fermer} aria-label="Fermer">
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}

export function Orbit({ petit = false }: { petit?: boolean }) {
  return (
    <div className={"orbit " + (petit ? "small-orbit" : "")} aria-hidden="true">
      <div className="orbit-grid" />
      <div className="orbit-ring ring-1" />
      <div className="orbit-ring ring-2" />
      <div className="orbit-ring ring-3" />
      <div className="orbit-center">
        <Triangle size={petit ? 42 : 72} />
      </div>
      <span className="satellite sat-1">
        <Database size={19} />
      </span>
      <span className="satellite sat-2">
        <Bot size={19} />
      </span>
      <span className="satellite sat-3">
        <ShieldCheck size={19} />
      </span>
      <div className="orbit-caption">
        <i />
        LOCAL INTELLIGENCE
      </div>
    </div>
  );
}
