import { t, useI18n } from "./i18n";
import { BrandGlyph } from "./BrandMark";
import {
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type RefObject,
} from "react";
import { useInView } from "motion/react";
import {
  MotionPreference,
  useReducedMotionPreference,
} from "./motion-preferences";
import { signalPath, type SignalReader } from "./audio-signal";

export type CorePhase =
  "idle" | "listening" | "thinking" | "speaking" | "loading";
export function NeuralCore({
  phase = "idle",
  signal,
  compact = false,
}: {
  phase?: CorePhase;
  signal?: RefObject<SignalReader | null>;
  compact?: boolean;
}) {
  useI18n();
  const ref = useRef<HTMLDivElement>(null);
  const trace = useRef<SVGPathElement>(null);
  const visible = useInView(ref, { margin: "60px" });
  const preference = useContext(MotionPreference);
  const reduced = useReducedMotionPreference();
  const [foreground, setForeground] = useState(!document.hidden);
  const id = useId().replace(/[^a-zA-Z0-9]/g, "");
  const enabled = preference && !reduced && foreground && visible;
  useEffect(() => {
    const update = () => setForeground(!document.hidden);
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);
  useEffect(() => {
    const element = ref.current;
    const path = trace.current;
    if (!element || !path) return;
    element.style.setProperty("--signal", "0");
    element.dataset.signal = "idle";
    path.setAttribute("d", signalPath());
    if (!enabled || (phase !== "speaking" && phase !== "listening")) return;
    let frame = 0,
      last = 0;
    const draw = (time: number) => {
      if (time - last >= 1000 / 30) {
        last = time;
        const data = signal?.current?.();
        element.dataset.signal = data ? "measured" : "unavailable";
        element.style.setProperty("--signal", String(data?.level || 0));
        path.setAttribute("d", signalPath(data?.samples));
      }
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [enabled, phase, signal]);
  return (
    <div
      ref={ref}
      className={"neural-core " + (compact ? "core-compact" : "")}
      data-phase={phase}
      data-resting={!enabled}
      aria-hidden="true"
    >
      <div className="core-halo" />
      <svg className="core-instrument" viewBox="0 0 512 512" fill="none">
        <defs>
          <radialGradient id={id + "glow"}>
            <stop stopColor="#b5ffff" stopOpacity=".22" />
            <stop offset=".55" stopColor="#30b8dd" stopOpacity=".06" />
            <stop offset="1" stopColor="#30b8dd" stopOpacity="0" />
          </radialGradient>
          <radialGradient id={id + "lens"} cx=".3" cy=".25">
            <stop stopColor="#327c87" />
            <stop offset=".5" stopColor="#122f44" />
            <stop offset="1" stopColor="#071821" />
          </radialGradient>
        </defs>
        <g className="core-heartbeat">
          <circle cx="256" cy="256" r="250" fill={`url(#${id}glow)`} />
          <circle className="core-pulse-ring" cx="256" cy="256" r="116" />
        </g>
        {/* Decorative breathing stays independent of measured microphone/voice energy. */}
        <g className="core-waves">
          <circle cx="256" cy="256" r="126" />
          <circle cx="256" cy="256" r="126" />
        </g>
        <g className="core-grid">
          <path d="M256 17v75m0 328v75M17 256h75m328 0h75M85 85l43 43m256 256 43 43M85 427l43-43m256-256 43-43" />
          <circle cx="256" cy="256" r="237" />
          <circle cx="256" cy="256" r="177" />
        </g>
        <g className="core-ticks">
          {Array.from({ length: 72 }, (_, index) => (
            <path
              key={index}
              transform={`rotate(${index * 5} 256 256)`}
              d={`M256 32v${index % 6 === 0 ? 13 : 4}`}
              opacity={index % 6 === 0 ? 0.85 : 0.35}
            />
          ))}
        </g>
        <g className="core-track track-one">
          <circle
            cx="256"
            cy="256"
            r="205"
            strokeDasharray="120 22 2 22 40 18"
          />
          <path d="M256 51a205 205 0 0 1 177 103" strokeWidth="3" />
          <circle cx="256" cy="51" r="4" fill="currentColor" />
        </g>
        <g className="core-track track-two">
          <circle cx="256" cy="256" r="164" strokeDasharray="2 7" />
          <path
            d="M92 256a164 164 0 0 1 164-164m164 164a164 164 0 0 1-164 164"
            strokeWidth="2"
          />
        </g>
        <g className="core-lattice">
          <ellipse
            cx="256"
            cy="256"
            rx="146"
            ry="51"
            transform="rotate(-28 256 256)"
          />
          <ellipse
            cx="256"
            cy="256"
            rx="146"
            ry="51"
            transform="rotate(65 256 256)"
          />
          <ellipse
            cx="256"
            cy="256"
            rx="146"
            ry="51"
            transform="rotate(155 256 256)"
          />
        </g>
        <path ref={trace} className="core-signal" d={signalPath()} />
        <g className="core-lens">
          <circle cx="256" cy="256" r="84" fill={`url(#${id}lens)`} />
          <circle cx="256" cy="256" r="77" />
          <g transform="translate(194 194) scale(1.3)">
            <BrandGlyph />
          </g>
          <circle cx="256" cy="256" r="93" strokeDasharray="3 8" />
        </g>
        <g className="core-points">
          <circle cx="110" cy="168" r="3" />
          <circle cx="408" cy="348" r="3" />
          <circle cx="334" cy="113" r="2" />
          <circle cx="178" cy="402" r="2" />
        </g>
      </svg>
      <span className="core-cross cross-north">+</span>
      <span className="core-cross cross-south">+</span>
      <div className="core-label-top">
        <span>AMBICRAFTED</span>
        <b>{t("NEURAL INTERFACE")}</b>
      </div>
      <div className="core-label-bottom">
        <i />
        {
          {
            idle: t("LOCAL INTELLIGENCE"),
            listening: t("Listening"),
            thinking: t("Thinking"),
            speaking: t("Speaking"),
            loading: t("Loading"),
          }[phase]
        }
      </div>
    </div>
  );
}
