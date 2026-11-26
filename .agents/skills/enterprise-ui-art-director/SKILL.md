---
name: enterprise-ui-art-director
description: Design or substantially redesign Royal Regent Nexus enterprise screens with high visual craft, task-driven composition, scenario-aware density, distinctive visual identity, and purposeful motion. Use for new modules, substantial redesigns, and explicit design reviews; skip routine fixes, backend-only tasks, and rule configuration.
---

# Enterprise UI Art Director

Create a refined, complete product experience, not a generic admin template. Follow [DESIGN.md](../../../DESIGN.md) as the single source for hard rules, flexible defaults and creative freedom. High visual quality is a delivery requirement; functional correctness alone is insufficient.

## 1. Discover the product and design opportunity

- Follow [AGENTS.md](../../../AGENTS.md). Load relevant project-memory facts, target route, real fields, workflow, permissions, factory context and neighboring code. Inspect the nearest package.json, src/style.css, shared components and scoped exceptions; do not import unrelated restrictions.
- Identify the primary jobs, high-frequency operations, information hierarchy, actual data and viewport contract. Select one or a combination of DESIGN.md §2.1 scenarios and §8 density / §11 motion levels.
- For a new module or major redesign, use [UI_BRIEF_TEMPLATE.md](../../../docs/frontend/UI_BRIEF_TEMPLATE.md). Establish visual references: user-supplied material first, existing strong project screens or Design Lab if implemented, otherwise a task-specific sketch or runnable local prototype. Label conceptual references and fixture data; no production data mutation.
- Explore meaningfully different compositions (e.g. dense split workspace vs timeline-first, dashboard vs device-first). Choose by task efficiency, distinctiveness and coherence; document the chosen direction and one rejected alternative concisely. Do not automatically copy adjacent screens or the default PageHeader/Card/SectionPanel composition.

## 2. Translate the concept into real UI

- Preserve reliable shared interaction primitives, keyboard/focus semantics and public contracts. Create module-specific visualizations, device panels, workflows, and compositions freely in the module scope. Expand shared variants only when justified by reuse and impact assessment.
- Apply the brand and state semantics, but adapt palette, typography, spacing, materials, layout, SVG and motion to the chosen scenario. Use semantic tokens or named, scoped visual variables; no blind dependency additions. Follow DESIGN.md §3 for dependency decisions.
- Design the entire experience: real content hierarchy, empty/loading/error/read-only/permission states, long text, dense data, keyboard and narrow screen behavior. Useful visualizations and delightful interactions should clarify real tasks, not serve as decorative quotas.
- Craft purposeful feedback and continuity; distinguish high-frequency work from immersive presentation. Respect reduced motion/transparency and measured performance.
- Review the rendered composition before considering implementation complete. If a screen is only an ordinary header, default cards, and a table without a task-driven design rationale, reconsider layout and hierarchy rather than adding decorative effects.

## 3. Verify and hand off

- Run [visual-qa-loop](../visual-qa-loop/SKILL.md) and follow DESIGN.md §17.1 for technical QA. Share current evidence instead of duplicating checks.
- For new modules and major redesigns, obtain the independent design review in DESIGN.md §17.2. A reviewer who did not implement the change examines the actual rendered page, the brief and the relevant reference. Review-only tasks report findings without code changes.
- A REWORK decision is a delivery blocker even when builds and functional tests pass. Rework the evidenced regions, recapture matching screenshots, rerun affected tests and interactions, and obtain re-review. If independent review or browser evidence is unavailable, record UNVERIFIED; never substitute self-review or an aesthetic score.
- Report the selected scene/density/motion, composition rationale, actual evidence, design review findings and unresolved items. Do not equate visual approval with business or production acceptance.
