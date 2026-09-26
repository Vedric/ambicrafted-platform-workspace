import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { motion, useInView, useMotionValue, useSpring } from "motion/react";
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
export const MotionPreference = createContext(true);
const reducedMotionQuery = "(prefers-reduced-motion: reduce)";
function subscribeToMotionPreference(notify: () => void) {
  const media = window.matchMedia?.(reducedMotionQuery);
  media?.addEventListener("change", notify);
  return () => media?.removeEventListener("change", notify);
}
export function useReducedMotionPreference() {
  return useSyncExternalStore(
    subscribeToMotionPreference,
    () => window.matchMedia?.(reducedMotionQuery).matches ?? false,
    () => true,
  );
}
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
        <strong>We couldn’t complete that action.</strong>
        <p>
          {erreur instanceof TypeError
            ? "The local API could not be reached. Check the connection and try again."
            : erreur?.message || "This resource is unavailable."}
        </p>
        {recommencer && (
          <button className="btn small" onClick={recommencer}>
            Try again
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
      <span>Preparing your workspace…</span>
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
    const dialog = ref.current;
    const previousFocus = document.activeElement;
    dialog?.showModal();
    dialog
      ?.querySelector<HTMLInputElement>('input:not([type="checkbox"]),textarea')
      ?.focus();
    return () => {
      dialog?.close();
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected)
        previousFocus.focus({ preventScroll: true });
    };
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
        <button className="icon-button" onClick={fermer} aria-label="Close">
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}

export function Orbit({ petit = false }: { petit?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const visible = useInView(ref, { margin: "80px" });
  const preference = useContext(MotionPreference);
  const reduced = useReducedMotionPreference();
  const enabled = preference && !reduced;
  const x = useMotionValue(0),
    y = useMotionValue(0);
  const rotateX = useSpring(x, { stiffness: 90, damping: 24 });
  const rotateY = useSpring(y, { stiffness: 90, damping: 24 });
  useEffect(() => {
    if (!enabled) {
      x.jump(0);
      y.jump(0);
      rotateX.jump(0);
      rotateY.jump(0);
    }
  }, [enabled, x, y, rotateX, rotateY]);
  return (
    <div
      ref={ref}
      className={"orbit " + (petit ? "small-orbit" : "")}
      aria-hidden="true"
      data-resting={!visible || !enabled}
      onPointerMove={(event) => {
        if (!enabled || event.pointerType !== "mouse") return;
        const rect = event.currentTarget.getBoundingClientRect();
        x.set(-((event.clientY - rect.top) / rect.height - 0.5) * 12);
        y.set(((event.clientX - rect.left) / rect.width - 0.5) * 12);
      }}
      onPointerLeave={() => {
        x.set(0);
        y.set(0);
      }}
    >
      <motion.div
        className="orbit-scene"
        style={{
          rotateX: enabled ? rotateX : 0,
          rotateY: enabled ? rotateY : 0,
        }}
      >
        <div className="orbit-grid" />
        <div className="orbit-aura" />
        <svg className="orbit-wireframe" viewBox="0 0 520 520" fill="none">
          <path d="M86 178 260 100 434 178v165L260 421 86 343Z" />
          <path d="m86 178 174 82 174-82M260 260v161M260 100v160M86 343l174-83 174 83" />
          <circle cx="260" cy="260" r="214" strokeDasharray="2 12" />
        </svg>
        <div className="orbit-ring ring-1" />
        <div className="orbit-ring ring-2" />
        <div className="orbit-ring ring-3" />
        <div className="orbit-particle particle-one" />
        <div className="orbit-particle particle-two" />
        <div className="orbit-center">
          <div className="core-facet" />
          <Triangle size={petit ? 42 : 72} />
          <span className="core-label">LOCAL CORE</span>
        </div>
        <span className="satellite sat-1">
          <span className="satellite-icon">
            <Database size={19} />
          </span>
          <span className="satellite-copy">
            <small>01 / OBSERVE</small>
            <strong>Signals into context</strong>
          </span>
        </span>
        <span className="satellite sat-2">
          <span className="satellite-icon">
            <Bot size={19} />
          </span>
          <span className="satellite-copy">
            <small>02 / REASON</small>
            <strong>Evidence, connected</strong>
          </span>
        </span>
        <span className="satellite sat-3">
          <span className="satellite-icon">
            <ShieldCheck size={19} />
          </span>
          <span className="satellite-copy">
            <small>03 / REVIEW</small>
            <strong>Your decision, always</strong>
          </span>
        </span>
        <div className="orbit-caption">
          <i />A PRIVATE INTELLIGENCE SYSTEM
        </div>
      </motion.div>
    </div>
  );
}
