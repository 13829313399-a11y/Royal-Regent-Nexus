import { onBeforeUnmount, watch } from 'vue'
let owners = 0, previous = ''
export function useUvScrollLock(locked: () => boolean) {
  let owns = false
  function release() { if (owns) { owns = false; if (--owners === 0) document.body.style.overflow = previous } }
  watch(locked, value => {
    if (value && !owns) { if (owners++ === 0) { previous = document.body.style.overflow; document.body.style.overflow = 'hidden' }; owns = true }
    else if (!value) release()
  }, { immediate: true, flush: 'sync' })
  onBeforeUnmount(release)
}
