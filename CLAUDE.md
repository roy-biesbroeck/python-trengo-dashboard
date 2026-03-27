# Trengo Dashboard

Real-time ticket statistics dashboard for Trengo, built with Flask + vanilla HTML/CSS/JS.

## Design Context

### Users
Support team members viewing a **wall-mounted, always-on display** in a team room. The dashboard shows live Trengo ticket statistics — users glance at it throughout the day to stay aware of queue health, team workload, and ticket aging. Readability at a distance and at a glance is critical. The UI language is Dutch (nl-NL).

### Brand Personality
**Friendly, Warm, Approachable** — the dashboard should feel inviting and human, not cold or intimidating. It serves a support team, so it should reflect the same approachability they bring to customers.

### Aesthetic Direction
- **References:** Notion and Stripe — clean, friendly, well-structured with clear visual hierarchy
- **Anti-references:** Avoid dense/dark monitoring tools (Grafana/Datadog style) or cold corporate dashboards
- **Theme:** Light mode with warm neutrals
- **Typography:** System font stack, generous sizing for wall-display legibility
- **Layout:** Spacious cards, clear groupings, breathing room between sections

### Color System
- **Primary:** #3b82f6 (blue) — actions, totals, brand accent
- **Status semantic:** green (#16a34a) = new/unassigned, amber (#d97706) = assigned, red (#dc2626) = critical
- **Closed tickets:** #8b5cf6 (purple)
- **Age gradient:** blue → green → lime → amber → orange → red (fresh → stale)
- **Neutrals:** #f1f5f9 background, #ffffff cards, #1e293b text, #e2e8f0 borders

### Accessibility Requirements
- **WCAG AA compliance** — contrast ratios 4.5:1 (normal text), 3:1 (large text)
- Color must never be the only status indicator (pair with labels/icons)
- Respect `prefers-reduced-motion`
- Support colorblind-safe distinctions

### Design Principles
1. **Glanceable at 3 meters** — large type, strong hierarchy, high contrast
2. **Warm, not sterile** — friendly language, generous spacing, subtle warmth
3. **Color tells the story** — preserve semantic meaning, support colorblind users
4. **Less is more** — clean structure, clear hierarchy, no unnecessary decoration
5. **Accessible by default** — WCAG AA is the floor, not the ceiling
