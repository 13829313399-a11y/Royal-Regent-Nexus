<script setup lang="ts">
import { CheckCircle2, CircleAlert, Info, X } from '@lucide/vue'
import { onBeforeUnmount, ref, watch } from 'vue'
import type { AsyncFeedback } from '../types'

const props = defineProps<{ feedback: AsyncFeedback | null }>()
const visible = ref(false)
let timer: number | undefined

watch(() => props.feedback, (feedback) => {
  window.clearTimeout(timer)
  visible.value = Boolean(feedback?.message && feedback.phase !== 'idle')
  if (feedback?.message && feedback.phase === 'succeeded' && feedback.tone !== 'error') {
    timer = window.setTimeout(() => { visible.value = false }, 3600)
  }
}, { immediate: true })

onBeforeUnmount(() => window.clearTimeout(timer))
</script>

<template>
  <Teleport to="body">
    <Transition name="feedback-toast">
      <div v-if="visible && feedback" class="scheduling-feedback-toast" :class="[feedback.tone, feedback.phase]" :role="feedback.tone === 'error' ? 'alert' : 'status'" :aria-live="feedback.tone === 'error' ? undefined : 'polite'" aria-atomic="true">
        <CheckCircle2 v-if="feedback.tone === 'success'" :size="17" />
        <CircleAlert v-else-if="feedback.tone === 'error' || feedback.tone === 'warning'" :size="17" />
        <Info v-else :size="17" />
        <span>{{ feedback.message }}</span>
        <button v-if="feedback.tone === 'error'" aria-label="关闭提示" @click="visible = false"><X :size="15" /></button>
      </div>
    </Transition>
  </Teleport>
</template>
