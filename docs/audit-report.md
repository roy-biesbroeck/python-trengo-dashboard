# Trengo Dashboard — UI Audit Report

**Date:** 2026-03-27
**Scope:** `templates/index.html` (single-file app: CSS + JS + HTML)
**Standard:** WCAG 2.1 AA, frontend-design anti-patterns

> **Hardening applied** (2026-03-27): Issues C1, C2, H1, H3, H4, H5, M2, M3, M5, L1, L2, L4 have been fixed.
> Remaining: H2 (accepted as AA-large compliant), M1 (chart hard-coded colors), M4/M6 (responsive — use `/adapt`), L3 (SRI hash).

---

## Anti-Patterns Verdict

**PASS — This does NOT look AI-generated.** The dashboard has a clear, purposeful design language that feels hand-crafted for its specific use case. No gradient text, no glassmorphism, no dark-mode-with-neon-accents, no generic card grids with icons-above-headings.

Minor flags:
- The 4-card summary strip with colored left borders is a common pattern but executed with restraint — it serves real data, not decoration.
- System font stack is the default choice, but appropriate for a wall-mounted dashboard where load speed matters more than brand typography.

**Verdict: Clean, functional, purpose-built. Not slop.**

---

## Executive Summary

| Severity | Count |
|----------|-------|
| Critical | 2 |
| High | 5 |
| Medium | 6 |
| Low | 4 |
| **Total** | **17** |

**Top 5 issues:**
1. Age-distribution number colors fail WCAG AA entirely (1.98–2.80:1 contrast)
2. Avatar initials unreadable on 4 of 8 background colors
3. No focus indicators — keyboard navigation is invisible
4. No semantic landmarks or ARIA roles on data tables
5. No `prefers-reduced-motion` support despite spinner animation

---

## Critical Issues

### C1. Age-distribution numbers are unreadable for low-vision users
- **Location:** `index.html:596` — `.age-num` colored with `AGE_COLORS[i]`
- **Category:** Accessibility
- **Description:** Age-count numbers use the age gradient colors as text on white. Four of six fail even AA-large (3:1): lime (#84cc16) at 1.98:1, amber (#f59e0b) at 2.15:1, green (#22c55e) at 2.28:1, orange (#f97316) at 2.80:1.
- **Impact:** Numbers are effectively invisible to anyone with moderate vision impairment. On a wall-mounted display at distance, even users with perfect vision will struggle.
- **WCAG:** 1.4.3 Contrast (Minimum) — Level AA
- **Recommendation:** Use `var(--text)` for all `.age-num` values. The adjacent color swatch already communicates the category — the number doesn't need to repeat the color.
- **Suggested command:** `/harden`

### C2. No keyboard focus indicators anywhere
- **Location:** Global — no `:focus` or `:focus-visible` styles defined
- **Category:** Accessibility
- **Description:** The reset (`*, *::before, *::after { margin: 0; padding: 0; }`) doesn't explicitly remove outlines, but no custom focus styles are defined either. Browsers may show default outlines, but the blue buttons on blue focus rings will be invisible.
- **Impact:** Keyboard-only users cannot see where they are on the page. The refresh button and trend-range buttons are the only interactive elements, but they're unreachable/invisible via keyboard.
- **WCAG:** 2.4.7 Focus Visible — Level AA
- **Recommendation:** Add `:focus-visible` styles with a visible ring (e.g., `outline: 2px solid var(--blue); outline-offset: 2px`) and ensure it contrasts against both white and blue backgrounds.
- **Suggested command:** `/harden`

---

## High-Severity Issues

### H1. Avatar text fails contrast on 4 of 8 colors
- **Location:** `index.html:269-276` — `.avatar` with white text on colored backgrounds
- **Category:** Accessibility
- **Description:** White `#fff` text on teal (#14b8a6, 2.49:1), amber (#f59e0b, 2.15:1), emerald (#10b981, 2.54:1), and orange (#f97316, 2.80:1) fails both AA and AA-large.
- **Impact:** Half of all agent avatars have unreadable initials.
- **WCAG:** 1.4.3 Contrast (Minimum) — Level AA
- **Recommendation:** Replace failing avatar colors with darker variants, or use dark text on light backgrounds for those colors.
- **Suggested command:** `/harden`

### H2. Summary card values fail AA for normal text
- **Location:** `index.html:136-144` — `.card-value` colored text
- **Category:** Accessibility
- **Description:** Blue (3.68:1), green (3.30:1), amber (3.19:1), and purple (4.23:1) card values fail AA for normal text. They DO pass AA-large (3:1), and at `clamp(1.75rem, 2.5vw, 2.25rem)` they qualify as large text — but at the smallest clamp value (1.75rem = 28px) with weight 800, this is borderline.
- **Impact:** On smaller viewports or when the clamp hits its minimum, these become harder to read.
- **WCAG:** 1.4.3 Contrast (Minimum) — Level AA
- **Recommendation:** Darken each status color by ~15% for text use, or accept this as AA-large compliant given the font size/weight. Document the decision.
- **Suggested command:** `/harden`

### H3. No semantic table markup for data grids
- **Location:** `index.html:537-577` — teams and users rendered as `<div>` grids
- **Category:** Accessibility
- **Description:** The teams and users sections are visually tables but use `<div>` with CSS Grid. Screen readers cannot navigate them as tables (no `<table>`, `<th>`, `<td>`, or ARIA `role="grid"`).
- **Impact:** Screen reader users cannot understand the data structure or navigate by row/column.
- **WCAG:** 1.3.1 Info and Relationships — Level A
- **Recommendation:** Either use semantic `<table>` elements or add ARIA roles (`role="grid"`, `role="row"`, `role="gridcell"`, `role="columnheader"`).
- **Suggested command:** `/harden`

### H4. Footer text fails AA contrast
- **Location:** `index.html:352-359` — `.footer` using `var(--muted)` on `var(--bg)`
- **Category:** Accessibility
- **Description:** #64748b on #f1f5f9 = 4.34:1, just below the 4.5:1 AA threshold for normal text at .6875rem.
- **Impact:** Footer explanatory text is harder to read, especially at distance on wall display.
- **WCAG:** 1.4.3 Contrast (Minimum) — Level AA
- **Recommendation:** Darken footer text to ~#536379 or use `var(--text)` with reduced opacity won't help — use a darker muted value.
- **Suggested command:** `/polish`

### H5. No `prefers-reduced-motion` media query
- **Location:** `index.html:361` — `@keyframes spin` and various `transition` properties
- **Category:** Accessibility
- **Description:** The spinner animation runs continuously with no opt-out for users who experience motion sickness or vestibular disorders.
- **Impact:** Can cause discomfort for motion-sensitive users.
- **WCAG:** 2.3.3 Animation from Interactions — Level AAA (but best practice for AA)
- **Recommendation:** Add `@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; } }`
- **Suggested command:** `/harden`

---

## Medium-Severity Issues

### M1. Hard-coded colors in JavaScript chart config
- **Location:** `index.html:662-679` — Chart.js dataset colors use hex literals
- **Category:** Theming
- **Description:** Chart colors are hard-coded as `'#3b82f6'`, `'#16a34a'`, etc. instead of reading from CSS custom properties. If the palette is updated in CSS, the chart won't follow.
- **Recommendation:** Read computed CSS variables at render time: `getComputedStyle(document.documentElement).getPropertyValue('--blue')`.
- **Suggested command:** `/normalize`

### M2. Hard-coded colors in inline styles
- **Location:** `index.html:114-115` — `.card-closed::before` and `.card-closed .card-value` use `#8b5cf6` directly
- **Category:** Theming
- **Description:** Purple is the only status color without a CSS custom property. All others use `var(--blue)`, `var(--green)`, etc.
- **Recommendation:** Add `--purple: #8b5cf6` to `:root` and use it consistently.
- **Suggested command:** `/normalize`

### M3. `innerHTML` used for rendering with user-controlled data
- **Location:** `index.html:742, 821` — `document.getElementById('main').innerHTML = ...`
- **Category:** Security / Robustness
- **Description:** While the `esc()` function is used for team/user names, the `sub.innerHTML` at line 496 constructs HTML from API data. If Trengo API returns malicious data, XSS is possible.
- **Impact:** Low risk (internal tool, trusted API), but defense-in-depth is warranted.
- **Recommendation:** Audit all `innerHTML` assignments for proper escaping.
- **Suggested command:** `/harden`

### M4. No responsive breakpoints for mobile/tablet
- **Location:** Global CSS
- **Category:** Responsive
- **Description:** No `@media` queries exist. The 3-column grid (`1.2fr 1fr .85fr`) will compress to unusable widths on tablets. The 4-card summary grid has no responsive variant.
- **Impact:** On tablets (used for checking stats on-the-go), the layout breaks. Not critical since primary use is wall-mounted, but limits flexibility.
- **Recommendation:** Add breakpoints to stack columns on screens < 1024px.
- **Suggested command:** `/adapt`

### M5. Touch targets too small for interactive elements
- **Location:** `index.html:381-393` — `.trend-btn` padding is `.15rem .5rem` (~2.4px × 8px)
- **Category:** Responsive / Accessibility
- **Description:** Trend range buttons (7d, 30d) are approximately 20×16px — well below the 44×44px minimum for touch targets.
- **Impact:** On touch devices, these buttons are very difficult to tap accurately.
- **WCAG:** 2.5.8 Target Size (Minimum) — Level AA
- **Recommendation:** Increase padding or add min-height/min-width of 44px.
- **Suggested command:** `/adapt`

### M6. `overflow: hidden` on body prevents content access if viewport is too small
- **Location:** `index.html:42` — `overflow: hidden` on `body`
- **Category:** Responsive
- **Description:** If the viewport is shorter than the content requires, data is clipped with no way to scroll to it.
- **Impact:** On shorter displays or when browser chrome takes space, bottom content (trend chart, footer) may be cut off.
- **Recommendation:** Use `overflow: auto` or `overflow-y: auto` as fallback, or add a min-height breakpoint.
- **Suggested command:** `/adapt`

---

## Low-Severity Issues

### L1. Color-only status indicators (dots)
- **Location:** `index.html:229-235` — `.dot.has-new` (green dot for teams with new tickets)
- **Category:** Accessibility
- **Description:** The green dot next to team names is the only indicator that a team has new/unassigned tickets. Colorblind users may miss this.
- **WCAG:** 1.4.1 Use of Color — Level A
- **Recommendation:** Add a subtle shape change (filled circle vs outline) or a small number badge.
- **Suggested command:** `/harden`

### L2. No `lang` attribute on dynamic content
- **Location:** `index.html:2` — `<html lang="nl">` is correct, but no `aria-live` regions
- **Category:** Accessibility
- **Description:** When data refreshes every 5 minutes, screen readers won't announce the update.
- **Recommendation:** Add `aria-live="polite"` to the summary grid and/or last-updated timestamp.
- **Suggested command:** `/harden`

### L3. Chart.js loaded from CDN without SRI hash
- **Location:** `index.html:8` — `<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/...">`
- **Category:** Security
- **Description:** No `integrity` or `crossorigin` attributes. If the CDN is compromised, arbitrary JS executes.
- **Recommendation:** Add `integrity="sha256-..."` and `crossorigin="anonymous"`.
- **Suggested command:** `/harden`

### L4. Emoji used as icon in header
- **Location:** `index.html:407` — `<div class="header-icon">🎫</div>`
- **Category:** Accessibility
- **Description:** The ticket emoji has no `aria-label` or `role="img"`. Screen readers may announce "admission tickets" or skip it entirely depending on the reader.
- **Recommendation:** Add `role="img" aria-label="Ticket icoon"` or replace with the SVG from favicon.
- **Suggested command:** `/polish`

---

## Positive Findings

1. **Excellent CSS custom properties usage** — Nearly all colors use tokens, making future theming straightforward
2. **Fluid typography with `clamp()`** — Responsive font sizing that works well for the wall-display use case
3. **Proper HTML escaping** — The `esc()` function is consistently used for user-generated content
4. **Efficient vanilla JS** — No framework overhead, fast load times, appropriate for an always-on display
5. **Good visual hierarchy** — Clear distinction between summary cards, data tables, and charts
6. **Smart use of `100dvh`** — Dynamic viewport height handles mobile browser chrome correctly
7. **Custom scrollbar styling** — Minimal, unobtrusive, fits the aesthetic
8. **Semantic heading** — Single `<h1>` for the page title is correct

---

## Recommendations by Priority

### Immediate (before next deploy)
1. Fix age-distribution number contrast (C1) — change to `var(--text)` color
2. Fix avatar contrast failures (H1) — swap 4 palette colors for darker variants
3. Add focus-visible styles (C2) — 5-line CSS addition

### Short-term (this sprint)
4. Add `prefers-reduced-motion` (H5) — 3-line CSS addition
5. Fix footer contrast (H4) — darken muted color or use separate footer color
6. Add ARIA roles to data grids (H3) — modify render functions
7. Add `--purple` CSS variable (M2) — 1-line addition + 2-line update

### Medium-term (next sprint)
8. Read chart colors from CSS variables (M1)
9. Add responsive breakpoints for tablet (M4)
10. Increase touch target sizes (M5)
11. Add `aria-live` for auto-refresh announcements (L2)

### Long-term (nice-to-have)
12. Add SRI hash for CDN script (L3)
13. Fix body overflow for short viewports (M6)
14. Add shape-based status indicators alongside color (L1)
15. Replace emoji icon with accessible SVG (L4)

---

## Suggested Commands for Fixes

| Command | Issues addressed | Description |
|---------|-----------------|-------------|
| `/harden` | C1, C2, H1, H2, H3, H5, L1, L2, M3 | Fix contrast, focus, ARIA, motion, security — **run this first** |
| `/normalize` | M1, M2 | Align hard-coded colors with design token system |
| `/adapt` | M4, M5, M6 | Add responsive breakpoints and fix touch targets |
| `/polish` | H4, L4 | Final detail pass on footer contrast and icon a11y |
