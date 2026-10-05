<script setup lang="ts">
import { computed } from 'vue'
import { LoaderCircle } from '@lucide/vue'
import { Button } from '@/components/ui/button'

defineOptions({ inheritAttrs: false })

type Tone = 'primary' | 'soft' | 'secondary' | 'ghost' | 'danger'
const props = withDefaults(defineProps<{
  tone?: Tone
  busy?: boolean
  disabled?: boolean
  type?: 'button' | 'submit' | 'reset'
}>(), {
  tone: 'secondary',
  busy: false,
  disabled: false,
  type: 'button',
})

const variant = computed(() => ({
  primary: 'default',
  soft: 'soft',
  secondary: 'outline',
  ghost: 'ghost',
  danger: 'destructive',
} as const)[props.tone])
</script>

<template>
  <Button
    v-bind="$attrs"
    :variant="variant"
    :type="type"
    :disabled="disabled || busy"
    :aria-busy="busy || undefined"
    class="tdp-button"
    :class="`tdp-button--${tone}`"
  >
    <span v-if="busy || $slots.icon" class="tdp-button__icon" aria-hidden="true">
      <LoaderCircle v-if="busy" class="tdp-button__spinner" :size="16" />
      <slot v-else name="icon" />
    </span>
    <span class="tdp-button__label"><slot /></span>
  </Button>
</template>
