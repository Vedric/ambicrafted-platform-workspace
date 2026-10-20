import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

async function login(page: Page) {
  const response = await page.request.post("/api/auth/ticket", {
    headers: { Authorization: "Bearer " + process.env.PLATFORM_E2E_KEY },
    data: {},
  });
  expect(response.ok()).toBe(true);
  await page.goto("/assistant#session=" + (await response.json()).ticket);
  await expect(page.getByLabel("Your message")).toBeEditable();
}
async function create(page: Page, format: "diagram" | "report") {
  await page.getByLabel("Response format").selectOption(format);
  await page
    .getByLabel("Your message")
    .fill(
      `Synthetic ${format} ${test.info().project.name}: describe UI, local investigation and human approval.`,
    );
  await page.getByRole("button", { name: "Send", exact: true }).click();
  const card = page.locator(".artifact-card");
  await expect(card).toHaveCount(1);
  return card;
}

test("real saved document renders a safe measurable graph, exports and survives reopening", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await login(page);
  const card = await create(page, "diagram");
  const svg = card.locator("svg.document-diagram");
  await expect(svg).toBeAttached();
  await expect(svg.locator("[data-diagram-node]")).toHaveCount(4);
  const geometry = await svg.evaluate((root) => {
    const graph = root as SVGSVGElement;
    const overflowing: string[] = [];
    for (const node of graph.querySelectorAll(
      "[data-diagram-node], [data-diagram-label]",
    )) {
      const rect = node.querySelector("rect")!.getBBox();
      for (const text of node.querySelectorAll("text")) {
        const box = text.getBBox();
        if (
          box.x < rect.x - 0.1 ||
          box.y < rect.y - 0.1 ||
          box.x + box.width > rect.x + rect.width + 0.1 ||
          box.y + box.height > rect.y + rect.height + 0.1
        )
          overflowing.push(text.textContent || "");
      }
    }
    return {
      overflowing,
      executable: graph.querySelectorAll("script,foreignObject,image,a,animate")
        .length,
      dimensions: [graph.width.baseVal.value, graph.height.baseVal.value],
    };
  });
  expect(geometry.overflowing).toEqual([]);
  expect(geometry.executable).toBe(0);
  expect(geometry.dimensions.every((size) => size > 500)).toBe(true);
  await card
    .getByRole("button", { name: "Open document", exact: true })
    .click();
  const modal = page.getByRole("dialog", { name: "Document workspace" });
  await expect(modal).toBeVisible();
  await modal.getByRole("button", { name: "Fit diagram", exact: true }).click();
  await page.screenshot({
    path: test.info().outputPath("diagram-workspace.png"),
  });
  await modal.getByRole("button", { name: "Actual size", exact: true }).click();
  await expect(modal.locator("output")).toHaveText("100%");
  const download = page.waitForEvent("download");
  await modal
    .getByRole("button", { name: "Download SVG", exact: true })
    .click();
  const saved = await download;
  expect(saved.suggestedFilename()).toMatch(/\.svg$/);
  const body = await readFile((await saved.path())!, "utf8");
  expect(body).toContain("Supervised investigation workflow");
  expect(body).toContain("Legend and provenance");
  expect(body).not.toMatch(
    /<script|<foreignObject|<image|<animate|onload=|<style/,
  );
  const pngDownload = page.waitForEvent("download");
  await modal
    .getByRole("button", { name: "Download PNG", exact: true })
    .click();
  const png = await readFile((await (await pngDownload).path())!);
  expect(png.subarray(0, 8)).toEqual(
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
  );
  expect(png.length).toBeGreaterThan(10_000);
  await modal.getByRole("button", { name: "Close", exact: true }).click();
  const id = await card.getAttribute("data-artifact-id");
  await page
    .getByRole("button", { name: "Conversation history", exact: true })
    .click();
  await page
    .getByLabel("Search conversations")
    .fill(`Synthetic diagram ${test.info().project.name}`);
  await page
    .locator(".history-list > div")
    .first()
    .getByRole("button")
    .first()
    .click();
  await expect(
    page.locator(`[data-artifact-id="${id}"] svg.document-diagram`),
  ).toBeAttached();
  const jsonDownload = page.waitForEvent("download");
  await card
    .getByRole("button", { name: "Download JSON", exact: true })
    .click();
  const json = JSON.parse(
    await readFile((await (await jsonDownload).path())!, "utf8"),
  );
  expect(json.id).toBe(id);
  expect(json.document.nodes).toHaveLength(4);
  expect(
    json.sources.every(
      (source: { verified: boolean }) => source.verified === false,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});

test("reports preserve tables, stay responsive and require explicit memory consent", async ({
  page,
}) => {
  await login(page);
  const card = await create(page, "report");
  await expect(card.getByRole("table")).toHaveCount(1);
  await expect(
    card.getByRole("cell", { name: "PostgreSQL", exact: true }),
  ).toBeVisible();
  for (const theme of ["dark", "light"]) {
    await page.evaluate((value) => {
      document.documentElement.dataset.theme = value;
    }, theme);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBe(true);
    const accessibility = await new AxeBuilder({ page })
      .include(".artifact-card")
      .analyze();
    expect(accessibility.violations).toEqual([]);
  }
  let writes = 0;
  await page.route("**/api/memoire/statut", (route) =>
    route.fulfill({ json: { ready: true, notes: 0 } }),
  );
  await page.route(/\/api\/memoire(?:\?|$)/, (route) => {
    if (route.request().method() === "POST") {
      writes++;
      return route.fulfill({ json: { id: "synthetic-note" } });
    }
    return route.fulfill({ json: { notes: [], limit: 100 } });
  });
  await card
    .getByRole("button", { name: "Prepare a memory note", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "Add memory note" });
  await expect(dialog).toBeVisible();
  expect(writes).toBe(0);
  await expect(dialog.getByLabel("Note type")).toHaveValue("question");
  await expect(dialog.getByLabel("Title", { exact: true })).toHaveValue(
    "Service readiness review",
  );
  const scope = dialog.getByLabel("Memory scope");
  await scope.fill("invalid scope");
  expect(
    await scope.evaluate(
      (element: HTMLInputElement) => element.validity.patternMismatch,
    ),
  ).toBe(true);
  await scope.fill("training");
  expect(
    await scope.evaluate((element: HTMLInputElement) =>
      element.checkValidity(),
    ),
  ).toBe(true);
  await dialog.getByRole("button", { name: "Save note", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  expect(writes).toBe(1);
});

test("complex diagrams retain every label in both directions and both themes", async ({
  page,
}) => {
  await login(page);
  const { diagramFixture } = await import("../src/artifact-fixtures");
  const artifact = structuredClone(diagramFixture);
  artifact.title =
    "Architecture d’investigation · frontières et responsabilités";
  artifact.document.groups = Array.from({ length: 6 }, (_, i) => ({
    id: `group-${i}`,
    label: `Périmètre ${i + 1}`,
    description: "Responsabilité et accès délimités",
  }));
  artifact.document.nodes = Array.from({ length: 24 }, (_, i) => ({
    ...artifact.document.nodes[0],
    id: `node-${i}`,
    group_id: `group-${Math.floor(i / 4)}`,
    label: `Composant ${i + 1} · observations et contrôles`,
    description:
      "Comparer les observations au périmètre demandé. Documenter les incertitudes avant de décider.",
    basis: i % 3 === 0 ? "proposed" : "provided",
  }));
  artifact.document.edges = Array.from({ length: 40 }, (_, i) => ({
    ...artifact.document.edges[0],
    id: `edge-${i}`,
    source: `node-${i % 24}`,
    target: `node-${(i + (i < 24 ? 1 : 5)) % 24}`,
    label: `Échange ${i + 1} · contexte et résultats`,
  }));
  await page.route(/\/api\/conversations\/[^/]+\/messages$/, (route) =>
    route.fulfill({
      contentType: "application/x-ndjson",
      body:
        JSON.stringify({
          type: "done",
          texte: artifact.summary,
          artefacts: [artifact],
        }) + "\n",
    }),
  );
  const card = await create(page, "diagram");
  await card
    .getByRole("button", { name: "Open document", exact: true })
    .click();
  const modal = page.getByRole("dialog", { name: "Document workspace" });
  for (const direction of ["LR", "TB"]) {
    await modal.getByLabel("Layout direction").selectOption(direction);
    const svg = modal.locator("svg.document-diagram");
    await expect(svg.locator("[data-diagram-node]")).toHaveCount(24);
    await expect(svg.locator("[data-diagram-label]")).toHaveCount(40);
    const errors = await svg.evaluate((root) => {
      const errors: string[] = [];
      for (const item of root.querySelectorAll(
        "[data-diagram-node], [data-diagram-label]",
      )) {
        const rect = item.querySelector("rect")!.getBBox();
        for (const text of item.querySelectorAll("text")) {
          const box = text.getBBox();
          if (
            box.x < rect.x - 0.5 ||
            box.y < rect.y - 0.5 ||
            box.x + box.width > rect.x + rect.width + 0.5 ||
            box.y + box.height > rect.y + rect.height + 0.5
          )
            errors.push(text.textContent || "");
        }
      }
      return errors;
    });
    expect(errors).toEqual([]);
    for (const theme of ["dark", "light"]) {
      await page.evaluate((value) => {
        document.documentElement.dataset.theme = value;
      }, theme);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth + 1,
        ),
      ).toBe(true);
      await expect(svg).toContainText("Proposed");
      await expect(svg).toContainText("Supplied context");
    }
  }
});

test("invalid generated markup preserves the draft and never becomes a saved-looking document", async ({
  page,
}) => {
  await login(page);
  await page.route(/\/api\/conversations\/[^/]+\/messages$/, (route) =>
    route.fulfill({
      contentType: "application/x-ndjson",
      body:
        JSON.stringify({
          type: "done",
          texte: "Looks complete",
          artefacts: [
            {
              type: "svg",
              document: { svg: '<svg onload="window.pwned=true"/>' },
            },
          ],
        }) + "\n",
    }),
  );
  await page
    .getByLabel("Your message")
    .fill("Synthetic unsafe document attempt");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByLabel("Your message")).toHaveValue(
    "Synthetic unsafe document attempt",
  );
  await expect(page.locator(".artifact-card")).toHaveCount(0);
  await expect(page.getByRole("alert")).toBeVisible();
  expect(
    await page.evaluate(() => (window as Window & { pwned?: boolean }).pwned),
  ).toBeUndefined();
});

test("printing isolates the selected report from other conversation content", async ({
  page,
}) => {
  await page.clock.install();
  await login(page);
  const card = await create(page, "report");
  await page.clock.pauseAt(await page.evaluate(() => Date.now() + 1000));
  await page.evaluate(() => {
    const state = window as Window & {
      printSnapshot?: { text: string; hidden: boolean };
    };
    window.print = () => {
      const printable = document.querySelector(".document-print")!;
      state.printSnapshot = {
        text: printable.textContent || "",
        hidden: [...document.body.children]
          .filter((node) => node !== printable)
          .every((node) => getComputedStyle(node).display === "none"),
      };
    };
  });
  // Activate the real control in screen mode, then enter print preview before
  // allowing the print callback to run. Print layout is not an interactive UI.
  await card
    .getByRole("button", { name: "Print / save PDF", exact: true })
    .click();
  await page.emulateMedia({ media: "print" });
  await page.clock.runFor(200);
  await expect
    .poll(() =>
      page.evaluate(
        () => !!(window as Window & { printSnapshot?: unknown }).printSnapshot,
      ),
    )
    .toBe(true);
  const snapshot = await page.evaluate(
    () =>
      (window as Window & { printSnapshot?: { text: string; hidden: boolean } })
        .printSnapshot!,
  );
  expect(snapshot.hidden).toBe(true);
  expect(snapshot.text).toContain("PostgreSQL");
  expect(snapshot.text).toContain("Recovery checks");
  expect(snapshot.text).not.toContain("Synthetic report desktop");
  await expect(page.locator(".document-print")).toHaveCount(0);
});
