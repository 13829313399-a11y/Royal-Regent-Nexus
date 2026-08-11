<script setup lang="ts">
import { computed, ref } from 'vue'
import RevisionConflictDialog from '../../components/RevisionConflictDialog.vue'
import SchedulingFeedbackToast from '../../components/SchedulingFeedbackToast.vue'
import SchedulingFreshnessBanner from '../../components/SchedulingFreshnessBanner.vue'
import { createAsyncFeedback, shouldShowFeedbackToast } from '../../presentation/asyncFeedback'
import type { AsyncFeedback, RevisionConflict, SchedulingSyncHealth } from '../../types'

const feedback = ref<AsyncFeedback | null>(null)
const conflict = ref<RevisionConflict | null>(null)
const syncHealth = ref<SchedulingSyncHealth>('live')
const sourceMessage = ref('正式数据库')
const toastFeedback = computed(() => shouldShowFeedbackToast(feedback.value, Boolean(conflict.value)) ? feedback.value : null)

function showSuccess() {
  conflict.value = null
  syncHealth.value = 'live'
  sourceMessage.value = '正式数据库'
  feedback.value = createAsyncFeedback('save', 'succeeded', 'success', '所有修改已由服务器确认保存')
}

function showInfo() {
  conflict.value = null
  syncHealth.value = 'live'
  sourceMessage.value = '正式数据库'
  feedback.value = createAsyncFeedback('refresh', 'succeeded', 'info', '排产数据已刷新')
}

function showError() {
  conflict.value = null
  syncHealth.value = 'live'
  sourceMessage.value = '正式数据库'
  feedback.value = createAsyncFeedback('save', 'failed', 'error', '保存失败：B1c 去敏网络错误')
}

function showStale() {
  conflict.value = null
  syncHealth.value = 'stale'
  sourceMessage.value = '数据同步暂时中断：B1c 去敏网络错误'
  feedback.value = createAsyncFeedback('refresh', 'failed', 'warning', '排产数据刷新失败，当前继续显示最近正式数据')
}

function showConflict() {
  syncHealth.value = 'live'
  sourceMessage.value = '正式数据库'
  feedback.value = createAsyncFeedback('save', 'failed', 'error', '保存已暂停：请处理版本冲突')
  conflict.value = {
    title: 'Task revision conflict',
    message: 'expected revision 14 but found revision 15',
    localValues: { status: 'RUNNING', targetQuantity: 90 },
    serverValues: { status: 'QUEUED', targetQuantity: 80 },
    retry: async () => {},
  }
}
</script>

<template>
  <main class="b1c-shell injection-scheduling-v2">
    <section class="b1c-panel">
      <h1>B1c Typed Async Feedback 去敏验收</h1>
      <p>不含生产数据；验证显式 operation / phase / tone、无障碍播报和反馈层级。</p>
      <div class="b1c-controls">
        <button type="button" @click="showSuccess">保存成功</button>
        <button type="button" @click="showInfo">刷新成功</button>
        <button type="button" @click="showError">保存失败</button>
        <button type="button" @click="showStale">同步过期</button>
        <button type="button" @click="showConflict">版本冲突</button>
      </div>
      <div class="b1c-state">
        <span>Operation<strong>{{ feedback?.operation ?? 'idle' }}</strong></span>
        <span>Phase<strong>{{ feedback?.phase ?? 'idle' }}</strong></span>
        <span>Tone<strong>{{ feedback?.tone ?? 'info' }}</strong></span>
      </div>
      <SchedulingFreshnessBanner :sync-health="syncHealth" source-mode="live" :source-message="sourceMessage" last-synced-at="16:42" :refreshing="false" @retry="showInfo" />
      <p class="b1c-note">保存错误保留到手工关闭；同步过期由持久 Banner 承担；版本冲突由 Dialog 承担。</p>
    </section>
    <SchedulingFeedbackToast :feedback="toastFeedback" />
    <RevisionConflictDialog :conflict="conflict" :loading="false" @close="conflict = null" @use-server="conflict = null" />
  </main>
</template>
