/** Synthetic scope only; a private one-use ticket never reaches output. */
import { chromium } from "playwright";
import { readFile, writeFile, unlink } from "node:fs/promises";
import { randomBytes } from "node:crypto";
const folder = process.argv[2];
if (!folder) throw Error("Private evidence directory required");
const { ticket } = JSON.parse(
  await readFile(folder + "/memory-ui-ticket-private.json", "utf8"),
);
const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
});
const page = await context.newPage();
const base = "http://127.0.0.1:8787";
const scope = "qualification-" + randomBytes(6).toString("hex");
const created = [];
let conversation;
const checks = [];
try {
  await page.addInitScript(() => {
    localStorage.setItem("ambicrafted-language", "en");
    localStorage.setItem("ambicrafted-welcome-audio", "off");
  });
  await page.goto(base + "/memoire#session=" + ticket);
  await page.getByText("Dedicated Neo4j connected", { exact: true }).waitFor();
  await page.getByLabel("Memory scope", { exact: true }).fill(scope);
  for (const title of [
    "Synthetic latency observation",
    "Synthetic deployment decision",
  ]) {
    await page
      .getByRole("button", { name: "Add memory note", exact: true })
      .click();
    const form = page.getByRole("dialog");
    await form.getByLabel("Title", { exact: true }).fill(title);
    await form
      .getByLabel("Context", { exact: true })
      .fill(
        "Synthetic qualification only. No customer information. This is not a verified cause.",
      );
    await form
      .getByLabel("Source", { exact: true })
      .fill("Synthetic local qualification 2026-09-27");
    const pending = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/memoire") && r.request().method() === "POST",
    );
    await form.getByRole("button", { name: "Save note", exact: true }).click();
    const response = await pending;
    if (!response.ok()) throw Error("Note creation failed");
    const body = await response.json();
    created.push(body.note?.id || body.id);
    await page.getByRole("heading", { name: title, exact: true }).waitFor();
  }
  checks.push("Create two sourced notes through the UI");
  const card = page
    .locator("article")
    .filter({
      has: page.getByRole("heading", {
        name: "Synthetic latency observation",
        exact: true,
      }),
    });
  await card
    .getByRole("button", { name: "View and connect context", exact: true })
    .click();
  await page
    .getByLabel("Connect another note", { exact: true })
    .selectOption({ label: "Synthetic deployment decision" });
  await page
    .getByRole("button", { name: "Connect notes", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("listitem")
    .filter({ hasText: "Synthetic deployment decision" })
    .waitFor();
  checks.push("Create and read a real Neo4j relationship");
  await page
    .getByRole("button", { name: "Use this context with AURA", exact: true })
    .click();
  await page.waitForURL("**/assistant?conversation=*");
  conversation = new URL(page.url()).searchParams.get("conversation");
  const source = page.getByRole("checkbox", { name: /memory-.*\.txt/ });
  await source.waitFor();
  if (!(await source.isChecked()))
    throw Error("New explicit source not selected");
  checks.push(
    "Copy memory into a saved AURA conversation with its source selected",
  );
  await page.screenshot({
    path: folder + "/memory-to-aura.png",
    fullPage: true,
  });
  await page.goto(base + "/memoire");
  await page.getByLabel("Memory scope", { exact: true }).fill(scope);
  await page
    .getByRole("heading", {
      name: "Synthetic latency observation",
      exact: true,
    })
    .waitFor();
  for (const title of [
    "Synthetic latency observation",
    "Synthetic deployment decision",
  ]) {
    await page
      .getByRole("button", { name: "Delete memory note " + title, exact: true })
      .click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Delete note", exact: true })
      .click();
    await page
      .getByRole("heading", { name: title, exact: true })
      .waitFor({ state: "detached" });
  }
  checks.push("Delete only the synthetic notes and relationship");
  await writeFile(
    folder + "/memory-ui-functional.json",
    JSON.stringify({ scope, checks }, null, 2) + "\n",
  );
  console.log(JSON.stringify({ checks }));
} finally {
  const session = await page.request.get(base + "/api/auth");
  if (session.ok()) {
    const auth = await session.json();
    const headers = {
      "X-CSRF-Token": auth.csrf,
      "Content-Type": "application/json",
      Origin: base,
    };
    for (const id of created.filter(Boolean))
      await page.request.delete(
        base + "/api/memoire/" + id + "?scope=" + scope,
        { headers, data: {} },
      );
    if (conversation)
      await page.request.delete(base + "/api/conversations/" + conversation, {
        headers,
        data: {},
      });
  }
  await unlink(folder + "/memory-ui-ticket-private.json").catch(() => {});
  await browser.close();
}
