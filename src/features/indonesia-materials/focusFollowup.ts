/** Keep a targeted editor visible after switching the workspace tab. */
export function focusFollowup(root: HTMLElement | null | undefined, field?: string) {
  if (!root) return
  if (root.closest<HTMLElement>('[role="tabpanel"]')?.style.display === 'none') return
  const label = field ? [...root.querySelectorAll('label')].find(node =>
    node.querySelector('span')?.textContent?.replace(/\s*\*$/, '').trim() === field) : undefined
  const target = label?.querySelector<HTMLElement>('input, select, textarea') ?? root
  target.scrollIntoView?.({ block: 'center' })
  if (target === root) root.tabIndex = -1
  target.focus({ preventScroll: true })
}
