import { t, useI18n, systemText } from "./i18n";
import {
  createContext,
  lazy,
  Suspense,
  useContext,
  useEffect,
  useRef,
  type ReactNode,
} from "react";
import { motion, useInView, useMotionValue, useSpring } from "motion/react";
import { LoaderCircle, Workflow, X, XCircle } from "lucide-react";
import { statuts } from "./api";
import {
  MotionPreference,
  useReducedMotionPreference,
} from "./motion-preferences";
import { NeuralCore } from "./NeuralCore";

export const ToastContext = createContext<
  (message: string, erreur?: boolean) => void
>(() => {});
export const useToast = () => useContext(ToastContext);
export {
  MotionPreference,
  useReducedMotionPreference,
} from "./motion-preferences";
export function Erreur({
  erreur,
  recommencer,
}: {
  erreur: Error | null;
  recommencer?: () => void;
}) {
  useI18n();
  return (
    <div className="error-box" role="alert">
      <XCircle size={20} />
      <div>
        <strong>{t("We couldn’t complete that action.")}</strong>
        <p>
          {erreur instanceof TypeError
            ? t(
                "The local API could not be reached. Check the connection and try again.",
              )
            : systemText(erreur?.message || t("This resource is unavailable."))}
        </p>
        {recommencer && (
          <button className="btn small" onClick={recommencer}>
            {t("Try again")}
          </button>
        )}
      </div>
    </div>
  );
}
export function Chargement() {
  useI18n();
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" size={22} />
      <span>{t("Preparing your workspace…")}</span>
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
  useI18n();
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
  useI18n();
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
  useI18n();
  return (
    <span className={"badge status-" + statut}>
      <i />
      {statuts[statut] || statut}
    </span>
  );
}
const MarkdownRenderer = lazy(() => import("./MarkdownRenderer"));
export function Markdown({ texte }: { texte: string }) {
  return (
    <Suspense fallback={<div className="markdown">{texte}</div>}>
      <MarkdownRenderer texte={texte} />
    </Suspense>
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
  useI18n();
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
        <button
          className="icon-button"
          onClick={fermer}
          aria-label={t("Close")}
        >
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}

export function Orbit({ petit = false }: { petit?: boolean }) {
  useI18n();
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
        <NeuralCore compact={petit} />
      </motion.div>
    </div>
  );
}
