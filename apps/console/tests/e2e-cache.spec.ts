import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("ambicrafted-welcome-audio", "off");
    localStorage.setItem("ambicrafted-language", "en");
  });
});

test("public build caching revalidates HTML and never caches private responses", async ({
  page,
  request,
}) => {
  const html = await request.get("/");
  expect(html.headers()["cache-control"]).toBe("no-cache");
  const repeated = await request.get("/", {
    headers: { "If-None-Match": html.headers().etag },
  });
  expect(repeated.status()).toBe(304);
  expect(await repeated.body()).toHaveLength(0);
  expect(repeated.headers()["cache-control"]).toBe("no-cache");

  await page.goto("/welcome", { waitUntil: "networkidle" });
  const asset = await page.locator('script[type="module"]').getAttribute("src");
  expect(asset).toMatch(/^\/assets\/.*-[\w-]{8}\.js$/);
  const bundle = await request.get(asset!);
  expect(bundle.status()).toBe(200);
  expect(bundle.headers()["cache-control"]).toBe(
    "public, max-age=31536000, immutable",
  );
  const absent = await request.get("/assets/missing-Ab12_C-d.js");
  expect(absent.status()).toBe(404);
  expect(absent.headers()["cache-control"]).toBe("no-store");
  expect(absent.headers()["content-type"]).not.toContain("text/html");
  const privateResponse = await request.get("/api/conversations");
  expect(privateResponse.status()).toBe(401);
  expect(privateResponse.headers()["cache-control"]).toBe("no-store");
});

test("a second document navigation reuses versioned assets in the real browser", async ({
  page,
}, testInfo) => {
  const measurements = async () =>
    page.evaluate(() =>
      performance
        .getEntriesByType("resource")
        .filter(
          (entry): entry is PerformanceResourceTiming =>
            entry instanceof PerformanceResourceTiming &&
            new URL(entry.name).pathname.startsWith("/assets/") &&
            entry.decodedBodySize > 0,
        )
        .map(({ name, transferSize, decodedBodySize }) => ({
          path: new URL(name).pathname,
          transferSize,
          decodedBodySize,
        })),
    );
  await page.goto("/welcome?cache-check=first", { waitUntil: "networkidle" });
  const first = await measurements();
  expect(first.some((entry) => entry.transferSize > 0)).toBe(true);
  await page.goto("/welcome?cache-check=second", { waitUntil: "networkidle" });
  const second = await measurements();
  const shared = second.filter((entry) =>
    first.some((initial) => initial.path === entry.path),
  );
  expect(shared.length).toBeGreaterThan(0);
  expect(shared.every((entry) => entry.transferSize === 0)).toBe(true);
  await testInfo.attach("browser-cache-measurements", {
    body: JSON.stringify({ first, second }),
    contentType: "application/json",
  });
});
