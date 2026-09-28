# Explicit motion controls — 0.4.4

Console **0.4.4**; control API **0.4.1**, speech runtime **0.3.1**.
This correction concerns the private console's movement controls and styles.

## Reproduced defect and correction

In a native browser with reduced motion emulated, the previous header displayed
**Pause animations** and root state `enabled`, while AURA was resting with **zero
running animations**. Clicking Pause then Enable still left zero running clocks.
This is a reproducible defect, not a verified diagnosis of all three Windows
browser profiles reported by the operator.

The header now shows the effective **Motion on / Motion off** state (French:
**Animations actives / Animations en pause**). **Enable animations** explicitly
selects full movement. **Settings → Appearance → Animation settings** offers
**Follow device settings**, **Full animations** and **Pause animations**. CSS,
AURA, charts, architecture flows, page transitions and scroll reveals use that
same choice. Shared scroll-progress styling now loads on direct page entry.
Narrow headers wrap their controls, including longer French labels, instead of
clipping them or pushing them beyond a 320-pixel viewport.

The default respects device accessibility preferences. Existing saved pauses are
preserved and can be cleared through Enable. Explicit choices survive reloads and
synchronize between same-origin tabs. Hidden tabs and offscreen AURA still pause.
No browser profile or Windows preference is edited. The guide is updated in both
languages; controls also appear in the public guide.

The release also pins corrective versions of three evaluation dependencies
flagged by the release audit: `fast-uri` 3.1.7, `ip-address` 10.5.1 and the SDK's
6.x `undici` 6.28.1. Pure local security regressions check URI authority injection
and IPv6 classification. See [dependency evidence and advisories](DEPENDENCIES.md#evaluation-dependency-correction--2026-09-29).

## Verification

Unit regression coverage includes preference migration, live device changes,
explicit overrides, storage failures and tab synchronization. Native Playwright
cases on Chromium desktop/mobile and Firefox verify running animation clocks,
changing transforms, real fade opacity/lifecycle in both scroll directions,
keyboard activation, reloads, bilingual controls and return to system behavior.
The existing desktop/mobile suite remains enabled; CI installs both engines and
rejects flaky results. Qualification and hosted CI are tied to the published
commit; release assets contain measured results.

Local checks covered 24 combinations of Welcome/Settings/AURA, 320/390/768/1440
pixel widths, English/French and the two themes, including 12 automated WCAG
A/AA scans: no tested violations, browser errors or overflowing controls remained.
Eight six-second scroll probes on AURA (1440/390 pixels, both themes, normal and
4× CPU throttling) measured p95 frame times of 16.7–16.8 ms, no frame over 34 ms
and no reported long tasks. These are bounded local headless measurements.

Browser engine tests do not certify the operator's actual Windows profiles or
physical-device performance. Previous voice measurements and personal-use
acceptance conditions remain in [0.4.3](RELEASE-0.4.3.md).

## Use

1. Reload [Welcome](http://127.0.0.1:8787/welcome).
2. If the header says **Motion off / Animations en pause**, click it once.
3. AURA's rings and pulse continue while visible; page sections fade on arrival
   and when scrolling down or back up. Settings can restore device behavior.

Preferences are independent between browsers and between `localhost` and
`127.0.0.1`. Technical decision: [ADR 0029](adr/0029-preferences-mouvement-explicites.md).
