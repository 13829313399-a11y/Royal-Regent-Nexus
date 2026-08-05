<script setup lang="ts">
import { CheckCircle2, CircleAlert, Info, X } from '@lucide/vue'
import { onBeforeUnmount, ref, watch } from 'vue'

const props = withDefaults(defineProps<{ message: string; tone?: 'success' | 'error' | 'info' }>(), { tone: 'info' })
const visible = ref(false)
let timer: number | undefined

watch(() => props.message, (message) => {
  window.clearTimeout(timer)
  visible.value = Boolean(message)
  if (message && props.tone !== 'error') timer = window.setTimeout(() => { visible.value = false }, 3600)
}, { immediate: true })

onBeforeUnmount(() => window.clearTimeout(timer))
</script>

<template>
  <Teleport to="body">
    <Transition name="feedback-toast">
      <div v-if="visible" class="scheduling-feedback-toast" :class="tone" role="status" aria-live="polite">
        <CheckCircle2 v-if="tone === 'success'" :size="17" />
        <CircleAlert v-else-if="tone === 'error'" :size="17" />
        <Info v-else :size="17" />
        <span>{{ message }}</span>
        <button v-if="tone === 'error'" aria-label="关闭提示" @click="visible = false"><X :size="15" /></button>
      </div>
    </Transition>
  </Teleport>
</template>
