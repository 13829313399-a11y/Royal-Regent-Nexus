<script setup lang="ts">
import { computed, inject, reactive, ref, watch } from 'vue'
import { Calculator, ChevronDown, Layers, Plus, Ruler } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type {
  BusinessDate,
  UvMachine,
  UvMutationResult,
  UvProcessVersion,
  UvProcessVersionInput,
  UvProduct,
  UvProductSaveInput,
  UvRateKind,
  UvRateVersion,
  UvResponse,
} from '../contracts'
import { UV_CONTEXT_KEY, UV_TRANSPORT_KEY } from '../composables/uvPageContext'
import { newOperationId, useUvCommand } from '../composables/useUvRequest'
import { formatDuration } from '../domain/businessTime'
import { decimalCompare, decimalIsZero, decimalMultiply, formatDecimal, money } from '../domain/decimal'
import { PRICING_STATE, RATE_KIND_LABELS } from '../domain/status'
import UvField from './UvField.vue'
import UvFormField from './UvFormField.vue'
import UvNumber from './UvNumber.vue'
import UvStatusPill from './UvStatusPill.vue'
import UvTable from './UvTable.vue'

/**
 * 产品版本与价规面板（产品定价页左栏）。
 *
 * - 工艺版本详情按契约逐项展示；每板件数为 null 时显示「未确认」，绝不猜测为 1；
 * - 计价面积 cm² 与机器打印面积 m² 分开保存、分开显示，不做互相换算；
 * - 价规分商业执行价 / 计件工价 / 面积费率三组，组内不串价、不跨币种回退；
 * - 基础设置（产品资料 / 工艺版本 / 价规维护）是页面内的「按需展开」披露区，
 *   不是又一个顶级菜单；维护动作受 master_write / cost_write / payroll_write 约束。
 */

const props = withDefaults(defineProps<{
  product: UvProduct | null
  /** 该产品的全部价规版本（已按 cost_read 权限决定是否可读）。 */
  productRates: UvRateVersion[]
  machines: UvMachine[]
  businessDate: BusinessDate
  /** 在业务日生效的价规 id，由页面统一按优先级解析。 */
  effectiveRateIds: string[]
  selectedVersionId: string
  canReadCost: boolean
  canPayrollRead: boolean
  canWriteCost: boolean
  canPayrollWrite: boolean
  canMasterWrite: boolean
  /** 页面统一维护的优先级与回退口径说明。 */
  priorityNote: string
}>(), {
  product: null,
})

const emit = defineEmits<{
  'select-version': [versionId: string]
  'create-rate': [kind: UvRateKind]
  'edit-rate': [rate: UvRateVersion]
  'saved-product': [product: UvProduct]
  'saved-version': [version: UvProcessVersion]
}>()

const transportRef = inject(UV_TRANSPORT_KEY)
const context = inject(UV_CONTEXT_KEY)
if (!transportRef || !context) {
  throw new Error('产品版本面板必须在 UV 工作区壳内使用。')
}

const RATE_KINDS: UvRateKind[] = ['commercial', 'piece_wage', 'area']

const basicsOpen = ref(false)
const productCommand = useUvCommand<UvResponse<UvMutationResult<UvProduct>>>()
const versionCommand = useUvCommand<UvResponse<UvMutationResult<UvProcessVersion>>>()
const productFieldErrors = reactive<Record<string, string>>({})
const versionFieldErrors = reactive<Record<string, string>>({})

let productOperation: { id: string; fingerprint: string } | null = null
let versionOperation: { id: string; fingerprint: string } | null = null

function operationFor(
  current: { id: string; fingerprint: string } | null,
  fingerprint: string,
): { id: string; fingerprint: string } {
  if (current && current.fingerprint === fingerprint) return current
  return { id: newOperationId(), fingerprint }
}

const productForm = reactive({
  product_no: '',
  name: '',
  customer_name: '',
  external_ref: '',
  external_ref_kind: 'none' as UvProductSaveInput['external_ref_kind'],
  aliasText: '',
})

const versionForm = reactive({
  version_label: '',
  effective_from: props.businessDate,
  material: '',
  pieces_per_board: '',
  board_seconds: '',
  width_cm: '',
  length_cm: '',
  machine_area_m2: '',
  ink_reference_ml: '',
})

function seedProductForm(product: UvProduct | null) {
  if (!product) return
  productForm.product_no = product.product_no
  productForm.name = product.name
  productForm.customer_name = product.customer_name
  productForm.external_ref = product.external_ref ?? ''
  productForm.external_ref_kind = product.external_ref_kind
  productForm.aliasText = product.aliases.join('、')
}

function seedVersionForm(product: UvProduct | null, businessDate: BusinessDate) {
  const latest = product?.process_versions[product.process_versions.length - 1]
  versionForm.version_label = latest ? nextLabel(latest.version_label) : 'v1'
  versionForm.effective_from = businessDate
  versionForm.material = latest?.material ?? ''
  versionForm.pieces_per_board = ''
  versionForm.board_seconds = ''
  versionForm.width_cm = latest?.width_cm ?? ''
  versionForm.length_cm = latest?.length_cm ?? ''
  versionForm.machine_area_m2 = latest?.machine_area_m2 ?? ''
  versionForm.ink_reference_ml = latest?.ink_reference_ml ?? ''
}

function nextLabel(label: string): string {
  const matched = /^v(\d+)$/i.exec(label.trim())
  return matched ? `v${Number(matched[1]) + 1}` : `${label}（新）`
}

watch(() => props.product?.id, () => {
  seedProductForm(props.product)
  seedVersionForm(props.product, props.businessDate)
  for (const key of Object.keys(productFieldErrors)) delete productFieldErrors[key]
  for (const key of Object.keys(versionFieldErrors)) delete versionFieldErrors[key]
  productCommand.clearError()
  versionCommand.clearError()
  productOperation = null
  versionOperation = null
}, { immediate: true })

const versions = computed(() => props.product?.process_versions ?? [])

const activeVersion = computed<UvProcessVersion | null>(() => {
  const list = versions.value
  return list.find((version) => version.is_active) ?? list[list.length - 1] ?? null
})

const selectedVersion = computed<UvProcessVersion | null>(() => {
  const list = versions.value
  return list.find((version) => version.id === props.selectedVersionId) ?? activeVersion.value
})

const machineLabels = computed(() => {
  const map = new Map<string, string>()
  for (const machine of props.machines) map.set(machine.id, machine.code)
  return map
})

function machineLabel(rate: UvRateVersion): string {
  if (!rate.machine_id) return '—'
  return machineLabels.value.get(rate.machine_id) ?? rate.machine_id
}

function priorityLabel(rate: UvRateVersion): string {
  if (rate.machine_id) return '精确机台覆盖'
  if (rate.price_group) return `价组覆盖（${rate.price_group}）`
  return '标准价'
}

function rateRows(kind: UvRateKind): UvRateVersion[] {
  return props.productRates
    .filter((rate) => rate.rate_kind === kind)
    .slice()
    .sort((a, b) => b.effective_from.localeCompare(a.effective_from))
}

/** 计件工价是工资口径，缺少计件工资读取权限时不显示金额。 */
function rateAmountVisible(rate: UvRateVersion): boolean {
  if (!props.canReadCost) return false
  return rate.rate_kind !== 'piece_wage' || props.canPayrollRead
}

function rateAmount(rate: UvRateVersion) {
  return money(rate.currency, rate.unit_price)
}

function rateIsZero(rate: UvRateVersion): boolean {
  return decimalIsZero(rate.unit_price)
}

function effectiveInterval(rate: UvRateVersion): string {
  return rate.effective_to ? `${rate.effective_from} 至 ${rate.effective_to}` : `${rate.effective_from} 起长期有效`
}

const emptyGroupNote: Record<UvRateKind, string> = {
  commercial: '没有生效的商业执行价：产值显示「未定价」，不显示 0，也不回退到面积费率。',
  piece_wage: '没有生效的计件工价：工资显示「未定价」，不会回退到商业执行价。',
  area: '没有生效的面积费率：面积产值不可算，不回退到按件单价。',
}

const commercialEffective = computed(() =>
  props.productRates.filter((rate) => rate.rate_kind === 'commercial' && props.effectiveRateIds.includes(rate.id)),
)

const commercialState = computed(() => {
  if (!props.canReadCost) return 'forbidden' as const
  if (!commercialEffective.value.length) return 'unpriced' as const
  return commercialEffective.value.every((rate) => decimalIsZero(rate.unit_price)) ? 'zero' as const : 'priced' as const
})

function boardSecondsLabel(seconds: number | null): string {
  if (seconds === null) return ''
  const minutes = Math.round(seconds / 60)
  return `${formatDuration(minutes)}（${seconds} 秒）`
}

const areaConsistency = computed(() => {
  const version = selectedVersion.value
  if (!version?.pricing_area_cm2 || !version.width_cm || !version.length_cm) return null
  const computedArea = decimalMultiply(version.length_cm, version.width_cm)
  return decimalCompare(computedArea, version.pricing_area_cm2) === 0
    ? null
    : `计价面积 ${formatDecimal(version.pricing_area_cm2, 2)} cm² 与 长×宽 = ${formatDecimal(computedArea, 2)} cm² 不一致，按服务端记录展示，不自动改写。`
})

const canMaintain = computed(() => props.canMasterWrite)

function rateKindWritable(kind: UvRateKind): boolean {
  return kind === 'piece_wage' ? props.canPayrollWrite : props.canWriteCost
}

function rateKindBlockedReason(kind: UvRateKind): string {
  if (rateKindWritable(kind)) return ''
  return `${RATE_KIND_LABELS[kind]}需要${kind === 'piece_wage' ? '「计件工资维护权限」' : '「成本维护权限」'}，当前账号没有该权限，新增已停用；是否允许写入以服务端判定为准。`
}

const masterBlockedReason = computed(() => (canMaintain.value
  ? ''
  : '维护产品资料与工艺版本需要「主数据维护权限」，当前账号没有该权限，保存已停用；是否允许写入以服务端判定为准。'))

function isDecimal(value: string): boolean {
  return /^\d+(\.\d+)?$/.test(value.trim())
}

function isOptionalDecimal(value: string): boolean {
  return value.trim() === '' || isDecimal(value)
}

function isOptionalPositiveInt(value: string): boolean {
  return value.trim() === '' || /^\d+$/.test(value.trim())
}

async function saveProduct() {
  const product = props.product
  if (!product || !canMaintain.value) return
  for (const key of Object.keys(productFieldErrors)) delete productFieldErrors[key]
  if (!productForm.product_no.trim()) {
    productFieldErrors.product_no = '货号必填；货号保留前导零，是价规与报工的精确匹配键'
  }
  if (!productForm.name.trim()) productFieldErrors.name = '品名必填'
  if (Object.keys(productFieldErrors).length) return
  const input: UvProductSaveInput = {
    factory_id: context!.workspace.scope.value.factory_id,
    operation_id: '',
    expected_version: product.version,
    id: product.id,
    product_no: productForm.product_no.trim(),
    name: productForm.name.trim(),
    customer_name: productForm.customer_name.trim(),
    external_ref: productForm.external_ref.trim() || null,
    external_ref_kind: productForm.external_ref_kind,
    aliases: productForm.aliasText
      .split(/[、,，\s]+/)
      .map((alias) => alias.trim())
      .filter(Boolean),
  }
  const fingerprint = JSON.stringify(input)
  productOperation = operationFor(productOperation, fingerprint)
  input.operation_id = productOperation.id
  const result = await productCommand.execute(productOperation.id, () => transportRef!.value.saveProduct(input))
  if (!result) {
    for (const [key, message] of Object.entries(productCommand.error.value?.fields ?? {})) {
      productFieldErrors[key] = message
    }
    return
  }
  productOperation = null
  context!.markDirty()
  emit('saved-product', result.data.entity)
}

async function saveProcessVersion() {
  const product = props.product
  if (!product || !canMaintain.value) return
  for (const key of Object.keys(versionFieldErrors)) delete versionFieldErrors[key]
  if (!versionForm.version_label.trim()) versionFieldErrors.version_label = '版本号必填'
  if (!versionForm.effective_from) versionFieldErrors.effective_from = '生效日必填'
  if (!versionForm.material.trim()) versionFieldErrors.material = '材料必填'
  if (!isOptionalPositiveInt(versionForm.pieces_per_board)) {
    versionFieldErrors.pieces_per_board = '每板件数必须是正整数；未确认请留空，不要填 1 代替'
  } else if (versionForm.pieces_per_board.trim() === '0') {
    versionFieldErrors.pieces_per_board = '每板件数必须大于 0；未确认请留空'
  }
  if (!isOptionalPositiveInt(versionForm.board_seconds)) {
    versionFieldErrors.board_seconds = '每板耗时必须是整数秒；未确认请留空'
  }
  for (const [key, label] of [
    ['width_cm', '宽'],
    ['length_cm', '长'],
    ['machine_area_m2', '机器打印面积'],
    ['ink_reference_ml', '耗墨参考'],
  ] as const) {
    if (!isOptionalDecimal(versionForm[key])) versionFieldErrors[key] = `${label}必须是非负十进制数字`
  }
  if (Object.keys(versionFieldErrors).length) return

  const input: UvProcessVersionInput = {
    factory_id: context!.workspace.scope.value.factory_id,
    operation_id: '',
    expected_version: product.version,
    product_id: product.id,
    version_label: versionForm.version_label.trim(),
    effective_from: versionForm.effective_from,
    material: versionForm.material.trim(),
    pieces_per_board: versionForm.pieces_per_board.trim() === '' ? null : Number(versionForm.pieces_per_board.trim()),
    board_seconds: versionForm.board_seconds.trim() === '' ? null : Number(versionForm.board_seconds.trim()),
    width_cm: versionForm.width_cm.trim() || null,
    length_cm: versionForm.length_cm.trim() || null,
    machine_area_m2: versionForm.machine_area_m2.trim() || null,
    ink_reference_ml: versionForm.ink_reference_ml.trim() || null,
  }
  const fingerprint = JSON.stringify(input)
  versionOperation = operationFor(versionOperation, fingerprint)
  input.operation_id = versionOperation.id
  const result = await versionCommand.execute(versionOperation.id, () => transportRef!.value.addProcessVersion(input))
  if (!result) {
    for (const [key, message] of Object.entries(versionCommand.error.value?.fields ?? {})) {
      versionFieldErrors[key] = message
    }
    return
  }
  versionOperation = null
  context!.markDirty()
  emit('saved-version', result.data.entity)
  seedVersionForm(props.product, props.businessDate)
}
</script>

<template>
  <section class="uv-panel" aria-labelledby="uv-catalog-version-title">
    <header class="uv-panel__head">
      <div>
        <h2 id="uv-catalog-version-title" class="uv-panel__title">工艺版本与价规</h2>
        <p class="uv-panel__subtitle">
          {{
            product
              ? `${product.product_no} · ${product.name}｜客户 ${product.customer_name || '未登记'}`
              : '从上方产品列表选择一个货号后，这里显示它的工艺版本与价规。'
          }}
        </p>
      </div>
      <div v-if="product" class="uv-actions">
        <UvStatusPill
          v-if="commercialState === 'priced'"
          :status="PRICING_STATE.priced"
          compact
          suffix="有生效执行价"
        />
        <UvStatusPill
          v-else-if="commercialState === 'zero'"
          :status="PRICING_STATE.priced"
          compact
          suffix="零价执行"
        />
        <UvStatusPill
          v-else-if="commercialState === 'unpriced'"
          :status="PRICING_STATE.unpriced"
          compact
        />
        <span v-else class="uv-form-readonly">价格无读取权限</span>
      </div>
    </header>

    <div class="uv-panel__body">
      <p v-if="!product" class="uv-state__hint">当前没有选中的产品。</p>

      <template v-else>
        <dl class="uv-detail-grid">
          <UvField label="货号" :value="product.product_no" mono hint="字符串精确匹配，保留前导零" />
          <UvField label="品名" :value="product.name" hint="同名不同货号是两条独立产品，不合并" />
          <UvField label="客户" :value="product.customer_name" missing-label="未登记客户" />
          <UvField
            label="外部引用"
            :value="product.external_ref"
            missing-label="未接入上游单号"
            :hint="product.external_ref_kind === 'order' ? '订单号' : product.external_ref_kind === 'quotation' ? '报价单号' : '手工录入，未标记单号类型'"
          />
          <UvField
            label="别名"
            :value="product.aliases.join('、')"
            missing-label="无别名"
            hint="别名只用于检索提示，不参与价格匹配"
          />
          <UvField label="产品版本" :value="`v${product.version}`" mono />
        </dl>

        <div class="uv-section">
          <h3 class="uv-section__title">
            <span class="uv-section__index" aria-hidden="true">1</span>
            工艺版本明细
          </h3>

          <UvTable
            :columns="[
              { key: 'label', label: '版本号', width: 110 },
              { key: 'effective', label: '生效日', width: 130 },
              { key: 'material', label: '材料', width: 100 },
              { key: 'pieces', label: '每板件数', width: 120, align: 'right', hint: '未确认必须留空' },
              { key: 'board', label: '每板耗时', width: 170, align: 'right', hint: '由秒换算' },
              { key: 'size', label: '尺寸 长×宽', width: 150, align: 'right' },
              { key: 'area', label: '计价面积 cm²', width: 130, align: 'right', hint: '长×宽' },
              { key: 'machineArea', label: '机器打印面积 m²', width: 150, align: 'right', hint: '与计价面积分开' },
              { key: 'ink', label: '耗墨参考 ml', width: 120, align: 'right' },
              { key: 'state', label: '版本状态', width: 120 },
            ]"
            :min-width="1320"
            dense
            :caption="`${product.product_no} 工艺版本`"
            keyboard-hint="使用 Tab 移动到版本行的选择按钮，Enter 选中该版本用于定价测算。"
          >
            <tr
              v-for="version in versions"
              :key="version.id"
              :aria-selected="selectedVersion?.id === version.id"
            >
              <td>
                <button type="button" class="uv-row-button" @click="emit('select-version', version.id)">
                  <span class="uv-row-primary uv-mono">{{ version.version_label }}</span>
                  <span class="sr-only">选为定价测算使用的工艺版本</span>
                </button>
              </td>
              <td>{{ version.effective_from }}</td>
              <td>{{ version.material }}</td>
              <td class="uv-table-cell--right">
                <UvNumber
                  v-if="version.pieces_per_board !== null"
                  :qty="version.pieces_per_board"
                  unit="件/板"
                />
                <template v-else>
                  <span class="uv-num uv-num--pending">未确认</span>
                  <span class="uv-field__hint">不按 1 件猜测</span>
                </template>
              </td>
              <td class="uv-table-cell--right">
                <template v-if="version.board_seconds !== null">
                  <span class="uv-num">{{ boardSecondsLabel(version.board_seconds) }}</span>
                </template>
                <span v-else class="uv-num uv-num--pending">未提供</span>
              </td>
              <td class="uv-table-cell--right">
                <template v-if="version.length_cm && version.width_cm">
                  {{ formatDecimal(version.length_cm, 2) }} × {{ formatDecimal(version.width_cm, 2) }} cm
                </template>
                <span v-else class="uv-num uv-num--missing">—</span>
              </td>
              <td class="uv-table-cell--right">
                <UvNumber
                  v-if="version.pricing_area_cm2"
                  :decimal="version.pricing_area_cm2"
                  :decimal-scale="2"
                  unit="cm²"
                />
                <span v-else class="uv-num uv-num--missing">—</span>
              </td>
              <td class="uv-table-cell--right">
                <UvNumber
                  v-if="version.machine_area_m2"
                  :decimal="version.machine_area_m2"
                  :decimal-scale="3"
                  unit="m²"
                />
                <span v-else class="uv-num uv-num--missing">—</span>
              </td>
              <td class="uv-table-cell--right">
                <UvNumber
                  v-if="version.ink_reference_ml"
                  :decimal="version.ink_reference_ml"
                  :decimal-scale="2"
                  unit="ml"
                />
                <span v-else class="uv-num uv-num--missing">无参考</span>
              </td>
              <td>
                <UvStatusPill
                  v-if="version.is_active"
                  :status="{ label: '当前生效', tone: 'teal' }"
                  compact
                />
                <UvStatusPill v-else :status="{ label: '历史版本', tone: 'slate' }" compact />
              </td>
            </tr>
          </UvTable>

          <p v-if="areaConsistency" class="uv-callout uv-callout--warning" role="status">
            <Ruler class="inline size-3.5" aria-hidden="true" />
            {{ areaConsistency }}
          </p>

          <dl v-if="selectedVersion" class="uv-detail-grid mt-3">
            <UvField
              label="选中版本"
              :value="`${selectedVersion.version_label} · 生效 ${selectedVersion.effective_from}`"
              emphasis
            />
            <UvField
              label="每板件数"
              :value="selectedVersion.pieces_per_board === null ? null : `${selectedVersion.pieces_per_board} 件/板`"
              missing-label="未确认"
              hint="留空表示工艺未确认，测算台不会按 1 件计算"
            />
            <UvField
              label="每板耗时"
              :value="selectedVersion.board_seconds === null ? null : boardSecondsLabel(selectedVersion.board_seconds)"
              missing-label="未提供"
              hint="测算台以小时为单位填写"
            />
            <UvField
              label="计价面积"
              :value="selectedVersion.pricing_area_cm2 ? `${formatDecimal(selectedVersion.pricing_area_cm2, 2)} cm²` : null"
              missing-label="未记录"
              hint="长 × 宽"
            />
            <UvField
              label="机器打印面积"
              :value="selectedVersion.machine_area_m2 ? `${formatDecimal(selectedVersion.machine_area_m2, 3)} m²` : null"
              missing-label="未记录"
              hint="设备口径，与计价面积不做换算"
            />
            <UvField
              label="耗墨参考"
              :value="selectedVersion.ink_reference_ml ? `${formatDecimal(selectedVersion.ink_reference_ml, 2)} ml` : null"
              missing-label="无参考"
            />
          </dl>
        </div>

        <div class="uv-section">
          <h3 class="uv-section__title">
            <span class="uv-section__index" aria-hidden="true">2</span>
            价规版本（三种价规分开计算）
          </h3>
          <p class="uv-callout uv-callout--accent">{{ priorityNote }}</p>

          <div v-for="kind in RATE_KINDS" :key="kind" class="uv-section">
            <h4 class="uv-section__title">
              <Layers class="size-3.5" aria-hidden="true" />
              {{ RATE_KIND_LABELS[kind] }}
              <span class="uv-form-readonly">{{ rateRows(kind).length }} 条</span>
            </h4>

            <UvTable
              v-if="rateRows(kind).length"
              :columns="[
                { key: 'priority', label: '优先级', width: 160 },
                { key: 'machine', label: '机台', width: 100 },
                { key: 'currency', label: '币种', width: 80 },
                { key: 'price', label: '单价', width: 130, align: 'right' },
                { key: 'interval', label: '生效区间', width: 240 },
                { key: 'note', label: '备注', width: 220 },
                { key: 'state', label: '状态', width: 130 },
                { key: 'actions', label: '操作', width: 110 },
              ]"
              :min-width="1180"
              dense
              :caption="`${product.product_no} ${RATE_KIND_LABELS[kind]}`"
              keyboard-hint=""
            >
              <tr v-for="rate in rateRows(kind)" :key="rate.id" :aria-selected="effectiveRateIds.includes(rate.id)">
                <td>{{ priorityLabel(rate) }}</td>
                <td class="uv-mono">{{ machineLabel(rate) }}</td>
                <td>{{ rate.currency }}</td>
                <td class="uv-table-cell--right">
                  <UvNumber v-if="rateAmountVisible(rate)" :money="rateAmount(rate)" />
                  <span v-else class="uv-num uv-num--pending">无读取权限</span>
                </td>
                <td>{{ effectiveInterval(rate) }}</td>
                <td>{{ rate.note || '—' }}</td>
                <td>
                  <span class="flex flex-wrap items-center gap-1">
                    <UvStatusPill
                      v-if="effectiveRateIds.includes(rate.id)"
                      :status="{ label: '当前生效', tone: 'green' }"
                      compact
                    />
                    <UvStatusPill
                      v-if="rateAmountVisible(rate) && rateIsZero(rate)"
                      :status="{ label: '零价执行', tone: 'blue' }"
                      compact
                    />
                  </span>
                </td>
                <td>
                  <Button
                    v-if="rateKindWritable(kind)"
                    variant="ghost"
                    size="xs"
                    type="button"
                    :aria-label="`编辑${RATE_KIND_LABELS[kind]}（${priorityLabel(rate)}）`"
                    @click="emit('edit-rate', rate)"
                  >
                    编辑
                  </Button>
                  <span v-else class="uv-field__hint">无权限编辑</span>
                </td>
              </tr>
            </UvTable>

            <p v-else class="uv-callout uv-callout--warning" role="status">
              {{ emptyGroupNote[kind] }}
            </p>
          </div>
        </div>

        <div class="uv-section">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <h3 class="uv-section__title">
              <span class="uv-section__index" aria-hidden="true">3</span>
              基础设置（产品资料 / 工艺版本 / 价规维护）
            </h3>
            <Button
              variant="outline"
              size="sm"
              type="button"
              aria-controls="uv-catalog-basics"
              :aria-expanded="basicsOpen"
              @click="basicsOpen = !basicsOpen"
            >
              <ChevronDown class="size-3.5 transition-transform" :class="basicsOpen ? 'rotate-180' : ''" aria-hidden="true" />
              {{ basicsOpen ? '收起维护表单' : '按需展开维护表单' }}
            </Button>
          </div>
          <p class="uv-form-help">
            维护表单默认收起：日常只做查询与测算，避免误改主数据。展开后才显示可编辑字段。
          </p>

          <div v-show="basicsOpen" id="uv-catalog-basics" class="grid gap-4">
            <div v-if="masterBlockedReason" class="uv-callout uv-callout--warning" role="alert">
              {{ masterBlockedReason }}
            </div>

            <form class="uv-form" novalidate @submit.prevent="saveProduct">
              <h4 class="uv-section__title uv-form-field--span-3">
                <Calculator class="size-3.5" aria-hidden="true" />
                产品资料
              </h4>
              <UvFormField
                label="货号"
                required
                field-id="uv-product-no"
                :error="productFieldErrors.product_no ?? ''"
                help="保留前导零；货号重复会被服务端拒绝，不会按品名合并。"
              >
                <template #default="{ describedBy, invalid }">
                  <input
                    id="uv-product-no"
                    v-model="productForm.product_no"
                    class="uv-input uv-mono"
                    :class="invalid ? 'uv-input--invalid' : ''"
                    type="text"
                    autocomplete="off"
                    :readonly="!canMaintain"
                    :aria-describedby="describedBy"
                    :aria-invalid="invalid"
                  >
                </template>
              </UvFormField>
              <UvFormField
                label="品名"
                required
                field-id="uv-product-name"
                :error="productFieldErrors.name ?? ''"
                help="同名可以存在多个货号，系统不做模糊合并。"
              >
                <template #default="{ describedBy, invalid }">
                  <input
                    id="uv-product-name"
                    v-model="productForm.name"
                    class="uv-input"
                    :class="invalid ? 'uv-input--invalid' : ''"
                    type="text"
                    :readonly="!canMaintain"
                    :aria-describedby="describedBy"
                    :aria-invalid="invalid"
                  >
                </template>
              </UvFormField>
              <UvFormField label="客户" field-id="uv-product-customer" :error="productFieldErrors.customer_name ?? ''">
                <template #default="{ describedBy, invalid }">
                  <input
                    id="uv-product-customer"
                    v-model="productForm.customer_name"
                    class="uv-input"
                    :class="invalid ? 'uv-input--invalid' : ''"
                    type="text"
                    :readonly="!canMaintain"
                    :aria-describedby="describedBy"
                    :aria-invalid="invalid"
                  >
                </template>
              </UvFormField>
              <UvFormField label="外部引用单号" field-id="uv-product-ref" :error="productFieldErrors.external_ref ?? ''">
                <template #default="{ describedBy, invalid }">
                  <input
                    id="uv-product-ref"
                    v-model="productForm.external_ref"
                    class="uv-input uv-mono"
                    :class="invalid ? 'uv-input--invalid' : ''"
                    type="text"
                    :readonly="!canMaintain"
                    :aria-describedby="describedBy"
                    :aria-invalid="invalid"
                  >
                </template>
              </UvFormField>
              <UvFormField label="引用类型" field-id="uv-product-ref-kind">
                <template #default="{ describedBy }">
                  <select
                    id="uv-product-ref-kind"
                    v-model="productForm.external_ref_kind"
                    class="uv-input uv-select"
                    :disabled="!canMaintain"
                    :aria-describedby="describedBy"
                  >
                    <option value="none">无外部引用</option>
                    <option value="order">订单号</option>
                    <option value="quotation">报价单号</option>
                  </select>
                </template>
              </UvFormField>
              <UvFormField label="别名" field-id="uv-product-alias" help="用顿号或逗号分隔；别名只用于检索，不参与价格匹配。">
                <template #default="{ describedBy }">
                  <input
                    id="uv-product-alias"
                    v-model="productForm.aliasText"
                    class="uv-input"
                    type="text"
                    :readonly="!canMaintain"
                    :aria-describedby="describedBy"
                  >
                </template>
              </UvFormField>
              <div class="uv-actions uv-form-field--span-3">
                <Button type="submit" size="sm" :disabled="!canMaintain || productCommand.pending.value">
                  {{ productCommand.pending.value ? '正在保存…' : '保存产品资料' }}
                </Button>
                <span v-if="!canMaintain" class="uv-field__hint">{{ masterBlockedReason }}</span>
              </div>
              <p v-if="productCommand.error.value" class="uv-callout uv-callout--warning uv-form-field--span-3" role="alert">
                保存失败：{{ productCommand.error.value.message }}（表单内容已保留，可修改后重试）
              </p>
            </form>

            <form class="uv-form" novalidate @submit.prevent="saveProcessVersion">
              <h4 class="uv-section__title uv-form-field--span-3">新增工艺版本</h4>
              <UvFormField
                label="版本号"
                required
                field-id="uv-version-label"
                :error="versionFieldErrors.version_label ?? ''"
              >
                <template #default="{ describedBy, invalid }">
                  <input
                    id="uv-version-label"
                    v-model="versionForm.version_label"
                    class="uv-input uv-mono"
                    :class="invalid ? 'uv-input--invalid' : ''"
                    type="text"
                    :readonly="!canMaintain"
                    :aria-describedby="describedBy"
                    :aria-invalid="invalid"
                  >
                </template>
              </UvFormField>
              <UvFormField
                label="生效日"
                required
                field-id="uv-version-effective"
                :error="versionFieldErrors.effective_from ?? ''"
                help="新版本生效后，旧版本自动转为历史版本。"
              >
                <template #default="{ describedBy, invalid }">
                  <input
                    id="uv-version-effective"
                    v-model="versionForm.effective_from"
                    class="uv-input"
                    :class="invalid ? 'uv-input--invalid' : ''"
                    type="date"
                    :readonly="!canMaintain"
                    :aria-describedby="describedBy"
                    :aria-invalid="invalid"
                  >
                </template>
              </UvFormField>
              <UvFormField
                label="材料"
                required
                field-id="uv-version-material"
                :error="versionFieldErrors.material ?? ''"
              >
                <template #default="{ describedBy, invalid }">
                  <input
                    id="uv-version-material"
                    v-model="versionForm.material"
                    class="uv-input"
                    :class="invalid ? 'uv-input--invalid' : ''"
                    type="text"
                    :readonly="!canMaintain"
                    :aria-describedby="describedBy"
                    :aria-invalid="invalid"
                  >
                </template>
              </UvFormField>
              <UvFormField
                label="每板件数"
                field-id="uv-version-pieces"
                :error="versionFieldErrors.pieces_per_board ?? ''"
                help="留空表示未确认；未确认不会被当成 1 件。"
              >
                <template #default="{ describedBy, invalid }">
                  <input
                    id="uv-version-pieces"
                    v-model="versionForm.pieces_per_board"
                    class="uv-input"
                    :class="invalid ? 'uv-input--invalid' : ''"
                    type="number"
                    inputmode="numeric"
                    min="1"
                    step="1"
                    :readonly="!canMaintain"
                    :aria-describedby="describedBy"
                    :aria-invalid="invalid"
                  >
                </template>
              </UvFormField>
              <UvFormField
                label="每板耗时（秒）"
                field-id="uv-version-seconds"
                :error="versionFieldErrors.board_seconds ?? ''"
                help="留空表示未提供；测算台会要求手工填写，不按 0 计算。"
              >
                <template #default="{ describedBy, invalid }">
                  <input
                    id="uv-version-seconds"
                    v-model="versionForm.board_seconds"
                    class="uv-input"
                    :class="invalid ? 'uv-input--invalid' : ''"
                    type="number"
                    inputmode="numeric"
                    min="1"
                    step="1"
                    :readonly="!canMaintain"
                    :aria-describedby="describedBy"
                    :aria-invalid="invalid"
                  >
                </template>
              </UvFormField>
              <UvFormField label="长 cm" field-id="uv-version-length" :error="versionFieldErrors.length_cm ?? ''">
                <template #default="{ describedBy, invalid }">
                  <input
                    id="uv-version-length"
                    v-model="versionForm.length_cm"
                    class="uv-input"
                    :class="invalid ? 'uv-input--invalid' : ''"
                    type="number"
                    inputmode="decimal"
                    min="0"
                    step="0.01"
                    :readonly="!canMaintain"
                    :aria-describedby="describedBy"
                    :aria-invalid="invalid"
                  >
                </template>
              </UvFormField>
              <UvFormField label="宽 cm" field-id="uv-version-width" :error="versionFieldErrors.width_cm ?? ''">
                <template #default="{ describedBy, invalid }">
                  <input
                    id="uv-version-width"
                    v-model="versionForm.width_cm"
                    class="uv-input"
                    :class="invalid ? 'uv-input--invalid' : ''"
                    type="number"
                    inputmode="decimal"
                    min="0"
                    step="0.01"
                    :readonly="!canMaintain"
                    :aria-describedby="describedBy"
                    :aria-invalid="invalid"
                  >
                </template>
              </UvFormField>
              <UvFormField
                label="机器打印面积 m²"
                field-id="uv-version-machine-area"
                :error="versionFieldErrors.machine_area_m2 ?? ''"
                help="设备口径面积，不与计价面积自动换算。"
              >
                <template #default="{ describedBy, invalid }">
                  <input
                    id="uv-version-machine-area"
                    v-model="versionForm.machine_area_m2"
                    class="uv-input"
                    :class="invalid ? 'uv-input--invalid' : ''"
                    type="number"
                    inputmode="decimal"
                    min="0"
                    step="0.001"
                    :readonly="!canMaintain"
                    :aria-describedby="describedBy"
                    :aria-invalid="invalid"
                  >
                </template>
              </UvFormField>
              <UvFormField
                label="耗墨参考 ml"
                field-id="uv-version-ink"
                :error="versionFieldErrors.ink_reference_ml ?? ''"
                help="参考值，不替代实际领用流水。"
              >
                <template #default="{ describedBy, invalid }">
                  <input
                    id="uv-version-ink"
                    v-model="versionForm.ink_reference_ml"
                    class="uv-input"
                    :class="invalid ? 'uv-input--invalid' : ''"
                    type="number"
                    inputmode="decimal"
                    min="0"
                    step="0.01"
                    :readonly="!canMaintain"
                    :aria-describedby="describedBy"
                    :aria-invalid="invalid"
                  >
                </template>
              </UvFormField>
              <div class="uv-actions uv-form-field--span-3">
                <Button type="submit" size="sm" :disabled="!canMaintain || versionCommand.pending.value">
                  {{ versionCommand.pending.value ? '正在保存…' : '新增工艺版本' }}
                </Button>
                <span class="uv-field__hint">计价面积由服务端按 长 × 宽 计算，前端不自行写入。</span>
              </div>
              <p v-if="versionCommand.error.value" class="uv-callout uv-callout--warning uv-form-field--span-3" role="alert">
                保存失败：{{ versionCommand.error.value.message }}（表单内容已保留，可修改后重试）
              </p>
            </form>

            <div>
              <h4 class="uv-section__title">
                <Plus class="size-3.5" aria-hidden="true" />
                价规维护
              </h4>
              <div class="uv-actions">
                <Button
                  v-for="kind in RATE_KINDS"
                  :key="kind"
                  variant="outline"
                  size="sm"
                  type="button"
                  :disabled="!rateKindWritable(kind)"
                  :title="rateKindBlockedReason(kind) || undefined"
                  @click="emit('create-rate', kind)"
                >
                  新增{{ RATE_KIND_LABELS[kind] }}
                </Button>
              </div>
              <p
                v-for="kind in RATE_KINDS.filter((item) => !rateKindWritable(item))"
                :key="`blocked-${kind}`"
                class="uv-field__hint"
              >
                {{ rateKindBlockedReason(kind) }}
              </p>
              <p class="uv-form-help">
                价规按「{{ priorityNote }}」解析；前端只做展示排序，最终以服务端生效价为准。
              </p>
              <p v-if="!canReadCost" class="uv-field__hint">
                当前账号没有价格读取权限，价规金额不会下发到前端，因此这里不显示「未定价」以外的任何推断。
              </p>
            </div>
          </div>
        </div>
      </template>
    </div>
  </section>
</template>
