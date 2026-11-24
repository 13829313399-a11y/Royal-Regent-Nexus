<script setup lang="ts">
import type { TabsListProps } from 'reka-ui'
import type { ComponentPublicInstance, HTMLAttributes } from 'vue'
import { computed, nextTick, onMounted, ref } from 'vue'
import { TabsIndicator, TabsList } from 'reka-ui'
import { cn } from '@/lib/utils'

interface Props extends TabsListProps {
  class?: HTMLAttributes['class']
}

const props = defineProps<Props>()
const indicatorRef = ref<(ComponentPublicInstance & { updateIndicatorStyle?: () => void }) | null>(null)

const delegatedProps = computed(() => {
  const { class: _class, ...delegated } = props
  return delegated
})

onMounted(() => {
  void nextTick(() => {
    indicatorRef.value?.updateIndicatorStyle?.()
  })
})
</script>

<template>
  <TabsList
    data-slot="tabs-list"
    v-bind="delegatedProps"
    :class="
      cn(
        'glass-chrome relative inline-flex max-w-full items-center gap-1 overflow-x-auto rounded-xl p-1 text-muted-foreground',
        props.class,
      )
    "
  >
    <TabsIndicator
      ref="indicatorRef"
      data-slot="tabs-indicator"
      aria-hidden="true"
      class="pointer-events-none absolute inset-y-1 left-0 z-0 w-(--reka-tabs-indicator-size) translate-x-(--reka-tabs-indicator-position) rounded-lg bg-card shadow-elevation-1 transition-[width,transform] duration-[var(--motion-duration-base)] ease-spring-snappy"
    />
    <slot />
  </TabsList>
</template>
