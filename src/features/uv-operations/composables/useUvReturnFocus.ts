import { onBeforeUnmount, type Ref } from 'vue'

export function uvReturnTarget(candidate: HTMLElement | null) {
  const usable = candidate?.isConnected && candidate!==document.body && candidate!==document.documentElement && !candidate.closest('[inert],[hidden]') && !candidate.matches(':disabled') && candidate.getClientRects().length && getComputedStyle(candidate).visibility !== 'hidden'
  return usable ? candidate : document.querySelector<HTMLElement>('[data-uv-focus-fallback]')
}

export function useUvReturnFocus(dialog: Ref<HTMLDialogElement | null>) {
  let trigger: HTMLElement | null = null
  let observer: MutationObserver | undefined, disposed=false
  const anotherModal=()=>[...document.querySelectorAll<HTMLElement>('dialog[open],[aria-modal="true"]')].some(el=>el!==dialog.value&&el.getClientRects().length)
  function stopWatching(){observer?.disconnect();observer=undefined;document.removeEventListener('focusin',stopWatching)}
  function capture() { stopWatching();const active=document.activeElement; if(active instanceof HTMLElement&&!dialog.value?.contains(active))trigger=active }
  function restore() {
    if(!trigger)return
    if(anotherModal())return
    const target=uvReturnTarget(trigger);trigger=null
    target?.focus({preventScroll:true})
    if(!target||disposed)return
    // A successful command may remove its trigger only after the following list refresh.
    // Watch that DOM lifetime until focus moves elsewhere, without delaying close.
    stopWatching()
    observer=new MutationObserver(()=>{
      if(target.isConnected)return
      const shouldRestore=document.activeElement===document.body&&!anotherModal()
      stopWatching()
      if(shouldRestore)uvReturnTarget(null)?.focus({preventScroll:true})
    })
    observer.observe(document.body,{childList:true,subtree:true})
    document.addEventListener('focusin',stopWatching)
  }
  onBeforeUnmount(()=>{disposed=true;stopWatching()})
  return { capture, restore }
}
