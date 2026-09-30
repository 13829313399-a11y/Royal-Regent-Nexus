<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import { Printer, X } from '@lucide/vue'

const props = defineProps<{ title: string; open: boolean }>()
const emit = defineEmits<{ close: []; 'after-close': [] }>()
const dialog = ref<HTMLDialogElement | null>(null)
const present = ref(props.open)
const phase = ref<'entering' | 'open' | 'exiting'>('open')
const titleId = useId()
let sequence = 0
let activeAnimation: Animation | null = null
let previousFocus: HTMLElement | null = null
let motionQuery: MediaQueryList | null = null

function cancelAnimation() {
  if (!activeAnimation) return
  activeAnimation.onfinish = null
  activeAnimation.oncancel = null
  activeAnimation.cancel()
  activeAnimation = null
}

function reducedMotion() { return motionQuery?.matches ?? false }

function restoreFocus() {
  const target = previousFocus?.isConnected
    ? previousFocus
    : document.querySelector<HTMLElement>('#tdp-main')
  target?.focus({ preventScroll: true })
  previousFocus = null
}

function finishClose(token: number) {
  if (token !== sequence || props.open) return
  cancelAnimation()
  const node = dialog.value
  if (node?.open) {
    if (typeof node.close === 'function') node.close()
    else node.removeAttribute('open')
  }
  present.value = false
  emit('after-close')
  void nextTick(restoreFocus)
}

async function syncOpen(open: boolean) {
  const token = ++sequence
  cancelAnimation()
  if (open) {
    if (!present.value) present.value = true
    await nextTick()
    if (token !== sequence || !props.open) return
    const node = dialog.value
    if (!node) return
    if (!node.open) {
      previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
      if (typeof node.showModal === 'function') node.showModal()
      else node.setAttribute('open', '')
    }
    phase.value = 'entering'
    if (reducedMotion() || typeof node.animate !== 'function') {
      phase.value = 'open'
      return
    }
    activeAnimation = node.animate(
      [
        { opacity: 0, transform: 'translateY(8px) scale(.99)' },
        { opacity: 1, transform: 'translateY(0) scale(1)' },
      ],
      { duration: 240, easing: 'cubic-bezier(.16, 1, .3, 1)' },
    )
    activeAnimation.onfinish = () => {
      if (token === sequence) phase.value = 'open'
      activeAnimation = null
    }
    return
  }

  if (!present.value) return
  const node = dialog.value
  if (!node?.open || reducedMotion() || typeof node.animate !== 'function') {
    finishClose(token)
    return
  }
  phase.value = 'exiting'
  activeAnimation = node.animate(
    [
      { opacity: 1, transform: 'translateY(0) scale(1)' },
      { opacity: 0, transform: 'translateY(5px) scale(.995)' },
    ],
    { duration: 160, easing: 'cubic-bezier(.2, .8, .2, 1)', fill: 'forwards' },
  )
  activeAnimation.onfinish = () => finishClose(token)
}

function onMotionChange() {
  if (!reducedMotion()) return
  if (phase.value === 'exiting') finishClose(sequence)
  else if (phase.value === 'entering') {
    cancelAnimation()
    phase.value = 'open'
  }
}

watch(() => props.open, open => { void syncOpen(open) }, { immediate: true, flush: 'post' })
onMounted(() => {
  motionQuery = window.matchMedia?.('(prefers-reduced-motion: reduce)') ?? null
  motionQuery?.addEventListener('change', onMotionChange)
})
onBeforeUnmount(() => {
  sequence++
  cancelAnimation()
  motionQuery?.removeEventListener('change', onMotionChange)
  if (dialog.value?.open) {
    if (typeof dialog.value.close === 'function') dialog.value.close()
    else dialog.value.removeAttribute('open')
  }
  restoreFocus()
})
</script>

<template>
  <dialog
    translate="no"
    v-if="present"
    ref="dialog"
    class="legacy-dialog three-d-workspace tdp-theme"
    :class="`tdp-dialog--${phase}`"
    :aria-labelledby="titleId"
    @cancel.self.prevent.stop="emit('close')"
    @click="$event.target === dialog && emit('close')"
  >
    <header>
      <div class="tdp-dialog-heading"><span class="tdp-dialog-heading-icon" aria-hidden="true"><Printer :size="16" /></span><h2 :id="titleId">{{ title }}</h2></div>
      <button type="button" aria-label="关闭" @click="emit('close')"><X :size="18" aria-hidden="true" /></button>
    </header>
    <div class="legacy-dialog-body"><slot /></div>
  </dialog>
</template>
