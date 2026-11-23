<script setup lang="ts">
import type { CheckboxRootEmits, CheckboxRootProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { computed } from 'vue'
import { Check, Minus } from '@lucide/vue'
import { CheckboxIndicator, CheckboxRoot, useForwardPropsEmits } from 'reka-ui'
import { cn } from '@/lib/utils'

interface Props extends CheckboxRootProps {
  class?: HTMLAttributes['class']
}

const props = defineProps<Props>()
const emits = defineEmits<CheckboxRootEmits>()

const delegatedProps = computed(() => {
  const { class: _class, ...delegated } = props
  return delegated
})

const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <CheckboxRoot
    data-slot="checkbox"
    v-bind="forwarded"
    :class="
      cn(
        'peer inline-flex size-4.5 shrink-0 cursor-pointer items-center justify-center rounded-[6px] border border-input bg-card text-primary-foreground shadow-[0_1px_2px_oklch(0.2_0.025_240/4%)] outline-none transition-[background-color,border-color,box-shadow,transform] duration-[var(--motion-duration-fast)] ease-spring-snappy hover:border-primary/45 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/25 active:scale-95 data-[state=checked]:border-primary data-[state=checked]:bg-primary data-[state=indeterminate]:border-primary data-[state=indeterminate]:bg-primary aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 disabled:cursor-not-allowed disabled:opacity-50',
        props.class,
      )
    "
  >
    <CheckboxIndicator
      data-slot="checkbox-indicator"
      class="grid place-content-center text-current"
    >
      <Minus v-if="props.modelValue === 'indeterminate'" class="size-3.5 stroke-[2.5]" />
      <Check v-else class="size-3.5 stroke-[2.5]" />
    </CheckboxIndicator>
  </CheckboxRoot>
</template>
