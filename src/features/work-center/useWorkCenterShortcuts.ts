export function useWorkCenterShortcuts(handle: (key: string) => boolean) {
  return (event: KeyboardEvent) => {
    if (event.defaultPrevented || event.isComposing || event.ctrlKey || event.metaKey || event.altKey) return
    const target = event.target instanceof Element ? event.target : null
    if (
      document.querySelector(
        '[role="dialog"][data-state="open"],[data-slot="popover-content"][data-state="open"],[role="listbox"][data-state="open"],[role="menu"][data-state="open"]',
      )
    )
      return
    if (
      target?.closest(
        'input,textarea,select,[contenteditable]:not([contenteditable="false"]),[role="combobox"],[role="textbox"],[role="dialog"]',
      )
    )
      return
    if (
      event.key === 'Enter' &&
      target?.closest('button,a,[role="tab"],[role="checkbox"]') &&
      !target.closest('[data-work-entry]')
    )
      return
    if (handle(event.key.length === 1 ? event.key.toLowerCase() : event.key)) event.preventDefault()
  }
}
