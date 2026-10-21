---
name: enterprise-ui-art-director
description: Design new or substantially redesigned enterprise screens in Royal Regent Nexus, including information hierarchy, layout and UI states. Use for explicit UI design reviews; skip routine bug fixes, minor styling corrections, backend-only work and workflow configuration.
---

# Enterprise UI Art Director

Adapt the requested enterprise page to its real users and business operations while preserving the project's established design system.

## Establish the baseline

- Follow the repository [AGENTS.md](../../../AGENTS.md) and retrieve only relevant project-memory facts.
- Read relevant sections of [DESIGN.md](../../../DESIGN.md), the actual route, neighboring pages and affected components. Check global tokens in `src/style.css`, shared components in `src/components/ui/` and `src/components/common/`, and documented feature-specific exceptions.
- Inspect the nearest package and actual implementation before choosing framework-specific patterns. The main application and a separately built subproject may use different frameworks.
- Identify the primary user action, real fields, data density, permissions, factory context and supported viewports. Reference images guide appearance; they do not redefine business contracts or authorize extra functionality.

## Design and implement within scope

1. For a new module or substantial redesign, fill the relevant parts of the [UI brief](../../../docs/frontend/UI_BRIEF_TEMPLATE.md). Explain the intended hierarchy and which existing components and tokens will be reused. For a review, provide findings without implementing changes unless requested.
2. Keep the design direction concise. Explore alternatives only when an unresolved layout choice materially affects usability. A new decorative motif or multiple concepts are optional, not deliverables for every page.
3. Specify the main operation, must-see information, filters, working surface and secondary details. Preserve useful density without shrinking essential text or hiding actions behind hover-only controls.
4. Describe relevant default, loading, empty, error, permission-restricted and detail states. Reuse existing state semantics, focus behavior and responsive patterns.
5. When implementation is authorized, reuse or deliberately extend existing components and tokens. Keep feature-specific effects scoped, preserve documented exceptions and take motion values from the project baseline. Do not change API contracts, permissions or factory isolation to match a mockup.
6. Use Chrome DevTools MCP to inspect the implemented route through the companion [visual-qa-loop](../visual-qa-loop/SKILL.md). Do not select the Playwright CLI Skill automatically for this phase. When another active skill already performs equivalent DevTools checks, share its evidence instead of repeating the entire workflow.

## Evidence and handoff

Report the design decision, reused components/tokens, affected states and intentional reference deviations. For implementation, include actual browser findings and evidence, or clearly identify verification that remains unavailable. Use the repository's existing delivery format; do not replace defect evidence with an aesthetic score or claim that design review proves business acceptance.
