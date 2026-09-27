import { expect, test } from "@playwright/test";

for (const language of ["en", "fr"] as const) {
  test(`semantic search removes previous results after an index refusal (${language})`, async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    let requests = 0;
    await page.route("**/api/recherche?*", (route) => {
      requests += 1;
      return requests === 1
        ? route.fulfill({
            json: {
              mode: "semantique",
              elements: [
                {
                  score: 0.83,
                  donnees: {
                    fichier: "synthetic-provenance.md",
                    chemin_titres: "# Synthetic source",
                    ligne_debut: 1,
                    corpus_sha256: "a".repeat(64),
                    texte: "Synthetic fresh passage.",
                  },
                },
              ],
            },
          })
        : route.fulfill({
            status: 503,
            json: {
              detail:
                "Recherche sémantique indisponible. Vérifier l'index et l'inférence locale.",
            },
          });
    });
    const response = await page.request.post("/api/auth/ticket", {
      headers: { Authorization: "Bearer " + process.env.PLATFORM_E2E_KEY },
      data: {},
    });
    expect(response.ok()).toBe(true);
    const { ticket } = await response.json();
    await page.goto("/#session=" + ticket);
    await expect(
      page.getByRole("heading", {
        name: "Your intelligence, in motion.",
        exact: true,
      }),
    ).toBeVisible();
    await page.getByLabel("Interface language").selectOption(language);
    await page.goto("/recherche");
    await page
      .getByRole("button", {
        name:
          language === "fr"
            ? "Recherche sémantique locale"
            : "Local semantic search",
        exact: true,
      })
      .click();
    await page
      .getByRole("textbox", {
        name: language === "fr" ? "Requête de recherche" : "Search query",
      })
      .fill("Synthetic provenance query");
    const search = page.getByRole("button", {
      name: language === "fr" ? "Recherche" : "Search",
      exact: true,
    });
    await search.click();
    await expect(
      page.getByText("Synthetic fresh passage.", { exact: true }),
    ).toBeVisible();
    await search.click();
    await expect(page.getByRole("alert")).toContainText(
      language === "fr"
        ? "Recherche sémantique indisponible"
        : "Semantic search is unavailable",
    );
    await expect(
      page.getByText("Synthetic fresh passage.", { exact: true }),
    ).toHaveCount(0);
    await expect(page.locator(".search-result")).toHaveCount(0);
    await expect(search).toBeEnabled();
    expect(requests).toBe(2);
    expect(errors).toEqual([]);
  });
}
