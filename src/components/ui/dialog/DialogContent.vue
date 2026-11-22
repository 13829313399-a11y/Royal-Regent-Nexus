<script setup lang="ts">
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
  class?: HTMLAttributes['class']
  overlayClass?: HTMLAttributes['class']
  showCloseButton?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  showCloseButton: true,
})
const emits = defineEmits<DialogContentEmits>()

const delegatedProps = computed(() => {
  const {
    class: _class,
    overlayClass: _overlayClass,
    showCloseButton: _showCloseButton,
    ...delegated
  } = props
  return delegated
})

const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <DialogPortal>
    <DialogOverlay
      data-slot="dialog-overlay"
      :class="
        cn(
          'ui-overlay fixed inset-0 z-50 bg-slate-950/35 backdrop-blur-[3px]',
          props.overlayClass,
        )
      "
    />
    <DialogContent
      data-slot="dialog-content"
      v-bind="{ ...$attrs, ...forwarded }"
      :class="
        cn(
          'glass-float ui-spring-pop fixed inset-0 z-50 m-auto flex h-fit max-h-[calc(100dvh-2rem)] w-[calc(100vw-2rem)] max-w-lg flex-col overflow-hidden rounded-2xl p-6 text-foreground outline-none sm:rounded-3xl',
          props.class,
        )
      "
    >
      <slot />
      <DialogClose
        v-if="showCloseButton"
        data-slot="dialog-close-button"
        aria-label="关闭"
        class="absolute top-4 right-4 inline-flex size-8 cursor-pointer items-center justify-center rounded-lg text-muted-foreground outline-none transition-[background-color,color,transform] duration-[var(--motion-duration-fast)] ease-spring-snappy hover:bg-accent/80 hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/25 active:scale-95"
      >
        <X aria-hidden="true" class="size-4" />
        <span class="sr-only">关闭</span>
      </DialogClose>
    </DialogContent>
  </DialogPortal>
</template>
