/** Genuine UI screenshots with SVG callouts rendered before browser capture. */
import { chromium } from "playwright";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve, join } from "node:path";
import { createHash } from "node:crypto";
const [sessionFile, evidence] = process.argv.slice(2);
if (!sessionFile || !evidence)
  throw Error(
    "Provide the disposable session file and private evidence directory.",
  );
const { key } = JSON.parse(await readFile(sessionFile, "utf8"));
const base = "http://127.0.0.1:8789";
const out = resolve("../../docs/media");
await mkdir(out, { recursive: true });
await mkdir(evidence, { recursive: true, mode: 0o700 });
const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1512, height: 1050 },
  reducedMotion: "reduce",
});
await context.addInitScript(() =>
  localStorage.setItem("ambicrafted-welcome-audio", "off"),
);
const request = async (path, data) => {
  const r = await context.request.fetch(base + "/api" + path, {
    method: data ? "POST" : "GET",
    headers: { Authorization: "Bearer " + key },
    data,
  });
  if (!r.ok()) throw Error(`Synthetic request failed: ${path} ${r.status()}`);
  return r.json();
};
const wait = async (id, expected) => {
  for (let i = 0; i < 100; i++) {
    const run = await request("/analyses/" + id);
    if (run.statut === expected) return;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw Error("Synthetic run did not settle");
};
for (let i = 0; i < 7; i++) {
  const run = await request("/analyses", {
    titre: [
      "Training · connection capacity",
      "Training · latency review",
      "Training · source verification",
    ][i % 3],
    alerte:
      "Synthetic demonstration. Inspect PostgreSQL connection counts; no production changes authorised.",
  });
  await wait(run.id, "en_attente_humain");
  if (i < 5) {
    await request(`/analyses/${run.id}/decision`, { approuver: i < 4 });
    await wait(run.id, i < 4 ? "complet" : "rejete_par_humain");
  }
}
const page = await context.newPage();
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
await page.goto(
  base + "/#session=" + (await request("/auth/ticket", {})).ticket,
);
await page.locator(".insights").waitFor();
const entries = [
  {
    name: "welcome",
    route: "/welcome",
    full: false,
    callouts: [
      {
        selector: ".welcome-audio-actions button",
        text: "Personal welcome · local audio",
        dx: -190,
        dy: -72,
      },
      {
        selector: ".welcome-instrument .neural-core",
        text: "AURA · measured voice visualization",
        dx: -240,
        dy: 80,
      },
    ],
  },
  {
    name: "assistant",
    route: "/assistant",
    full: true,
    callouts: [
      {
        selector: ".aura-stage .neural-core",
        text: "Local bilingual conversation",
        dx: 160,
        dy: -100,
      },
      {
        selector: ".conversation-toolbar",
        text: "Saved history · explicit context",
        dx: 250,
        dy: 65,
      },
      {
        selector: ".attachment-toolbar",
        text: "Documents and images stay local",
        dx: -110,
        dy: 70,
      },
    ],
  },
  {
    name: "workspace",
    route: "/",
    full: true,
    callouts: [
      {
        selector: ".insight-heading",
        text: "Measured data · explicit scope",
        dx: 500,
        dy: 18,
      },
      {
        selector: ".insight-grid > section:nth-child(2)",
        text: "Inspect states, legends and tables",
        dx: -400,
        dy: -40,
      },
    ],
  },
  {
    name: "architecture",
    route: "/architecture",
    full: true,
    callouts: [
      {
        selector: ".architecture-canvas",
        text: "Select a component to explore its role",
        dx: 0,
        dy: -220,
      },
      {
        selector: ".architecture-details",
        text: "Data flow and trust boundaries",
        dx: -330,
        dy: 120,
      },
    ],
  },
  {
    name: "settings",
    route: "/parametres",
    full: false,
    callouts: [
      {
        selector: ".theme-options",
        text: "Day and night · saved preferences",
        dx: 0,
        dy: -94,
      },
      {
        selector: "#audio-settings h2",
        text: "Welcome audio · system defaults",
        dx: -90,
        dy: 90,
      },
    ],
  },
];
const results = [];
try {
  for (const theme of ["dark", "light"])
    for (const entry of entries) {
      await page.evaluate((theme) => {
        localStorage.setItem("ambicrafted-theme", theme);
        localStorage.setItem("ambicrafted-language", "en");
      }, theme);
      await page.goto(base + entry.route);
      await page.locator("h1").waitFor();
      await page.evaluate(() => document.fonts.ready);
      if (entry.route === "/") await page.locator(".insight-grid").waitFor();
      if (entry.route === "/parametres")
        await page.locator("#audio-settings").waitFor();
      if (entry.route === "/architecture")
        await page.locator(".architecture-canvas").waitFor();
      await page.screenshot({
        path: join(evidence, `${entry.name}-${theme}-original.png`),
        fullPage: entry.full,
      });
      await page.evaluate(
        ({ callouts, full }) => {
          const ns = "http://www.w3.org/2000/svg";
          const height = full
            ? document.documentElement.scrollHeight
            : innerHeight;
          const svg = document.createElementNS(ns, "svg");
          svg.setAttribute("width", String(innerWidth));
          svg.setAttribute("height", String(height));
          Object.assign(svg.style, {
            position: "absolute",
            inset: "0",
            zIndex: "99999",
            pointerEvents: "none",
          });
          const element = (name, attrs) => {
            const el = document.createElementNS(ns, name);
            for (const [key, value] of Object.entries(attrs))
              el.setAttribute(key, String(value));
            return el;
          };
          const defs = element("defs", {});
          const marker = element("marker", {
            id: "capture-arrow",
            viewBox: "0 0 10 10",
            refX: "9",
            refY: "5",
            markerWidth: "7",
            markerHeight: "7",
            orient: "auto-start-reverse",
          });
          marker.append(
            element("path", { d: "M0 0L10 5L0 10Z", fill: "#ea9b25" }),
          );
          defs.append(marker);
          svg.append(defs);
          for (const item of callouts) {
            const target = document.querySelector(item.selector);
            if (!target)
              throw Error("Missing capture target: " + item.selector);
            const bounds = target.getBoundingClientRect();
            const x = bounds.x + bounds.width / 2;
            const y = bounds.y + scrollY + bounds.height / 2;
            const measure = document.createElement("canvas").getContext("2d");
            measure.font = "600 14px sans-serif";
            const width = Math.max(
              205,
              Math.ceil(measure.measureText(item.text).width) + 28,
            );
            const bx = Math.max(
              15,
              Math.min(innerWidth - width - 15, x + item.dx - width / 2),
            );
            const by = Math.max(15, Math.min(height - 80, y + item.dy));
            svg.append(
              element("path", {
                d: `M${bx + width / 2} ${by + 22} Q${bx + width / 2} ${y} ${x} ${y}`,
                fill: "none",
                stroke: "#ea9b25",
                "stroke-width": "3",
                "marker-end": "url(#capture-arrow)",
              }),
            );
            svg.append(
              element("rect", {
                x: bx,
                y: by,
                width,
                height: 42,
                rx: 9,
                fill: "#122239",
                stroke: "#ea9b25",
                "stroke-width": 1.5,
              }),
            );
            const label = element("text", {
              x: bx + 14,
              y: by + 27,
              fill: "#fff",
              "font-family": "sans-serif",
              "font-size": 14,
              "font-weight": 600,
            });
            label.textContent = item.text;
            svg.append(label);
          }
          svg.append(
            element("rect", {
              x: 15,
              y: height - 39,
              width: 420,
              height: 28,
              rx: 6,
              fill: "#122239",
            }),
          );
          const note = element("text", {
            x: 26,
            y: height - 20,
            fill: "#c1d3e6",
            "font-family": "sans-serif",
            "font-size": 12,
          });
          note.textContent =
            "Real interface capture · synthetic demo data · annotated";
          svg.append(note);
          document.body.append(svg);
        },
        { callouts: entry.callouts, full: entry.full },
      );
      const file = `${entry.name}-${theme}.png`;
      await page.screenshot({ path: join(out, file), fullPage: entry.full });
      const bytes = await readFile(join(out, file));
      results.push({
        file,
        route: entry.route,
        theme,
        sha256: createHash("sha256").update(bytes).digest("hex"),
        bytes: bytes.length,
      });
      console.log(file);
    }
  if (errors.length) throw Error("Browser exceptions: " + errors.join("; "));
  await writeFile(
    join(out, "provenance.json"),
    JSON.stringify(
      {
        source:
          "Local deterministic E2E application, Playwright Chromium, 1512×1050 viewport",
        annotations:
          "SVG arrows and labels rendered in the browser before capture; original screenshots retained in private qualification evidence",
        data: "Synthetic disposable data; no customer data, credentials or live production metrics",
        screenshots: results,
      },
      null,
      2,
    ),
  );
} finally {
  await browser.close();
}
