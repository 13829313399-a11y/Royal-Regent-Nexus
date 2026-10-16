<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import type { CartonCustomerResponse } from '@/api/cartonProcurement'
import { getApiErrorMessage } from '@/lib/http'
import { standardPaperTypes, paperQualities } from '@/features/carton-procurement/paperCatalog'
import { convertOrderGroup, groupStorageKey, groupSubmission, newGroupPaper, newGroupStyle, newOrderGroup, readGroups, saveGroups, type OrderGroupDraft } from '@/features/carton-procurement/orderGroups'
import CartonPaperPicker from './CartonPaperPicker.vue'
import CartonDimensionInput from './CartonDimensionInput.vue'
const props = defineProps<{ factoryId: string; customers: CartonCustomerResponse[]; defaultUnit: string }>()
const emit = defineEmits<{ close: []; created: [] }>()
const dialog = ref<HTMLElement | null>(null), returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
onMounted(() => { void nextTick(() => dialog.value?.querySelector<HTMLElement>('button:not(:disabled)')?.focus()) })
function trapFocus(event: KeyboardEvent) {
  if (event.key !== 'Tab') return
  const elements = [...(dialog.value?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled)') ?? [])]
  const first = elements[0], last = elements.at(-1)
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}
const auth = useAuthStore(), groups = ref<OrderGroupDraft[]>([]), selected = ref('')
const error = ref(''), message = ref(''), busy = ref(false), corrupted = ref(false), confirmRemove = ref(false)
const context = computed(() => auth.currentUser?.id ? groupStorageKey(auth.currentUser.id, auth.currentUser.identity?.employment_epoch ?? 1, props.factoryId) : '')
const group = computed(() => groups.value.find(row => row.id === selected.value))
const canWrite = computed(() => ['carton', 'pmc-warehouse'].some(dept => auth.can('carton_procurement:order_write', props.factoryId, dept)))
const locked = computed(() => busy.value || !!group.value?.pending || !!group.value?.submitted || !canWrite.value)
let generation = 0, hydrating = false
watch(context, key => {
  generation++; hydrating = true; busy.value = false; error.value = ''; message.value = ''; corrupted.value = false
  try { groups.value = key ? readGroups(localStorage, key) : []; selected.value = groups.value[0]?.id ?? '' }
  catch (cause) { groups.value = []; selected.value = ''; corrupted.value = true; error.value = `草稿读取失败：${getApiErrorMessage(cause)}` }
  finally { hydrating = false }
}, { immediate: true })
function persist() {
  if (!context.value || corrupted.value) return false
  try { saveGroups(localStorage, context.value, groups.value); message.value = '已保存在此浏览器，换设备不会同步。'; return true }
  catch (cause) { message.value = ''; error.value = `草稿保存失败：${getApiErrorMessage(cause)}`; return false }
}
watch(groups, () => { if (!hydrating) persist() }, { deep: true, flush: 'sync' })
function close() {
  if (!busy.value && (!groups.value.length || corrupted.value || persist())) emit('close')
}
watch(selected, () => { confirmRemove.value = false })
function add() {
  if (groups.value.length >= 30 || corrupted.value || !canWrite.value) return
  const value = newOrderGroup(props.defaultUnit); groups.value.push(value); selected.value = value.id
}
function remove() {
  if (busy.value || !group.value || group.value.pending) return
  groups.value = groups.value.filter(row => row.id !== selected.value); selected.value = groups.value[0]?.id ?? ''
}
async function convert() {
  if (!group.value || busy.value || !canWrite.value || group.value.submitted) return
  const current = group.value, token = generation, key = context.value, hadPending = !!group.value.pending
  error.value = ''; busy.value = true
  try {
    const customer = props.customers.find(row => row.customer_code === current.customer_code)
    if (!customer) throw new Error('当前客户已不可操作，请刷新客户授权后继续')
    current.pending ??= groupSubmission(current, props.factoryId, customer.customer_name)
    // Persist the exact frozen request before a network call. Uncertain writes retry it only.
    if (!persist()) { if (!hadPending) delete current.pending; return }
    const result = await convertOrderGroup(current.pending)
    if (token !== generation || key !== context.value) return
    current.submitted = result; delete current.pending; persist()
    message.value = `已逐款生成 ${result.length} 张待下单订单。请返回台账勾选并使用“批量确认并锁定”，沿用现有合并采购单。`
  } catch (cause) {
    if (token !== generation) return
    const status = (cause as { response?: { status?: number } }).response?.status
    const reason = getApiErrorMessage(cause)
    const priorResult = status === 409 && /该合单草稿已转为订单|原订单已删除/.test(reason)
    if (status && status >= 400 && status < 500 && status !== 408 && !priorResult) { delete current.pending; persist() }
    error.value = `${getApiErrorMessage(cause)}${current.pending ? '；转单结果未确认，草稿已冻结，请重试原请求取回结果，勿另建同组订单。' : '；整组未生成订单，可补齐资料后重试。'}`
  } finally { if (token === generation) busy.value = false }
}
onBeforeUnmount(() => { generation++; returnFocus?.focus() })
</script>
<template>
  <div class="fixed inset-0 z-[75] flex items-center justify-center bg-slate-950/45 p-4" @keydown.esc.stop="close">
    <section ref="dialog" role="dialog" aria-modal="true" aria-label="合单草稿组" @keydown="trapFocus" class="max-h-[92vh] w-full max-w-6xl overflow-auto rounded-xl bg-white p-5 shadow-xl">
      <header class="flex items-start justify-between gap-4"><div><h2 class="text-lg font-bold">合单草稿组</h2><p class="mt-2 text-xs text-slate-500">同厂区、同客户、同供应商（本厂默认供应商）。按实际数量增加或移除 PO / 款式（每组最多 50 款），合同号和货号可后补；各款纸品和来源分别保留。草稿不向供应商发行，不产生库存或应付。</p></div><button type="button" :disabled="busy" class="shrink-0 rounded border px-3 py-2" @click="close">保存并关闭</button></header>
      <p v-if="error" role="alert" class="my-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
      <p v-if="message" role="status" class="my-3 text-xs text-teal-700">{{ message }}</p>
      <nav class="my-4 flex flex-wrap gap-2"><button v-for="row in groups" :key="row.id" type="button" :disabled="busy" class="rounded border px-3 py-2 text-xs" :class="selected === row.id ? 'border-teal-500 bg-teal-50' : ''" @click="selected = row.id">{{ row.name }} · {{ row.rows.length }} 款{{ row.submitted ? ' · 已转单' : row.pending ? ' · 结果待核' : '' }}</button><button type="button" :disabled="corrupted || !canWrite || groups.length >= 30" class="rounded border border-teal-300 px-3 py-2 text-xs text-teal-800" @click="add">新增合单草稿组</button></nav>
      <template v-if="group">
        <div v-if="confirmRemove" role="alert" class="mb-3 flex flex-wrap items-center gap-3 rounded border border-amber-200 bg-amber-50 p-3 text-xs"><span>确认移除此浏览器的草稿组？未转单内容将被移除，已生成的正式订单仍保留。</span><button type="button" class="rounded border bg-white px-3 py-2" @click="confirmRemove = false">保留草稿</button><button type="button" class="rounded border border-red-200 px-3 py-2 text-red-700" @click="remove(); confirmRemove = false">确认移除此草稿组</button></div>
        <fieldset :disabled="locked" class="space-y-4">
          <div class="grid gap-3 rounded-lg bg-slate-50 p-3 sm:grid-cols-3"><label class="text-xs">组名<input v-model="group.name" aria-label="合单组名称" maxlength="128" class="mt-1 h-9 w-full rounded border px-2"></label><label class="text-xs">客户<select v-model="group.customer_code" aria-label="合单组客户" class="mt-1 h-9 w-full rounded border px-2"><option value="">请选择同一客户</option><option v-for="row in customers" :key="row.id" :value="row.customer_code">{{ row.customer_name }} · {{ row.customer_code }}</option></select></label><label class="text-xs">下单日期<input v-model="group.order_date" type="date" aria-label="合单组下单日期" class="mt-1 h-9 w-full rounded border px-2"></label></div>
          <article v-for="(row, index) in group.rows" :key="row.id" class="space-y-3 rounded-lg border p-3">
            <div class="flex justify-between text-sm font-bold"><h3>第 {{ index + 1 }} 款</h3><button v-if="group.rows.length > 1" type="button" class="text-xs text-red-600" @click="group.rows.splice(index, 1)">移除此款</button></div>
            <div class="grid gap-3 sm:grid-cols-3"><label v-for="field in (['customer_po', 'contract_no', 'item_no', 'product_name', 'quantity', 'customer_due_date'] as const)" :key="field" class="text-xs">{{ { customer_po: '客户 PO', contract_no: '合同号（可后补）', item_no: '货号（可后补）', product_name: '产品名称', quantity: '产品数量（选填）', customer_due_date: '客户交期' }[field] }}<input :value="row[field]" @input="row[field] = ($event.target as HTMLInputElement).value" :type="field === 'customer_due_date' ? 'date' : field === 'quantity' ? 'number' : 'text'" :aria-label="`合单 ${field} ${index + 1}`" :maxlength="field === 'product_name' ? 255 : 128" class="mt-1 h-9 w-full rounded border px-2"></label></div>
            <label class="block text-xs">此款来源 / 凭据说明<textarea v-model="row.source" :aria-label="`合单来源 ${index + 1}`" maxlength="2000" placeholder="如客户 PO 文件名、表页及行号；每款分别保留" class="mt-1 w-full rounded border p-2" /></label>
            <div v-for="(line, paperIndex) in row.lines" :key="line.id" class="space-y-3 rounded border border-slate-200 bg-slate-50 p-3">
              <div class="grid gap-3 sm:grid-cols-3"><CartonPaperPicker v-model="line.packaging_type" :options="standardPaperTypes.map(row => row.name)" :label="`合单纸品类型 ${index + 1}-${paperIndex + 1}`" :disabled="locked" /><CartonPaperPicker v-model="line.paper_quality" :options="paperQualities.map(row => row.name)" :label="`合单纸质 ${index + 1}-${paperIndex + 1}`" :disabled="locked" /><CartonPaperPicker v-model="line.specification" :options="[]" dimension-paste :label="`合单规格 ${index + 1}-${paperIndex + 1}`" :disabled="locked" /></div>
              <CartonDimensionInput v-model="line.dimension_unit" :specification="line.specification" :label="`合单尺寸单位 ${index + 1}-${paperIndex + 1}`" :disabled="locked" />
              <div class="grid gap-3 sm:grid-cols-4"><label v-for="field in (['required_quantity', 'usage_quantity', 'unit_price', 'unit'] as const)" :key="field" class="text-xs">{{ { required_quantity: '本款纸品需求数量 *', usage_quantity: '每箱装产品数（选填）', unit_price: '单价 CNY（选填）', unit: '计量单位 *' }[field] }}<input :value="line[field]" @input="line[field] = ($event.target as HTMLInputElement).value" :type="field === 'unit' ? 'text' : 'number'" step="any" min="0" :aria-label="`合单 ${field} ${index + 1}-${paperIndex + 1}`" class="mt-1 h-9 w-full rounded border px-2"></label></div>
              <button v-if="row.lines.length > 1" type="button" class="text-xs text-red-600" @click="row.lines.splice(paperIndex, 1)">移除此纸品</button>
            </div>
            <button type="button" :disabled="row.lines.length >= 50" class="rounded border px-3 py-2 text-xs" @click="row.lines.push(newGroupPaper(defaultUnit))">添加纸品 / 配卡</button>
          </article>
          <button type="button" :disabled="group.rows.length >= 50" class="rounded border px-3 py-2 text-xs" @click="group.rows.push(newGroupStyle(defaultUnit))">增加 PO / 款式</button>
        </fieldset>
        <div v-if="group.submitted" class="my-4 rounded border border-teal-200 bg-teal-50 p-3 text-sm"><p v-for="order in group.submitted" :key="order.id">{{ order.customer_po }} · {{ order.contract_no }} · {{ order.item_no }} → {{ order.order_no }}</p><button type="button" class="mt-3 rounded bg-teal-700 px-4 py-2 text-white" @click="emit('created')">返回订单台账继续批量下单</button></div>
        <footer class="mt-5 flex flex-wrap justify-between gap-3 border-t pt-4"><button type="button" :disabled="busy || !!group.pending" class="text-xs text-red-600" @click="confirmRemove = true">移除此本机草稿组</button><button v-if="!group.submitted" type="button" :disabled="busy || !canWrite || corrupted" class="rounded bg-teal-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-50" @click="convert">{{ busy ? '整组校验并转单中…' : group.pending ? '核对原转单结果 / 重试' : '资料齐全，整组转为待下单订单' }}</button></footer>
      </template>
    </section>
  </div>
</template>
