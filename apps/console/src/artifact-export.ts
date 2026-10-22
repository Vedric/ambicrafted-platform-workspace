import type { Artifact } from "./artifacts";
import { artifactFileName } from "./artifacts";
import { t } from "./i18n";

function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob),
    link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  // Keep the URL alive long enough for WebKit to start a real download.
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

/** Only our own bounded React SVG tree enters this serializer. */
export function serializeDiagram(svg: SVGSVGElement): string {
  const clone = svg.cloneNode(true) as SVGSVGElement;
  const width = svg.dataset.exportWidth,
    height = svg.dataset.exportHeight;
  if (width && height) {
    clone.setAttribute("width", width);
    clone.setAttribute("height", height);
    clone.setAttribute("viewBox", `0 0 ${width} ${height}`);
  }
  clone.removeAttribute("style");
  clone.removeAttribute("class");
  clone.removeAttribute("role");
  clone.removeAttribute("aria-labelledby");
  clone
    .querySelectorAll("[class]")
    .forEach((node) => node.removeAttribute("class"));
  return new XMLSerializer().serializeToString(clone);
}

export async function exportDiagram(
  svg: SVGSVGElement,
  artifact: Artifact,
  format: "svg" | "png",
) {
  const serialized = serializeDiagram(svg);
  if (format === "svg") {
    download(
      new Blob([serialized], { type: "image/svg+xml;charset=utf-8" }),
      artifactFileName(artifact, "svg"),
    );
    return;
  }
  const width = Math.ceil(
      Number(svg.dataset.exportWidth || svg.getAttribute("width")),
    ),
    height = Math.ceil(
      Number(svg.dataset.exportHeight || svg.getAttribute("height")),
    );
  if (
    !Number.isFinite(width) ||
    !Number.isFinite(height) ||
    width <= 0 ||
    height <= 0 ||
    width > 8192 ||
    height > 8192 ||
    width * height > 12_000_000
  )
    throw new Error(
      t(
        "This diagram is too large for a readable PNG. Download the SVG to retain every detail.",
      ),
    );
  const canvas = document.createElement("canvas"),
    image = new Image();
  canvas.width = width;
  canvas.height = height;
  try {
    await exportInSession(async (signal) => {
      const context = canvas.getContext("2d");
      if (!context)
        throw new Error(
          t("The document could not be exported. Please try again."),
        );
      await awaitExport(
        signal,
        new Promise<void>((resolve, reject) => {
          image.onload = () => resolve();
          image.onerror = () =>
            reject(
              new Error(
                t("The document could not be exported. Please try again."),
              ),
            );
          // Same-origin content only; img-src already permits data:. No CSP relaxation.
          image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(serialized)}`;
        }),
      );
      signal.throwIfAborted();
      context.drawImage(image, 0, 0);
      const blob = await awaitExport(
        signal,
        new Promise<Blob>((resolve, reject) => {
          canvas.toBlob(
            (value) =>
              value
                ? resolve(value)
                : reject(
                    new Error(
                      t(
                        "The document could not be exported. Please try again.",
                      ),
                    ),
                  ),
            "image/png",
          );
        }),
      );
      signal.throwIfAborted();
      download(blob, artifactFileName(artifact, "png"));
    }, 8000);
  } finally {
    image.onload = image.onerror = null;
    image.src = "";
    canvas.width = canvas.height = 0;
  }
}

export async function exportStoredDocument(
  conversation: string,
  artifact: Artifact,
  format: "json" | "markdown",
) {
  return exportInSession(async (signal) => {
    const response = await fetch(
      `/api/conversations/${encodeURIComponent(conversation)}/artefacts/${encodeURIComponent(artifact.id)}/export?format=${format}`,
      {
        credentials: "same-origin",
        signal,
        redirect: "error",
      },
    );
    if (response.status === 401)
      window.dispatchEvent(new Event("session-expiree"));
    if (
      !response.ok ||
      !response.body ||
      !response.headers
        .get("content-type")
        ?.includes(format === "json" ? "application/json" : "text/markdown")
    )
      throw new Error(
        t("The document could not be exported. Please try again."),
      );
    const reader = response.body.getReader();
    const chunks: Uint8Array<ArrayBuffer>[] = [];
    let bytes = 0;
    try {
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) break;
        bytes += chunk.value.byteLength;
        if (bytes > 262_144)
          throw new Error(
            t("The document could not be exported. Please try again."),
          );
        chunks.push(new Uint8Array(chunk.value));
      }
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
    // Session revocation can unmount the card while an authorized response is
    // still arriving. Never turn that stale completion into a private download.
    signal.throwIfAborted();
    download(
      new Blob(chunks, {
        type:
          format === "json"
            ? "application/json"
            : "text/markdown;charset=utf-8",
      }),
      artifactFileName(artifact, format === "markdown" ? "md" : "json"),
    );
  });
}

/** Every asynchronous export belongs to the currently authenticated workspace. */
async function exportInSession(
  operation: (signal: AbortSignal) => Promise<void>,
  timeout = 10_000,
) {
  const controller = new AbortController(),
    timer = setTimeout(() => controller.abort(), timeout);
  const expire = () => controller.abort();
  window.addEventListener("session-expiree", expire);
  try {
    await operation(controller.signal);
  } finally {
    window.removeEventListener("session-expiree", expire);
    clearTimeout(timer);
  }
}

/** Native image/canvas operations cannot all be stopped, but their publication can. */
async function awaitExport<T>(
  signal: AbortSignal,
  work: Promise<T>,
): Promise<T> {
  let cancel!: () => void;
  const aborted = new Promise<T>((_resolve, reject) => {
    cancel = () => reject(signal.reason);
    signal.addEventListener("abort", cancel, { once: true });
    if (signal.aborted) cancel();
  });
  try {
    return await Promise.race([work, aborted]);
  } finally {
    signal.removeEventListener("abort", cancel);
  }
}
