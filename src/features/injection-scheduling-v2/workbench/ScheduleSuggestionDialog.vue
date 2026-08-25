<script setup lang="ts">
import { ref } from 'vue'
import { CheckCircle2, CircleAlert, LockKeyhole, Sparkles, X } from '@lucide/vue'
import { useDialogFocus } from '../composables/useDialogFocus'
import WorkbenchActionButton from './ui/WorkbenchActionButton.vue'
import type { SchedulePreview } from './types'

const props = defineProps<{ open: boolean; preview: SchedulePreview | null; loading: boolean; canApply: boolean }>()
const emit = defineEmits<{ close: []; preview: []; apply: [] }>()
const root = ref<HTMLElement | null>(null)
const { announcement } = useDialogFocus(() => props.open, root, {
  onEscape: () => emit('close'),
  initialFocus: () => root.value?.querySelector<HTMLElement>('[data-schedule-preview]') ?? null,
})
</script>

<template>
  <Teleport to="body">
    <Transition name="wb-modal-pop">
      <div v-if="open" class="wb-modal-layer" @mousedown.self="emit('close')">
        <section ref="root" class="wb-modal wb-schedule-modal" role="dialog" aria-modal="true" aria-labelledby="wb-schedule-title" tabindex="-1">
          <p class="wb-sr-only" role="status" aria-live="polite">{{ announcement }}</p>
          <header><div><p>单方案 · 简单贪心启发式</p><h2 id="wb-schedule-title">排期建议</h2></div><WorkbenchActionButton variant="ghost" icon-only aria-label="关闭排期建议" @click="emit('close')"><template #icon><X :size="18" /></template></WorkbenchActionButton></header>
          <Transition name="wb-view-morph" mode="out-in">
            <div v-if="!preview" key="empty" class="wb-schedule-empty">
              <span class="wb-schedule-orb"><Sparkles :size="28" /></span>
              <h3>生成一份可审阅的机台排期建议</h3>
              <p>按交期、A 级适配、换料换色和机台负载计算。这里只生成预览，应用前不会改变当前规划。</p>
              <WorkbenchActionButton data-schedule-preview variant="primary" :disabled="!canApply" :loading="loading" loading-text="计算建议中…" @click="emit('preview')"><template #icon><Sparkles :size="15" /></template>生成建议</WorkbenchActionButton>
            </div>
            <div v-else key="result" class="wb-schedule-result">
              <div class="success"><CheckCircle2 :size="18" /><span>建议排入</span><b>{{ preview.assignmentCount }}</b><small>将分配到适配机台</small></div>
              <div><LockKeyhole :size="18" /><span>仍未排</span><b>{{ preview.unscheduledCount }}</b><small>保留在待排池</small></div>
              <div :class="{ warning: preview.warningCount }"><CircleAlert :size="18" /><span>需注意</span><b>{{ preview.warningCount }}</b><small>应用前建议复核</small></div>
              <p><LockKeyhole :size="14" />一次性预览；已锁定任务不会被移动，当前业务规则保持不变。</p>
            </div>
          </Transition>
          <p v-if="!canApply" class="wb-inline-warning wb-schedule-disabled" role="status">当前计划不是“规划中”状态，暂不能生成或应用新的排期建议。</p>
          <footer><WorkbenchActionButton variant="secondary" @click="emit('close')">取消</WorkbenchActionButton><WorkbenchActionButton v-if="preview" variant="primary" :disabled="!canApply" :loading="loading" loading-text="应用建议中…" @click="emit('apply')">应用建议</WorkbenchActionButton></footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>
