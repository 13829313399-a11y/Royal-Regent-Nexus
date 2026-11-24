<script setup lang="ts">
import type { LabelProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { computed } from 'vue'
import { Label } from 'reka-ui'
import { cn } from '@/lib/utils'

interface Props extends LabelProps {
  required?: boolean
  class?: HTMLAttributes['class']
}

const props = defineProps<Props>()

const delegatedProps = computed(() => {
  const { class: _class, required: _required, ...delegated } = props
  return delegated
})
</script>

<template>
  <Label
    data-slot="label"
    v-bind="delegatedProps"
    :class="
      cn(
        'inline-flex items-center gap-1 text-[13px] font-medium leading-none text-foreground select-none peer-disabled:cursor-not-allowed peer-disabled:opacity-60 group-data-[disabled=true]:pointer-events-none group-data-[disabled=true]:opacity-60',
        props.class,
      )
    "
  >
    <slot />
    <span
      v-if="required"
      aria-hidden="true"
      class="text-destructive"
    >*</span>
  </Label>
</template>
