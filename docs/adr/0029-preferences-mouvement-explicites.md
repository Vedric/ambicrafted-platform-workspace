# ADR 0029 — Préférences de mouvement explicites

Date: 2026-09-29. Status: accepted for the private console.

## Context

The previous header reflected the saved boolean rather than effective movement.
With device reduced motion enabled, it displayed “Pause animations” while native
AURA animations numbered zero. Toggling off/on could not override the device:
independent component hooks and several CSS media rules still disabled movement.
An older saved pause could also survive without an obvious textual indication.
This reproduces a control defect; it does not prove the user's Windows browsers
all have reduced motion enabled.

## Decision

Use three explicit modes: `system` (default), `full`, and `paused`. Derive one
effective state for the header, CSS, React motion and component hooks. The header
shows the effective state; enabling movement is an explicit choice of `full`.
Settings offers all three modes, including a return to the device preference.
CSS accessibility fallbacks remain active unless `full` was explicitly selected.
Offscreen and hidden-tab suspension continues in every mode.

Store explicit selections under `ambicrafted-motion-mode`. Preserve a legacy
`paused` choice; legacy `enabled` is treated as `system` because older code wrote
it automatically. Do not persist the initial default as an explicit selection.
Synchronize same-origin tabs through storage events. Blocked storage leaves the
current tab usable. Do not alter operating-system settings or browser profiles.

Move shared scroll-progress styling out of the lazily loaded chart stylesheet so
direct Welcome and Settings entry does not depend on a prior Overview visit.

## Verification and consequences

Unit tests cover migration, dynamic device changes, storage errors, synchronization
and override precedence. Native Chromium desktop/mobile and Firefox tests cover
actual changing transforms, running clocks, fades in both directions, reloading,
keyboard activation and Settings. An explicit full override may move content on
a device configured to reduce motion; the user can always pause or restore system
behavior. Previous paused sessions need one explicit activation after updating.
See [the delivery report](../RELEASE-0.4.4.md).
