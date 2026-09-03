<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Search, X } from '@lucide/vue'
import { internalQuoteApi, type ApiInternalQuoteHistoryProduct } from '@/api/internalQuote'
import { getApiErrorMessage } from '@/lib/http'

const props = defineProps<{ open: boolean; factoryId: string; customer: string; isJustPlay: boolean; kind: 'product' | 'component'; multiple: boolean }>()
const emit = defineEmits<{ close: []; confirm: [items: Array<{ product: ApiInternalQuoteHistoryProduct; componentId?: string }>] }>()
const keyword = ref('')
const customerFilter = ref('')
const region = ref('')
const page = ref(1)
const total = ref(0)
const rows = ref<ApiInternalQuoteHistoryProduct[]>([])
const selected = ref<Record<string, { product: ApiInternalQuoteHistoryProduct; componentId?: string }>>({})
const busy = ref(false)
const error = ref('')
let sequence = 0
const selectedItems = computed(() => Object.values(selected.value))
const regionLabel = (code: string) => code === 'mainland' ? '大陆价' : code === 'indonesia' ? '印尼价' : '未分地区'
const statuses: Record<string, string> = { drafting: '草稿', collaborating: '协作中', final_reviewing: '审核中', fully_approved: '已审核', exported: '已输出', rejected: '已退回' }
function keyFor(row: ApiInternalQuoteHistoryProduct, componentId = '') { return `${row.quote_id}:${componentId}` }
function toggle(product: ApiInternalQuoteHistoryProduct, componentId = '') {
  const key = keyFor(product, componentId)
  if (selected.value[key]) { delete selected.value[key]; return }
  if (!props.multiple) selected.value = {}
  selected.value[key] = { product, componentId: componentId || undefined }
}
async function search(reset = false) {
  if (reset) page.value = 1
  const request = ++sequence
  busy.value = true
  error.value = ''
  try {
    const result = await internalQuoteApi.historyProducts(props.factoryId, { keyword: keyword.value.trim(), customer: customerFilter.value.trim(), region_code: region.value, page: page.value })
    if (request !== sequence || !props.open) return
    rows.value = result.items
    total.value = result.total
  } catch (reason) { if (request === sequence) error.value = getApiErrorMessage(reason) }
  finally { if (request === sequence) busy.value = false }
}
watch(() => [props.open, props.factoryId, props.kind, props.customer] as const, ([open]) => {
  sequence += 1
  if (!open) return
  keyword.value = ''; region.value = ''; customerFilter.value = props.customer
  selected.value = {}; rows.value = []; total.value = 0
  void search(true)
}, { immediate: true })
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="history-backdrop" @keydown.esc.stop="emit('close')" @mousedown.self="emit('close')">
      <section class="history-dialog" role="dialog" aria-modal="true" :aria-label="kind === 'product' ? '引用历史产品' : '引用历史配件'">
        <header><div><h2>{{ kind === 'product' ? '引用历史产品' : '引用历史配件' }}</h2><p>选择具体地区和款式；{{ kind === 'product' ? '每个选中产品独立加入新单。' : '选中分项加入当前产品，不携带共享包装和纸箱。' }}</p></div><button aria-label="关闭历史选择" @click="emit('close')"><X /></button></header>
        <form class="history-search" @submit.prevent="search(true)">
          <input v-model="keyword" aria-label="搜索历史报价" placeholder="报价号 / 产品名称 / 客户">
          <input v-model="customerFilter" aria-label="历史客户筛选" placeholder="客户名称（留空查看所有）">
          <select v-model="region" aria-label="历史地区筛选"><option value="">全部地区</option><option value="mainland">大陆价</option><option value="indonesia">印尼价</option></select>
          <button type="submit" :disabled="busy"><Search />搜索</button>
        </form>
        <p v-if="error" role="alert" class="history-error">{{ error }}</p>
        <div class="history-results" :aria-busy="busy">
          <p v-if="busy">正在读取历史产品…</p><p v-else-if="!rows.length">没有找到历史产品，可清空客户筛选后重试。</p>
          <article v-for="row in rows" :key="row.quote_id" :class="{ incompatible: row.is_justplay !== isJustPlay }">
            <div class="history-product"><label v-if="kind === 'product'"><input type="checkbox" :checked="!!selected[keyFor(row)]" :disabled="row.is_justplay !== isJustPlay || busy" @change="toggle(row)"><strong>{{ row.product_name }}</strong></label><strong v-else>{{ row.product_name }}</strong><span>{{ regionLabel(row.region_code) }}</span><span>{{ statuses[row.status] || row.status }}</span></div>
            <p>{{ row.batch_quote_no || row.quote_no }} / {{ row.quote_no }} · {{ row.version_label }} · {{ row.customer }} · {{ row.qty.toLocaleString() }} PCS</p>
            <small v-if="row.is_justplay !== isJustPlay">普通客和 JustPlay 的报价结构不同，不能互相引用。</small>
            <div v-else-if="kind === 'component'" class="history-components"><label v-for="component in row.components" :key="component.id"><input type="checkbox" :checked="!!selected[keyFor(row, component.id)]" :disabled="busy" @change="toggle(row, component.id)">{{ component.name }}</label><small v-if="!row.components.length">该历史产品尚未建立分项。</small></div>
            <small v-else-if="row.is_justplay">含：{{ row.components.map(c => c.name).join('、') }}</small>
          </article>
        </div>
        <nav><button :disabled="busy || page <= 1" @click="page--; search()">上一页</button><span>第 {{ page }} 页 · 共 {{ total }} 款</span><button :disabled="busy || page * 10 >= total" @click="page++; search()">下一页</button></nav>
        <footer><p>已选 {{ selectedItems.length }} {{ kind === 'product' ? '款产品' : '个分项' }}。沿用明细输入，新单重新核价、重新审核。</p><div><button @click="emit('close')">取消</button><button class="primary" :disabled="busy || !selectedItems.length" @click="emit('confirm', selectedItems)">确认引用</button></div></footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.history-backdrop{position:fixed;inset:0;z-index:130;display:grid;place-items:center;padding:24px;background:#0f172a88}.history-dialog{display:flex;flex-direction:column;width:min(1000px,100%);max-height:90vh;border-radius:18px;background:#fff;box-shadow:0 24px 80px #0004;overflow:hidden;color:#0f172a}.history-dialog header,.history-dialog footer{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:18px 22px;background:#f0fdfa}.history-dialog h2{font-size:20px;margin:0}.history-dialog p{margin:6px 0;color:#64748b;font-size:13px}.history-dialog button{display:inline-flex;align-items:center;gap:6px;border:1px solid #cbd5e1;border-radius:8px;padding:9px 12px;background:#fff;cursor:pointer}.history-dialog button:disabled{opacity:.45;cursor:default}.history-dialog svg{width:18px;height:18px}.history-search{display:flex;gap:8px;padding:16px 22px;flex-wrap:wrap}.history-search input,.history-search select{padding:9px;border:1px solid #cbd5e1;border-radius:8px;min-width:0}.history-search input:first-child{flex:1}.history-results{overflow:auto;padding:0 22px;min-height:160px}.history-results article{border:1px solid #dbe5ea;border-radius:10px;margin:0 0 10px;padding:12px}.history-product{display:flex;align-items:center;gap:12px}.history-product label,.history-components label{display:inline-flex;align-items:center;gap:7px;cursor:pointer}.history-product span{font-size:12px;background:#f1f5f9;padding:3px 8px;border-radius:5px}.history-components{display:flex;flex-wrap:wrap;gap:10px;margin-top:10px}.history-components label{padding:7px 12px;background:#f0fdfa;border-radius:7px}.history-results small{color:#64748b}.history-results .incompatible{opacity:.6}.history-dialog nav{display:flex;align-items:center;justify-content:center;gap:16px;padding:12px}.history-dialog footer>div{display:flex;gap:8px;flex-shrink:0}.history-dialog .primary{background:#0f766e;border-color:#0f766e;color:#fff}.history-error{padding:12px;color:#b91c1c!important}@media(max-width:650px){.history-backdrop{padding:8px}.history-dialog footer{align-items:flex-start;flex-direction:column}.history-product{flex-wrap:wrap}.history-search input{width:100%}}
</style>
