# Shared Mold Database Design QA

- source visual truth path: `C:\Users\匡树杰\AppData\Local\Temp\codex-clipboard-2085c240-8fbc-44ce-b90e-f13f60cc97f3.png`
- implementation screenshot path: `D:\RR\royal-regent-nexus\.codex-phase1-qa\mold-database-implementation-revised-1280x720.png`
- focused detail screenshot: `D:\RR\royal-regent-nexus\.codex-phase1-qa\mold-database-detail-1280x720.png`
- focused proposal screenshot: `D:\RR\royal-regent-nexus\.codex-phase1-qa\mold-database-proposal-1280x720.png`
- normalized comparison: `D:\RR\royal-regent-nexus\.codex-phase1-qa\mold-database-side-by-side-revised.png`
- viewport: 1280 x 720 CSS px, device pixel ratio 1
- source pixels: 1918 x 934
- implementation pixels: 1280 x 720
- density normalization: the source was proportionally reduced to 1280 x 623 and vertically centered in a 1280 x 720 frame; the implementation was captured at native 1280 x 720. The two frames were combined into one 2560 x 720 comparison image.
- state: authenticated Huaxing user, formal database, shared mold catalog page 1 with 4,971 active definitions

## Comparison Scope

The supplied screenshot is the visual-language truth for the existing injection-scheduling product, not an exact mock of the new mold-database route. The comparison therefore checks shared shell, density, tokens, typography, table treatment and command hierarchy. The catalog, detail drawer and proposal drawer are new product states and were checked for consistency with that system rather than false pixel-for-pixel identity.

## Full-view Comparison Evidence

- Fonts and typography: both use the existing Segoe UI / PingFang SC / Microsoft YaHei stack, compact 9–13 px operational text, bold numeric KPI hierarchy and truncated dense-table copy.
- Spacing and layout rhythm: the 58 px dark top bar, compact white command bar, card strip, dense workspace, 7–11 px radii and shallow elevation match the scheduling page. The new page intentionally uses four master-data KPIs in one row instead of the scheduler's eight execution KPIs.
- Colors and visual tokens: navy shell, teal primary action, blue/amber/violet semantic cards, white work surface, cool gray grid and amber readiness chips use the same product tokens.
- Image quality and asset fidelity: no new raster illustrations or product images are required. Existing product mark, account menu and the installed Lucide icon set are reused; no placeholder or handcrafted replacement assets were introduced.
- Copy and content: the page uses production Chinese labels, separates company definition from factory readiness and clearly states that proposals do not directly activate data.

## Focused Region Evidence

- Detail drawer: captured separately and verified for basic definition, outputs, Huaxing capability/assets, permission-aware CNY pricing and governance notice. The source screenshot has no drawer state, so the check is internal token and hierarchy consistency.
- Proposal drawer: captured separately and verified for required fields, repeatable product outputs, optional capability, permission-aware per-shot CNY price, governance copy and sticky actions. The source screenshot has no proposal state, so the check is interaction density and consistency with the existing import dialog language.

## Comparison History

### Iteration 1

- [P1] Catalog search was hidden at the 1280 px browser viewport by an inherited scheduler breakpoint. This removed a core interaction from the new page.
  - Fix: added a more specific mold-database breakpoint override that keeps the search field visible with a 190 px minimum width.
- [P2] Imported machine-arm, fixture and data-quality codes were shown as `single`, `suction_cup` and `APPROVED_SOURCE`.
  - Fix: mapped those values to `单臂`, `吸盘` and `已审核来源` in the catalog and detail drawer.

### Iteration 2

The revised combined image shows the search field above the fold, localized operational labels, aligned command controls, readable table density and no clipped persistent actions. No actionable P0, P1 or P2 differences remain.

## Browser Verification

- Opened the page from the scheduling command-bar `正式数据库` control.
- Loaded 4,971 active definitions through the paginated catalog API.
- Opened and closed a real mold detail drawer.
- Opened the proposal drawer, filled required mold/product/reason fields, confirmed the submit action became enabled, then cancelled without writing production data.
- Verified the price and capability fields appear only with their scoped permissions.
- Browser console contained only Vite connection debug messages; zero warnings and zero errors.

## Residual Test Gap

The supplied visual target is the parent scheduling workspace rather than an exact mold-database mock. This prevents exact content-level comparison of the new catalog and drawers, but does not leave a P0/P1/P2 implementation issue.

final result: passed
