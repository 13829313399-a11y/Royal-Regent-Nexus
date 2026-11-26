<script setup lang="ts">
import type { DialogDescriptionProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { computed } from 'vue'
import { DialogDescription, useForwardProps } from 'reka-ui'
import { cn } from '@/lib/utils'

interface Props extends DialogDescriptionProps {
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
  <DialogDescription
    data-slot="dialog-description"
    v-bind="forwarded"
    :class="cn('text-sm leading-relaxed text-muted-foreground', props.class)"
  >
    <slot />
  </DialogDescription>
</template>
