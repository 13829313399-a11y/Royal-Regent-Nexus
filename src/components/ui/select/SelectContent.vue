<script setup lang="ts">
import type { SelectContentEmits, SelectContentProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { computed } from 'vue'
import { ChevronDown, ChevronUp } from '@lucide/vue'
import {
  SelectContent,
  SelectPortal,
  SelectScrollDownButton,
  SelectScrollUpButton,
  SelectViewport,
  useForwardPropsEmits,
} from 'reka-ui'
import { cn } from '@/lib/utils'

defineOptions({
  inheritAttrs: false,
})

interface Props extends SelectContentProps {
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {
  position: 'popper',
  sideOffset: 6,
})
const emits = defineEmits<SelectContentEmits>()

const delegatedProps = computed(() => {
  const { class: _class, ...delegated } = props
  return delegated
})

const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <SelectPortal>
    <SelectContent
      data-slot="select-content"
      v-bind="{ ...$attrs, ...forwarded }"
      :class="
        cn(
          'glass-float ui-spring-pop relative z-50 max-h-80 min-w-36 origin-(--reka-select-content-transform-origin) overflow-hidden rounded-xl text-popover-foreground',
          props.class,
        )
      "
    >
      <SelectScrollUpButton class="flex cursor-default items-center justify-center py-1 text-muted-foreground">
        <ChevronUp aria-hidden="true" class="size-4" />
      </SelectScrollUpButton>
      <SelectViewport
        :class="
          cn(
            'p-1.5',
            position === 'popper' &&
              'h-(--reka-select-trigger-height) w-full min-w-(--reka-select-trigger-width)',
          )
        "
      >
        <slot />
      </SelectViewport>
      <SelectScrollDownButton class="flex cursor-default items-center justify-center py-1 text-muted-foreground">
        <ChevronDown aria-hidden="true" class="size-4" />
      </SelectScrollDownButton>
    </SelectContent>
  </SelectPortal>
</template>
