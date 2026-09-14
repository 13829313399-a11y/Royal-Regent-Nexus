<script setup lang="ts">
import { computed, inject, nextTick, ref, watch } from 'vue'
import { Keyboard, Save, ScanLine } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/auth'
import type {
  CreateUvReport,
  UvMachine,
  UvPrintJob,
  UvProduct,
  UvQuality,
  UvShiftTemplate,
  UvWorkerRef,
} from '../contracts'
import { UV_CONTEXT_KEY, UV_TRANSPORT_KEY } from '../composables/uvPageContext'
import { operationForPayload, useUvCommand, useUvRequest } from '../composables/useUvRequest'
import { useUvToast } from '../composables/useUvToast'
import UvDrawer from './UvDrawer.vue'
import UvFormField from './UvFormField.vue'
import UvStatusPill from './UvStatusPill.vue'
import UvNumber from './UvNumber.vue'
import { QUALITY_BUCKET_LABELS, QUALITY_BUCKETS } from '../domain/quality'
import { RAW_UNIT, RECONCILIATION } from '../domain/status'
import { formatDuration } from '../domain/businessTime'
import { effectiveShiftTemplateFor } from '../domain/shiftTemplates'
import { readAllPages } from '../transport/pagination'

/**
 * 现场快速报工。
 *
 * - 默认记住本页最近选择的机台/班次，但不跨账号持久化；
 * - 扫码或搜索货号后 Enter 确认、Tab 连续输入、Ctrl/Cmd+Enter 提交；
 *   输入法组合期间不触发快捷键；
 * - 提交后支持「保存并继续」，保持机台与班次，清空产品与数量；
 * - 失败保留表单内容与 operation_id，可幂等重试；
 * - 离线只支持报工草稿：按当前用户 + 华康A 隔离保存到本地草稿存储，
 *   提示「已存本地，未提交」，不计入正式汇总。
 */

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: []; saved: [] }>()

const ctx = inject(UV_CONTEXT_KEY)!
const transport = inject(UV_TRANSPORT_KEY)!
const toast = useUvToast()
const workspace = ctx.workspace

const authStore = useAuthStore()
const draftKey = computed(() => `uv:report-draft:${workspace.isPreview.value ? 'preview' : 'live'}:huakang-a:${authStore.currentUser?.id ?? 'anonymous'}`)

const machineRequest = useUvRequest<{ items: UvMachine[] }>(
  (signal) => readAllPages((nextScope, nextSignal) => transport.value.machines(nextScope, nextSignal), workspace.scope.value, signal),
  { watchSource: () => [ctx.revision.value] },
)
const productRequest = useUvRequest<{ items: UvProduct[] }>(
  (signal) => readAllPages((nextScope, nextSignal) => transport.value.products(nextScope, nextSignal), workspace.scope.value, signal),
  { watchSource: () => [ctx.revision.value] },
)
const workerRequest = useUvRequest<{ items: UvWorkerRef[] }>(
  (signal) => readAllPages((nextScope, nextSignal) => transport.value.workers(nextScope, nextSignal), { ...workspace.scope.value, status: 'active' }, signal),
  { watchSource: () => [ctx.revision.value] },
)
const jobRequest = useUvRequest<{ items: UvPrintJob[] }>(
  (signal) => readAllPages((nextScope, nextSignal) => transport.value.jobs(nextScope, nextSignal), {
    ...workspace.scope.value,
    date_from: workspace.scope.value.business_date,
    date_to: workspace.scope.value.business_date,
  }, signal),
  { watchSource: () => [workspace.scope.value.business_date, ctx.revision.value] },
)
const shiftTemplateRequest = useUvRequest<{ items: UvShiftTemplate[] }>(
  (signal) => readAllPages((nextScope, nextSignal) => transport.value.shiftTemplates(nextScope, nextSignal), workspace.scope.value, signal),
  { watchSource: () => [workspace.business_date.value, ctx.revision.value] },
)

const machines = computed(() => machineRequest.data.value?.items ?? [])
const products = computed(() => productRequest.data.value?.items ?? [])
const workers = computed(() => workerRequest.data.value?.items ?? [])
const jobs = computed(() => jobRequest.data.value?.items ?? [])
/** 本页最近选择，仅页面级记忆，不跨账号持久化。 */
const lastMachineId = ref<string>('')
const lastShift = ref<'day' | 'night'>('day')

const machineId = ref('')
const shift = ref<'day' | 'night'>('day')
const effectiveShiftTemplate = computed(() => effectiveShiftTemplateFor(
  shiftTemplateRequest.data.value?.items ?? [], shift.value, workspace.business_date.value,
))
const productQuery = ref('')
const productId = ref('')
const reportedQty = ref<string>('')
const quality = ref<UvQuality>({ reported_qty: 0, good_qty: 0, defective_qty: 0, pending_qty: 0, semi_finished_qty: 0 })
const workerIds = ref<string[]>([])
const notes = ref('')
const selectedJobId = ref('')
const selectedJobQty = ref<string>('')
const composing = ref(false)
const productInput = ref<HTMLInputElement | null>(null)

const command = useUvCommand<unknown>()
const pendingOperation = ref<{ fingerprint: string; id: string } | null>(null)

const matchedProducts = computed(() => {
  const needle = productQuery.value.trim().toLowerCase()
  if (!needle) return products.value.slice(0, 6)
  return products.value
    .filter((product) =>
      product.product_no.toLowerCase().includes(needle)
      || product.name.toLowerCase().includes(needle)
      || product.aliases.some((alias) => alias.toLowerCase().includes(needle)),
    )
    .slice(0, 8)
})

const selectedProduct = computed(() => products.value.find((product) => product.id === productId.value) ?? null)
const selectedMachine = computed(() => machines.value.find((machine) => machine.id === machineId.value) ?? null)
const processVersion = computed(() => selectedProduct.value?.process_versions.find((version) => version.is_active)
  ?? selectedProduct.value?.process_versions[0]
  ?? null)

const candidateJobs = computed(() => jobs.value.filter((job) =>
  job.machine_id === machineId.value
  && job.reconciliation !== 'ignored'
  && (job.available_piece_qty ?? 0) > 0,
))

const selectedJob = computed(() => candidateJobs.value.find((job) => job.id === selectedJobId.value) ?? null)

const qualityTotal = computed(() =>
  quality.value.good_qty + quality.value.defective_qty + quality.value.pending_qty + quality.value.semi_finished_qty,
)

const quantityNumber = computed(() => Number(reportedQty.value || '0'))

const qualityDifference = computed(() => qualityTotal.value - quantityNumber.value)

const fieldErrors = computed(() => {
  const errors: Record<string, string> = {}
  if (!machineId.value) errors.machine_id = '请选择机台'
  if (!productId.value) errors.product_id = '请选择产品或先扫码'
  if (!Number.isInteger(quantityNumber.value) || quantityNumber.value < 0) errors.reported_qty = '报工数量必须为非负整数'
  if (qualityTotal.value !== quantityNumber.value) {
    errors.quality = `分桶合计 ${qualityTotal.value} 与报工数量 ${quantityNumber.value} 不一致，差额 ${qualityDifference.value} 件`
  }
  if (selectedJob.value && Number(selectedJobQty.value || '0') > (selectedJob.value.available_piece_qty ?? 0)) {
    errors.job = `作业只剩 ${selectedJob.value.available_piece_qty} 件可分配`
  }
  return errors
})

const canSubmit = computed(() => Object.keys(fieldErrors.value).length === 0 && !command.pending.value)

function syncPendingWithReported() {
  const total = qualityTotal.value
  if (total === quantityNumber.value) return
  quality.value = {
    reported_qty: quantityNumber.value,
    good_qty: quality.value.good_qty,
    defective_qty: quality.value.defective_qty,
    pending_qty: Math.max(0, quality.value.pending_qty + (quantityNumber.value - total)),
    semi_finished_qty: quality.value.semi_finished_qty,
  }
}

/** 质量桶是互斥的四个字段，写入时同步 reported_qty 以便守恒校验。 */
const QUALITY_BUCKET_KEYS = QUALITY_BUCKETS

/** 桶名到 UvQuality 字段名的显式映射，避免模板里做联合类型索引。 */
const QUALITY_FIELD = {
  good: 'good_qty',
  defective: 'defective_qty',
  pending: 'pending_qty',
  semi_finished: 'semi_finished_qty',
} as const satisfies Record<(typeof QUALITY_BUCKETS)[number], keyof UvQuality>

function bucketValue(bucket: (typeof QUALITY_BUCKETS)[number]): number {
  return quality.value[QUALITY_FIELD[bucket]]
}

function setBucket(bucket: (typeof QUALITY_BUCKETS)[number], raw: string) {
  const value = Math.max(0, Math.trunc(Number(raw || '0')))
  quality.value = {
    ...quality.value,
    [QUALITY_FIELD[bucket]]: Number.isFinite(value) ? value : 0,
    reported_qty: quantityNumber.value,
  }
}

function pickProduct(product: UvProduct) {
  productId.value = product.id
  productQuery.value = `${product.product_no} · ${product.name}`
  selectedJobId.value = ''
  void nextTick(() => {
    document.getElementById('uv-report-qty')?.focus()
  })
}

function onProductKeydown(event: KeyboardEvent) {
  if (composing.value || event.isComposing) return
  if (event.key === 'Enter') {
    event.preventDefault()
    const first = matchedProducts.value[0]
    if (first) pickProduct(first)
  }
}

function onFormKeydown(event: KeyboardEvent) {
  if (composing.value || event.isComposing) return
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    event.preventDefault()
    void submit(false)
  }
}

function toggleWorker(workerId: string) {
  workerIds.value = workerIds.value.includes(workerId)
    ? workerIds.value.filter((id) => id !== workerId)
    : [...workerIds.value, workerId]
}

function buildInput(operationId: string): CreateUvReport {
  return {
    factory_id: 'huakang-a',
    operation_id: operationId,
    expected_version: 0,
    business_date: workspace.business_date.value,
    shift: shift.value,
    shift_template_version_id: effectiveShiftTemplate.value?.id ?? '',
    machine_id: machineId.value,
    product_id: productId.value,
    process_version_id: processVersion.value?.id ?? '',
    reported_qty: quantityNumber.value,
    good_qty: quality.value.good_qty,
    defective_qty: quality.value.defective_qty,
    pending_qty: quality.value.pending_qty,
    semi_finished_qty: quality.value.semi_finished_qty,
    worker_ids: [...workerIds.value],
    notes: notes.value,
    source_allocations: selectedJob.value && selectedJobQty.value
      ? [{
          job_id: selectedJob.value.id,
          piece_qty: Number(selectedJobQty.value),
          job_version: selectedJob.value.version,
        }]
      : [],
    evidence_job_ids: [],
  }
}

function saveDraftLocally(input: CreateUvReport, reason: string) {
  try {
    const drafts = JSON.parse(window.localStorage.getItem(draftKey.value) ?? '[]') as unknown[]
    drafts.push({ input, reason, saved_at: new Date().toISOString() })
    window.localStorage.setItem(draftKey.value, JSON.stringify(drafts.slice(-10)))
    toast.push({
      message: '已存本地草稿，未提交',
      detail: '草稿不计入正式汇总；恢复网络并重新确认身份/厂区后可再次提交。',
      tone: 'amber',
      retryable: false,
    })
  } catch {
    toast.push({ message: '本地草稿保存失败', detail: '浏览器存储不可用，请保持页面打开并稍后重试。', tone: 'red', retryable: false })
  }
}

async function submit(keepGoing: boolean) {
  if (!canSubmit.value) return
  if (!effectiveShiftTemplate.value) {
    toast.push({ message: '该业务日没有有效班次模板', detail: '请先刷新模板或由主管配置班次版本。', tone: 'red', retryable: true })
    return
  }
  const draft = buildInput('')
  const fingerprint = JSON.stringify(draft)
  pendingOperation.value = operationForPayload(pendingOperation.value, fingerprint)
  const input = buildInput(pendingOperation.value.id)
  const result = await command.execute(input.operation_id, async () => {
    const response = await transport.value.createReport(input)
    return response.data
  })

  if (!result) {
    const error = command.error.value
    if (error && error.status === null) {
      // 网络不确定：保留表单与 operation_id，本地存草稿，不伪装成功。
      saveDraftLocally(input, '网络不确定，等待重试')
    }
    return
  }

  lastMachineId.value = machineId.value
  lastShift.value = shift.value
  ctx.markDirty()
  toast.push({
    message: `已提交报工：${selectedProduct.value?.product_no ?? ''} ${quantityNumber.value} 件`,
    detail: selectedJob.value ? `关联采集作业 ${selectedJob.value.source_job_id}，不新增第二份有效产量。` : '未关联采集作业。',
    tone: 'green',
    retryable: false,
  })

  if (keepGoing) {
    pendingOperation.value = null
    productId.value = ''
    productQuery.value = ''
    reportedQty.value = ''
    quality.value = { reported_qty: 0, good_qty: 0, defective_qty: 0, pending_qty: 0, semi_finished_qty: 0 }
    selectedJobId.value = ''
    selectedJobQty.value = ''
    notes.value = ''
    await nextTick()
    productInput.value?.focus()
    return
  }
  pendingOperation.value = null
  emit('saved')
}

watch(() => props.open, async (open) => {
  if (!open) return
  command.clearError()
  machineId.value = machineId.value || lastMachineId.value || machines.value.find((machine) => machine.admin_status !== 'disabled')?.id || ''
  shift.value = lastShift.value
  await nextTick()
  productInput.value?.focus()
})

watch([() => machineId.value, () => lastMachineId.value], () => {
  const machine = machines.value.find((candidate) => candidate.id === machineId.value)
  if (!machine) return
  if (machine.current_task_name) notes.value = machine.current_task_name
})
</script>

<template>
  <UvDrawer
    :open="open"
    size="lg"
    title="现场快速报工"
    subtitle="业务日期与班次沿用顶栏；提交前会重新校验剩余可分配量。"
    :busy="command.pending.value"
    close-hint="Esc 关闭，Ctrl/Cmd+Enter 提交"
    @close="emit('close')"
  >
    <div class="uv-section">
      <p class="uv-section__title"><span class="uv-section__index">1</span>我确认什么</p>
      <div class="uv-form" @keydown="onFormKeydown">
        <UvFormField label="机台" required field-id="uv-report-machine" :error="fieldErrors.machine_id">
          <select id="uv-report-machine" v-model="machineId" class="uv-input uv-select">
            <option value="">请选择机台</option>
            <option v-for="machine in machines" :key="machine.id" :value="machine.id">
              {{ machine.code }} · {{ machine.name }}{{ machine.admin_status === 'disabled' ? '（已停用）' : '' }}
            </option>
          </select>
        </UvFormField>

        <UvFormField label="班次" required field-id="uv-report-shift">
          <select id="uv-report-shift" v-model="shift" class="uv-input uv-select">
            <option value="day">白班</option>
            <option value="night">夜班</option>
          </select>
        </UvFormField>

        <UvFormField
          label="扫码 / 搜索货号或品名"
          required
          field-id="uv-report-product"
          :error="fieldErrors.product_id"
          help="按 Enter 选中第一条候选；输入法组合期间不会触发快捷键。"
          :span="2"
        >
          <template #default="{ invalid }">
            <div style="display: flex; gap: 6px">
              <ScanLine class="size-4" aria-hidden="true" style="align-self: center" />
              <input
                id="uv-report-product"
                ref="productInput"
                v-model="productQuery"
                class="uv-input"
                :class="invalid ? 'uv-input--invalid' : ''"
                type="search"
                placeholder="DEMO-0001 / 面板外壳 A"
                autocomplete="off"
                @keydown="onProductKeydown"
                @compositionstart="composing = true"
                @compositionend="composing = false"
              >
            </div>
            <div v-if="matchedProducts.length" class="uv-check-row" style="margin-top: 6px">
              <button
                v-for="product in matchedProducts"
                :key="product.id"
                type="button"
                class="uv-check"
                :class="product.id === productId ? 'uv-check--on' : ''"
                @click="pickProduct(product)"
              >
                {{ product.product_no }} · {{ product.name }}
              </button>
            </div>
            <p v-else class="uv-form-help">没有匹配的产品：货号必须保留前导零，不能按品名模糊覆盖。</p>
          </template>
        </UvFormField>

        <UvFormField label="报工数量（件）" required field-id="uv-report-qty" :error="fieldErrors.reported_qty">
          <template #default="{ invalid }">
            <input
              id="uv-report-qty"
              v-model="reportedQty"
              class="uv-input"
              :class="invalid ? 'uv-input--invalid' : ''"
              type="number"
              min="0"
              step="1"
              inputmode="numeric"
              @blur="syncPendingWithReported"
            >
          </template>
        </UvFormField>

        <UvFormField label="参与人员" field-id="uv-report-workers" help="同机同班同工作批次默认等分，可稍后在人员班次页调整。">
          <div class="uv-check-row">
            <label
              v-for="worker in workers"
              :key="worker.id"
              class="uv-check"
              :class="workerIds.includes(worker.id) ? 'uv-check--on' : ''"
            >
              <input
                type="checkbox"
                :checked="workerIds.includes(worker.id)"
                @change="toggleWorker(worker.id)"
              >
              {{ worker.display_name }}
            </label>
          </div>
        </UvFormField>

        <UvFormField label="备注" field-id="uv-report-notes" :span="2">
          <textarea id="uv-report-notes" v-model="notes" class="uv-input uv-textarea" rows="2" />
        </UvFormField>
      </div>
    </div>

    <div class="uv-section">
      <p class="uv-section__title"><span class="uv-section__index">2</span>质量分桶（reported = 合格 + 不良 + 待判 + 半成品）</p>
      <div class="uv-form">
        <UvFormField
          v-for="bucket in QUALITY_BUCKET_KEYS"
          :key="bucket"
          :label="QUALITY_BUCKET_LABELS[bucket]"
          :field-id="`uv-report-q-${bucket}`"
        >
          <input
            :id="`uv-report-q-${bucket}`"
            :value="bucketValue(bucket)"
            class="uv-input"
            type="number"
            min="0"
            step="1"
            inputmode="numeric"
            @input="setBucket(bucket, ($event.target as HTMLInputElement).value)"
          >
        </UvFormField>
      </div>
      <div class="uv-callout" :class="fieldErrors.quality ? 'uv-callout--warning' : ''">
        报工数量 {{ quantityNumber }} 件 · 分桶合计 {{ qualityTotal }} 件
        <template v-if="fieldErrors.quality">：{{ fieldErrors.quality }}（不自动抹平）</template>
        <template v-else>：守恒通过</template>
      </div>
      <p class="uv-state__hint">
        「不良」不自动等于「报废」，「半成品」不自动当合格品；未做质量判定可先保存全部待判。
      </p>
    </div>

    <div class="uv-section">
      <p class="uv-section__title"><span class="uv-section__index">3</span>关联采集作业（可选）</p>
      <p class="uv-state__hint">
        人工离线补录后来匹配到自动作业时，关联已有报工，不新增第二份有效产量。已确认单位的作业才能分配件数。
      </p>
      <div v-if="!candidateJobs.length" class="uv-callout">
        该机台当天没有可分配的采集作业；本次将作为纯人工报工保存。
      </div>
      <div v-else class="uv-form">
        <UvFormField label="采集作业" field-id="uv-report-job">
          <select id="uv-report-job" v-model="selectedJobId" class="uv-input uv-select">
            <option value="">不关联</option>
            <option v-for="job in candidateJobs" :key="job.id" :value="job.id">
              {{ job.raw_task_name }} · {{ RAW_UNIT[job.raw_unit] }} {{ job.raw_count ?? '—' }} · 可分配 {{ job.available_piece_qty }}
            </option>
          </select>
        </UvFormField>
        <UvFormField
          v-if="selectedJob"
          label="本次分配合计（件）"
          field-id="uv-report-job-qty"
          :error="fieldErrors.job"
          :help="`建议量 ${selectedJob.suggested_piece_qty ?? '—'} 件 · 剩余 ${selectedJob.available_piece_qty ?? '—'} 件`"
        >
          <input id="uv-report-job-qty" v-model="selectedJobQty" class="uv-input" type="number" min="0" step="1">
        </UvFormField>
      </div>
      <div v-if="selectedJob" class="uv-callout uv-callout--accent">
        <p>
          选中的作业：{{ selectedJob.raw_task_name }} ·
          <UvStatusPill :status="RECONCILIATION[selectedJob.reconciliation]" compact />
        </p>
        <p v-if="selectedJob.duplicate_suspect">
          同一机台同名前 60 秒内还有一条合法完成记录：只提示相似，不自动删除，合法连续打印必须保留。
        </p>
        <p v-if="selectedJob.print_time_seconds">
          设备打印时长 {{ formatDuration(Math.round(selectedJob.print_time_seconds / 60)) }} ·
          面积 {{ selectedJob.print_area_m2 ?? '—' }} m² · 遥测耗墨 {{ selectedJob.ink_total_ml ?? '—' }} ml（仅参考，不扣库存）
        </p>
      </div>
    </div>

    <div v-if="command.error.value" class="uv-callout uv-callout--warning" role="alert">
      <p><strong>{{ command.error.value.message }}</strong></p>
      <ul class="uv-list">
        <li v-for="(message, field) in command.error.value.fields" :key="field">
          <span class="uv-list__dot" aria-hidden="true" />{{ field }}：{{ message }}
        </li>
      </ul>
      <p class="uv-state__hint">
        表单内容与 operation_id 已保留，重试不会重复记账（同键同体重放返回原结果）。
      </p>
    </div>

    <p v-if="!workspace.can('uv_printing:report')" class="uv-readonly-note">
      没有报工权限：只能查看，提交按钮不可用。
    </p>

    <template #actions>
      <span class="uv-state__hint">
        <Keyboard class="inline size-3" aria-hidden="true" />
        Ctrl/Cmd+Enter 提交
      </span>
      <Button variant="outline" type="button" @click="emit('close')">取消</Button>
      <Button
        variant="secondary"
        type="button"
        :disabled="!canSubmit"
        @click="submit(true)"
      >
        保存并继续
      </Button>
      <Button type="button" :disabled="!canSubmit" @click="submit(false)">
        <Save class="size-4" aria-hidden="true" />
        {{ command.pending.value ? '提交中…' : '提交报工' }}
      </Button>
    </template>
  </UvDrawer>
</template>
