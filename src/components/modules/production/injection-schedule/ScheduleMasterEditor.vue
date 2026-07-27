<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { Boxes, ClipboardList, LoaderCircle, Save, X } from '@lucide/vue'
import type {
  InjectionMoldCreateInput,
  InjectionMoldRecord,
  InjectionOrderCreateInput,
  InjectionOrderRecord,
} from '@/types/injectionSchedule'

type EditorKind = 'mold' | 'order'

const props = withDefaults(defineProps<{
  open: boolean
  kind: EditorKind
  factoryName: string
  mold?: InjectionMoldRecord | null
  order?: InjectionOrderRecord | null
  busy?: boolean
  error?: string
}>(), {
  mold: null,
  order: null,
  busy: false,
  error: '',
})

const emit = defineEmits<{
  close: []
  saveMold: [payload: {
    moldId: string | null
    expectedRevision: number | null
    input: InjectionMoldCreateInput
  }]
  saveOrder: [payload: {
    orderId: string | null
    expectedRevision: number | null
    input: InjectionOrderCreateInput
  }]
}>()

interface MoldForm {
  moldCode: string
  moldName: string
  machineClass: string
  robotType: string
  fixtureType: string
  lengthMm: string
  widthMm: string
  heightMm: string
  moldWeightKg: string
  grossShotWeightG: string
  moldThicknessMm: string
  requiredOpeningStrokeMm: string
  requiredScrewType: string
  cavities: string
  cycleSeconds: string
  requiredCapabilities: string
  materialRules: string
  qualityStatus: string
}

interface OrderForm {
  naturalKey: string
  orderNo: string
  productCode: string
  productName: string
  moldCode: string
  color: string
  pigment: string
  material: string
  machineClass: string
  orderQty: string
  producedQty: string
  dailyTargetQty: string
  deliveryDueDate: string
  priorityFlag: string
  colorRank: string
  downstreamUrgency: string
  warehouseBufferHours: string
  downstreamBufferHours: string
  specialHandlingReason: string
  status: 'open' | 'completed' | 'canceled'
  importedAssignedMachineCode: string
  qualityStatus: string
}

const dialog = ref<HTMLElement | null>(null)
const moldForm = reactive<MoldForm>({
  moldCode: '',
  moldName: '',
  machineClass: '',
  robotType: '',
  fixtureType: '',
  lengthMm: '',
  widthMm: '',
  heightMm: '',
  moldWeightKg: '',
  grossShotWeightG: '',
  moldThicknessMm: '',
  requiredOpeningStrokeMm: '',
  requiredScrewType: '',
  cavities: '',
  cycleSeconds: '',
  requiredCapabilities: '',
  materialRules: '',
  qualityStatus: 'incomplete',
})
const orderForm = reactive<OrderForm>({
  naturalKey: '',
  orderNo: '',
  productCode: '',
  productName: '',
  moldCode: '',
  color: '',
  pigment: '',
  material: '',
  machineClass: '',
  orderQty: '0',
  producedQty: '0',
  dailyTargetQty: '',
  deliveryDueDate: '',
  priorityFlag: '',
  colorRank: '',
  downstreamUrgency: '',
  warehouseBufferHours: '0',
  downstreamBufferHours: '0',
  specialHandlingReason: '',
  status: 'open',
  importedAssignedMachineCode: '',
  qualityStatus: 'incomplete',
})

function positiveNumberOrNull(value: string) {
  const normalized = value.trim()
  if (!normalized) return null
  const parsed = Number(normalized)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null
}

function nonNegativeNumber(value: string) {
  const normalized = value.trim()
  if (!normalized) return 0
  const parsed = Number(normalized)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : Number.NaN
}

function boundedNumberOrNull(value: string, minimum: number, maximum: number) {
  const normalized = value.trim()
  if (!normalized) return null
  const parsed = Number(normalized)
  return Number.isFinite(parsed) && parsed >= minimum && parsed <= maximum
    ? parsed
    : null
}

function listValue(value: string) {
  return [...new Set(value
    .split(/[、,，]/)
    .map((entry) => entry.trim())
    .filter(Boolean))]
}

watch(
  () => [props.open, props.kind, props.mold?.id, props.order?.id] as const,
  async ([open, kind]) => {
    if (kind === 'mold') {
      const source = props.mold
      Object.assign(moldForm, {
        moldCode: source?.moldCode ?? '',
        moldName: source?.moldName ?? '',
        machineClass: source?.machineClass ?? '',
        robotType: source?.robotType ?? '',
        fixtureType: source?.fixtureType ?? '',
        lengthMm: source?.lengthMm?.toString() ?? '',
        widthMm: source?.widthMm?.toString() ?? '',
        heightMm: source?.heightMm?.toString() ?? '',
        moldWeightKg: source?.moldWeightKg?.toString() ?? '',
        grossShotWeightG: source?.grossShotWeightG?.toString() ?? '',
        moldThicknessMm: source?.moldThicknessMm?.toString() ?? '',
        requiredOpeningStrokeMm: source?.requiredOpeningStrokeMm?.toString() ?? '',
        requiredScrewType: source?.requiredScrewType ?? '',
        cavities: source?.cavities?.toString() ?? '',
        cycleSeconds: source?.cycleSeconds?.toString() ?? '',
        requiredCapabilities: source?.requiredCapabilities.join('、') ?? '',
        materialRules: source?.materialRules.join('、') ?? '',
        qualityStatus: source?.qualityStatus ?? 'incomplete',
      })
    } else {
      const source = props.order
      Object.assign(orderForm, {
        naturalKey: source?.naturalKey ?? '',
        orderNo: source?.orderNo ?? '',
        productCode: source?.productCode ?? '',
        productName: source?.productName ?? '',
        moldCode: source?.moldCode ?? '',
        color: source?.color ?? '',
        pigment: source?.pigment ?? '',
        material: source?.material ?? '',
        machineClass: source?.machineClass ?? '',
        orderQty: source?.orderQty?.toString() ?? '0',
        producedQty: source?.producedQty?.toString() ?? '0',
        dailyTargetQty: source?.dailyTargetQty?.toString() ?? '',
        deliveryDueDate: source?.deliveryDueDate ?? '',
        priorityFlag: source?.priorityFlag ?? '',
        colorRank: source?.colorRank?.toString() ?? '',
        downstreamUrgency: source?.downstreamUrgency?.toString() ?? '',
        warehouseBufferHours: source?.warehouseBufferHours?.toString() ?? '0',
        downstreamBufferHours: source?.downstreamBufferHours?.toString() ?? '0',
        specialHandlingReason: source?.specialHandlingReason ?? '',
        status: source?.status ?? 'open',
        importedAssignedMachineCode: source?.importedAssignedMachineCode ?? '',
        qualityStatus: source?.qualityStatus ?? 'incomplete',
      })
    }
    if (open) {
      await nextTick()
      dialog.value?.querySelector<HTMLInputElement>('input')?.focus()
    }
  },
  { immediate: true },
)

const validationMessage = computed(() => {
  if (props.kind === 'mold') {
    if (!moldForm.moldCode.trim()) return '请填写模号'
    if (!moldForm.moldName.trim()) return '请填写模具名称'
    const positiveFields = [
      ['模具长度', moldForm.lengthMm],
      ['模具宽度', moldForm.widthMm],
      ['模具高度', moldForm.heightMm],
      ['模具重量', moldForm.moldWeightKg],
      ['整啤毛重', moldForm.grossShotWeightG],
      ['模具厚度', moldForm.moldThicknessMm],
      ['所需开模行程', moldForm.requiredOpeningStrokeMm],
      ['腔数', moldForm.cavities],
      ['标准周期', moldForm.cycleSeconds],
    ]
    const invalid = positiveFields.find(([, value]) => (
      value.trim() && positiveNumberOrNull(value) == null
    ))
    return invalid ? `${invalid[0]}必须是正数` : ''
  }

  if (!orderForm.orderNo.trim()) return '请填写订单号'
  if (!orderForm.productName.trim()) return '请填写产品名称'
  if (!orderForm.moldCode.trim()) return '请填写模号'
  const orderQty = nonNegativeNumber(orderForm.orderQty)
  const producedQty = nonNegativeNumber(orderForm.producedQty)
  if (!Number.isFinite(orderQty) || !Number.isFinite(producedQty)) {
    return '订单数量和已生产数量必须是非负数字'
  }
  if (producedQty > orderQty) return '已生产数量不能大于订单数量'
  if (
    orderForm.dailyTargetQty.trim()
    && positiveNumberOrNull(orderForm.dailyTargetQty) == null
  ) {
    return '日产目标必须是正数'
  }
  if (
    orderForm.colorRank.trim()
    && boundedNumberOrNull(orderForm.colorRank, 0, 100) == null
  ) return '颜色等级必须在 0 到 100 之间'
  if (
    orderForm.downstreamUrgency.trim()
    && boundedNumberOrNull(orderForm.downstreamUrgency, 0, 1) == null
  ) return '下游紧急度必须在 0 到 1 之间'
  for (const [label, value] of [
    ['仓库缓冲', orderForm.warehouseBufferHours],
    ['下游缓冲', orderForm.downstreamBufferHours],
  ]) {
    if (boundedNumberOrNull(value, 0, 720) == null) return `${label}必须在 0 到 720 小时之间`
  }
  return ''
})

const title = computed(() => {
  if (props.kind === 'mold') {
    return props.mold ? `编辑 ${props.mold.moldCode}` : '新增模具'
  }
  return props.order ? `编辑 ${props.order.orderNo}` : '新增订单'
})

function submit() {
  if (validationMessage.value || props.busy) return
  if (props.kind === 'mold') {
    emit('saveMold', {
      moldId: props.mold?.id ?? null,
      expectedRevision: props.mold?.revision ?? null,
      input: {
        moldCode: moldForm.moldCode.trim(),
        moldName: moldForm.moldName.trim(),
        machineClass: moldForm.machineClass.trim(),
        robotType: moldForm.robotType.trim(),
        fixtureType: moldForm.fixtureType.trim(),
        lengthMm: positiveNumberOrNull(moldForm.lengthMm),
        widthMm: positiveNumberOrNull(moldForm.widthMm),
        heightMm: positiveNumberOrNull(moldForm.heightMm),
        moldWeightKg: positiveNumberOrNull(moldForm.moldWeightKg),
        grossShotWeightG: positiveNumberOrNull(moldForm.grossShotWeightG),
        moldThicknessMm: positiveNumberOrNull(moldForm.moldThicknessMm),
        requiredOpeningStrokeMm: positiveNumberOrNull(moldForm.requiredOpeningStrokeMm),
        requiredScrewType: moldForm.requiredScrewType.trim(),
        cavities: positiveNumberOrNull(moldForm.cavities),
        cycleSeconds: positiveNumberOrNull(moldForm.cycleSeconds),
        requiredCapabilities: listValue(moldForm.requiredCapabilities),
        materialRules: listValue(moldForm.materialRules),
        qualityStatus: moldForm.qualityStatus.trim() || 'incomplete',
      },
    })
    return
  }

  emit('saveOrder', {
    orderId: props.order?.id ?? null,
    expectedRevision: props.order?.revision ?? null,
    input: {
      naturalKey: orderForm.naturalKey.trim() || null,
      orderNo: orderForm.orderNo.trim(),
      productCode: orderForm.productCode.trim(),
      productName: orderForm.productName.trim(),
      moldCode: orderForm.moldCode.trim(),
      color: orderForm.color.trim(),
      pigment: orderForm.pigment.trim(),
      material: orderForm.material.trim(),
      machineClass: orderForm.machineClass.trim(),
      orderQty: nonNegativeNumber(orderForm.orderQty),
      producedQty: nonNegativeNumber(orderForm.producedQty),
      dailyTargetQty: positiveNumberOrNull(orderForm.dailyTargetQty),
      deliveryDueDate: orderForm.deliveryDueDate,
      priorityFlag: orderForm.priorityFlag.trim(),
      colorRank: boundedNumberOrNull(orderForm.colorRank, 0, 100),
      downstreamUrgency: boundedNumberOrNull(orderForm.downstreamUrgency, 0, 1),
      warehouseBufferHours: boundedNumberOrNull(orderForm.warehouseBufferHours, 0, 720) ?? 0,
      downstreamBufferHours: boundedNumberOrNull(orderForm.downstreamBufferHours, 0, 720) ?? 0,
      specialHandlingReason: orderForm.specialHandlingReason.trim(),
      status: orderForm.status,
      importedAssignedMachineCode: orderForm.importedAssignedMachineCode.trim(),
      qualityStatus: orderForm.qualityStatus.trim() || 'incomplete',
    },
  })
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="master-editor-backdrop" @click.self="emit('close')">
      <section
        ref="dialog"
        class="master-editor"
        role="dialog"
        aria-modal="true"
        aria-labelledby="master-editor-title"
        @keydown.esc="emit('close')"
      >
        <header>
          <span>
            <Boxes v-if="kind === 'mold'" aria-hidden="true" />
            <ClipboardList v-else aria-hidden="true" />
          </span>
          <div>
            <small>Phase 3 · {{ factoryName }}主数据</small>
            <h2 id="master-editor-title">{{ title }}</h2>
            <p>保存后写入厂区主数据，并使用 revision 防止覆盖他人的修改。</p>
          </div>
          <button type="button" aria-label="关闭主数据编辑器" @click="emit('close')">
            <X aria-hidden="true" />
          </button>
        </header>

        <form @submit.prevent="submit">
          <template v-if="kind === 'mold'">
            <fieldset>
              <legend>模具识别与适配</legend>
              <label>
                <span>模号 *</span>
                <input v-model="moldForm.moldCode" :disabled="Boolean(mold)" maxlength="128">
              </label>
              <label>
                <span>模具名称 *</span>
                <input v-model="moldForm.moldName" maxlength="255">
              </label>
              <label>
                <span>推荐机安</span>
                <input v-model="moldForm.machineClass" maxlength="128" placeholder="例如：180T">
              </label>
              <label>
                <span>机械手要求</span>
                <input v-model="moldForm.robotType" maxlength="64" placeholder="无 / 单臂 / 双臂">
              </label>
              <label>
                <span>夹具要求</span>
                <input v-model="moldForm.fixtureType" maxlength="64">
              </label>
              <label>
                <span>资料状态</span>
                <select v-model="moldForm.qualityStatus">
                  <option value="incomplete">待补资料</option>
                  <option value="verified">已核对</option>
                  <option value="ready">可校验</option>
                </select>
              </label>
            </fieldset>

            <fieldset>
              <legend>发布校验参数</legend>
              <label><span>长度 mm</span><input v-model="moldForm.lengthMm" inputmode="decimal"></label>
              <label><span>宽度 mm</span><input v-model="moldForm.widthMm" inputmode="decimal"></label>
              <label><span>高度 mm</span><input v-model="moldForm.heightMm" inputmode="decimal"></label>
              <label><span>模具重量 kg</span><input v-model="moldForm.moldWeightKg" inputmode="decimal"></label>
              <label><span>整啤毛重 g</span><input v-model="moldForm.grossShotWeightG" inputmode="decimal"></label>
              <label><span>模具厚度 mm</span><input v-model="moldForm.moldThicknessMm" inputmode="decimal"></label>
              <label><span>所需开模行程 mm</span><input v-model="moldForm.requiredOpeningStrokeMm" inputmode="decimal"></label>
              <label><span>所需螺杆类型</span><input v-model="moldForm.requiredScrewType" maxlength="64"></label>
              <label><span>腔数</span><input v-model="moldForm.cavities" inputmode="numeric"></label>
              <label><span>标准周期 秒</span><input v-model="moldForm.cycleSeconds" inputmode="decimal"></label>
              <label class="master-editor__wide">
                <span>所需能力</span>
                <input v-model="moldForm.requiredCapabilities" placeholder="多个值用顿号或逗号分隔">
              </label>
              <label class="master-editor__wide">
                <span>材料规则</span>
                <input v-model="moldForm.materialRules" placeholder="多个值用顿号或逗号分隔">
              </label>
            </fieldset>
          </template>

          <template v-else>
            <fieldset>
              <legend>订单识别</legend>
              <label>
                <span>自然键</span>
                <input v-model="orderForm.naturalKey" :disabled="Boolean(order)" maxlength="256">
              </label>
              <label><span>订单号 *</span><input v-model="orderForm.orderNo" maxlength="128"></label>
              <label><span>产品编号</span><input v-model="orderForm.productCode" maxlength="128"></label>
              <label><span>产品名称 *</span><input v-model="orderForm.productName" maxlength="255"></label>
              <label><span>模号 *</span><input v-model="orderForm.moldCode" maxlength="128"></label>
              <label><span>推荐机安</span><input v-model="orderForm.machineClass" maxlength="128"></label>
            </fieldset>

            <fieldset>
              <legend>数量、交期与工艺</legend>
              <label><span>订单数量</span><input v-model="orderForm.orderQty" inputmode="decimal"></label>
              <label><span>已生产数量</span><input v-model="orderForm.producedQty" inputmode="decimal"></label>
              <label><span>日产目标</span><input v-model="orderForm.dailyTargetQty" inputmode="decimal"></label>
              <label><span>交货日期</span><input v-model="orderForm.deliveryDueDate" type="date"></label>
              <label><span>优先标记</span><input v-model="orderForm.priorityFlag" maxlength="32" placeholder="P0 / P1 / P2 / P3"></label>
              <label>
                <span>订单状态</span>
                <select v-model="orderForm.status">
                  <option value="open">未完成</option>
                  <option value="completed">已完成</option>
                  <option value="canceled">已取消</option>
                </select>
              </label>
              <label><span>颜色</span><input v-model="orderForm.color" maxlength="128"></label>
              <label><span>颜色等级 0–100</span><input v-model="orderForm.colorRank" inputmode="numeric"></label>
              <label><span>色粉</span><input v-model="orderForm.pigment" maxlength="128"></label>
              <label><span>材料</span><input v-model="orderForm.material" maxlength="255"></label>
              <label><span>下游紧急度 0–1</span><input v-model="orderForm.downstreamUrgency" inputmode="decimal"></label>
              <label><span>仓库缓冲（小时）</span><input v-model="orderForm.warehouseBufferHours" inputmode="decimal"></label>
              <label><span>下游缓冲（小时）</span><input v-model="orderForm.downstreamBufferHours" inputmode="decimal"></label>
              <label class="master-editor__wide">
                <span>特殊处理原因</span>
                <input v-model="orderForm.specialHandlingReason" maxlength="2000" placeholder="如喷油、装配急单等">
              </label>
              <label><span>Excel 指定机台</span><input v-model="orderForm.importedAssignedMachineCode" maxlength="64"></label>
              <label>
                <span>资料状态</span>
                <select v-model="orderForm.qualityStatus">
                  <option value="incomplete">待补资料</option>
                  <option value="verified">已核对</option>
                  <option value="ready">可排产</option>
                </select>
              </label>
            </fieldset>
          </template>

          <p v-if="validationMessage || error" class="master-editor__error" role="alert">
            {{ validationMessage || error }}
          </p>

          <footer>
            <button type="button" class="master-editor__cancel" :disabled="busy" @click="emit('close')">
              取消
            </button>
            <button type="submit" class="master-editor__save" :disabled="busy || Boolean(validationMessage)">
              <LoaderCircle v-if="busy" class="spin" aria-hidden="true" />
              <Save v-else aria-hidden="true" />
              {{ busy ? '保存中…' : '保存主数据' }}
            </button>
          </footer>
        </form>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.master-editor-backdrop {
  position: fixed;
  inset: 0;
  z-index: 95;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(7, 18, 32, 0.64);
  backdrop-filter: blur(6px);
}

.master-editor {
  width: min(860px, 100%);
  max-height: calc(100vh - 48px);
  overflow: auto;
  border: 1px solid #d6e0eb;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 26px 80px rgba(7, 25, 46, 0.3);
}

.master-editor > header {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 14px;
  align-items: start;
  padding: 22px 24px 18px;
  color: #fff;
  background: linear-gradient(135deg, #0c3156, #075c73);
}

.master-editor > header > span {
  display: grid;
  width: 40px;
  height: 40px;
  place-items: center;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.14);
}

.master-editor > header svg {
  width: 20px;
}

.master-editor h2,
.master-editor p {
  margin: 0;
}

.master-editor h2 {
  margin-top: 3px;
  font-size: 22px;
}

.master-editor header p,
.master-editor header small {
  color: #cfe6ee;
}

.master-editor header button {
  border: 0;
  background: transparent;
  color: #fff;
  cursor: pointer;
}

.master-editor form {
  display: grid;
  gap: 16px;
  padding: 20px 24px 24px;
}

.master-editor fieldset {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin: 0;
  padding: 16px;
  border: 1px solid #dce5ed;
  border-radius: 14px;
}

.master-editor legend {
  padding: 0 8px;
  color: #24445f;
  font-weight: 800;
}

.master-editor label {
  display: grid;
  gap: 6px;
  color: #37536a;
  font-size: 13px;
  font-weight: 700;
}

.master-editor input,
.master-editor select {
  min-width: 0;
  height: 38px;
  padding: 0 11px;
  border: 1px solid #cbd8e4;
  border-radius: 9px;
  background: #fbfdff;
  color: #172f43;
}

.master-editor input:focus,
.master-editor select:focus {
  outline: 2px solid rgba(15, 118, 110, 0.24);
  border-color: #0f766e;
}

.master-editor input:disabled {
  color: #708495;
  background: #eef3f7;
}

.master-editor__wide {
  grid-column: span 2;
}

.master-editor__error {
  padding: 11px 13px;
  border-radius: 10px;
  color: #9f1239;
  background: #fff1f2;
  font-weight: 700;
}

.master-editor footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.master-editor footer button {
  display: inline-flex;
  min-height: 40px;
  align-items: center;
  gap: 8px;
  padding: 0 16px;
  border-radius: 10px;
  font-weight: 800;
  cursor: pointer;
}

.master-editor footer svg {
  width: 17px;
}

.master-editor__cancel {
  border: 1px solid #cad7e2;
  background: #fff;
  color: #36546a;
}

.master-editor__save {
  border: 1px solid #0f766e;
  background: #0f766e;
  color: #fff;
}

.master-editor footer button:disabled {
  cursor: not-allowed;
  opacity: 0.58;
}

.spin {
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 760px) {
  .master-editor-backdrop {
    padding: 10px;
  }

  .master-editor fieldset {
    grid-template-columns: 1fr;
  }

  .master-editor__wide {
    grid-column: auto;
  }
}
</style>
