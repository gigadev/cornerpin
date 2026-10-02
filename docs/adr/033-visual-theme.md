# ADR-033: The "survey and land" visual theme

- **Status:** Accepted
- **Date:** 2026-10-02
- **Applies from:** P1-12 (before the first deploy)

## Context

The brand (wordmark, colours, typeface) is an open item in the plan, and until now the app used
shadcn/ui's neutral palette and the system fonts (ADR-024). Before the site goes live, Scott
asked for a theme so the public pages don't look like a bare scaffold. There is still no
designed logo, so this is a working identity that a real brand can replace.

## Decision

Scott chose the "survey and land" direction on 2026-10-02, applied to the public pages first.

- **Colours** are the shadcn tokens in `app/globals.css`, so every component follows them: warm
  sand background (`#f7f4ee`), deep slate text (`#1f2a33`), sage-green primary (`#4f6b4a`), with
  dark-mode values alongside. Text on the background, cards and muted surfaces is at least
  4.5:1 (WCAG AA).
- **Lot status keeps the map's hues** (ADR-026: green available, amber on hold, grey sold).
  Status badges use darker text on a soft tint of the same hue, from `--status-*` tokens, so a
  badge and its lot on the map always agree. The brand colour never means a status.
- **Type:** Fraunces for headings, Inter for everything else, both self-hosted at build time
  by `next/font`, so pages make no request to Google. The service worker keeps them in a
  `fonts` cache on first use (their file names carry a hash), so saved pages look the same
  offline.
- **The mark** is a lot's boundary with a survey pin at one corner (`components/wordmark.tsx`),
  next to "Cornerpin" in Fraunces. The app icons and link-preview cards draw the same mark.
- **Contours.** Page openings (home, subdivision, lot, sign-in, help) sit on faint
  topographic lines, a CSS mask over `public/contours.svg` tinted by `--contour`.
- **Scope.** The public pages get real styling. The owner portal takes the colours and fonts
  but keeps its layout until it gets its own pass.
- Manifests and the browser theme colour use sage, with a sand background for the splash screen.

## Consequences

- A real brand later is mostly a change to the tokens, the two fonts and the mark.
- The build needs network access the first time it fetches the fonts (CI and Docker builds
  have it).
- New public components should use the tokens (`bg-card`, `text-primary`,
  `bg-status-available-soft`, …), never raw colours. Printed signs stay black on white.
- Link-preview cards use Satori's built-in font, not Fraunces, to keep the image routes simple.

## Related

ADR-024 (its "UI kit" palette and font bullet is replaced by this ADR), ADR-026 (status colours),
ADR-030 (offline: why the fonts are self-hosted)
