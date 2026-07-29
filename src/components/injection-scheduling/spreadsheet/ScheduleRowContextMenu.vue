<script setup lang="ts">
import { ArrowDown, ArrowUp, Eye, MoveRight, X } from '@lucide/vue'

defineProps<{
  open: boolean
  x: number
  y: number
  current: boolean
}>()

const emit = defineEmits<{
  close: []
  inspect: []
  move: []
  nudge: [direction: 'up' | 'down']
}>()
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-[88]" @pointerdown="emit('close')" @contextmenu.prevent="emit('close')">
      <div
        class="absolute w-44 overflow-hidden rounded-lg border border-slate-200 bg-white p-1 shadow-2xl"
        :style="{ left: `${x}px`, top: `${y}px` }"
        role="menu"
        @pointerdown.stop
      >
        <button type="button" class="context-action" role="menuitem" @click="emit('inspect'); emit('close')"><Eye class="size-3.5" />查看任务详情</button>
        <button type="button" class="context-action" role="menuitem" :disabled="current" @click="emit('nudge', 'up'); emit('close')"><ArrowUp class="size-3.5" />向前移动</button>
        <button type="button" class="context-action" role="menuitem" :disabled="current" @click="emit('nudge', 'down'); emit('close')"><ArrowDown class="size-3.5" />向后移动</button>
        <button type="button" class="context-action" role="menuitem" :disabled="current" @click="emit('move'); emit('close')"><MoveRight class="size-3.5" />更换机台</button>
        <button type="button" class="context-action text-slate-400" role="menuitem" @click="emit('close')"><X class="size-3.5" />关闭菜单</button>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.context-action {
  display: flex;
  width: 100%;
  height: 30px;
  align-items: center;
  gap: 8px;
  border-radius: 6px;
  padding: 0 8px;
  color: rgb(51 65 85);
  font-size: 10px;
  font-weight: 700;
}
.context-action:hover:not(:disabled) { background: rgb(240 253 250); color: rgb(15 118 110); }
.context-action:disabled { cursor: not-allowed; color: rgb(203 213 225); }
</style>
