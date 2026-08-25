<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { X } from '@lucide/vue'
import { useDialogFocus } from '../composables/useDialogFocus'
import type { ShiftReportInput, WorkbenchJob } from './types'

const props = defineProps<{ job: WorkbenchJob | null; canReport: boolean; saving: boolean }>()
const emit = defineEmits<{ close: []; report: [job: WorkbenchJob, input: ShiftReportInput] }>()
const drawerRoot = ref<HTMLElement | null>(null)
const shiftCode = ref<'DAY' | 'NIGHT'>('DAY')
const quantity = ref(0)
const targetQuantity = ref(0)
const downtimeMinutes = ref(0)
const exceptionCode = ref('')
const exceptionDetail = ref('')
const reportedStatus = ref<ShiftReportInput['reportedStatus']>('RUNNING')
const { announcement } = useDialogFocus(() => Boolean(props.job), drawerRoot, {
  onEscape: () => emit('close'),
  initialFocus: () => drawerRoot.value?.querySelector<HTMLElement>('[data-drawer-close]') ?? null,
})

watch(() => props.job?.id, () => {
  quantity.value = 0
  targetQuantity.value = props.job?.shiftTargetQuantity ?? 0
  downtimeMinutes.value = 0
  exceptionCode.value = ''
  exceptionDetail.value = ''
  reportedStatus.value = props.job?.status === 'PAUSED' ? 'BLOCKED' : props.job?.status === 'DONE' ? 'COMPLETED' : 'RUNNING'
})
const lineageEntries = computed(() => Object.entries(props.job?.lineage ?? {}).filter(([, value]) => value != null && value !== '').slice(0, 12))
function submit() {
  if (!props.job) return
  emit('report', props.job, {
    shiftCode: shiftCode.value, quantity: quantity.value, targetQuantity: targetQuantity.value,
    downtimeMinutes: downtimeMinutes.value, exceptionCode: exceptionCode.value,
    exceptionDetail: exceptionDetail.value, reportedStatus: reportedStatus.value,
  })
}
</script>

<template>
  <Teleport to="body">
    <div v-if="job" class="wb-drawer-layer" @mousedown.self="emit('close')">
      <aside ref="drawerRoot" class="wb-detail-drawer" role="dialog" aria-modal="true" aria-labelledby="wb-job-detail-title" tabindex="-1">
        <p class="wb-sr-only" role="status" aria-live="polite">{{ announcement }}</p>
        <header>
          <div><p>{{ job.machineCode || '待排池' }} · {{ job.status }}</p><h2 id="wb-job-detail-title">{{ job.itemNo }} {{ job.productName }}</h2></div>
          <button type="button" class="wb-icon-button" aria-label="关闭任务详情" data-drawer-close @click="emit('close')"><X :size="18" /></button>
        </header>
        <div class="wb-drawer-scroll">
          <section class="wb-detail-grid">
            <div><span>生产单</span><b>{{ job.orderNo || '—' }}</b></div>
            <div><span>模具</span><b>{{ job.moldNo || '待补' }}</b></div>
            <div><span>订单 / 已完</span><b>{{ job.orderQuantity.toLocaleString('zh-CN') }} / {{ job.completedQuantity.toLocaleString('zh-CN') }}</b></div>
            <div><span>交期</span><b>{{ job.deliveryDueDate || '—' }}</b></div>
            <div><span>材料 / 颜色</span><b>{{ job.materialName || '—' }} / {{ job.colorName || '—' }}</b></div>
            <div><span>机械手 / 夹具</span><b>{{ job.armRequirement || '—' }} / {{ job.fixtureRequirement || '—' }}</b></div>
          </section>
          <section class="wb-progress-panel">
            <div><span>开期已完 {{ job.openingCompletedQuantity.toLocaleString('zh-CN') }}</span><span>系统回报 {{ job.reportedQuantity.toLocaleString('zh-CN') }}</span></div>
            <progress :value="job.completionRate" max="1"></progress>
            <b>{{ (job.completionRate * 100).toFixed(1) }}%</b>
          </section>
          <section v-if="job.taskId" class="wb-report-form">
            <h3>班次回报</h3>
            <div class="wb-segmented"><button type="button" :class="{ active: shiftCode === 'DAY' }" @click="shiftCode = 'DAY'">白班</button><button type="button" :class="{ active: shiftCode === 'NIGHT' }" @click="shiftCode = 'NIGHT'">夜班</button></div>
            <div class="wb-form-grid">
              <label>本班良品数<input v-model.number="quantity" type="number" min="0" /></label>
              <label>本班目标<input v-model.number="targetQuantity" type="number" min="0" /></label>
              <label>停机分钟<input v-model.number="downtimeMinutes" type="number" min="0" max="1440" /></label>
              <label>状态<select v-model="reportedStatus"><option value="RUNNING">生产中</option><option value="BLOCKED">暂停</option><option value="COMPLETED">完成</option><option value="QUEUED">已排</option></select></label>
              <label>异常代码<input v-model="exceptionCode" maxlength="64" placeholder="可选" /></label>
              <label class="wide">异常说明<textarea v-model="exceptionDetail" rows="2" maxlength="2000"></textarea></label>
            </div>
            <p v-if="!canReport" class="wb-inline-note">当前计划尚未进入执行，班次回报暂不可提交。</p>
            <button type="button" class="wb-primary-button" :disabled="!canReport || saving" @click="submit">{{ saving ? '保存中…' : '提交回报' }}</button>
          </section>
          <details class="wb-source-details"><summary>来源追溯</summary><dl><template v-for="([key, value]) in lineageEntries" :key="key"><dt>{{ key }}</dt><dd>{{ value }}</dd></template></dl></details>
        </div>
      </aside>
    </div>
  </Teleport>
</template>
