import ELK from "elkjs/lib/elk-api";
import workerUrl from "elkjs/lib/elk-worker.min.js?url";
import type { DiagramDocument } from "./artifacts";
import {
  prepareDiagram,
  readLayout,
  type BasisCaptions,
  type DiagramLayout,
  type MeasureText,
} from "./diagram-layout";

// One bounded worker at a time, even when reopening a long conversation.
let queue: Promise<unknown> = Promise.resolve();
export function computeDiagram(
  document: DiagramDocument,
  signal: AbortSignal,
  captions?: BasisCaptions,
): Promise<DiagramLayout> {
  const work = queue
    .catch(() => {})
    .then(async () => {
      signal.throwIfAborted();
      let elk: InstanceType<typeof ELK> | undefined;
      let timer: ReturnType<typeof setTimeout> | undefined;
      let abort: (() => void) | undefined;
      const interrupted = new Promise<never>((_, reject) => {
        abort = () => {
          elk?.terminateWorker();
          reject(new DOMException("Cancelled", "AbortError"));
        };
        signal.addEventListener("abort", abort, { once: true });
        timer = setTimeout(() => {
          elk?.terminateWorker();
          reject(new Error("Layout time limit exceeded"));
        }, 8000);
      });
      try {
        // Fonts are part of the deadline too; a stalled font request must not
        // retain the global layout queue after navigation or cancellation.
        await Promise.race([globalThis.document.fonts.ready, interrupted]);
        signal.throwIfAborted();
        const canvas = globalThis.document.createElement("canvas");
        const context = canvas.getContext("2d");
        if (!context) throw new Error("Text measurement unavailable");
        const measure: MeasureText = (value, size, bold) => {
          context.font = `${bold ? 600 : 400} ${size}px "Manrope Variable", sans-serif`;
          return context.measureText(value).width;
        };
        elk = new ELK({ workerFactory: () => new Worker(workerUrl) });
        for (const spacious of [false, true]) {
          signal.throwIfAborted();
          const prepared = prepareDiagram(
            document,
            measure,
            spacious,
            captions,
          );
          const graph = await Promise.race([
            elk.layout(prepared.graph),
            interrupted,
          ]);
          try {
            return readLayout(graph, document, prepared);
          } catch (error) {
            if (spacious) throw error;
          }
        }
        throw new Error("Layout unavailable");
      } finally {
        clearTimeout(timer);
        if (abort) signal.removeEventListener("abort", abort);
        elk?.terminateWorker();
      }
    });
  queue = work.catch(() => {});
  return work;
}
