<script setup lang="ts">
import type { ProgressRootProps } from 'reka-ui'
import type { HTMLAttributes, StyleValue } from 'vue'
import { computed } from 'vue'
import { ProgressIndicator, ProgressRoot } from 'reka-ui'
import { cn } from '@/lib/utils'

interface Props extends ProgressRootProps {
  class?: HTMLAttributes['class']
  indicatorClass?: HTMLAttributes['class']
  indicatorStyle?: StyleValue
}

const props = defineProps<Props>()

const delegatedProps = computed(() => {
  const {
    class: _class,
    indicatorClass: _indicatorClass,
    indicatorStyle: _indicatorStyle,
    ...delegated
  } = props

  return delegated
})

const progressStyle = computed<StyleValue>(() => {
  if (typeof props.modelValue !== 'number') {
    return props.indicatorStyle
  }

  return [
    {
      transform: `translateX(-${100 - props.modelValue}%)`,
    },
    props.indicatorStyle,
  ]
})
</script>

<template>
  <ProgressRoot
    data-slot="progress"
    v-bind="delegatedProps"
    :class="cn('relative h-4 w-full overflow-hidden rounded-full bg-secondary', props.class)"
  >
    <ProgressIndicator
      data-slot="progress-indicator"
      :class="cn('h-full w-full flex-1 bg-primary transition-all', props.indicatorClass)"
      :style="progressStyle"
    />
  </ProgressRoot>
</template>
