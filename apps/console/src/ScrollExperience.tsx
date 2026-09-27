import { useContext, useEffect, useRef } from "react";
import {
  MotionPreference,
  useReducedMotionPreference,
} from "./motion-preferences";

const targets = [
  ".page-scene .page-title",
  ".page-scene .hero-panel",
  ".page-scene .panel",
  ".page-scene .stat-card",
  ".page-scene .mission-ribbon",
  ".page-scene .mission-card",
  ".page-scene .runbook-card",
  ".page-scene .readiness-check",
  ".page-scene .readiness-summary > button",
  ".page-scene .aura-stage",
  ".page-scene .voice-aside > *",
  ".page-scene .insight-heading",
  ".page-scene .architecture-journey-header",
  ".page-scene .architecture-connections-guide",
  ".page-scene .architecture-health",
  ".page-scene .architecture-boundary",
  ".landing-main > *",
  ".landing-principles > *",
].join(",");

/** Entry accents never hide content or change layout/focus. */
export function ScrollExperience({ routeKey }: { routeKey: string }) {
  const preference = useContext(MotionPreference);
  const reduced = useReducedMotionPreference();
  const progress = useRef<HTMLDivElement>(null);
  const enabled = preference && !reduced;
  useEffect(() => {
    if (
      !enabled ||
      typeof IntersectionObserver === "undefined" ||
      typeof HTMLElement.prototype.animate !== "function"
    )
      return;
    const watched = new Map<HTMLElement, boolean>();
    const animations = new Map<HTMLElement, Animation>();
    let previousY = window.scrollY;
    let direction = 1;
    let frame = 0;
    const cancel = (element: HTMLElement) => {
      animations.get(element)?.cancel();
      animations.delete(element);
    };
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const element = entry.target as HTMLElement;
          const wasVisible = watched.get(element);
          watched.set(element, entry.isIntersecting);
          if (!entry.isIntersecting) {
            cancel(element);
            continue;
          }
          if (
            wasVisible ||
            document.hidden ||
            element.contains(document.activeElement)
          )
            continue;
          cancel(element);
          const animation = element.animate(
            [
              {
                opacity: 0.4,
                transform: "translateY(" + direction * 18 + "px)",
              },
              { opacity: 1, transform: "translateY(0)" },
            ],
            { duration: 620, easing: "cubic-bezier(.22,1,.36,1)" },
          );
          animations.set(element, animation);
          const done = () => {
            if (animations.get(element) === animation)
              animations.delete(element);
          };
          animation.onfinish = done;
          animation.oncancel = done;
        }
      },
      { threshold: 0.08, rootMargin: "0px 0px -12px 0px" },
    );
    const collect = () => {
      for (const element of watched.keys()) {
        if (!element.isConnected) {
          observer.unobserve(element);
          watched.delete(element);
          cancel(element);
        }
      }
      for (const element of document.querySelectorAll<HTMLElement>(targets)) {
        if (watched.size >= 120) break;
        // Nested panels remain part of their parent's single entrance accent.
        if (watched.has(element) || element.parentElement?.closest(targets))
          continue;
        watched.set(element, false);
        observer.observe(element);
      }
    };
    const updateProgress = () => {
      frame = 0;
      if (document.hidden) return;
      const y = window.scrollY;
      if (y !== previousY) direction = y > previousY ? 1 : -1;
      previousY = y;
      const range = document.documentElement.scrollHeight - window.innerHeight;
      progress.current?.style.setProperty(
        "--page-progress",
        String(range > 0 ? Math.max(0, Math.min(1, y / range)) : 0),
      );
    };
    const scroll = () => {
      if (!frame && !document.hidden)
        frame = requestAnimationFrame(updateProgress);
    };
    const focus = () => {
      for (const element of animations.keys())
        if (element.contains(document.activeElement)) cancel(element);
    };
    const visibility = () => {
      if (document.hidden) {
        if (frame) cancelAnimationFrame(frame);
        frame = 0;
        for (const element of animations.keys()) cancel(element);
      } else updateProgress();
    };
    const mutation = new MutationObserver(collect);
    mutation.observe(document.getElementById("root") ?? document.body, {
      childList: true,
      subtree: true,
    });
    collect();
    updateProgress();
    window.addEventListener("scroll", scroll, { passive: true });
    window.addEventListener("resize", scroll, { passive: true });
    document.addEventListener("focusin", focus);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      observer.disconnect();
      mutation.disconnect();
      if (frame) cancelAnimationFrame(frame);
      for (const element of animations.keys()) cancel(element);
      watched.clear();
      window.removeEventListener("scroll", scroll);
      window.removeEventListener("resize", scroll);
      document.removeEventListener("focusin", focus);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [enabled, routeKey]);
  return enabled ? (
    <div className="scroll-progress" ref={progress} aria-hidden="true" />
  ) : null;
}
