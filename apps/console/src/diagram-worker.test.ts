import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { diagramFixture } from "./artifact-fixtures";
import { computeDiagram } from "./diagram-worker";
const mocks = vi.hoisted(() => ({
  terminate: vi.fn(),
  layout: vi.fn(),
  construct: vi.fn(),
}));
vi.mock("elkjs/lib/elk-api", () => ({
  default: class {
    constructor() {
      mocks.construct();
    }
    layout = mocks.layout;
    terminateWorker = mocks.terminate;
  },
}));
const originalFonts = Object.getOwnPropertyDescriptor(document, "fonts");
function fonts(ready: Promise<unknown>) {
  Object.defineProperty(document, "fonts", {
    configurable: true,
    value: { ready },
  });
}
beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  if (originalFonts) Object.defineProperty(document, "fonts", originalFonts);
  else Reflect.deleteProperty(document, "fonts");
});
describe("bounded diagram worker", () => {
  it("releases the shared queue when font loading is cancelled", async () => {
    fonts(new Promise(() => {}));
    const controller = new AbortController();
    const first = computeDiagram(diagramFixture.document, controller.signal);
    const rejected = expect(first).rejects.toMatchObject({
      name: "AbortError",
    });
    await Promise.resolve();
    await Promise.resolve();
    controller.abort();
    await rejected;
    expect(mocks.construct).not.toHaveBeenCalled();
    // A later document must get its own deadline, not remain behind the old font wait.
    const second = computeDiagram(
      diagramFixture.document,
      new AbortController().signal,
    );
    const timeout = expect(second).rejects.toThrow("time limit");
    await vi.advanceTimersByTimeAsync(8001);
    await timeout;
  });
  it("terminates a stalled worker and removes its timeout", async () => {
    fonts(Promise.resolve());
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      measureText: (text: string) => ({ width: text.length * 8 }),
    } as CanvasRenderingContext2D);
    mocks.layout.mockReturnValue(new Promise(() => {}));
    const controller = new AbortController();
    const job = computeDiagram(diagramFixture.document, controller.signal);
    const timeout = expect(job).rejects.toThrow("time limit");
    await vi.advanceTimersByTimeAsync(8001);
    await timeout;
    expect(mocks.layout).toHaveBeenCalledTimes(1);
    expect(mocks.terminate).toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });
});
