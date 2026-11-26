---
name: visual-qa-loop
description: Verify Royal Regent Nexus frontend appearance and interactions with Chrome DevTools MCP; for new modules and substantial redesigns, require a separate independent design review and rework of material visual defects. Skip backend-only, documentation and workflow configuration.
---

# Visual QA Loop

Follow [AGENTS.md](../../../AGENTS.md), [DESIGN.md](../../../DESIGN.md) §17, and the relevant [frontend workflow](../../../docs/frontend/WORKFLOWS.md). A review-only request does not authorize code changes.

## 1. Establish the actual test environment

- Read affected package scripts, route, acceptance criteria, account/factory context and design brief/reference. Reuse an appropriate local server after confirming source and port; use the existing loopback-bound dev command when authorized and necessary.
- Use Chrome DevTools MCP and its current schemas. It replaces Browser/IAB-first and automatic Playwright fallback routing. Playwright CLI Skill is only used on explicit user request; existing automatic tests retain their purpose. Do not install another plugin/MCP/package merely for this workflow.
- On tool/environment failure, follow WORKFLOWS.md, state specific limitations and unverified items; continue independent work without silently switching tools. Reuse equivalent current-route evidence.

## 2. Technical QA (DESIGN.md §17.1)

- `list_pages` identifies the relevant page; reuse or `new_page` for the exact URL, retain returned pageId, use `navigate_page` to navigate/reload. Read `take_snapshot` before targeting UIDs; exercise `click`, `fill_form`, `press_key` as relevant; refresh snapshot after transitions. `evaluate_script` may inspect identity, geometry, focus and viewport read-only.
- Inspect `list_console_messages` and `list_network_requests`; inspect individual messages/requests as needed, distinguishing expected from unexplained failures. DOM alone does not prove visual quality.
- Select viewports from DESIGN.md §17 and page contract: new/major ordinary pages cover required breakpoint matrix plus actual desktop such as 1366×768 or 1440×900, add 1920×1080 when useful; fixed-width workspaces verify minimum and fallback; small fixes target relevant widths. Record actual innerWidth/innerHeight; when using emulate include continuing settings and reduced-motion preferences.
- Exercise changed interactions and a main journey, covering relevant loading/empty/error/permission/read-only/long-text states available in authorized test conditions. Verify keyboard/focus, contrast, scrolling, overlays and reduced motion/transparency as relevant. Mark unavailable states unverified.
- Capture `take_screenshot` evidence. Save only to permitted paths; if denied omit filePath for inline evidence and report unsaved. Do not widen permissions or change tools to bypass restrictions.

## 3. Independent design review (DESIGN.md §17.2)

- Mandatory for new modules and substantial UI redesigns, separate from technical QA. Explicit design review requests follow the same visual rubric without requiring implementation. Review the real rendered page and main interaction against the brief/reference; a screenshot plus relevant actual interaction observation is evidence, not just code or DOM.
- The reviewer must not have implemented the change; use an available independent agent/session or user review. Supply route, tested state/viewport, screenshots, brief/reference and relevant source/diff when needed. Do not present implementer self-assessment as independent. If unavailable, mark design review UNVERIFIED.
- Assess composition and distinctiveness, visual craft/brand, density and efficiency, meaningful business visualization, interaction craft and overall product completion. Use DESIGN.md's rubric. Distinguish functional bugs from design findings. No pass merely because it runs, matches tokens or has no overflow. No arbitrary score or decoration count.
- Record each applicable dimension PASS / REWORK / UNVERIFIED, with actual visual/interaction evidence, specific region, reason and improvement direction (or justified N/A). A plain, mechanical template, weak hierarchy or visibly unfinished UI that misses the brief is a material design defect.
- If REWORK and implementation is authorized, redesign affected layout, hierarchy, components or interactions; do not mask structural issues with decoration. Reload, recheck same route/state/viewport and repeat independent review of affected findings. Reuse unchanged evidence. Continue until required checks pass or a concrete blocker prevents completion; do not impose fixed rounds. Technical pass + design REWORK/UNVERIFIED is not complete.

## 4. Evidence and boundaries

- Preserve real user records/production data. Use authorized test fixtures for mutating journeys. Keep QA artifacts in existing permitted local locations outside source commits unless explicitly requested; preserve historical evidence.
- Report changed files, actual commands/results, routes/states/viewports, screenshot paths or inline evidence, technical QA status, design review status, reviewer, findings and recheck result. Build/type/unit, browser, design and production/device acceptance establish different facts.
- If no browser ran, report browser QA unverified. If no independent reviewer, report design review unverified. Do not claim full completion when required gates are unresolved.

Defect record: `Type (technical/design) | Priority | Route/state/viewport | Evidence | Problem | Fix | Recheck`.
