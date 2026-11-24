<script setup lang="ts">
import { onMounted, onUnmounted, watch } from 'vue'
import { useWorkCenterStore } from '@/stores/workCenter'
import { useNotificationSound } from '@/composables/useNotificationSound'
import { BellRing, X } from '@lucide/vue'
import { Button } from '@/components/ui'
import { useWorkActions } from './useWorkActions'
import WorkIconButton from './WorkIconButton.vue'
const center = useWorkCenterStore(),
  actions = useWorkActions(),
  sound = useNotificationSound()
let timer: ReturnType<typeof setTimeout> | undefined, feedbackTimer: ReturnType<typeof setTimeout> | undefined
function pause() {
  clearTimeout(timer)
}
function resume() {
  pause()
  if (center.toasts.length) timer = setTimeout(() => center.toasts.shift(), 9000)
}
watch(
  () => center.preferences.sound_enabled,
  (enabled) => {
    void sound.setSoundEnabled(enabled)
  },
)
watch(
  () => center.toasts[0]?.id,
  (id, old) => {
    resume()
    if (id && id !== old && center.preferences.sound_enabled) void sound.playNotificationSound()
  },
)
watch(
  () => center.feedback,
  (message) => {
    clearTimeout(feedbackTimer)
    if (message) feedbackTimer = setTimeout(() => (center.feedback = ''), 6500)
  },
)
onMounted(center.start)
onUnmounted(() => {
  center.stop()
  pause()
  clearTimeout(feedbackTimer)
})
</script>
<template>
  <Transition name="nc-toast"
    ><aside
      v-if="center.toasts[0] || center.toastOverflow"
      class="nc-toast-host glass-float"
      role="status"
      @mouseenter="pause"
      @mouseleave="resume"
      @focusin="pause"
      @focusout="resume"
    >
      <BellRing :size="20" />
      <div v-if="center.toasts[0]">
        <strong>{{ center.toasts[0].reference_label || center.toasts[0].title }}</strong>
        <p>{{ center.toasts[0].stage_label }}</p>
        <Button size="sm" @click="actions.open(center.toasts.shift()!)">前往办理</Button
        ><Button size="sm" variant="ghost" @click="actions.preview(center.toasts.shift()!)"
          >工作台预览</Button
        >
      </div>
      <div v-else>
        <strong>另有 {{ center.toastOverflow }} 项新待办</strong
        ><Button as-child variant="link"
          ><RouterLink :to="{ name: 'notification-center' }" @click="center.toastOverflow = 0"
            >打开事项工作台</RouterLink
          ></Button
        >
      </div>
      <WorkIconButton
        :icon="X"
        label="关闭提醒"
        @activate="center.toasts.length ? center.toasts.shift() : (center.toastOverflow = 0)"
      /></aside
  ></Transition>
  <p v-if="center.feedback" class="nc-feedback glass-float" role="status">{{ center.feedback }}</p>
</template>
