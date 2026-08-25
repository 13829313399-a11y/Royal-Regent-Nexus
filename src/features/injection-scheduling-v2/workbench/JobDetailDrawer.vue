<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ChevronDown, ClockAlert, Database, X } from '@lucide/vue'
import ProgressMeter from '@/components/common/ProgressMeter.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { useDialogFocus } from '../composables/useDialogFocus'
import { dueSlackPresentation, formatAClass, priorityPresentation, statusPresentation } from './presentation'
import WorkbenchActionButton from './ui/WorkbenchActionButton.vue'
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
const sourceOpen = ref(false)
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
  sourceOpen.value = false
})
const lineageEntries = computed(() => Object.entries(props.job?.lineage ?? {}).filter(([, value]) => value != null && value !== '').slice(0, 12))
const completionPercent = computed(() => Math.round((props.job?.completionRate ?? 0) * 1000) / 10)
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
    <Transition name="wb-drawer-slide">
      <div v-if="job" class="wb-drawer-layer" @mousedown.self="emit('close')">
        <aside ref="drawerRoot" class="wb-detail-drawer" role="dialog" aria-modal="true" aria-labelledby="wb-job-detail-title" tabindex="-1">
          <p class="wb-sr-only" role="status" aria-live="polite">{{ announcement }}</p>
          <header>
            <div class="wb-drawer-heading">
              <div><StatusPill :label="statusPresentation(job.status).label" :tone="statusPresentation(job.status).tone" /><span>{{ job.machineCode || '待排池' }}</span></div>
              <h2 id="wb-job-detail-title">{{ job.itemNo || job.orderNo }} · {{ job.productName }}</h2>
            </div>
            <WorkbenchActionButton variant="ghost" icon-only aria-label="关闭任务详情" data-drawer-close @click="emit('close')"><template #icon><X :size="18" /></template></WorkbenchActionButton>
          </header>
          <div class="wb-drawer-scroll">
            <section class="wb-detail-hero" :class="dueSlackPresentation(job.deliverySlackDays).className">
              <div><span>未完数量</span><b>{{ job.outstandingQuantity.toLocaleString('zh-CN') }}</b><small>订单 {{ job.orderQuantity.toLocaleString('zh-CN') }}</small></div>
              <div class="wb-detail-chips"><StatusPill :label="priorityPresentation(job.priority).label" :tone="priorityPresentation(job.priority).tone" /><StatusPill :label="dueSlackPresentation(job.deliverySlackDays).label" :tone="dueSlackPresentation(job.deliverySlackDays).tone" /></div>
            </section>
            <section class="wb-detail-grid">
              <div><span>生产单</span><b>{{ job.orderNo || '—' }}</b></div>
              <div><span>模具</span><b>{{ job.moldNo || '待补' }}</b></div>
              <div><span>要求机台</span><b>{{ formatAClass(job.requiredMachineA) }}</b></div>
              <div><span>交货日期</span><b>{{ job.deliveryDueDate || '—' }}</b></div>
              <div><span>材料 / 颜色</span><b>{{ job.materialName || '—' }} / {{ job.colorName || '—' }}</b></div>
              <div><span>机械手 / 夹具</span><b>{{ job.armRequirement || '—' }} / {{ job.fixtureRequirement || '—' }}</b></div>
            </section>
            <section class="wb-progress-panel">
              <div><span>任务完成进度</span><b>{{ completionPercent.toFixed(1) }}%</b></div>
              <ProgressMeter :value="completionPercent" tone="teal" />
              <p><span>期初已完 {{ job.openingCompletedQuantity.toLocaleString('zh-CN') }}</span><span>系统回报 {{ job.reportedQuantity.toLocaleString('zh-CN') }}</span></p>
            </section>
            <section v-if="job.taskId" class="wb-report-form">
              <div class="wb-section-title"><div><h3>班次回报</h3><p>提交后将保留回报人与审计时间</p></div><ClockAlert :size="17" /></div>
              <div class="wb-segmented" role="group" aria-label="选择班次"><button type="button" :aria-pressed="shiftCode === 'DAY'" :class="{ active: shiftCode === 'DAY' }" @click="shiftCode = 'DAY'">白班</button><button type="button" :aria-pressed="shiftCode === 'NIGHT'" :class="{ active: shiftCode === 'NIGHT' }" @click="shiftCode = 'NIGHT'">夜班</button></div>
              <div class="wb-form-grid">
                <label>本班良品数<input v-model.number="quantity" type="number" min="0" /></label>
                <label>本班目标<input v-model.number="targetQuantity" type="number" min="0" /></label>
                <label>停机分钟<input v-model.number="downtimeMinutes" type="number" min="0" max="1440" /></label>
                <label>状态<select v-model="reportedStatus"><option value="RUNNING">生产中</option><option value="BLOCKED">暂停</option><option value="COMPLETED">完成</option><option value="QUEUED">已排</option></select></label>
                <label>异常代码<input v-model="exceptionCode" maxlength="64" placeholder="可选" /></label>
                <label class="wide">异常说明<textarea v-model="exceptionDetail" rows="2" maxlength="2000"></textarea></label>
              </div>
              <p v-if="!canReport" class="wb-inline-note">当前计划尚未进入执行，班次回报暂不可提交。</p>
              <WorkbenchActionButton variant="primary" :disabled="!canReport" :loading="saving" loading-text="保存回报中…" @click="submit">提交回报</WorkbenchActionButton>
            </section>
            <section class="wb-source-details">
              <button type="button" :aria-expanded="sourceOpen" aria-controls="wb-source-lineage" @click="sourceOpen = !sourceOpen"><span><Database :size="15" />来源追溯</span><ChevronDown :size="15" :class="{ open: sourceOpen }" /></button>
              <div v-show="sourceOpen" id="wb-source-lineage"><dl><template v-for="([key, value]) in lineageEntries" :key="key"><dt>{{ key }}</dt><dd>{{ value }}</dd></template></dl><p v-if="!lineageEntries.length">暂无可展示的来源字段。</p></div>
            </section>
          </div>
        </aside>
      </div>
    </Transition>
  </Teleport>
</template>
