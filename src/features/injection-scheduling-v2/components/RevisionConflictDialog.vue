<script setup lang="ts">
import { GitCompareArrows, X } from '@lucide/vue'
import { ref } from 'vue'
import { useDialogFocus } from '../composables/useDialogFocus'
import type { RevisionConflict } from '../types'

const props = defineProps<{ conflict: RevisionConflict | null; loading: boolean }>()
const emit = defineEmits<{ close: []; useServer: []; reapply: [] }>()
const dialogRoot = ref<HTMLElement | null>(null)
useDialogFocus(() => Boolean(props.conflict), dialogRoot)
</script>

<template>
  <Teleport to="body">
  <Transition name="modal">
  <div v-if="conflict" ref="dialogRoot" class="modal-backdrop" tabindex="-1" @mousedown.self="emit('close')" @keydown.esc="emit('close')">
    <section class="phase2-dialog conflict-dialog" role="dialog" aria-modal="true" aria-label="版本冲突对比">
      <header><div><span class="eyebrow">计划版本冲突</span><strong>{{ conflict.title }}</strong></div><button aria-label="关闭版本冲突弹窗" @click="emit('close')"><X :size="17" /></button></header>
      <p class="conflict-message"><GitCompareArrows :size="18" />{{ conflict.message }}</p>
      <div class="conflict-columns"><section><strong>本地待保存值</strong><dl><div v-for="(value, key) in conflict.localValues" :key="String(key)"><dt>{{ key }}</dt><dd>{{ value }}</dd></div></dl></section><section><strong>服务器当前值</strong><dl><div v-for="(value, key) in conflict.serverValues" :key="String(key)"><dt>{{ key }}</dt><dd>{{ value }}</dd></div><p v-if="!Object.keys(conflict.serverValues).length">已刷新最新计划，请重新确认。</p></dl></section></div>
      <footer><button @click="emit('useServer')">采用服务器值</button><button class="primary" :disabled="loading || !conflict.retry" @click="emit('reapply')">{{ loading ? '处理中…' : '基于最新版本重新应用' }}</button></footer>
    </section>
  </div>
  </Transition>
  </Teleport>
</template>
