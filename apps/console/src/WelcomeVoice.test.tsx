import { StrictMode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, audioLocal, type Vue } from "./api";
import { setLanguage } from "./i18n";
import WelcomeVoice from "./WelcomeVoice";

vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  api: vi.fn(),
  audioLocal: vi.fn(),
}));
vi.mock("./audio-devices", () => ({
  useAudioDevices: () => ({ outputId: "default" }),
  applyAudioOutput: vi.fn(async () => {}),
}));
vi.mock("./NeuralCore", () => ({
  NeuralCore: () => <div aria-hidden="true" />,
}));

let client: QueryClient;
const players: FakeAudio[] = [];
let playError: Error | null;
class FakeAudio {
  onplaying: (() => void) | null = null;
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  paused = true;
  currentTime = 0;
  pause = vi.fn(() => {
    this.paused = true;
  });
  load = vi.fn();
  removeAttribute = vi.fn();
  play = vi.fn(async () => {
    if (playError) throw playError;
    this.paused = false;
    this.onplaying?.();
  });
  constructor(public src: string) {
    players.push(this);
  }
}
const workspace = {
  sante: {
    services: [
      { id: "litellm", ok: true },
      { id: "qdrant", ok: false },
    ],
  },
  statuts: { en_attente_humain: 3, en_file: 2, en_cours: 1, decision: 1 },
  runbooks: 7,
} as unknown as Vue;
function mount(connected = false) {
  return render(
    <StrictMode>
      <QueryClientProvider client={client}>
        <WelcomeVoice connected={connected} />
      </QueryClientProvider>
    </StrictMode>,
  );
}
beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("ambicrafted-welcome-audio", "off");
  setLanguage("en");
  players.length = 0;
  playError = null;
  vi.mocked(api).mockReset().mockResolvedValue(workspace);
  vi.mocked(audioLocal)
    .mockReset()
    .mockResolvedValue(new Blob(["wave"]));
  client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  vi.stubGlobal("Audio", FakeAudio);
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(new Uint8Array(44))),
  );
  vi.stubGlobal(
    "URL",
    Object.assign(URL, {
      createObjectURL: vi.fn(() => "blob:private-briefing"),
      revokeObjectURL: vi.fn(),
    }),
  );
});
afterEach(() => {
  cleanup();
  client.clear();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("personal local welcome", () => {
  it("chains fresh public news that arrives while the greeting is already playing", async () => {
    let finish!: (value: unknown) => void;
    vi.mocked(api).mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    mount();
    fireEvent.click(
      screen.getByRole("button", { name: "Listen to my welcome" }),
    );
    await screen.findByText("AURA is speaking");
    await act(async () =>
      finish({
        stale: false,
        briefings: { en: { text: "Public news, with sources." } },
      }),
    );
    await screen.findByRole("button", { name: "Listen to technology watch" });
    await act(async () => players[0].onended?.());
    await waitFor(() => expect(players).toHaveLength(2));
    expect(players[1].src).toBe("/api/veille/audio/en");
    expect(screen.getByText("Public news, with sources.")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(players[1].paused).toBe(true);
    expect(audioLocal).not.toHaveBeenCalled();
  });

  it("does not chain outdated technology news after the greeting", async () => {
    vi.mocked(api).mockResolvedValue({
      stale: true,
      briefings: { en: { text: "Old news." } },
    });
    mount();
    fireEvent.click(
      screen.getByRole("button", { name: "Listen to my welcome" }),
    );
    await screen.findByText("AURA is speaking");
    await act(async () => players[0].onended?.());
    expect(players).toHaveLength(1);
    expect(players[0].paused).toBe(true);
  });
  it("plays a public fixed greeting without querying private workspace data", async () => {
    mount();
    expect(players).toHaveLength(0);
    fireEvent.click(
      screen.getByRole("button", { name: "Listen to my welcome" }),
    );
    expect(await screen.findByText("AURA is speaking")).toBeVisible();
    expect(players[0].src).toBe("/audio/aura-welcome-en.wav");
    expect(
      vi.mocked(api).mock.calls.every(([path]) => path === "/veille"),
    ).toBe(true);
    expect(audioLocal).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("button", { name: "Listen to my briefing" }),
    ).toBeNull();
  });

  it("attempts only one arrival greeting in StrictMode and can remember an opt-out", async () => {
    localStorage.removeItem("ambicrafted-welcome-audio");
    mount();
    await screen.findByText("AURA is speaking");
    expect(players).toHaveLength(1);
    fireEvent.click(
      screen.getByRole("checkbox", { name: "Welcome me on arrival" }),
    );
    expect(localStorage.getItem("ambicrafted-welcome-audio")).toBe("off");
    expect(players[0].pause).toHaveBeenCalledOnce();
    expect(players[0].removeAttribute).toHaveBeenCalledWith("src");
  });

  it("explains autoplay restrictions and allows a successful explicit retry", async () => {
    playError = new DOMException("Autoplay denied", "NotAllowedError");
    mount();
    fireEvent.click(
      screen.getByRole("button", { name: "Listen to my welcome" }),
    );
    expect(await screen.findByText(/Your browser needs a click/)).toBeVisible();
    expect(players[0].pause).toHaveBeenCalled();
    playError = null;
    fireEvent.click(
      screen.getByRole("button", { name: "Listen to my welcome" }),
    );
    expect(await screen.findByText("AURA is speaking")).toBeVisible();
  });

  it("stops native playback on Escape and on page unmount", async () => {
    const view = mount();
    fireEvent.click(
      screen.getByRole("button", { name: "Listen to my welcome" }),
    );
    await screen.findByText("AURA is speaking");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(players[0].paused).toBe(true);
    fireEvent.click(
      screen.getByRole("button", { name: "Listen to my welcome" }),
    );
    await screen.findByText("AURA is speaking");
    view.unmount();
    expect(players[1].paused).toBe(true);
    expect(players[1].removeAttribute).toHaveBeenCalledWith("src");
  });

  it("changes the public audio and transcript together in French", async () => {
    mount();
    act(() => setLanguage("fr"));
    fireEvent.click(
      screen.getByRole("button", { name: "Écouter mon accueil" }),
    );
    await waitFor(() => expect(players[0]?.play).toHaveBeenCalled());
    expect(players[0].src).toBe("/audio/aura-welcome-fr.wav");
    expect(
      screen.getByText(/Bonjour Védric, contente de vous retrouver/),
    ).toBeInTheDocument();
  });

  it("fetches current measurements before generating a private briefing", async () => {
    vi.mocked(api).mockResolvedValue({ ...workspace, runbooks: 1 });
    mount(true);
    const button = await screen.findByRole("button", {
      name: "Listen to my briefing",
    });
    await waitFor(() => expect(button).toBeEnabled());
    const beforeRefresh = vi.mocked(api).mock.calls.length;
    vi.mocked(api).mockResolvedValue(workspace);
    fireEvent.click(button);
    await waitFor(() => expect(audioLocal).toHaveBeenCalledOnce());
    const text = vi.mocked(audioLocal).mock.calls[0][0];
    expect(text).toContain("1 of 2 services");
    expect(text).toContain("3 analyses");
    expect(text).toContain("4 executions");
    expect(text).toContain("7 runbooks");
    expect(api).toHaveBeenCalledTimes(beforeRefresh + 1);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:private-briefing");
  });

  it("never reads stale cached values as a fresh briefing after a refresh failure", async () => {
    mount(true);
    const button = await screen.findByRole("button", {
      name: "Listen to my briefing",
    });
    await waitFor(() => expect(button).toBeEnabled());
    vi.mocked(api).mockRejectedValueOnce(new Error("Offline"));
    fireEvent.click(button);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Workspace data is unavailable",
    );
    expect(audioLocal).not.toHaveBeenCalled();
    expect(players).toHaveLength(0);
  });

  it("cancels synthesis when leaving and ignores its late result", async () => {
    let finish!: (value: Blob) => void;
    vi.mocked(audioLocal).mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const view = mount(true);
    const button = await screen.findByRole("button", {
      name: "Listen to my briefing",
    });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    await waitFor(() => expect(audioLocal).toHaveBeenCalled());
    const abort = vi.mocked(audioLocal).mock.calls[0][1];
    view.unmount();
    expect(abort?.aborted).toBe(true);
    await act(async () => finish(new Blob(["late"])));
    expect(players).toHaveLength(0);
  });
});
