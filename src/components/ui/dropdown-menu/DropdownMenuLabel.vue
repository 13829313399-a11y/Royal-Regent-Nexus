<script setup lang="ts">
import type { DropdownMenuLabelProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { computed } from 'vue'
import { DropdownMenuLabel } from 'reka-ui'
import { cn } from '@/lib/utils'

interface Props extends DropdownMenuLabelProps {
  inset?: boolean
  class?: HTMLAttributes['class']
}

const props = defineProps<Props>()

const delegatedProps = computed(() => {
  const { class: _class, inset: _inset, ...delegated } = props
  return delegated
})
</script>

<template>
  <DropdownMenuLabel
    data-slot="dropdown-menu-label"
    v-bind="delegatedProps"
    :class="cn('px-2.5 py-1.5 text-xs font-semibold text-muted-foreground', inset && 'pl-8', props.class)"
  >
    <slot />
  </DropdownMenuLabel>
</template>
