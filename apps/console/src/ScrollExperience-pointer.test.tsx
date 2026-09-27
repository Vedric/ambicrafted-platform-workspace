import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ScrollExperience } from "./ScrollExperience";

let callback: IntersectionObserverCallback;
let watched: Element;
const animation = {
  pause: vi.fn(),
  cancel: vi.fn(),
  onfinish: null,
  oncancel: null,
};
beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(cb: IntersectionObserverCallback) {
        callback = cb;
      }
      observe(element: Element) {
        watched = element;
      }
      unobserve() {}
      disconnect() {}
    },
  );
  vi.stubGlobal("matchMedia", () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
  }));
  Object.defineProperty(HTMLElement.prototype, "animate", {
    configurable: true,
    value: vi.fn(() => animation),
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(HTMLElement.prototype, "animate");
});

function setup() {
  const clicked = vi.fn();
  render(
    <div id="root">
      <ScrollExperience routeKey="/test" />
      <div className="page-scene">
        <article className="panel">
          <button onClick={clicked}>Open context</button>
        </article>
      </div>
    </div>,
  );
  callback(
    [{ target: watched, isIntersecting: true } as IntersectionObserverEntry],
    {} as IntersectionObserver,
  );
  return {
    clicked,
    button: screen.getByRole("button", { name: "Open context" }),
  };
}

it("keeps an entering control in place through pointer focus and click", () => {
  const { button, clicked } = setup();
  fireEvent.pointerDown(button);
  button.focus();
  expect(animation.pause).toHaveBeenCalledOnce();
  expect(animation.cancel).not.toHaveBeenCalled();
  fireEvent.pointerUp(button);
  expect(animation.cancel).not.toHaveBeenCalled();
  fireEvent.click(button);
  expect(clicked).toHaveBeenCalledOnce();
  expect(animation.cancel).toHaveBeenCalled();
});

it("finishes motion immediately when reached by keyboard focus", () => {
  const { button } = setup();
  button.focus();
  expect(animation.cancel).toHaveBeenCalled();
  expect(animation.pause).not.toHaveBeenCalled();
});
