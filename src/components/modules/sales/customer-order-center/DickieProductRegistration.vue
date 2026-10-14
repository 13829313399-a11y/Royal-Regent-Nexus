<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { CustomerOrderImportPreview } from '@/types/customerOrder'
import type { OrderProductChoice, OrderProductCatalog, OrderProductChange } from '@/types/customerOrderProduct'
import { customerOrderProductsApi as api } from '@/api/customerOrderProducts'
import { getApiErrorMessage } from '@/lib/http'

const props = defineProps<{ preview: CustomerOrderImportPreview; busy: boolean }>()
const emit = defineEmits<{ apply: [choices: OrderProductChoice[]]; refresh: [product: string] }>()
const catalog = ref<OrderProductCatalog | null>(null)
const error = ref('')
const loading = ref(false)
const saving = ref(false)
const expanded = ref(false)
const search = ref('')
const picked = ref('')
const active = ref(true)
const history = ref<OrderProductChange[]>([])
const draft = ref<OrderProductChoice>({ product_no: '', item_sheet_name: '', product_name_zh: '', product_name_en: '', default_pack: '', reason: '' })
let epoch = 0
let selectionEpoch = 0
let controller = new AbortController()
const normalize = (value: string) => value.toUpperCase().replace(/[^A-Z0-9]/g, '')
const allowed = computed(() => props.preview.factory_id === 'huaxing' && props.preview.customer_code === 'dickie')
const rows = computed(() => [...new Map(props.preview.rows.map(row => [normalize(row.product_no), row])).values()])
const unresolved = computed(() => rows.value.filter(row => row.issues.some(i => ['unmapped_item_sheet', 'product_rule_conflict'].includes(i.code))))
const allProducts = computed(() => [...new Set([...rows.value.map(r => r.product_no), ...Object.values(catalog.value?.products ?? {}).map(p => p.product_no)])])
const visibleProducts = computed(() => allProducts.value.filter(p => normalize(p).includes(normalize(search.value))).slice(0, 50))
const enabled = computed(() => allowed.value && props.preview.product_registration?.available && !props.busy && !saving.value && !loading.value)
const canApply = computed(() => enabled.value && Boolean(draft.value.product_no) && props.preview.product_registration?.sheets.includes(draft.value.item_sheet_name)
  && draft.value.reason.trim().length >= 4 && (!draft.value.default_pack || /^[1-9]\d{0,6}$/.test(draft.value.default_pack) && Number(draft.value.default_pack) <= 1000000))
const currentPO = computed(() => rows.value.find(r => normalize(r.product_no) === normalize(draft.value.product_no)))

function clearProtected() { catalog.value = null; history.value = []; picked.value = ''; draft.value.product_no = '' }
function failure(cause: unknown) {
  error.value = getApiErrorMessage(cause)
  if ([401, 403].includes((cause as { response?: { status?: number } })?.response?.status ?? 0)) clearProtected()
}
async function select(product: string) {
  if (!allowed.value) return
  picked.value = product; history.value = []; error.value = ''
  const selection = ++selectionEpoch
  const k = normalize(product)
  const rule = catalog.value?.products[k]
  const row = rows.value.find(r => normalize(r.product_no) === k)
  const once = props.preview.product_registration?.choices.find(c => normalize(c.product_no) === k)
  draft.value = { product_no: product, item_sheet_name: once?.item_sheet_name ?? rule?.item_sheet_name ?? row?.item_sheet_name ?? '',
    product_name_zh: once?.product_name_zh ?? rule?.product_name_zh ?? row?.product_name_zh ?? '',
    product_name_en: once?.product_name_en ?? rule?.product_name_en ?? row?.product_name_en ?? '',
    default_pack: once?.default_pack ?? rule?.default_pack ?? row?.units_per_carton ?? '', reason: '' }
  active.value = rule?.active ?? true
  if (!catalog.value?.available) return
  const token = epoch
  try {
    const result = await api.history(product, controller.signal)
    if (token === epoch && selection === selectionEpoch) history.value = result.items
  } catch (cause) { if (token === epoch && selection === selectionEpoch) failure(cause) }
}
async function load() {
  controller.abort(); controller = new AbortController()
  const token = ++epoch
  clearProtected(); error.value = ''; loading.value = true
  if (!allowed.value) { loading.value = false; return }
  try {
    const result = await api.catalog(controller.signal)
    if (token !== epoch) return
    catalog.value = result
    if (result.revision !== props.preview.product_registration?.revision) {
      error.value = '货号规则已更新，请重新解析PO后核对。'; return
    }
    const first = unresolved.value[0] ?? rows.value[0]
    if (first) await select(first.product_no)
  } catch (cause) { if (token === epoch) failure(cause) }
  finally { if (token === epoch) loading.value = false }
}
function apply() {
  if (!canApply.value || !currentPO.value) return
  const choices = (props.preview.product_registration?.choices ?? []).filter(c => normalize(c.product_no) !== normalize(draft.value.product_no))
  emit('apply', [...choices, { ...draft.value, reason: draft.value.reason.trim() }])
}
async function save() {
  if (!canApply.value || !catalog.value?.can_write) return
  const token = epoch
  saving.value = true; error.value = ''
  try {
    await api.save({ ...draft.value, reason: draft.value.reason.trim(), active: active.value, expected_revision: catalog.value.revision }, controller.signal)
    if (token !== epoch) return
    emit('refresh', draft.value.product_no)
  } catch (cause) { if (token === epoch) failure(cause) }
  finally { if (token === epoch) saving.value = false }
}
watch(() => [props.preview.preview_fingerprint, props.preview.factory_id, props.preview.customer_code], () => { expanded.value = unresolved.value.length > 0; void load() }, { immediate: true })
onBeforeUnmount(() => { epoch += 1; controller.abort() })
</script>

<template>
  <section v-if="allowed" class="product-registration" data-testid="dickie-product-registration">
    <header><h3>Dickie 新货号建档与分类确认</h3><button type="button" :disabled="busy || saving" @click="expanded = !expanded">{{ expanded ? '收起' : '维护货号' }}</button></header>
    <p>当前 {{ unresolved.length }} 个货号待确认分类。规则只用于华兴 Dickie 的后续新单，不修改旧订单、库存或客户原件。</p>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="loading">正在读取货号规则及权限…</p>
    <template v-if="expanded && !loading">
      <p v-if="!preview.product_registration?.available">新货号维护尚未执行迁移 20261014_0161，请联系管理员。未确定分类的订单不能直接跳过。</p>
      <template v-else>
        <label>搜索本批或已保存货号<input v-model="search" aria-label="搜索货号" :disabled="busy || saving"></label>
        <label>选择货号<select :value="picked" aria-label="选择货号" :disabled="busy || saving" @change="select(($event.target as HTMLSelectElement).value)"><option value="">请选择</option><option v-for="product in visibleProducts" :key="product" :value="product">{{ product }}</option></select></label>
        <p v-if="allProducts.length > 50">最多显示50项，请输入完整货号搜索。</p>
        <template v-if="draft.product_no">
          <p>PO装箱数：{{ currentPO?.units_per_carton || '未提供／该货号不在本批' }}。价格、数量、交期始终按当前PO，不保存为产品默认值。</p>
          <div class="product-registration__fields">
            <label>目标ITEM分类<select v-model="draft.item_sheet_name" aria-label="目标ITEM分类" :disabled="busy || saving"><option value="">必须明确选择</option><option v-for="sheet in preview.product_registration?.sheets" :key="sheet" :value="sheet">{{ sheet }}</option></select></label>
            <label>中文名称<input v-model="draft.product_name_zh" aria-label="产品中文名称" maxlength="200" :disabled="busy || saving"></label>
            <label>英文名称<input v-model="draft.product_name_en" aria-label="产品英文名称" maxlength="300" :disabled="busy || saving"></label>
            <label>默认装箱数（仅当前PO未提供时参考）<input v-model="draft.default_pack" aria-label="默认装箱数" inputmode="numeric" maxlength="7" :disabled="busy || saving"></label>
          </div>
          <label>核对原因（4–500字）<textarea v-model="draft.reason" aria-label="产品核对原因" maxlength="500" :disabled="busy || saving" /></label>
          <button type="button" :disabled="!canApply || !currentPO" @click="apply">仅本次应用并重新预览</button>
          <label v-if="catalog?.can_write"><input v-model="active" type="checkbox" aria-label="启用货号规则" :disabled="busy || saving">启用此规则；取消勾选后保存为停用，历史记录仍保留。</label>
          <button v-if="catalog?.can_write" type="button" :disabled="!canApply" @click="save">{{ saving ? '正在保存…' : '保存规则并重新预览' }}</button>
          <p v-else>当前账号不能保存或停用公共货号规则；本次补录仍须有订单保存／导出权限。</p>
          <p>重新预览会撤销旧的放行确认和未应用编辑。PO已有值不会被默认名称或装箱数覆盖；规则与历史分类冲突时必须人工重新核对。</p>
          <details><summary>修改记录（最近20条）</summary><ul><li v-for="entry in history" :key="entry.revision">V{{ entry.revision }} · {{ entry.created_at }} · {{ entry.actor }} · {{ entry.data.after.active ? '启用' : '停用' }} · {{ entry.data.after.item_sheet_name }} · {{ entry.data.reason }}</li></ul></details>
        </template>
      </template>
    </template>
  </section>
</template>

<style scoped>
.product-registration{display:grid;gap:12px;padding:20px;border:1px solid var(--border,#cbd5e1);border-radius:12px;background:var(--card,#fff);color:var(--foreground,#263844)}
.product-registration header{display:flex;justify-content:space-between;gap:12px;align-items:center}.product-registration h3,.product-registration p{margin:0}.product-registration p{font-size:14px;line-height:1.6}.product-registration label{display:grid;gap:6px}.product-registration input,.product-registration select,.product-registration textarea{border:1px solid var(--border,#cbd5e1);border-radius:6px;padding:9px;background:var(--background,#fff);color:inherit;font:inherit}.product-registration button{border:1px solid var(--border,#cbd5e1);border-radius:6px;padding:9px 14px;background:var(--primary,#006b64);color:var(--primary-foreground,#fff);cursor:pointer}.product-registration button:disabled{opacity:.5;cursor:not-allowed}.product-registration [role=alert]{color:var(--destructive,#b42318)}.product-registration__fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.product-registration input[type=checkbox]{width:auto;justify-self:start}@media(max-width:700px){.product-registration__fields{grid-template-columns:1fr}}
</style>
