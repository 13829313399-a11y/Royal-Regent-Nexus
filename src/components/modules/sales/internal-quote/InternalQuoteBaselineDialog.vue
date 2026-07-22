<script setup lang="ts">
import { Eye, LockKeyhole, Plus, Save, Settings2, Trash2, X } from '@lucide/vue'
import { computed, reactive, ref, watch } from 'vue'
import type {
  ApiInternalQuotePricingBaseline,
  InternalQuotePricingBaselineUpdateRequest,
} from '@/api/internalQuote'

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

const localError = ref('')
const displayFactoryName = computed(() =>
  props.factoryName?.trim() || props.baseline?.workshop_name || '当前厂区',
)
const form = reactive<InternalQuotePricingBaselineUpdateRequest>({
  revision: 0,
  workshop_name: '当前厂区',
  material_prices: [],
  machine_prices: [],
})

function resetForm() {
  const baseline = props.baseline
  form.revision = baseline?.revision ?? 0
  form.workshop_name = baseline?.workshop_name ?? displayFactoryName.value
  form.material_prices = (baseline?.material_prices ?? []).map((row) => ({ ...row }))
  form.machine_prices = (baseline?.machine_prices ?? []).map((row) => ({ ...row }))
  localError.value = ''
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

function normalizedPrice(value: string | number) {
  return String(value ?? '').trim()
}

function positivePrice(value: string | number) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0
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
) {
  if (!materialPrices.length || !machinePrices.length) {
    return '初始材料价和初始机型价都至少保留一项'
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
  const materialKeys = materialPrices.map((row) => `${row.material.trim().toLocaleLowerCase()}|${row.grade.trim().toLocaleLowerCase()}`)
  if (new Set(materialKeys).size !== materialKeys.length) return '初始材料价存在重复的材质和料型'
  const machineKeys = machinePrices.map((row) => row.machine_range.trim().toLocaleLowerCase())
  if (new Set(machineKeys).size !== machineKeys.length) return '初始机型价存在重复的机型范围'
  return ''
}

function save() {
  if (!props.canEdit || props.busy) return
  const materialPrices = form.material_prices.filter((row) => !isBlankMaterialRow(row))
  const machinePrices = form.machine_prices.filter((row) => !isBlankMachineRow(row))
  form.material_prices = materialPrices
  form.machine_prices = machinePrices
  localError.value = validate(materialPrices, machinePrices)
  if (localError.value) return
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
                <p>维护{{ displayFactoryName }}内部报价的初始材料价与初始机型价。</p>
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

            <section class="quote-baseline-card">
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

            <section class="quote-baseline-card">
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
.quote-baseline-backdrop{position:fixed;z-index:90;inset:0;display:flex;align-items:center;justify-content:center;background:rgb(15 23 42/.48);padding:24px;backdrop-filter:blur(5px)}.quote-baseline-dialog{display:flex;width:min(1120px,100%);max-height:calc(100vh - 48px);flex-direction:column;overflow:hidden;border:1px solid #dbe5ea;border-radius:20px;background:#f8fafc;box-shadow:0 30px 80px rgb(15 23 42/.28)}.quote-baseline-dialog>header{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;border-bottom:1px solid #e2e8f0;background:#fff;padding:20px 22px}.quote-baseline-title-row{display:flex;gap:13px}.quote-baseline-icon{display:grid;width:48px;height:48px;flex:0 0 auto;place-items:center;border-radius:14px;background:#ccfbf1;color:#0f766e}.quote-baseline-icon svg{width:24px}.quote-baseline-title-line{display:flex;align-items:center;flex-wrap:wrap;gap:10px}.quote-baseline-title-line h2{margin:0;color:#0f172a;font-size:22px;font-weight:950}.quote-baseline-title-line span{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:5px 8px;font-size:11px;font-weight:900}.quote-baseline-title-line span svg{width:13px}.quote-baseline-title-line .editable{background:#ecfdf5;color:#047857}.quote-baseline-title-line .readonly{background:#eff6ff;color:#1d4ed8}.quote-baseline-title-row p{margin:5px 0 0;color:#64748b;font-size:13px}.quote-baseline-close{display:grid;width:36px;height:36px;place-items:center;border:0;border-radius:9px;background:transparent;color:#64748b}.quote-baseline-close:hover{background:#f1f5f9;color:#0f172a}.quote-baseline-close svg{width:20px}.quote-baseline-body{display:grid;gap:14px;overflow:auto;padding:18px 22px}.quote-baseline-note{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:10px;border:1px solid #99f6e4;border-radius:11px;background:#f0fdfa;padding:10px 12px;color:#0f766e;font-size:12px}.quote-baseline-note strong{font-weight:950}.quote-baseline-note span:last-child{color:#64748b;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px}.quote-baseline-error{margin:0;border:1px solid #fecaca;border-radius:10px;background:#fef2f2;padding:9px 11px;color:#b91c1c;font-size:12px}.quote-baseline-card{overflow:hidden;border:1px solid #dbe5ea;border-radius:13px;background:#fff}.quote-baseline-card-title{display:flex;align-items:center;justify-content:space-between;gap:16px;border-bottom:1px solid #e2e8f0;padding:13px 14px}.quote-baseline-card-title h3{margin:0;color:#0f172a;font-size:15px;font-weight:950}.quote-baseline-card-title p{margin:4px 0 0;color:#64748b;font-size:11px}.quote-baseline-card-title button{display:inline-flex;height:34px;align-items:center;gap:5px;border:1px solid #5eead4;border-radius:9px;background:#f0fdfa;padding:0 10px;color:#0f766e;font-size:12px;font-weight:900}.quote-baseline-card-title button:hover{background:#ccfbf1}.quote-baseline-card-title button svg{width:15px}.quote-baseline-table-scroll{max-height:280px;overflow:auto}.quote-baseline-card table{width:100%;border-collapse:collapse;table-layout:fixed}.quote-baseline-card th{position:sticky;z-index:1;top:0;background:#f1f5f9;padding:9px 11px;color:#64748b;font-size:11px;font-weight:900;text-align:left}.quote-baseline-card th:last-child,.quote-baseline-card td:last-child{width:52px}.quote-baseline-card td{border-top:1px solid #eef2f6;padding:6px 8px}.quote-baseline-card input{width:100%;height:34px;border:1px solid #dbe5ea;border-radius:8px;background:#fff;padding:0 9px;color:#0f172a;font-size:12px;outline:0}.quote-baseline-card input:focus{border-color:#14b8a6;box-shadow:0 0 0 3px rgb(20 184 166/.1)}.quote-baseline-card input:disabled{border-color:transparent;background:transparent;color:#334155;opacity:1}.quote-baseline-delete{display:grid;width:32px;height:32px;place-items:center;border:1px solid #fee2e2;border-radius:8px;background:#fff;color:#dc2626}.quote-baseline-delete:hover:not(:disabled){background:#fef2f2}.quote-baseline-delete:disabled{cursor:not-allowed;opacity:.35}.quote-baseline-delete svg{width:15px}.quote-baseline-dialog>footer{display:flex;align-items:center;justify-content:space-between;gap:16px;border-top:1px solid #e2e8f0;background:#fff;padding:14px 22px}.quote-baseline-dialog>footer>span{color:#64748b;font-size:11px}.quote-baseline-dialog>footer>div{display:flex;gap:9px}.quote-baseline-cancel,.quote-baseline-save{height:38px;border-radius:9px;padding:0 14px;font-size:12px;font-weight:900}.quote-baseline-cancel{border:1px solid #cbd5e1;background:#fff;color:#475569}.quote-baseline-save{display:inline-flex;align-items:center;gap:7px;border:1px solid #0f766e;background:#0f766e;color:#fff;box-shadow:0 8px 20px rgb(15 118 110/.18)}.quote-baseline-save:hover{background:#115e59}.quote-baseline-save:disabled{cursor:wait;opacity:.6}.quote-baseline-save svg{width:15px}.baseline-modal-enter-active,.baseline-modal-leave-active{transition:opacity 180ms ease}.baseline-modal-enter-active .quote-baseline-dialog,.baseline-modal-leave-active .quote-baseline-dialog{transition:transform 220ms ease,opacity 180ms ease}.baseline-modal-enter-from,.baseline-modal-leave-to{opacity:0}.baseline-modal-enter-from .quote-baseline-dialog{opacity:0;transform:translateY(12px) scale(.985)}.baseline-modal-leave-to .quote-baseline-dialog{opacity:0;transform:translateY(6px) scale(.99)}
@media(max-width:760px){.quote-baseline-backdrop{align-items:flex-end;padding:0}.quote-baseline-dialog{max-height:94vh;border-radius:18px 18px 0 0}.quote-baseline-note{grid-template-columns:1fr}.quote-baseline-dialog>header,.quote-baseline-body,.quote-baseline-dialog>footer{padding-left:14px;padding-right:14px}.quote-baseline-dialog>footer{align-items:stretch;flex-direction:column}.quote-baseline-dialog>footer>div{display:grid;grid-template-columns:1fr 1fr}.quote-baseline-card table{min-width:620px}}
@media(prefers-reduced-motion:reduce){.baseline-modal-enter-active,.baseline-modal-leave-active,.baseline-modal-enter-active .quote-baseline-dialog,.baseline-modal-leave-active .quote-baseline-dialog{transition:none}}
</style>
