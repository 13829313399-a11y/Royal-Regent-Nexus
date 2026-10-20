---
name: visual-qa-loop
description: Verify Royal Regent Nexus frontend appearance and interactions with Chrome DevTools MCP after UI changes or an explicit visual QA request. Compare references, inspect relevant states and recheck evidenced defects. Skip backend-only, documentation and workflow-configuration changes.
---

# Visual QA Loop

Verify the actual rendered page against the requested outcome and the relevant [DESIGN.md](../../../DESIGN.md) baseline. Follow repository [AGENTS.md](../../../AGENTS.md); a review-only request does not authorize implementation.

## Prepare the correct environment

- Read the affected package's dev and test scripts and the task's route, account/factory context and acceptance criteria. Reuse an appropriate running local server after confirming its source and port; if UI implementation includes local preview, use the existing loopback-bound dev command when needed. Honor requests that limit work to analysis or configuration.
- Use Chrome DevTools MCP and its current tool schemas. It replaces Browser/IAB-first and automatic Playwright fallback routing for this workflow. Use the Playwright CLI Skill only on an explicit user request; existing automated tests retain their purpose. Do not install another plugin, MCP or package merely to follow this skill. If DevTools or the target environment is unavailable, report the specific limitation and what remains unverified; continue independent work without silently switching browser tools.
- For repeated QA already covered by another active workflow, reuse its current-route evidence and inspect only the remaining gaps.

## Chrome DevTools MCP operations

- Use `list_pages` to check the connection and identify the relevant page. Reuse it or call `new_page` for the exact URL, then retain the returned `pageId` throughout the flow; use `navigate_page` for navigation or reload.
- Read `take_snapshot` before targeting element UIDs. Exercise relevant actions with `click`, `fill_form` or `press_key`, then refresh the snapshot after navigation or state changes and verify the result. Use `evaluate_script` for read-only page identity, layout, focus or viewport checks.
- Inspect `list_console_messages` and `list_network_requests`; read individual messages/requests when needed to distinguish expected responses from failures. Do not claim a clean console while unexplained errors remain.
- Set viewports and reduced-motion preferences with `emulate`, including all settings still needed in each call. Record actual `innerWidth` and `innerHeight` rather than assuming window dimensions are content dimensions.
- Capture `take_screenshot` evidence. Save only to a permitted evidence path; if the MCP rejects `filePath`, omit it to return the screenshot inline and state that the requested file was not saved. Do not expand permissions or use a different browser to bypass the path restriction.

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
- Report changed files, checked routes/states/viewports, actual screenshot paths or inline-only evidence, executed checks and remaining limitations. If no browser ran, state that visual QA is unverified.

Defect record: `Priority | Route / state / viewport | Evidence | Problem | Fix or recommendation | Recheck result`.
