---
name: enterprise-ui-art-director
description: Design new or substantially redesigned enterprise screens in Royal Regent Nexus with Apple VisionOS spatial hierarchy, minimalist breathing room, spring physics motion, expressive micro-interactions, and primitive-first assembly. Use for new modules, substantial redesigns, and explicit UI design reviews; skip routine bug fixes, minor styling corrections, backend-only work, and workflow configuration.
---

# Enterprise UI Art Director

Deliver modern, tactile, Apple VisionOS–inspired enterprise screens for Royal Regent Nexus without sacrificing operational clarity or business contracts. Reject legacy ERP aesthetics (gray bordered table walls, cramped forms, heavy fieldsets, stiff transitions).

## 1. Establish the Baseline

- Follow [AGENTS.md](../../../AGENTS.md) and load only relevant project-memory facts.
- Read [DESIGN.md](../../../DESIGN.md) (especially sections 2, 5–11, 16, 17), `src/style.css`, shared components in `src/components/ui/` and `src/components/common/`, and the target route's neighboring code. Only read a module file under [docs/frontend/exceptions/](../../../docs/frontend/exceptions/README.md) when working inside that module's scope.
- Inspect the nearest `package.json` before assuming framework conventions; do not add animation, component, or font dependencies.
- Identify the single primary user task, real fields, data density, permissions, factory isolation, and viewport contract. Reference visuals guide craft; they never alter API contracts, permissions, or factory boundaries.

## 2. Art Direction & Spatial Craft

Apply these concrete rules to every new page or substantial redesign:

1. **Four-Layer Spatial Hierarchy (DESIGN.md §7)**
   - **L0 Canvas**: `--background` with at most two restrained ambient glow pools (`--ambient-glow-primary` / `--ambient-glow-secondary`) behind content, never reducing text contrast.
   - **L1 Content**: Solid `bg-card`, 1px `--glass-stroke-subtle`, `shadow-elevation-1`, `rounded-2xl` panels / `rounded-xl` inner cards. **Keep tables, long lists, and form bodies solid—never apply `backdrop-filter` to scrolling rows or inputs.**
   - **L2 Chrome** (top bar, sidebar, floating toolbars, sticky headers, segmented controls): `--glass-surface-chrome`, `backdrop-blur-glass-md`, `saturate(var(--glass-saturate))`, 1px `--glass-stroke`, `--glass-highlight`, `shadow-elevation-2`.
   - **L3 Floating** (Dialog, Drawer, Popover, menus, Toast, command palette): `--glass-surface-float`, `backdrop-blur-glass-lg`, 1px `--glass-stroke`, `--glass-highlight`, `shadow-elevation-3`, `rounded-2xl`–`rounded-3xl`.
   - Never stack more than two blurred layers in the same viewport; always ensure glass sits over perceptible content or ambient glow and meets WCAG AA contrast.

2. **Minimalist Breathing Room & Typographic Tension (DESIGN.md §6, §8)**
   - Give every screen **one primary visual focal point** and **one primary action** (`Button` default variant).
   - Build hierarchy through scale, weight (`400`/`500`/`600` only), tight display tracking (`-0.02em`), `tabular-nums` for all numeric/code columns, and generous spacing (`40–64px` between major sections, `24–32px` desktop card padding, `≥40px` data row height).
   - Separate groups by whitespace and typography instead of nested borders or divider lines. Limit card nesting to **2 levels max**.
   - Keep secondary metadata, raw enums, revision hashes, and technical caveats out of the main canvas—place them in drawers, tooltips, or progressive disclosure.

3. **Physics-Driven Motion & Tactile Micro-Interactions (DESIGN.md §11)**
   - Use project motion tokens (`--motion-duration-*`, `ease-spring-smooth`, `ease-spring-snappy`, `ease-spring-bouncy`, `ease-standard`). Reject linear and default `ease` curves for spatial transitions.
   - Animate **only `transform` and `opacity`** (use FLIP or `TransitionGroup` for layout shifts; never `transition: all`). Keep animations interruptible and spatially continuous (overlays scale `0.96 → 1` from trigger origin and return along the same path).
   - Craft responsive feedback on every interactive element (≤100ms perceived start): button press `scale(0.97)`, interactive card lift `≤2px` + `shadow-elevation-2`, spring-gliding tab/segmented indicator, smooth input focus ring, subtle check-mark/copy confirmation, and shimmer skeletons matching final geometry.
   - Honor `prefers-reduced-motion` and `prefers-reduced-transparency` cleanly; never replay entry choreography on background refresh or fabricate counting animations for unverified business metrics.

4. **Primitive-First Assembly (DESIGN.md §9)**
   - Assemble strictly in order: `src/components/ui/` → `src/components/common/` → `reka-ui` primitives → generate missing primitives into `src/components/ui/` via `npx shadcn-vue add <component>` and style with project tokens → module-local components only as last resort.
   - **Never hand-roll native `<select>`, nested `<details>`, raw `<dialog>` backdrops, `title` tooltips, or custom unstyled checkboxes/tabs** for business interactions (except documented §15 module exceptions or print views).
   - Never hardcode hex colors, ad-hoc box-shadows, or magic-number durations when semantic/spatial/motion tokens apply.

## 3. Workflow, Design Review & Anti-Patterns

- **Brief first**: For a new module or substantial redesign, fill the relevant sections of [UI_BRIEF_TEMPLATE.md](../../../docs/frontend/UI_BRIEF_TEMPLATE.md), specifying L0–L3 allocation, primary focus, reused primitives, all states (default, loading, empty, error, permission-restricted, read-only, success), and key micro-interactions. For a review-only request, report findings without modifying code.
- **Anti-pattern check (reject before handoff)**:
  - Gray-on-gray bordered table walls, heavy `<fieldset>` frames, double borders, or >2 levels of nested cards.
  - Engineering disclaimers or defensive notices dominating the primary workspace.
  - Multiple competing primary buttons, red used for non-destructive emphasis, rainbow gradients, neon glows, or Emoji icons.
  - Glass blur on table rows/form inputs, abrupt pop-in overlays without exit motion, or fabricated placeholder KPIs.

## 4. Visual Verification & Handoff

- After authorized implementation, inspect the real rendered route with Chrome DevTools MCP via [visual-qa-loop](../visual-qa-loop/SKILL.md). Do not switch automatically to Playwright CLI. When another active skill already performs equivalent DevTools checks, share evidence instead of duplicating work.
- Verify both technical QA (DESIGN.md §17.1) and aesthetic QA (DESIGN.md §17.2), including `prefers-reduced-motion` and `prefers-reduced-transparency`.
- Report design decisions, L0–L3 surface plan, reused/added primitives and tokens, affected states, intentional reference deviations, and actual browser evidence or verification gaps. Do not substitute an aesthetic score for defect evidence or claim visual review proves business acceptance.
