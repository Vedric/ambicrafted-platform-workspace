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
  ".page-scene .guide-step",
  ".page-scene .guide-video",
  ".page-scene .guide-flow",
  ".page-scene .guide-faq > details",
  ".page-scene [data-reveal]",
  ".landing-main > *",
  ".landing-principles > *",
  ".landing-updates > *",
  ".landing-guide-link",
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
    let pointerActive = false;
    let pointerEnd = 0;
    const pointerAnimations = new Set<HTMLElement>();
    const cancel = (element: HTMLElement) => {
      animations.get(element)?.cancel();
      animations.delete(element);
      element.dataset.revealState = "visible";
    };
    const observer = new IntersectionObserver(
      (entries) => {
        let stagger = 0;
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
          element.dataset.revealState = "entering";
          element.dataset.revealDirection = direction > 0 ? "down" : "up";
          // Keep observed geometry stable. Translating a card across the
          // viewport edge can retrigger its own observer indefinitely and make
          // controls jitter, especially below the fold on mobile.
          const animation = element.animate(
            [{ opacity: 0.12 }, { opacity: 1 }],
            {
              duration: 520,
              delay: Math.min(stagger++, 5) * 55,
              fill: "backwards",
              easing: "cubic-bezier(.16,1,.3,1)",
            },
          );
          animations.set(element, animation);
          const done = () => {
            if (animations.get(element) === animation) {
              animations.delete(element);
              element.dataset.revealState = "visible";
            }
          };
          animation.onfinish = done;
          animation.oncancel = done;
        }
      },
      { threshold: 0.01, rootMargin: "0px 0px -24px 0px" },
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
      // Focusing a control happens between pointer-down and click. Snapping its
      // moving parent to the final position here makes the click miss the control.
      if (pointerActive) return;
      for (const element of animations.keys())
        if (element.contains(document.activeElement)) cancel(element);
    };
    const pointerStart = (event: PointerEvent) => {
      window.clearTimeout(pointerEnd);
      pointerActive = true;
      for (const [element, animation] of animations) {
        if (event.target instanceof Node && element.contains(event.target)) {
          animation.pause();
          pointerAnimations.add(element);
        }
      }
    };
    const pointerRelease = () => {
      window.clearTimeout(pointerEnd);
      pointerActive = false;
      for (const element of pointerAnimations) cancel(element);
      pointerAnimations.clear();
      focus();
    };
    const pointerUp = () => {
      // Click captures its target before this fallback runs, including touch taps.
      pointerEnd = window.setTimeout(pointerRelease, 0);
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
    document.addEventListener("pointerdown", pointerStart, true);
    document.addEventListener("pointerup", pointerUp, true);
    document.addEventListener("pointercancel", pointerRelease, true);
    document.addEventListener("click", pointerRelease, true);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      observer.disconnect();
      mutation.disconnect();
      if (frame) cancelAnimationFrame(frame);
      window.clearTimeout(pointerEnd);
      for (const element of animations.keys()) cancel(element);
      watched.clear();
      window.removeEventListener("scroll", scroll);
      window.removeEventListener("resize", scroll);
      document.removeEventListener("focusin", focus);
      document.removeEventListener("pointerdown", pointerStart, true);
      document.removeEventListener("pointerup", pointerUp, true);
      document.removeEventListener("pointercancel", pointerRelease, true);
      document.removeEventListener("click", pointerRelease, true);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [enabled, routeKey]);
  return enabled ? (
    <div className="scroll-progress" ref={progress} aria-hidden="true" />
  ) : null;
}
