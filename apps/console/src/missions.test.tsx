import { afterEach, describe, expect, it } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { missions, findMission } from "./missions";
import { setLanguage } from "./i18n";
import { Missions } from "./pages/missions";

afterEach(() => {
  cleanup();
  setLanguage("en");
});
describe("engineering missions", () => {
  it("covers every requested discipline with distinct editable briefs", () => {
    expect(missions).toHaveLength(18);
    expect(new Set(missions.map((m) => m.id)).size).toBe(18);
    expect(new Set(missions.map((m) => m.area))).toEqual(
      new Set([
        "SRE",
        "DevOps",
        "DevSecOps",
        "Cloud Architecture",
        "Platform Engineering",
        "Security Engineering",
        "AI Agentic Engineering",
      ]),
    );
    for (const mission of missions) {
      expect(findMission(mission.id)).toBe(mission);
      expect(mission.draft.length).toBeGreaterThan(150);
      expect(mission.draft.length).toBeLessThan(4000);
    }
    expect(findMission("invented")).toBeUndefined();
  });
  it("translates each title, description and draft when switching language", () => {
    setLanguage("en");
    const english = missions.map((m) => ({
      title: m.title,
      description: m.description,
      draft: m.draft,
    }));
    setLanguage("fr");
    missions.forEach((mission, index) => {
      expect(mission.title).not.toBe(english[index].title);
      expect(mission.description).not.toBe(english[index].description);
      expect(mission.draft).not.toBe(english[index].draft);
    });
    expect(findMission("cicd")?.title).toContain("CI/CD");
  });
  it("combines discipline and search filters and links to the correct brief", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Missions />
      </MemoryRouter>,
    );
    await user.click(screen.getByRole("button", { name: "DevSecOps" }));
    expect(
      screen.getByRole("heading", {
        name: "Review secrets and workload identity",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Review a Kubernetes workload" }),
    ).not.toBeInTheDocument();
    await user.type(
      screen.getByRole("textbox", { name: "Find a mission" }),
      "supply chain",
    );
    expect(
      screen.queryByRole("heading", {
        name: "Review secrets and workload identity",
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Review software supply chain risks/ }),
    ).toHaveAttribute("href", "/analyses/nouvelle?mission=supply-chain");
  });
});
