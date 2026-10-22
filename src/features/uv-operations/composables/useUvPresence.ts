import { nextTick, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { useUvMotion } from './useUvMotionPreference'

/** Presentation only: never creates a business request or changes its operation id. */
export function useUvPresence(element: Ref<HTMLElement | null>, enterToken = '--uv-motion-dialog-enter', motion = useUvMotion()) {
  const present = ref(false), phase = ref<'closed' | 'opening' | 'open' | 'closing'>('closed')
  let generation = 0, timer: ReturnType<typeof setTimeout> | undefined
  let animation: Animation | undefined
  let afterClose: (() => void) | undefined
  function capture() {
    if (!present.value || !element.value) return undefined
    const style = getComputedStyle(element.value)
    return { opacity: style.opacity, transform: style.transform }
  }
  function cancel() { generation++; clearTimeout(timer); timer = undefined; if(animation){animation.onfinish=null;animation.cancel();animation=undefined} }
  function settle() {
    cancel()
    if (phase.value === 'closing') { present.value = false; phase.value = 'closed'; const done = afterClose; afterClose = undefined; done?.() }
    else if (present.value) phase.value = 'open'
  }
  async function schedule(token: string, from?: {opacity:string;transform:string}) {
    const version = generation
    await nextTick()
    if (version !== generation) return
    const computed = element.value ? getComputedStyle(element.value) : undefined
    const value = computed?.getPropertyValue(token).trim() ?? '0'
    const duration = (parseFloat(value) || 0) * (value.endsWith('ms') ? 1 : 1000)
    if (!motion.allowed.value || !duration) settle()
    else {
      const closing = phase.value === 'closing', drawer = enterToken.includes('drawer')
      const distance = computed?.getPropertyValue(drawer?'--uv-motion-drawer-distance':'--uv-motion-dialog-distance').trim() || '0px'
      const offset = {opacity:'0',transform:`translate${drawer?'X':'Y'}(${distance})`}, visible = {opacity:'1',transform:'none'}
      if(element.value?.animate){
        animation=element.value.animate([from??(closing?visible:offset),closing?offset:visible],{duration,easing:computed?.getPropertyValue(closing?'--uv-motion-ease':'--uv-motion-ease-enter').trim()||'ease',fill:'both'})
        animation.onfinish=()=>{if(version===generation)settle()}
      }
      timer=setTimeout(()=>{if(version===generation)settle()},duration)
    }
  }
  function open() { const from=capture();cancel(); afterClose = undefined; present.value = true; phase.value = 'opening'; void schedule(enterToken,from) }
  function close(done?: () => void, immediate = false) {
    const from=capture();cancel(); afterClose = done
    if (!present.value) { settle(); afterClose = undefined; done?.(); return }
    phase.value = 'closing'
    if (immediate || !motion.allowed.value) settle(); else void schedule('--uv-motion-leave',from)
  }
  watch(motion.allowed, allowed => { if (!allowed) settle() }, { flush: 'sync' })
  onBeforeUnmount(() => { cancel(); afterClose = undefined })
  return { present, phase, open, close, motion }
}
