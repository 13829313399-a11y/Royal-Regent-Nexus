<script setup lang="ts">
import type { SelectItemProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { computed } from 'vue'
import { Check } from '@lucide/vue'
import { SelectItem, SelectItemIndicator, SelectItemText, useForwardProps } from 'reka-ui'
import { cn } from '@/lib/utils'

interface Props extends SelectItemProps {
  class?: HTMLAttributes['class']
}

const props = defineProps<Props>()

const delegatedProps = computed(() => {
  const { class: _class, ...delegated } = props
  return delegated
})

const forwarded = useForwardProps(delegatedProps)
</script>

<template>
  <SelectItem
    data-slot="select-item"
    v-bind="forwarded"
    :class="
      cn(
        'relative flex w-full cursor-pointer select-none items-center rounded-lg py-2 pr-8 pl-2.5 text-sm text-foreground outline-none transition-colors duration-[var(--motion-duration-instant)] ease-standard focus:bg-accent/80 focus:text-accent-foreground data-[state=checked]:font-medium data-[state=checked]:text-primary data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
        props.class,
      )
    "
  >
    <span class="pointer-events-none absolute right-2.5 flex size-4 items-center justify-center text-primary">
      <SelectItemIndicator>
        <Check aria-hidden="true" class="size-4 stroke-[2.25]" />
      </SelectItemIndicator>
    </span>
    <SelectItemText>
      <slot />
    </SelectItemText>
  </SelectItem>
</template>
