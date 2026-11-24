<script setup lang="ts">
import type { TabsContentProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { computed } from 'vue'
import { TabsContent } from 'reka-ui'
import { cn } from '@/lib/utils'

interface Props extends TabsContentProps {
  class?: HTMLAttributes['class']
}

const props = defineProps<Props>()

const delegatedProps = computed(() => {
  const { class: _class, ...delegated } = props
  return delegated
})
</script>

<template>
  <TabsContent
    data-slot="tabs-content"
    v-bind="delegatedProps"
    :class="
      cn(
        'outline-none focus-visible:ring-3 focus-visible:ring-ring/25 data-[state=active]:animate-[ui-fade-in_var(--motion-duration-fast)_var(--motion-ease-standard)_both]',
        props.class,
      )
    "
  >
    <slot />
  </TabsContent>
</template>
