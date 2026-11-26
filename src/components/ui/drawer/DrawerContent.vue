<script setup lang="ts">
import type { HomeMotion } from '@/composables/useHomeAppearance'
import type { DialogContentEmits, DialogContentProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { computed } from 'vue'
import { X } from '@lucide/vue'
import {
  DialogClose,
  DialogContent,
  DialogOverlay,
  DialogPortal,
  useForwardPropsEmits,
} from 'reka-ui'
import { cn } from '@/lib/utils'

defineOptions({
  inheritAttrs: false,
})

interface Props extends DialogContentProps {
  motion?: HomeMotion
  side?: 'right' | 'left' | 'bottom'
  class?: HTMLAttributes['class']
  overlayClass?: HTMLAttributes['class']
  showCloseButton?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  side: 'right',
  showCloseButton: true,
})
const emits = defineEmits<DialogContentEmits>()

const delegatedProps = computed(() => {
  const {
    side: _side,
    motion: _motion,
    class: _class,
    overlayClass: _overlayClass,
    showCloseButton: _showCloseButton,
    ...delegated
  } = props
  return delegated
})

const forwarded = useForwardPropsEmits(delegatedProps, emits)

const sideClasses: Record<'right' | 'left' | 'bottom', string> = {
  right:
    'ui-drawer-right inset-y-2 right-2 h-[calc(100dvh-1rem)] w-[calc(100vw-1rem)] max-w-xl rounded-2xl sm:inset-y-3 sm:right-3 sm:h-[calc(100dvh-1.5rem)] sm:rounded-3xl',
  left:
    'ui-drawer-left inset-y-2 left-2 h-[calc(100dvh-1rem)] w-[calc(100vw-1rem)] max-w-md rounded-2xl sm:inset-y-3 sm:left-3 sm:h-[calc(100dvh-1.5rem)] sm:rounded-3xl',
  bottom:
    'ui-drawer-bottom inset-x-2 bottom-2 max-h-[85dvh] w-[calc(100vw-1rem)] rounded-2xl sm:inset-x-3 sm:bottom-3 sm:w-[calc(100vw-1.5rem)] sm:rounded-3xl',
}
</script>

<template>
  <DialogPortal>
    <DialogOverlay
      data-slot="drawer-overlay"
      :data-rr-local-backdrop="motion"
      :class="
        cn(
          'ui-overlay fixed inset-0 z-50 bg-slate-950/35 backdrop-blur-[3px]',
          props.overlayClass,
        )
      "
    />
    <DialogContent
      data-slot="drawer-content"
      :data-rr-local-panel="motion"
      :data-side="side"
      v-bind="{ ...$attrs, ...forwarded }"
      :class="
        cn(
          'glass-float fixed z-50 flex flex-col overflow-hidden text-foreground outline-none',
          sideClasses[side],
          props.class,
        )
      "
    >
      <slot />
      <DialogClose
        v-if="showCloseButton"
        data-slot="drawer-close-button"
        aria-label="关闭"
        class="absolute top-4 right-4 inline-flex size-8 cursor-pointer items-center justify-center rounded-lg text-muted-foreground outline-none transition-[background-color,color,transform] duration-[var(--motion-duration-fast)] ease-spring-snappy hover:bg-accent/80 hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/25 active:scale-95"
      >
        <X aria-hidden="true" class="size-4" />
        <span class="sr-only">关闭</span>
      </DialogClose>
    </DialogContent>
  </DialogPortal>
</template>
