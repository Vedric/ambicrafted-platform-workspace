import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Assistant, { reportedUsage, texteOral } from "./Assistant";

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  audio: vi.fn(),
  notifier: vi.fn(),
}));
vi.mock("./NeuralCore", () => ({
  NeuralCore: () => <div aria-hidden="true" />,
}));
vi.mock("./api", () => ({ api: mocks.api, audioLocal: mocks.audio }));
vi.mock("./ui", () => ({
  useToast: () => mocks.notifier,
  Titre: ({ titre }: { titre: string }) => <h1>{titre}</h1>,
  Erreur: ({ erreur }: { erreur: Error }) => (
    <div role="alert">{erreur.message}</div>
  ),
  Markdown: ({ texte }: { texte: string }) => <p>{texte}</p>,
}));

const piste = { stop: vi.fn() };
const stream = { getTracks: () => [piste] };
class Enregistreur {
  static isTypeSupported() {
    return true;
  }
  state = "inactive";
  mimeType = "audio/webm;codecs=opus";
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  onerror: (() => void) | null = null;
  start() {
    this.state = "recording";
  }
  stop() {
    this.state = "inactive";
    queueMicrotask(() => {
      this.ondataavailable?.({ data: new Blob(["synthetic"]) });
      this.onstop?.();
    });
  }
}

const mediaInitial = Object.getOwnPropertyDescriptor(navigator, "mediaDevices");
beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  mocks.api.mockImplementation((route: string) =>
    Promise.resolve(
      route.startsWith("/voix/statut")
        ? { pret: true, local: true, voix: "voix-feminine-en", langue: "en-US" }
        : route === "/voix/transcrire"
          ? { texte: "Une alerte à vérifier." }
          : { texte: "Je vous accompagne." },
    ),
  );
  mocks.audio.mockResolvedValue(new Blob(["wave"], { type: "audio/wav" }));
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn().mockResolvedValue(stream) },
  });
  vi.stubGlobal("MediaRecorder", Enregistreur);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  if (mediaInitial)
    Object.defineProperty(navigator, "mediaDevices", mediaInitial);
  else Reflect.deleteProperty(navigator, "mediaDevices");
});

function afficher() {
  return render(
    <MemoryRouter>
      <Assistant />
    </MemoryRouter>,
  );
}

describe("spoken text conversion", () => {
  it.each([
    undefined,
    null,
    [],
    { prompt_tokens: true, completion_tokens: -1, total_tokens: "23" },
    { prompt_tokens: 1.2, completion_tokens: Infinity, total_tokens: 2 ** 53 },
  ])("treats missing or malformed usage as unknown: %j", (usage) => {
    expect(reportedUsage(usage)).toEqual({
      prompt_tokens: null,
      completion_tokens: null,
      total_tokens: null,
    });
  });
  it("removes Markdown syntax and replaces code without reading link destinations", () => {
    const texte = texteOral(
      "# Bonjour\n\n**Équipe** : [guide](https://private.invalid)\n```sh\nrm impossible\n```\n- Fin.",
    );
    expect(texte).toContain("Bonjour");
    expect(texte).toContain("Équipe : guide");
    expect(texte).toContain("A code example is available on screen.");
    expect(texte).not.toContain("private.invalid");
    expect(texte).not.toContain("rm impossible");
    expect(texteOral("é".repeat(2500))).toBe(
      "The rest is available on screen.",
    );
    expect(texteOral("a".repeat(1999) + "😀")).toBe(
      "The rest is available on screen.",
    );
    expect(texteOral("```sh\nsynthetic command\n```", "fr")).toBe(
      "Un exemple de code est disponible à l’écran.",
    );
  });
});

describe("private assistant conversation", () => {
  it("keeps automatic playback off and sends an explicit local text message", async () => {
    afficher();
    expect(
      screen.getByRole("heading", { name: "Voice assistant" }),
    ).toBeVisible();
    expect(screen.getByLabelText("Conversation language")).toHaveValue("en");
    expect(
      screen.getByLabelText("Read replies automatically"),
    ).not.toBeChecked();
    await userEvent.type(
      screen.getByLabelText("Your message"),
      "Comment lancer une analyse ?",
    );
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Je vous accompagne.")).toBeVisible();
    expect(mocks.api).toHaveBeenCalledWith(
      "/assistant/dialogue",
      "POST",
      {
        langue: "en",
        messages: [{ role: "user", content: "Comment lancer une analyse ?" }],
      },
      expect.any(AbortSignal),
    );
    expect(mocks.audio).not.toHaveBeenCalled();
    expect(localStorage.length).toBe(0);
  });

  it("restores the draft when the local model request fails", async () => {
    mocks.api.mockImplementation((route: string) =>
      route === "/assistant/dialogue"
        ? Promise.reject(new Error("Local assistant unavailable."))
        : Promise.resolve({ pret: true }),
    );
    afficher();
    await userEvent.type(
      screen.getByLabelText("Your message"),
      "Mon contexte à conserver",
    );
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Local assistant unavailable.",
    );
    expect(screen.getByLabelText("Your message")).toHaveValue(
      "Mon contexte à conserver",
    );
  });

  it("aborts a pending response and restores the unsent draft", async () => {
    let signal: AbortSignal | undefined;
    mocks.api.mockImplementation(
      (route: string, _method: unknown, _body: unknown, s: AbortSignal) => {
        if (route === "/assistant/dialogue") {
          signal = s;
          return new Promise(() => {});
        }
        return Promise.resolve({ pret: true });
      },
    );
    afficher();
    await userEvent.type(
      screen.getByLabelText("Your message"),
      "Contexte conservé",
    );
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    await userEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(signal?.aborted).toBe(true);
    expect(screen.getByLabelText("Your message")).toHaveValue(
      "Contexte conservé",
    );
  });

  it("transcribes the microphone into an editable draft without sending or approving it", async () => {
    afficher();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Record" })).toBeEnabled(),
    );
    await userEvent.click(screen.getByRole("button", { name: "Record" }));
    await userEvent.click(
      await screen.findByRole("button", { name: "Stop recording" }),
    );
    await waitFor(() =>
      expect(screen.getByLabelText("Your message")).toHaveValue(
        "Une alerte à vérifier.",
      ),
    );
    expect(piste.stop).toHaveBeenCalled();
    expect(mocks.notifier).toHaveBeenCalledWith(
      "Transcript ready. Review the text, then select Send.",
    );
    expect(
      mocks.api.mock.calls.some(([route]) => route === "/assistant/dialogue"),
    ).toBe(false);
    await userEvent.type(
      screen.getByLabelText("Your message"),
      " Texte corrigé.",
    );
    expect(screen.getByLabelText("Your message")).toHaveValue(
      "Une alerte à vérifier. Texte corrigé.",
    );
  });

  it("stops microphone tracks granted after the page has been left", async () => {
    let autoriser!: (stream: unknown) => void;
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockImplementation(
          () =>
            new Promise((resolve) => {
              autoriser = resolve;
            }),
        ),
      },
    });
    const vue = afficher();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Record" })).toBeEnabled(),
    );
    await userEvent.click(screen.getByRole("button", { name: "Record" }));
    vue.unmount();
    autoriser(stream);
    await waitFor(() => expect(piste.stop).toHaveBeenCalled());
    expect(
      mocks.api.mock.calls.some(([route]) => route === "/voix/transcrire"),
    ).toBe(false);
  });

  it("explains a refused microphone permission and preserves text entry", async () => {
    navigator.mediaDevices.getUserMedia = vi
      .fn()
      .mockRejectedValue(new DOMException("Denied", "NotAllowedError"));
    afficher();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Record" })).toBeEnabled(),
    );
    await userEvent.click(screen.getByRole("button", { name: "Record" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Microphone access was denied",
    );
    expect(screen.getByLabelText("Your message")).toBeEnabled();
  });

  it("stops playback explicitly and releases audio resources when leaving", async () => {
    const pause = vi.fn(),
      revocation = vi.fn();
    class UrlTest extends URL {
      static createObjectURL() {
        return "blob:fixture";
      }
      static revokeObjectURL = revocation;
    }
    class AudioTest {
      play = vi.fn().mockResolvedValue(undefined);
      pause = pause;
      removeAttribute = vi.fn();
      load = vi.fn();
      onended = null;
      onerror = null;
    }
    vi.stubGlobal("URL", UrlTest);
    vi.stubGlobal("Audio", AudioTest);
    const vue = afficher();
    await userEvent.type(screen.getByLabelText("Your message"), "Bonjour");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    await userEvent.click(
      await screen.findByRole("button", { name: "Listen" }),
    );
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("Speaking…"),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Stop playback" }),
    );
    expect(screen.getByRole("status")).toHaveTextContent("Ready when you are");
    expect(pause).toHaveBeenCalledTimes(1);
    expect(revocation).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: "Listen" }));
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("Speaking…"),
    );
    vue.unmount();
    expect(pause).toHaveBeenCalledTimes(2);
    expect(revocation).toHaveBeenCalledTimes(2);
    expect(revocation).toHaveBeenCalledWith("blob:fixture");
  });
});
