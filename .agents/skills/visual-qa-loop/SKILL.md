---
name: visual-qa-loop
description: Verify Royal Regent Nexus frontend appearance and interactions in a real browser after UI changes or an explicit visual QA request. Compare references, inspect relevant states and recheck evidenced defects. Skip backend-only, documentation and workflow-configuration changes.
---

# Visual QA Loop

Verify the actual rendered page against the requested outcome and the relevant [DESIGN.md](../../../DESIGN.md) baseline. Follow repository [AGENTS.md](../../../AGENTS.md); a review-only request does not authorize implementation.

## Prepare the correct environment

- Read the affected package's dev and test scripts and the task's route, account/factory context and acceptance criteria. Reuse an appropriate running local server after confirming its source and port; if UI implementation includes local preview, use the existing loopback-bound dev command when needed. Honor requests that limit work to analysis or configuration.
- Use available browser tools and their relevant usage instructions. Do not install another plugin, MCP or package merely to follow this skill. If the environment or access is unavailable, report the specific limitation and what remains unverified.
- For repeated QA already covered by another active workflow, reuse its current-route evidence and inspect only the remaining gaps.

## Inspect, correct and recheck

1. Open the exact route. Confirm the expected source/environment, successful rendering, appropriate account/factory context, and any relevant console or request errors. Inspect the DOM before treating an apparently blank area as missing content.
2. Select viewports from DESIGN.md section 17 and the page's support contract. For new or substantially redesigned ordinary pages, cover the required breakpoint matrix and representative desktop sizes such as 1366×768 or 1440×900; add 1920×1080 for wide layouts. Fixed-width workspaces use their declared minimum width and small-screen fallback. For a narrow fix, target the affected viewport plus the relevant breakpoint. Supplemental mobile/tablet examples never replace the project's required matrix. Record what was actually checked.
3. Exercise the changed interaction and a relevant main journey: navigation, filtering, table overflow, drawer/modal behavior, keyboard focus or another affected operation. Inspect loading, empty, error, permission and long-text states when available in authorized local test conditions; mark inaccessible states as unverified.
4. Review hierarchy, spacing, text wrapping, data alignment, density, scrolling, overlays, icon consistency, contrast and reduced-motion behavior as relevant. Compare supplied references by region and record intentional deviations required by real product constraints.
5. Record evidenced defects with priority, route/state/viewport and screenshot or DOM evidence. If fixing is in scope, repair the relevant defect, reload and inspect the affected behavior again. Continue while material defects remain; stop when the acceptance criteria are met or a concrete blocker prevents further verification. Do not invent defects or make changes to satisfy a fixed number of rounds.

## Verification boundaries

- Preserve real user records and production data; do not create QA states by altering them. Use an existing authorized test environment for mutating journeys.
- Use the repository's existing local evidence location, keep screenshots and temporary QA data outside source commits unless explicitly requested, and do not delete historical evidence as part of a visual check.
- Build/type checks and unit tests establish different facts from browser observation. A rendered page does not establish production rollout, database correctness or physical-device acceptance.
- Report changed files, checked routes/states/viewports, actual screenshot paths, executed checks and remaining limitations. If no browser ran, state that visual QA is unverified.

Defect record: `Priority | Route / state / viewport | Evidence | Problem | Fix or recommendation | Recheck result`.
