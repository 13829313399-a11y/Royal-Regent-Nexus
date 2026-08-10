# Injection Scheduling Backlog Deletion Design QA

- source visual truth path: `browser:Selected browser region` from the current user comment (Huaxing backlog view before the delete action)
- implementation screenshot path: `D:\RR\royal-regent-nexus\artifacts\design-qa\backlog-delete-list.png`
- confirmation screenshot path: `D:\RR\royal-regent-nexus\artifacts\design-qa\backlog-delete-dialog.png`
- viewport: 1538 x 698 CSS px
- source pixels: browser-comment capture at the same 1538 x 698 page viewport
- implementation pixels: 1538 x 697
- CSS size and density: desktop in-app browser at devicePixelRatio 1.25; screenshot API returned 1538 x 697 pixels
- density normalization: source browser comment and implementation use the same route, factory, authenticated data state and desktop viewport; no rescaling was used for the visual comparison
- state: authenticated Huaxing formal-data workspace, `待排订单` active, three imported backlog orders visible; implementation adds a delete action and its reason-required confirmation dialog

## Full-view Comparison Evidence

- Fonts and typography: the existing Chinese UI font stack, weights, compact labels and row hierarchy remain unchanged. The new `删除` label uses the same small button typography and stays legible.
- Spacing and layout rhythm: the three order rows retain their original height, left priority marker, order details and right-side qualification facts. The compact delete button sits beside the existing append action without clipping, horizontal overflow or row growth.
- Colors and visual tokens: the existing navy, teal, slate and white surfaces remain unchanged. Red is reserved for the destructive cancellation action, warning notice and confirm button.
- Image quality and asset fidelity: this workflow contains no raster product imagery. Trash, warning, close and loading icons use the installed Lucide library; no handcrafted SVG, CSS drawing, emoji or placeholder asset was introduced.
- Copy and content: the action is named `删除` in the list and `删除待排单` in confirmation. The dialog explains that the row leaves scheduling while its workbook, order version and audit history remain preserved.

## Focused Region Comparison Evidence

The source selection covers the complete backlog list at `x=22.4, y=330.4, width=1484.8, height=268.8`. At the same viewport, `backlog-delete-list.png` shows the intentional delta: each row gains one compact red bordered delete button aligned with the disabled append button. `backlog-delete-dialog.png` verifies the focused confirmation state at original resolution, including order context, warning copy, reason field, counter and footer actions.

## Findings

- No actionable P0, P1 or P2 visual mismatch remains.
- P3 follow-up only: the bottom backlog dock uses a two-column wrapped action group on each compact card; this preserves all actions but may benefit from an overflow menu if more card actions are added later.

## Comparison History

### Iteration 1

- Finding: adding a second direct row button would exceed the original single-action grid column and compress button copy.
- Fix: grouped row actions into a responsive right-aligned action area, widened only the action track, and kept all order-detail columns flexible.
- Post-fix evidence: `backlog-delete-list.png` shows all three rows at their original height with fully visible append and delete controls; no P0, P1 or P2 issue remains.

## Interaction and Accessibility Verification

- Verified all three imported backlog rows expose an enabled `删除` action for a scheduling editor.
- Verified the dialog uses `role="dialog"`, `aria-modal="true"`, a labelled title and an explicit close button.
- Verified confirmation is disabled with an empty reason and enabled after entering `重复下单`.
- Verified `取消` closes the dialog without deleting formal data; the destructive confirm action was intentionally not submitted against the user's live local records.
- Browser console after the final interaction pass: zero warnings and zero errors.

## Verification Notes

- Backend manual/imported backlog lifecycle tests: 3 passed.
- Existing published-task withdrawal regression: 1 passed.
- Frontend backlog/manual/withdraw tests: 7 passed.
- Production frontend type-check and build: passed.
- Python compilation and `git diff --check`: passed.
- Live backend route check: `/api/injection-scheduling/backlog/{order_id}/cancel` is present after restart.

final result: passed
