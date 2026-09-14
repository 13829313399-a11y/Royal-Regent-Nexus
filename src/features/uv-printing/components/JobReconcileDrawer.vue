<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import { Link2, Save, ShieldQuestion } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type { UvMachine, UvPrintJob, UvProcessVersion, UvProduct, UvRawUnit } from '../contracts'
import { UV_CONTEXT_KEY, UV_TRANSPORT_KEY } from '../composables/uvPageContext'
import { newOperationId, useUvCommand } from '../composables/useUvRequest'
import { useUvToast } from '../composables/useUvToast'
import UvDrawer from './UvDrawer.vue'
import UvField from './UvField.vue'
import UvFormField from './UvFormField.vue'
import UvStatusPill from './UvStatusPill.vue'
import { JOB_STATE, RAW_UNIT, RECONCILIATION, TIME_EVIDENCE_LABEL } from '../domain/status'
import { formatDuration, shanghaiDateTimeString } from '../domain/businessTime'
import { decimalDivide, formatDecimal, formatMoney } from '../domain/decimal'

/**
 * 来源核对抽屉：三段式「我看到了什么 / 我确认什么 / 会影响什么」。
 *
 * - 原始采集与人工确认在视觉上分别标注「设备记录」「人工确认」；
 * - 原始打印次数不是件数：只有适配器已声明是板数且每板件数已确认时，
 *   才用「完整板数 × 每板件数 + 尾板确认件数」提出建议量；
 * - 部分打印、取消、不同层多遍打印、混板产品进入人工核对；
 * - 原始单位未确认时允许附作证据，但禁止伪造可分配件数。
 */

const props = defineProps<{
  open: boolean
  job: UvPrintJob | null
  machines: UvMachine[]
  products: UvProduct[]
}>()

const emit = defineEmits<{ close: []; saved: [] }>()

const ctx = inject(UV_CONTEXT_KEY)!
const transport = inject(UV_TRANSPORT_KEY)!
const toast = useUvToast()

const productId = ref('')
const processVersionId = ref('')
const confirmedUnit = ref<UvRawUnit>('unknown')
const tailPieces = ref<string>('')
const wholeBoards = ref<string>('')
const note = ref('')
const command = useUvCommand<unknown>()

const machine = computed(() => props.machines.find((candidate) => candidate.id === props.job?.machine_id) ?? null)
const product = computed(() => props.products.find((candidate) => candidate.id === productId.value) ?? null)
const processVersion = computed<UvProcessVersion | null>(() =>
  product.value?.process_versions.find((version) => version.id === processVersionId.value) ?? null,
)

const piecesPerBoard = computed(() => processVersion.value?.pieces_per_board ?? null)

/** 建议量只作为建议：需要「板数 + 已确认每板件数」，尾板单独确认。 */
const suggestedPieces = computed(() => {
  if (confirmedUnit.value !== 'board') return null
  const boards = Number(wholeBoards.value || '0')
  if (!piecesPerBoard.value || !Number.isFinite(boards)) return null
  const tail = Number(tailPieces.value || '0')
  return boards * piecesPerBoard.value + tail
})

const blockReason = computed(() => {
  if (!props.job) return '没有选中采集作业'
  if (props.job.state === 'cancelled') return '现场已取消，未产生合格品'
  if (props.job.state === 'uncertain') return '连续读不到软件 UI，属于不确定结束：进入待核，不自动判定合格完工'
  if (confirmedUnit.value === 'unknown') return '原始单位尚未确认，只能作为证据附在报工上，不能分配件数'
  if (confirmedUnit.value === 'board' && !piecesPerBoard.value) return '产品工艺的每板件数未确认，不能盲乘'
  return ''
})

const canReconcile = computed(() => Boolean(productId.value) && !blockReason.value)

/** 单件计价面积与面积参考产值（仅在有成本权限时展示）。 */
const areaReference = computed(() => {
  const job = props.job
  if (!job?.print_area_m2) return null
  return formatDecimal(job.print_area_m2, 4)
})

watch(() => props.open, (open) => {
  if (!open) return
  command.clearError()
  const job = props.job
  productId.value = job?.product_id ?? job?.candidates[0]?.product_id ?? ''
  processVersionId.value = job?.process_version_id ?? ''
  confirmedUnit.value = job?.raw_unit ?? 'unknown'
  wholeBoards.value = job?.raw_unit === 'board' ? (job.raw_count ?? '') : ''
  tailPieces.value = ''
  note.value = job?.reconcile_note ?? ''
})

watch(productId, () => {
  const active = product.value?.process_versions.find((version) => version.is_active)
  processVersionId.value = active?.id ?? product.value?.process_versions[0]?.id ?? ''
})

async function reconcile(ignore: boolean) {
  const job = props.job
  if (!job) return
  const operationId = newOperationId()
  const result = await command.execute(operationId, async () => {
    const response = await transport.value.reconcileJob({
      factory_id: 'huakang-a',
      operation_id: operationId,
      expected_version: job.version,
      job_id: job.id,
      product_id: ignore ? null : productId.value,
      process_version_id: ignore ? null : processVersionId.value,
      confirmed_unit: ignore ? 'unknown' : confirmedUnit.value,
      confirmed_piece_qty: ignore ? null : suggestedPieces.value,
      note: note.value,
      ignore,
    })
    return response.data
  })
  if (!result) return
  ctx.markDirty()
  toast.push({
    message: ignore ? `已忽略作业 ${job.source_job_id}` : `已核对作业 ${job.source_job_id}`,
    detail: ignore
      ? '忽略是明确的业务决定，记录保留并标注原因。'
      : suggestedPieces.value === null
        ? '仅关联产品与单位，未产生可分配件数。'
        : `建议可分配 ${suggestedPieces.value} 件，仍需报工确认后才进入产量台账。`,
    tone: ignore ? 'slate' : 'green',
    retryable: false,
  })
  emit('saved')
}

/** 只作为提示：相似记录不会被删除，必须由人工判断。 */
</script>

<template>
  <UvDrawer
    :open="open"
    size="lg"
    :title="job ? `来源核对 · ${job.raw_task_name}` : '来源核对'"
    :subtitle="job ? `源作业 ${job.source_job_id} · 采集器 ${job.connector_id}（${job.generation}）` : ''"
    :busy="command.pending.value"
    @close="emit('close')"
  >
    <template v-if="job">
      <div class="uv-section">
        <p class="uv-section__title"><span class="uv-section__index">1</span>我看到了什么（设备记录）</p>
        <dl class="uv-detail-grid">
          <UvField label="原始任务名" :value="job.raw_task_name" />
          <UvField label="原始产品名" :value="job.raw_product_name" missing-label="软件未提供" />
          <UvField label="机台" :value="machine ? `${machine.code} · ${machine.name}` : job.machine_id" />
          <UvField label="采集器 / 模式" :value="`${job.connector_id} · ${machine?.connector_mode ?? '未登记'}`" />
          <UvField
            label="开始时间"
            :value="job.started_at ? shanghaiDateTimeString(job.started_at) : null"
            :missing-label="TIME_EVIDENCE_LABEL[job.time_evidence]"
            :hint="TIME_EVIDENCE_LABEL[job.time_evidence]"
          />
          <UvField
            label="完成时间"
            :value="job.completed_at ? shanghaiDateTimeString(job.completed_at) : null"
            :missing-label="job.state === 'uncertain' ? '不确定结束' : '时间待确认'"
          />
          <UvField
            label="原始次数与单位"
            :value="`${job.raw_count ?? '—'} ${RAW_UNIT[job.raw_unit]}`"
            :hint="job.raw_unit === 'unknown' ? '适配器未声明单位：不自动当件数' : ''"
          />
          <UvField
            label="设备打印时长"
            :value="job.print_time_seconds !== null ? formatDuration(Math.round(job.print_time_seconds / 60)) : null"
            missing-label="设备未提供"
          />
          <UvField label="打印幅面" :value="job.print_area_m2 ? `${formatDecimal(job.print_area_m2, 4)} m²` : null" missing-label="设备未提供" />
          <UvField label="分辨率 / 色数" :value="[job.resolution, job.color_count ? `${job.color_count} 色` : null].filter(Boolean).join(' · ') || null" missing-label="设备未提供" />
          <UvField
            label="遥测耗墨"
            :value="job.ink_total_ml ? `${formatDecimal(job.ink_total_ml, 2)} ml` : null"
            missing-label="设备未提供"
            hint="仅用于参考/差异分析，不再次扣减库房库存，也不重复计费"
            :span="2"
          />
          <UvField label="源记录 ID" :value="job.source_event_id" mono :span="2" />
        </dl>

        <div v-if="job.ink_by_color.length" class="uv-section">
          <p class="uv-section__title">分色墨量（设备提供）</p>
          <ul class="uv-list">
            <li v-for="line in job.ink_by_color" :key="line.color">
              <span class="uv-list__dot" aria-hidden="true" />
              <span>{{ line.color }}：{{ formatDecimal(line.ml, 2) }} ml</span>
            </li>
          </ul>
        </div>

        <div class="uv-callout">
          <p>
            <strong>作业状态</strong>
            <UvStatusPill :status="JOB_STATE[job.state]" compact />
            <strong>核对状态</strong>
            <UvStatusPill :status="RECONCILIATION[job.reconciliation]" compact />
          </p>
          <p v-if="job.duplicate_suspect">
            同一机台同名前 60 秒内还有另一条完成记录：只提示相似，不硬删除；合法连续打印必须保留。
          </p>
        </div>
      </div>

      <div class="uv-section">
        <p class="uv-section__title"><span class="uv-section__index">2</span>我确认什么（人工确认）</p>

        <div class="uv-form">
          <UvFormField label="关联产品" required field-id="uv-rc-product" help="同名不同货号必须各自确认，不能按品名模糊过账。">
            <select id="uv-rc-product" v-model="productId" class="uv-input uv-select">
              <option value="">请选择产品</option>
              <option v-for="candidate in products" :key="candidate.id" :value="candidate.id">
                {{ candidate.product_no }} · {{ candidate.name }}
              </option>
            </select>
          </UvFormField>

          <UvFormField label="工艺版本" required field-id="uv-rc-pv" :help="`每板件数 ${piecesPerBoard ?? '未确认'}`">
            <select id="uv-rc-pv" v-model="processVersionId" class="uv-input uv-select">
              <option value="">请选择工艺版本</option>
              <option v-for="version in product?.process_versions ?? []" :key="version.id" :value="version.id">
                {{ version.version_label }} · 生效 {{ version.effective_from }}{{ version.is_active ? '（当前）' : '' }}
              </option>
            </select>
          </UvFormField>

          <UvFormField label="原始单位确认" required field-id="uv-rc-unit" help="件/板/次的换算版本确认后才形成件数。">
            <select id="uv-rc-unit" v-model="confirmedUnit" class="uv-input uv-select">
              <option value="unknown">单位未知（只作证据）</option>
              <option value="piece">件</option>
              <option value="board">板</option>
              <option value="cycle">次</option>
            </select>
          </UvFormField>

          <template v-if="confirmedUnit === 'board'">
            <UvFormField label="完整板数" field-id="uv-rc-boards">
              <input id="uv-rc-boards" v-model="wholeBoards" class="uv-input" type="number" min="0" step="1">
            </UvFormField>
            <UvFormField label="尾板确认件数" field-id="uv-rc-tail" help="尾板、部分打印必须人工确认，不能套用整板公式。">
              <input id="uv-rc-tail" v-model="tailPieces" class="uv-input" type="number" min="0" step="1">
            </UvFormField>
          </template>

          <UvFormField label="核对说明" field-id="uv-rc-note" :span="2">
            <textarea id="uv-rc-note" v-model="note" class="uv-input uv-textarea" rows="2" />
          </UvFormField>
        </div>

        <div v-if="job.candidates.length" class="uv-callout">
          <p><strong>系统候选产品</strong>（只生成候选，人工确认后保存 ID 与版本）</p>
          <ul class="uv-list">
            <li v-for="candidate in job.candidates" :key="candidate.product_id">
              <span class="uv-list__dot" aria-hidden="true" />
              <span>
                {{ products.find((item) => item.id === candidate.product_id)?.product_no ?? candidate.product_id }}
                · {{ candidate.reason }}（置信度 {{ Math.round(candidate.confidence * 100) }}%）
              </span>
            </li>
          </ul>
        </div>
      </div>

      <div class="uv-section">
        <p class="uv-section__title"><span class="uv-section__index">3</span>会影响什么</p>
        <dl class="uv-detail-grid">
          <UvField
            label="建议可分配件数"
            :value="suggestedPieces === null ? null : `${suggestedPieces} 件`"
            :missing-label="blockReason || '需要确认单位与每板件数'"
            emphasis
          />
          <UvField
            label="当前剩余可分配"
            :value="job.available_piece_qty === null ? null : `${job.available_piece_qty} 件`"
            :missing-label="'单位未确认，暂无可分配量'"
          />
          <UvField label="单件计价面积" :value="processVersion?.pricing_area_cm2 ? `${processVersion.pricing_area_cm2} cm²` : null" missing-label="工艺未确认" />
          <UvField label="设备打印面积" :value="areaReference ? `${areaReference} m²` : null" missing-label="设备未提供" hint="与计费面积分开保存，不能混为一个字段" />
          <UvField
            label="产量影响"
            value="核对本身不产生合格产量"
            hint="确认后仍需业务报工；草稿不计入有效产量、工资与经营产值"
            :span="2"
          />
        </dl>

        <div class="uv-callout uv-callout--warning">
          <p>
            <ShieldQuestion class="inline size-3.5" aria-hidden="true" />
            <strong>人工补录先到达时</strong>：之后匹配到自动作业只关联原报工，不新增第二份有效产量；
            一条可分配作业拆给多份报工时，累计分配量不得超过可分配量。
          </p>
          <p v-if="job.suggested_piece_qty !== null && job.available_piece_qty !== null && job.available_piece_qty < job.suggested_piece_qty">
            该作业已被分配 {{ job.suggested_piece_qty - job.available_piece_qty }} 件。
          </p>
        </div>

        <p v-if="!ctx.workspace.can('uv_printing:cost_read')" class="uv-readonly-note">
          没有成本权限：这里不展示单价、产值或工资预览，服务端也不会下发这些字段。
        </p>
        <p v-if="!ctx.workspace.can('uv_printing:report')" class="uv-readonly-note">
          没有报工权限：核对与忽略按钮不可用。后端权限才是权威边界。
        </p>
      </div>

      <div v-if="command.error.value" class="uv-callout uv-callout--warning" role="alert">
        <p><strong>{{ command.error.value.message }}</strong></p>
        <ul class="uv-list">
          <li v-for="(message, field) in command.error.value.fields" :key="field">
            <span class="uv-list__dot" aria-hidden="true" />{{ field }}：{{ message }}
          </li>
        </ul>
      </div>
    </template>

    <template #actions>
      <Button variant="ghost" type="button" @click="emit('close')">取消</Button>
      <Button
        variant="outline"
        type="button"
        :disabled="!ctx.workspace.can('uv_printing:report') || command.pending.value"
        @click="reconcile(true)"
      >
        忽略这条作业
      </Button>
      <Button
        type="button"
        :disabled="!canReconcile || !ctx.workspace.can('uv_printing:report') || command.pending.value"
        @click="reconcile(false)"
      >
        <Link2 class="size-4" aria-hidden="true" />
        {{ command.pending.value ? '保存核对中…' : '保存核对结果' }}
      </Button>
    </template>
  </UvDrawer>
</template>
