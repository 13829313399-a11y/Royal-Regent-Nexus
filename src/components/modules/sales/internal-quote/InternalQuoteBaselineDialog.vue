<script setup lang="ts">
import { Eye, LockKeyhole, Plus, Save, Settings2, Trash2, X } from '@lucide/vue'
import { computed, reactive, ref, watch } from 'vue'
import type {
  ApiInternalQuotePricingBaseline,
  InternalQuotePricingBaselineUpdateRequest,
} from '@/api/internalQuote'
import { defaultSalesFreightReferenceRoutes, salesFreightCapacityDefinitions } from '@/lib/internalQuoteSectionPayload'

const props = defineProps<{
  open: boolean
  baseline: ApiInternalQuotePricingBaseline | null
  busy: boolean
  canEdit: boolean
  externalError?: string
  factoryName?: string
}>()

const emit = defineEmits<{
  close: []
  save: [payload: InternalQuotePricingBaselineUpdateRequest]
}>()

type BaselineTab = 'materials' | 'machines' | 'freight'

const localError = ref('')
const activeTab = ref<BaselineTab>('materials')
const baselineTabs: Array<{ key: BaselineTab; label: string; description: string }> = [
  { key: 'materials', label: '初始材料价', description: '材质、料型与 HKD/Lb' },
  { key: 'machines', label: '初始机型价', description: '机型范围与 HKD/班' },
  { key: 'freight', label: '运输费用', description: '运费与吊柜费默认值' },
]
const displayFactoryName = computed(() =>
  props.factoryName?.trim() || props.baseline?.workshop_name || '当前厂区',
)
const defaultFreightRoutes = defaultSalesFreightReferenceRoutes.map((route) => ({
  route_key: route.key,
  route_name: route.label,
  capacity_key: salesFreightCapacityDefinitions.find(({ key }) => key === route.capacityKey)?.label ?? route.capacityKey,
  freight_hkd: String(route.freightCostHkd),
  lifting_hkd: String(route.liftingCostHkd),
}))
let freightRouteSequence = 0
const form = reactive<InternalQuotePricingBaselineUpdateRequest>({
  revision: 0,
  workshop_name: '当前厂区',
  material_prices: [],
  machine_prices: [],
  freight_routes: defaultFreightRoutes.map((row) => ({ ...row })),
})

function resetForm() {
  const baseline = props.baseline
  form.revision = baseline?.revision ?? 0
  form.workshop_name = baseline?.workshop_name ?? displayFactoryName.value
  form.material_prices = (baseline?.material_prices ?? []).map((row) => ({ ...row }))
  form.machine_prices = (baseline?.machine_prices ?? []).map((row) => ({ ...row }))
  form.freight_routes = (baseline?.freight_routes ?? defaultFreightRoutes).map((row) => ({
    ...row,
    capacity_key: capacityTypeLabel(row.capacity_key),
  }))
  localError.value = ''
  activeTab.value = 'materials'
}

watch(
  () => [props.open, props.baseline] as const,
  ([open]) => {
    if (open) resetForm()
  },
  { immediate: true, deep: true },
)

function addMaterial() {
  form.material_prices.push({ material: '', grade: '', price_hkd_lb: '' })
}

function addMachine() {
  form.machine_prices.push({ machine_range: '', machine: '', shift_price_hkd: '' })
}

function addFreightRoute() {
  freightRouteSequence += 1
  form.freight_routes.push({
    route_key: `route_${Date.now().toString(36)}_${freightRouteSequence}`,
    route_name: '',
    capacity_key: '',
    freight_hkd: '',
    lifting_hkd: '',
  })
}

function normalizedCapacityType(value: string) {
  const trimmed = value.trim()
  const comparable = trimmed.replace(/\s+/g, '').toLocaleLowerCase()
  const known = salesFreightCapacityDefinitions.find(({ key, label }) => (
    key.toLocaleLowerCase() === comparable
    || label.replace(/\s+/g, '').toLocaleLowerCase() === comparable
  ))
  return known?.key ?? trimmed
}

function capacityTypeLabel(value: string) {
  const normalized = normalizedCapacityType(value)
  return salesFreightCapacityDefinitions.find(({ key }) => key === normalized)?.label ?? value.trim()
}

function normalizedPrice(value: string | number) {
  return String(value ?? '').trim()
}

function positivePrice(value: string | number) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0
}

function nonnegativePrice(value: string | number) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed >= 0 && normalizedPrice(value) !== ''
}

function isBlankMaterialRow(row: InternalQuotePricingBaselineUpdateRequest['material_prices'][number]) {
  return !row.material.trim() && !row.grade.trim() && !normalizedPrice(row.price_hkd_lb)
}

function isBlankMachineRow(row: InternalQuotePricingBaselineUpdateRequest['machine_prices'][number]) {
  return !row.machine_range.trim() && !row.machine.trim() && !normalizedPrice(row.shift_price_hkd)
}

function validate(
  materialPrices: InternalQuotePricingBaselineUpdateRequest['material_prices'],
  machinePrices: InternalQuotePricingBaselineUpdateRequest['machine_prices'],
  freightRoutes: InternalQuotePricingBaselineUpdateRequest['freight_routes'],
) {
  if (!materialPrices.length || !machinePrices.length || !freightRoutes.length) {
    return '初始材料价、初始机型价和运输方案都至少保留一项'
  }
  const invalidMaterialIndex = materialPrices.findIndex(
    (row) => !row.material.trim() || !row.grade.trim() || !positivePrice(row.price_hkd_lb),
  )
  if (invalidMaterialIndex >= 0) {
    return `请完整填写第 ${invalidMaterialIndex + 1} 项材料的材质、料型和大于 0 的 HKD/Lb 单价`
  }
  const invalidMachineIndex = machinePrices.findIndex(
    (row) => !row.machine_range.trim() || !row.machine.trim() || !positivePrice(row.shift_price_hkd),
  )
  if (invalidMachineIndex >= 0) {
    return `请完整填写第 ${invalidMachineIndex + 1} 项机型范围、机型和大于 0 的每班价格`
  }
  const invalidFreightIndex = freightRoutes.findIndex((row) => (
    !row.route_key.trim() || !row.route_name.trim() || !row.capacity_key.trim()
    || !nonnegativePrice(row.freight_hkd) || !nonnegativePrice(row.lifting_hkd)
  ))
  if (invalidFreightIndex >= 0) return `请完整填写第 ${invalidFreightIndex + 1} 项运输方案、容量类型，以及大于或等于 0 的运费和吊柜费 HKD`
  const materialKeys = materialPrices.map((row) => `${row.material.trim().toLocaleLowerCase()}|${row.grade.trim().toLocaleLowerCase()}`)
  if (new Set(materialKeys).size !== materialKeys.length) return '初始材料价存在重复的材质和料型'
  const machineKeys = machinePrices.map((row) => row.machine_range.trim().toLocaleLowerCase())
  if (new Set(machineKeys).size !== machineKeys.length) return '初始机型价存在重复的机型范围'
  const freightNames = freightRoutes.map((row) => row.route_name.trim().toLocaleLowerCase())
  if (new Set(freightNames).size !== freightNames.length) return '运输方案名称不能重复'
  return ''
}

function save() {
  if (!props.canEdit || props.busy) return
  const materialPrices = form.material_prices.filter((row) => !isBlankMaterialRow(row))
  const machinePrices = form.machine_prices.filter((row) => !isBlankMachineRow(row))
  form.material_prices = materialPrices
  form.machine_prices = machinePrices
  localError.value = validate(materialPrices, machinePrices, form.freight_routes)
  if (localError.value) {
    if (localError.value.includes('材料') || localError.value.includes('材质') || localError.value.includes('料型')) activeTab.value = 'materials'
    else if (localError.value.includes('机型')) activeTab.value = 'machines'
    else if (localError.value.includes('运输') || localError.value.includes('运费') || localError.value.includes('吊柜费')) activeTab.value = 'freight'
    return
  }
  emit('save', {
    revision: form.revision,
    workshop_name: form.workshop_name.trim(),
    material_prices: materialPrices.map((row) => ({
      material: row.material.trim(),
      grade: row.grade.trim(),
      price_hkd_lb: normalizedPrice(row.price_hkd_lb),
    })),
    machine_prices: machinePrices.map((row) => ({
      machine_range: row.machine_range.trim(),
      machine: row.machine.trim(),
      shift_price_hkd: normalizedPrice(row.shift_price_hkd),
    })),
    freight_routes: form.freight_routes.map((row) => ({
      route_key: row.route_key.trim(),
      route_name: row.route_name.trim(),
      capacity_key: normalizedCapacityType(row.capacity_key),
      freight_hkd: normalizedPrice(row.freight_hkd),
      lifting_hkd: normalizedPrice(row.lifting_hkd),
    })),
  })
}
</script>

<template>
  <Teleport to="body">
    <Transition name="baseline-modal">
      <div v-if="open" class="quote-baseline-backdrop" @click.self="emit('close')">
        <section class="quote-baseline-dialog" role="dialog" aria-modal="true" aria-labelledby="quote-baseline-title">
          <header>
            <div class="quote-baseline-title-row">
              <span class="quote-baseline-icon"><Settings2 aria-hidden="true" /></span>
              <div>
                <div class="quote-baseline-title-line">
                  <h2 id="quote-baseline-title">调整报价基数</h2>
                  <span :class="canEdit ? 'editable' : 'readonly'">
                    <LockKeyhole v-if="canEdit" aria-hidden="true" />
                    <Eye v-else aria-hidden="true" />
                    {{ canEdit ? '业务主管可修改' : '跟客只读查看' }}
                  </span>
                </div>
                <p>维护{{ displayFactoryName }}内部报价的初始材料价、初始机型价、运费与吊柜费默认值。</p>
              </div>
            </div>
            <button type="button" class="quote-baseline-close" :disabled="busy" aria-label="关闭报价基数" @click="emit('close')"><X aria-hidden="true" /></button>
          </header>

          <div class="quote-baseline-body">
            <div class="quote-baseline-note">
              <strong>生效规则</strong>
              <span>保存后供新建报价冻结参考快照；历史报价继续使用原快照，如需采用新基数应在报价内执行“同步参考快照”。</span>
              <span v-if="baseline">当前 revision {{ baseline.revision }} · {{ baseline.source_type === 'default' ? '系统初始值' : `最近更新：${baseline.updated_by_name || '业务主管'} ${baseline.updated_at}` }}</span>
            </div>

            <p v-if="localError || externalError" class="quote-baseline-error" role="alert">{{ localError || externalError }}</p>

            <nav class="quote-baseline-tabs" role="tablist" aria-label="报价基数价格区域">
              <button
                v-for="tab in baselineTabs"
                :id="`quote-baseline-tab-${tab.key}`"
                :key="tab.key"
                type="button"
                role="tab"
                :data-testid="`baseline-tab-${tab.key}`"
                :aria-controls="`quote-baseline-panel-${tab.key}`"
                :aria-selected="activeTab === tab.key"
                :class="{ active: activeTab === tab.key }"
                @click="activeTab = tab.key"
              >
                <strong>{{ tab.label }}</strong>
                <span>{{ tab.description }}</span>
              </button>
            </nav>

            <section
              v-show="activeTab === 'materials'"
              id="quote-baseline-panel-materials"
              class="quote-baseline-card quote-baseline-tab-panel"
              role="tabpanel"
              aria-labelledby="quote-baseline-tab-materials"
            >
              <div class="quote-baseline-card-title">
                <div><h3>初始材料价</h3><p>材质与料型组合必须唯一，币种单位为 HKD/Lb。</p></div>
                <button v-if="canEdit" type="button" @click="addMaterial"><Plus aria-hidden="true" />新增材料</button>
              </div>
              <div class="quote-baseline-table-scroll">
                <table>
                  <thead><tr><th>材质</th><th>料型</th><th>HKD/Lb</th><th v-if="canEdit"><span class="sr-only">操作</span></th></tr></thead>
                  <tbody>
                    <tr v-for="(row, index) in form.material_prices" :key="`material-${index}`">
                      <td><input v-model="row.material" :disabled="!canEdit" maxlength="64" aria-label="材质"></td>
                      <td><input v-model="row.grade" :disabled="!canEdit" maxlength="128" aria-label="料型"></td>
                      <td><input v-model="row.price_hkd_lb" :data-testid="`material-price-${index}`" :disabled="!canEdit" type="number" min="0.0001" step="0.01" aria-label="材料价格 HKD/Lb"></td>
                      <td v-if="canEdit"><button type="button" class="quote-baseline-delete" :disabled="form.material_prices.length === 1" aria-label="删除材料" @click="form.material_prices.splice(index, 1)"><Trash2 aria-hidden="true" /></button></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>

            <section
              v-show="activeTab === 'freight'"
              id="quote-baseline-panel-freight"
              class="quote-baseline-card quote-baseline-tab-panel"
              role="tabpanel"
              aria-labelledby="quote-baseline-tab-freight"
            >
              <div class="quote-baseline-card-title">
                <div><h3>运费与吊柜费 HKD 默认值</h3><p>运输方案由业务主管增删改；两项费用按同一柜/车容量分别计算每件金额。</p></div>
                <button v-if="canEdit" type="button" data-testid="add-freight-route" @click="addFreightRoute"><Plus aria-hidden="true" />新增方案</button>
              </div>
              <div class="quote-baseline-table-scroll">
                <table class="freight-baseline-table">
                  <thead><tr><th>运输方案</th><th>容量类型</th><th>运费 HKD</th><th>吊柜费 HKD</th><th aria-label="操作"></th></tr></thead>
                  <tbody>
                    <tr v-for="(row, index) in form.freight_routes" :key="row.route_key">
                      <td><input v-model="row.route_name" :data-testid="`freight-name-${index}`" :disabled="!canEdit" maxlength="128" aria-label="运输方案名称"></td>
                      <td>
                        <input
                          v-model="row.capacity_key"
                          :data-testid="`freight-capacity-${index}`"
                          :disabled="!canEdit"
                          maxlength="128"
                          placeholder="例如：40 尺柜容量"
                          aria-label="容量类型"
                        >
                      </td>
                      <td><input v-model="row.freight_hkd" :data-testid="`freight-cost-${row.route_key}`" :disabled="!canEdit" type="number" min="0" step="1" :aria-label="`${row.route_name || `第 ${index + 1} 项`}运费 HKD`"></td>
                      <td><input v-model="row.lifting_hkd" :data-testid="`lifting-cost-${row.route_key}`" :disabled="!canEdit" type="number" min="0" step="1" :aria-label="`${row.route_name || `第 ${index + 1} 项`}吊柜费 HKD`"></td>
                      <td><button type="button" class="quote-baseline-delete" :disabled="!canEdit" :data-testid="`delete-freight-${row.route_key}`" aria-label="删除运输方案" @click="form.freight_routes.splice(index, 1)"><Trash2 aria-hidden="true" /></button></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>

            <section
              v-show="activeTab === 'machines'"
              id="quote-baseline-panel-machines"
              class="quote-baseline-card quote-baseline-tab-panel"
              role="tabpanel"
              aria-labelledby="quote-baseline-tab-machines"
            >
              <div class="quote-baseline-card-title">
                <div><h3>初始机型价</h3><p>按 A 机范围匹配机型及每班价格，币种单位为 HKD/班。</p></div>
                <button v-if="canEdit" type="button" @click="addMachine"><Plus aria-hidden="true" />新增机型</button>
              </div>
              <div class="quote-baseline-table-scroll">
                <table>
                  <thead><tr><th>机型范围</th><th>机型</th><th>HKD/班</th><th v-if="canEdit"><span class="sr-only">操作</span></th></tr></thead>
                  <tbody>
                    <tr v-for="(row, index) in form.machine_prices" :key="`machine-${index}`">
                      <td><input v-model="row.machine_range" :disabled="!canEdit" maxlength="64" aria-label="机型范围"></td>
                      <td><input v-model="row.machine" :disabled="!canEdit" maxlength="128" aria-label="机型"></td>
                      <td><input v-model="row.shift_price_hkd" :data-testid="`machine-price-${index}`" :disabled="!canEdit" type="number" min="0.0001" step="1" aria-label="机型每班价格"></td>
                      <td v-if="canEdit"><button type="button" class="quote-baseline-delete" :disabled="form.machine_prices.length === 1" aria-label="删除机型" @click="form.machine_prices.splice(index, 1)"><Trash2 aria-hidden="true" /></button></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>
          </div>

          <footer>
            <span>{{ canEdit ? '保存会生成新的报价基数 revision' : '当前账号仅可查看，不能修改报价基数' }}</span>
            <div>
              <button type="button" class="quote-baseline-cancel" :disabled="busy" @click="emit('close')">关闭</button>
              <button v-if="canEdit" type="button" class="quote-baseline-save" data-testid="save-pricing-baseline" :disabled="busy" @click="save"><Save aria-hidden="true" />{{ busy ? '保存中…' : '保存报价基数' }}</button>
            </div>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.quote-baseline-backdrop{position:fixed;z-index:90;inset:0;display:flex;align-items:center;justify-content:center;background:rgb(15 23 42/.48);padding:24px;backdrop-filter:blur(5px)}.quote-baseline-dialog{display:flex;width:min(1240px,100%);max-height:calc(100vh - 48px);flex-direction:column;overflow:hidden;border:1px solid #dbe5ea;border-radius:20px;background:#f8fafc;box-shadow:0 30px 80px rgb(15 23 42/.28)}.quote-baseline-dialog>header{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;border-bottom:1px solid #e2e8f0;background:#fff;padding:20px 22px}.quote-baseline-title-row{display:flex;gap:13px}.quote-baseline-icon{display:grid;width:48px;height:48px;flex:0 0 auto;place-items:center;border-radius:14px;background:#ccfbf1;color:#0f766e}.quote-baseline-icon svg{width:24px}.quote-baseline-title-line{display:flex;align-items:center;flex-wrap:wrap;gap:10px}.quote-baseline-title-line h2{margin:0;color:#0f172a;font-size:22px;font-weight:950}.quote-baseline-title-line span{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:5px 8px;font-size:11px;font-weight:900}.quote-baseline-title-line span svg{width:13px}.quote-baseline-title-line .editable{background:#ecfdf5;color:#047857}.quote-baseline-title-line .readonly{background:#eff6ff;color:#1d4ed8}.quote-baseline-title-row p{margin:5px 0 0;color:#64748b;font-size:13px}.quote-baseline-close{display:grid;width:36px;height:36px;place-items:center;border:0;border-radius:9px;background:transparent;color:#64748b}.quote-baseline-close:hover{background:#f1f5f9;color:#0f172a}.quote-baseline-close svg{width:20px}.quote-baseline-body{display:grid;gap:14px;min-height:0;overflow:auto;padding:18px 22px}.quote-baseline-note{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:10px;border:1px solid #99f6e4;border-radius:11px;background:#f0fdfa;padding:10px 12px;color:#0f766e;font-size:12px}.quote-baseline-note strong{font-weight:950}.quote-baseline-note span:last-child{color:#64748b;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px}.quote-baseline-error{margin:0;border:1px solid #fecaca;border-radius:10px;background:#fef2f2;padding:9px 11px;color:#b91c1c;font-size:12px}.quote-baseline-tabs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;border:1px solid #dbe5ea;border-radius:13px;background:#fff;padding:7px}.quote-baseline-tabs button{display:grid;gap:3px;border:1px solid transparent;border-radius:10px;background:transparent;padding:10px 12px;color:#64748b;text-align:left;cursor:pointer}.quote-baseline-tabs button:hover{background:#f8fafc}.quote-baseline-tabs button.active{border-color:#5eead4;background:#f0fdfa;color:#0f766e;box-shadow:0 4px 14px rgb(15 118 110/.1)}.quote-baseline-tabs strong{font-size:13px}.quote-baseline-tabs span{font-size:10px}.quote-baseline-card{overflow:hidden;border:1px solid #dbe5ea;border-radius:13px;background:#fff}.quote-baseline-tab-panel{min-height:360px}.quote-baseline-card-title{display:flex;align-items:center;justify-content:space-between;gap:16px;border-bottom:1px solid #e2e8f0;padding:13px 14px}.quote-baseline-card-title h3{margin:0;color:#0f172a;font-size:15px;font-weight:950}.quote-baseline-card-title p{margin:4px 0 0;color:#64748b;font-size:11px}.quote-baseline-card-title button{display:inline-flex;height:34px;align-items:center;gap:5px;border:1px solid #5eead4;border-radius:9px;background:#f0fdfa;padding:0 10px;color:#0f766e;font-size:12px;font-weight:900}.quote-baseline-card-title button:hover{background:#ccfbf1}.quote-baseline-card-title button svg{width:15px}.quote-baseline-table-scroll{max-height:420px;overflow:auto}.quote-baseline-card table{width:100%;border-collapse:collapse;table-layout:fixed}.quote-baseline-card th{position:sticky;z-index:1;top:0;background:#f1f5f9;padding:9px 11px;color:#64748b;font-size:11px;font-weight:900;text-align:left}.quote-baseline-card th:last-child,.quote-baseline-card td:last-child{width:52px}.quote-baseline-card td{border-top:1px solid #eef2f6;padding:6px 8px}.quote-baseline-card input,.quote-baseline-card select{width:100%;height:38px;border:1px solid #dbe5ea;border-radius:8px;background:#fff;padding:0 9px;color:#0f172a;font-size:13px;outline:0}.quote-baseline-card input:focus,.quote-baseline-card select:focus{border-color:#14b8a6;box-shadow:0 0 0 3px rgb(20 184 166/.1)}.quote-baseline-card input:disabled,.quote-baseline-card select:disabled{border-color:transparent;background:transparent;color:#334155;opacity:1}.quote-baseline-delete{display:grid;width:32px;height:32px;place-items:center;border:1px solid #fee2e2;border-radius:8px;background:#fff;color:#dc2626}.quote-baseline-delete:hover:not(:disabled){background:#fef2f2}.quote-baseline-delete:disabled{cursor:not-allowed;opacity:.35}.quote-baseline-delete svg{width:15px}.quote-baseline-dialog>footer{display:flex;align-items:center;justify-content:space-between;gap:16px;border-top:1px solid #e2e8f0;background:#fff;padding:14px 22px}.quote-baseline-dialog>footer>span{color:#64748b;font-size:11px}.quote-baseline-dialog>footer>div{display:flex;gap:9px}.quote-baseline-cancel,.quote-baseline-save{height:38px;border-radius:9px;padding:0 14px;font-size:12px;font-weight:900}.quote-baseline-cancel{border:1px solid #cbd5e1;background:#fff;color:#475569}.quote-baseline-save{display:inline-flex;align-items:center;gap:7px;border:1px solid #0f766e;background:#0f766e;color:#fff;box-shadow:0 8px 20px rgb(15 118 110/.18)}.quote-baseline-save:hover{background:#115e59}.quote-baseline-save:disabled{cursor:wait;opacity:.6}.quote-baseline-save svg{width:15px}.baseline-modal-enter-active,.baseline-modal-leave-active{transition:opacity 180ms ease}.baseline-modal-enter-active .quote-baseline-dialog,.baseline-modal-leave-active .quote-baseline-dialog{transition:transform 220ms ease,opacity 180ms ease}.baseline-modal-enter-from,.baseline-modal-leave-to{opacity:0}.baseline-modal-enter-from .quote-baseline-dialog{opacity:0;transform:translateY(12px) scale(.985)}.baseline-modal-leave-to .quote-baseline-dialog{opacity:0;transform:translateY(6px) scale(.99)}
@media(max-width:760px){.quote-baseline-backdrop{align-items:flex-end;padding:0}.quote-baseline-dialog{max-height:94vh;border-radius:18px 18px 0 0}.quote-baseline-note{grid-template-columns:1fr}.quote-baseline-tabs{grid-template-columns:1fr}.quote-baseline-tabs button{display:flex;align-items:center;justify-content:space-between}.quote-baseline-dialog>header,.quote-baseline-body,.quote-baseline-dialog>footer{padding-left:14px;padding-right:14px}.quote-baseline-dialog>footer{align-items:stretch;flex-direction:column}.quote-baseline-dialog>footer>div{display:grid;grid-template-columns:1fr 1fr}.quote-baseline-card table{min-width:620px}}
@media(prefers-reduced-motion:reduce){.baseline-modal-enter-active,.baseline-modal-leave-active,.baseline-modal-enter-active .quote-baseline-dialog,.baseline-modal-leave-active .quote-baseline-dialog{transition:none}}
</style>
