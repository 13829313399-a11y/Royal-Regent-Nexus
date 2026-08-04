<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { FileClock, Save } from '@lucide/vue'
import type { EditableCellKey, OrderRecord, ScheduleTaskRecord } from '../types'

const props = defineProps<{
  task: ScheduleTaskRecord
  order: OrderRecord
  planStatus: string
  canReport: boolean
  pendingCount: number
  saving: boolean
}>()
const emit = defineEmits<{
  stage: [edits: Array<{ key: EditableCellKey; value: string | number }>]
  save: []
}>()
const form = reactive({ reported: 0, completed: 0, target: 0, downtime: 0, exception: '', status: 'RUNNING' })
const enabled = computed(() => props.planStatus === 'PUBLISHED' && props.task.activeExecution && props.canReport)

watch(() => [props.task.id, props.task.revision, props.order.revision], () => {
  form.reported = props.task.reportedQuantity
  form.completed = props.order.completedQuantity
  form.target = props.task.targetQuantity
  form.downtime = 0
  form.exception = ''
  form.status = ['QUEUED', 'RUNNING', 'BLOCKED', 'COMPLETED'].includes(props.task.status) ? props.task.status : 'RUNNING'
}, { immediate: true })

function stage() {
  emit('stage', [
    { key: 'shiftCompleted', value: form.reported },
    { key: 'completedQuantity', value: form.completed },
    { key: 'targetQuantity', value: form.target },
    { key: 'downtime', value: form.downtime },
    { key: 'exception', value: form.exception },
    { key: 'status', value: form.status },
  ])
}
</script>

<template>
  <section class="inspector-section production-report-panel">
    <div class="section-heading"><strong>生产回报</strong><span>{{ enabled ? '服务器确认后生效' : '当前不可回报' }}</span></div>
    <div class="report-progress"><span>累计完成</span><strong>{{ order.completedQuantity.toLocaleString('zh-CN') }} / {{ order.orderQuantity.toLocaleString('zh-CN') }}</strong><i><b :style="{ width: `${Math.min(order.completionRate * 100, 100)}%` }"></b></i></div>
    <div class="report-form-grid">
      <label><span>任务累计已啤</span><input v-model.number="form.reported" type="number" min="0" :disabled="!enabled" /></label>
      <label><span>订单累计已啤</span><input v-model.number="form.completed" type="number" min="0" :disabled="!enabled" /></label>
      <label><span>本班目标</span><input v-model.number="form.target" type="number" min="0" :disabled="!enabled" /></label>
      <label><span>停机分钟</span><input v-model.number="form.downtime" type="number" min="0" max="1440" :disabled="!enabled" /></label>
      <label><span>执行状态</span><select v-model="form.status" :disabled="!enabled"><option value="QUEUED">排队</option><option value="RUNNING">生产中</option><option value="BLOCKED">异常/待料</option><option value="COMPLETED">完成</option></select></label>
      <label><span>异常类型</span><input v-model="form.exception" maxlength="64" :disabled="!enabled" placeholder="例如 MATERIAL_SHORTAGE" /></label>
    </div>
    <div class="report-actions">
      <button type="button" :disabled="!enabled" @click="stage"><FileClock :size="15" />加入批量保存</button>
      <button type="button" class="primary" :disabled="!pendingCount || saving" @click="emit('save')"><Save :size="15" />{{ saving ? '保存中' : `保存全部 ${pendingCount}` }}</button>
    </div>
  </section>
</template>
