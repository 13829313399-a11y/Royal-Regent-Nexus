<script setup lang="ts">
import { onMounted, onUnmounted, watch } from 'vue'
import { useWorkCenterStore } from '@/stores/workCenter'
import { useNotificationSound } from '@/composables/useNotificationSound'
import { BellRing, X } from '@lucide/vue'
const center = useWorkCenterStore()
const sound = useNotificationSound()
let timer: ReturnType<typeof setTimeout> | undefined
function resume() { clearTimeout(timer); if (center.toasts.length) timer = setTimeout(() => center.toasts.shift(), 9000) }
function pause() { clearTimeout(timer) }
watch(() => center.preferences.sound_enabled, enabled => { void sound.setSoundEnabled(enabled) })
watch(() => center.toasts[0]?.id, (id, old) => { resume(); if (id && id !== old && center.preferences.sound_enabled) void sound.playNotificationSound() })
onMounted(center.start)
onUnmounted(() => { center.stop(); pause() })
</script>

<template>
  <Transition name="nc-toast">
    <aside v-if="center.toasts[0] || center.toastOverflow" class="nc-toast-host" role="status" @mouseenter="pause" @mouseleave="resume" @focusin="pause" @focusout="resume">
      <template v-if="center.toasts[0]">
      <BellRing :size="20" /><div><strong>{{ center.toasts[0].title }}</strong><p>{{ center.toasts[0].reference_label }}</p><RouterLink :to="{ name: 'notification-center', query: { entry: center.toasts[0].id } }" @click="center.toasts = []">打开事项工作台</RouterLink></div>
      <button type="button" aria-label="关闭提醒" @click="center.toasts.shift()"><X :size="18" /></button>
      </template>
      <template v-else><BellRing :size="20" /><div><strong>另有 {{ center.toastOverflow }} 项新待办</strong><p>请进入工作台查看当前责任。</p><RouterLink :to="{ name: 'notification-center' }" @click="center.toastOverflow = 0">打开事项工作台</RouterLink></div><button aria-label="关闭汇总提醒" @click="center.toastOverflow = 0"><X :size="18" /></button></template>
    </aside>
  </Transition>
</template>
