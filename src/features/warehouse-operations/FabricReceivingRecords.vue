<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { ArrowUpRight, ChevronRight, ClipboardList, Plus, RefreshCw, Search, X } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { fabricReceivingApi as api, materialCategoryLabels, type FabricReceipt, type FabricStockBatch } from '@/api/fabricReceiving'
import FabricReceiptDetail from './FabricReceiptDetail.vue'

const props = defineProps<{ mode: 'receipts' | 'stock' | 'movements' }>()
const search = ref(''), appliedSearch = ref(''), offset = ref(0), total = ref<number>(), busy = ref(false), error = ref('')
const receipts = ref<FabricReceipt[]>([]), stock = ref<FabricStockBatch[]>([]), selected = ref<FabricReceipt>()
const title = computed(() => props.mode === 'receipts' ? '实际入库记录' : props.mode === 'stock' ? '原始入库批次' : '实际入库流水')
const page = computed(() => Math.floor(offset.value / 50) + 1)
const pageCount = computed(() => Math.max(1, Math.ceil((total.value ?? 0) / 50)))
const pendingTarget = { path: '/modules/pmc-warehouse/fabric-warehouse/receipts', query: { factory: 'huakang-c', view: 'pending' } }
const stockTarget = { path: '/modules/pmc-warehouse/fabric-warehouse/inventory', query: { factory: 'huakang-c', view: 'stock' } }
function shortId(id: string) { return id.length > 16 ? `${id.slice(0, 8)}…${id.slice(-4)}` : id }
function locations(record: FabricReceipt) {
  const names = [...new Set(record.batches.map(batch => batch.location).filter(Boolean))]
  return names.length > 2 ? `${names.slice(0, 2).join(' / ')} 等 ${names.length} 个仓位` : names.join(' / ') || '—'
}
let sequence = 0
async function load() {
  const ticket = ++sequence
  busy.value = true; error.value = ''; total.value = undefined; receipts.value = []; stock.value = []; selected.value = undefined
  try {
    if (props.mode === 'receipts') {
      const result = await api.receipts(appliedSearch.value, offset.value)
      if (ticket === sequence) { total.value = result.total; receipts.value = result.items }
    } else {
      const result = await api.stock(appliedSearch.value, offset.value)
      if (ticket === sequence) { total.value = result.total; stock.value = result.items }
    }
  } catch (e) { if (ticket === sequence) error.value = getApiErrorMessage(e) }
  finally { if (ticket === sequence) busy.value = false }
}
function query() { appliedSearch.value = search.value.trim(); offset.value = 0; void load() }
function clearSearch() { search.value = ''; query() }
function changePage(direction: number) { offset.value += direction * 50; void load() }
watch(() => props.mode, () => { search.value = ''; appliedSearch.value = ''; offset.value = 0; void load() }, { immediate: true })
onBeforeUnmount(() => { sequence++ })
</script>

<template>
  <div class="fabric-receiving-records" :aria-busy="busy">
    <header class="receipt-records-heading">
      <div><div class="receipt-records-title"><h2>{{ title }}</h2><span v-if="total !== undefined" class="receipt-records-count">{{ total }} 笔</span></div><p>按收货日期查看已确认的实收单据与批次明细。</p></div>
      <div class="receipt-records-actions"><RouterLink :to="stockTarget" class="receipt-records-link">库存台账<ArrowUpRight :size="15" aria-hidden="true" /></RouterLink><RouterLink :to="pendingTarget" class="receipt-records-primary"><Plus :size="16" aria-hidden="true" />登记入库</RouterLink></div>
    </header>
    <form class="receipt-records-toolbar" role="search" aria-label="查询入库记录" @submit.prevent="query">
      <div class="receipt-records-search"><Search :size="17" aria-hidden="true" /><input v-model="search" aria-label="查找实际入库记录" type="search" maxlength="128" placeholder="搜索采购单、送货依据、物料或供应商" :disabled="busy" /><button v-if="search" type="button" aria-label="清空入库搜索" :disabled="busy" @click="clearSearch"><X :size="15" aria-hidden="true" /></button></div>
      <Button type="submit" variant="outline" :disabled="busy">查询</Button><Button type="button" variant="ghost" :disabled="busy" aria-label="刷新入库记录" @click="load"><RefreshCw :size="15" :class="{ 'receipt-records-spinning': busy }" aria-hidden="true" />刷新</Button>
      <span class="receipt-records-order">按收货日期 · 最新在前</span>
    </form>
    <div v-if="appliedSearch && !busy && !error" class="receipt-records-filter">搜索结果：<strong>{{ appliedSearch }}</strong><button type="button" @click="clearSearch">清空搜索</button></div>

    <div v-if="busy" class="receipt-records-state" role="status"><RefreshCw :size="24" class="receipt-records-spinning" aria-hidden="true" /><strong>正在读取入库记录</strong><p>正在核对已登记的实收单据，请稍候。</p></div>
    <div v-else-if="error" class="receipt-records-state receipt-records-error" role="alert"><ClipboardList :size="28" aria-hidden="true" /><strong>入库记录读取失败</strong><p>{{ error }}</p><Button variant="outline" @click="load">重新加载</Button></div>
    <div v-else-if="total === 0" class="receipt-records-state" role="status"><ClipboardList :size="30" aria-hidden="true" /><strong>{{ appliedSearch ? '没有找到匹配的入库记录' : '还没有实际入库记录' }}</strong><p>{{ appliedSearch ? '可换用采购单号、物料编码或供应商名称查询。' : '在待收料中确认本次实收后，单据会出现在这里。' }}</p><Button v-if="appliedSearch" variant="outline" @click="clearSearch">查看全部记录</Button><RouterLink v-else :to="pendingTarget" class="receipt-records-link">前往待收料<ArrowUpRight :size="15" aria-hidden="true" /></RouterLink></div>
    <template v-else-if="total !== undefined">
      <div class="receipt-records-table-scroll" :class="{ 'receipt-records-desktop': mode === 'receipts' }" tabindex="0" role="region" :aria-label="mode === 'receipts' ? '实际入库记录' : '原始入库明细'">
        <table v-if="mode === 'receipts'" class="receipt-records-table"><caption class="sr-only">已登记实收入库，查看详情可追溯完整单号与批次</caption><colgroup><col style="width:15%" /><col style="width:22%" /><col style="width:20%" /><col style="width:12%" /><col style="width:12%" /><col style="width:12%" /><col style="width:7%" /></colgroup><thead><tr><th scope="col">收货日期 / 入库单</th><th scope="col">物料</th><th scope="col">采购来源 / 供应商</th><th scope="col" class="receipt-records-numeric">本次实收</th><th scope="col">批次 / 仓位</th><th scope="col">送货依据 / 登记人</th><th scope="col" class="receipt-records-action-cell">操作</th></tr></thead><tbody><tr v-for="record in receipts" :key="record.id">
          <td><strong>{{ record.receipt_date }}</strong><span class="receipt-records-id" :title="record.id">{{ shortId(record.id) }}</span></td>
          <td><strong>{{ record.facts.material_name || '—' }}</strong><span class="receipt-records-secondary"><span class="receipt-records-code">{{ record.facts.material_code || '—' }}</span><span class="receipt-records-tag">{{ materialCategoryLabels[record.material_category] }}</span></span></td>
          <td><strong>{{ record.facts.order_no || '—' }}<span v-if="record.facts.source_category === 'SUPPLEMENT'" class="receipt-records-tag supplement">补数</span></strong><span class="receipt-records-secondary">{{ record.facts.supplier || '—' }}</span></td>
          <td class="receipt-records-numeric"><strong class="receipt-records-quantity">{{ record.quantity }} <small>{{ record.unit }}</small></strong></td>
          <td><strong>{{ record.batches.length }} 项实物</strong><span class="receipt-records-secondary">{{ locations(record) }}</span></td>
          <td><strong>{{ record.delivery_reference || '—' }}</strong><span class="receipt-records-secondary">{{ record.actor_name }}</span></td>
          <td class="receipt-records-action-cell"><button class="receipt-records-detail-button" type="button" :aria-label="`查看入库详情 ${record.id}`" @click="selected = record">详情<ChevronRight :size="15" aria-hidden="true" /></button></td>
        </tr></tbody></table>
        <table v-else class="receipt-records-table receipt-records-legacy"><thead><tr><th scope="col">{{ mode === 'movements' ? '流水 / 入库单' : '批次 / 入库单' }}</th><th scope="col">物料 / 分类</th><th scope="col">采购来源 / 供应商</th><th scope="col">仓位</th><th scope="col">缸号 / 卷号</th><th scope="col">原始入库数量</th><th scope="col">入库时质量</th><th scope="col">收货日期</th><th scope="col">送货依据 / 登记人</th></tr></thead><tbody><tr v-for="batch in stock" :key="batch.id">
          <td><strong :title="mode === 'movements' ? batch.movement_id : batch.id">{{ shortId(mode === 'movements' ? batch.movement_id : batch.id) }}</strong><span class="receipt-records-id" :title="batch.receipt_id">{{ shortId(batch.receipt_id) }}</span></td><td><strong>{{ batch.facts.material_name }}</strong><span class="receipt-records-secondary">{{ batch.facts.material_code }} · {{ materialCategoryLabels[batch.material_category] }}</span></td><td><strong>{{ batch.facts.order_no }}</strong><span class="receipt-records-secondary">{{ batch.facts.supplier }}</span></td><td>{{ batch.location }}</td><td><template v-if="batch.material_category === 'FABRIC'">{{ batch.dye_lot || '—' }}<span class="receipt-records-secondary">{{ batch.roll_no || '—' }}</span></template><template v-else>—</template></td><td>{{ batch.quantity }} {{ batch.unit }}</td><td>待检</td><td>{{ batch.receipt_date }}</td><td>{{ batch.delivery_reference }}<span class="receipt-records-secondary">{{ batch.actor_name }}</span></td>
        </tr></tbody></table>
      </div>
      <div v-if="mode === 'receipts'" class="receipt-records-mobile" aria-label="入库记录卡片"><article v-for="record in receipts" :key="record.id"><header><strong>{{ record.receipt_date }}</strong><span>{{ materialCategoryLabels[record.material_category] }}</span></header><h3>{{ record.facts.material_name || record.facts.material_code }}</h3><p>{{ record.facts.material_code }}</p><dl><div><dt>采购单</dt><dd>{{ record.facts.order_no || '—' }}</dd></div><div><dt>供应商</dt><dd>{{ record.facts.supplier || '—' }}</dd></div><div><dt>仓位</dt><dd>{{ locations(record) }} · {{ record.batches.length }} 项</dd></div></dl><footer><strong>{{ record.quantity }} <small>{{ record.unit }}</small></strong><button class="receipt-records-detail-button" type="button" :aria-label="`查看入库详情 ${record.id}`" @click="selected = record">查看详情<ChevronRight :size="15" aria-hidden="true" /></button></footer></article></div>
    </template>
    <footer v-if="total !== undefined" class="receipt-records-footer"><span>共 {{ total }} 笔<template v-if="total"> · 显示 {{ offset + 1 }}–{{ Math.min(offset + 50, total) }} 笔</template></span><div><Button variant="outline" size="sm" :disabled="busy || offset === 0" @click="changePage(-1)">上一页</Button><span>{{ page }} / {{ pageCount }}</span><Button variant="outline" size="sm" :disabled="busy || offset + 50 >= total" @click="changePage(1)">下一页</Button></div></footer>
    <div class="receipt-records-note">这里只保留原始实收记录，不含历史库存期初；当前结余与质量请查看<RouterLink :to="stockTarget">库存台账</RouterLink>。</div>
    <FabricReceiptDetail v-if="selected" :record="selected" @close="selected = undefined" />
  </div>
</template>

<style scoped>
.fabric-receiving-records{color:#0f172a;background:#fff;min-width:0}
.receipt-records-heading{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:24px 24px 20px;flex-wrap:wrap}
.receipt-records-title,.receipt-records-actions{display:flex;align-items:center;gap:12px}
.receipt-records-title h2{font-size:20px;line-height:1.4;font-weight:700;letter-spacing:-.3px}
.receipt-records-heading p{font-size:13px;color:#64748b;margin-top:6px}
.receipt-records-count{background:#f1f5f9;border:1px solid #e2e8f0;color:#475569;border-radius:6px;padding:2px 8px;font-size:12px;font-variant-numeric:tabular-nums}
.receipt-records-link,.receipt-records-primary{display:inline-flex;align-items:center;justify-content:center;gap:6px;min-height:36px;padding:7px 12px;border-radius:7px;text-decoration:none;font-size:13px;font-weight:600;white-space:nowrap}
.receipt-records-link{color:#0f766e}.receipt-records-link:hover{background:#f0fdfa}.receipt-records-primary{background:#0f766e;color:#fff;border:1px solid #0f766e;box-shadow:0 1px 2px #0f172a12}.receipt-records-primary:hover{background:#115e59}
.receipt-records-toolbar{display:flex;align-items:center;gap:8px;padding:0 24px 20px}
.receipt-records-search{display:flex;align-items:center;gap:10px;height:40px;max-width:480px;flex:1;min-width:160px;border:1px solid #cbd5e1;border-radius:8px;padding:0 12px;color:#94a3b8;background:#fff;box-shadow:0 1px 2px #0f172a05}
.receipt-records-search:focus-within{border-color:#0d9488;box-shadow:0 0 0 3px #ccfbf180}.receipt-records-search>svg{flex-shrink:0}
.receipt-records-search input{min-width:0;width:100%;height:100%;padding:0;border:0;outline:0;background:transparent;color:#0f172a;font-size:13px}.receipt-records-search input::placeholder{color:#94a3b8}.receipt-records-search input::-webkit-search-cancel-button{display:none}.receipt-records-search button{display:grid;place-items:center;padding:4px;border-radius:4px;color:#64748b}
.receipt-records-order{margin-left:auto;font-size:12px;color:#94a3b8;white-space:nowrap}.receipt-records-filter{display:flex;align-items:center;gap:8px;padding:0 24px 14px;font-size:12px;color:#64748b}.receipt-records-filter strong{overflow-wrap:anywhere;font-weight:500;color:#334155}.receipt-records-filter button{color:#0f766e;white-space:nowrap}
.receipt-records-table-scroll{overflow:auto;border-top:1px solid #e2e8f0;max-height:calc(100dvh - 340px);min-height:140px}
.receipt-records-table{width:100%;min-width:1040px;border-collapse:separate;border-spacing:0;table-layout:fixed;text-align:left;font-size:13px;line-height:1.6}
.receipt-records-table th{position:sticky;top:0;z-index:1;background:#f8fafc;border-bottom:1px solid #e2e8f0;color:#64748b;font-size:12px;font-weight:500;padding:12px 16px;white-space:nowrap}
.receipt-records-table td{padding:20px 16px;border-bottom:1px solid #f1f5f9;vertical-align:top;overflow-wrap:anywhere}
.receipt-records-table th:first-child,.receipt-records-table td:first-child{padding-left:24px}.receipt-records-table th:last-child,.receipt-records-table td:last-child{padding-right:24px}.receipt-records-table tbody tr:last-child td{border-bottom:0}.receipt-records-table tbody tr:hover{background:#f8fdfc}
.receipt-records-table td>strong{display:block;font-weight:550;color:#1e293b}.receipt-records-secondary{display:block;color:#64748b;font-size:12px;margin-top:6px;line-height:1.6}.receipt-records-code,.receipt-records-id{font-variant-numeric:tabular-nums}.receipt-records-id{display:block;margin-top:6px;color:#94a3b8;font-size:11px;white-space:nowrap}
.receipt-records-tag{display:inline-block;font-size:10px;font-weight:500;color:#64748b;background:#f1f5f9;border:1px solid #e2e8f0;border-radius:4px;padding:0 5px;margin-left:8px;vertical-align:middle;white-space:nowrap}.receipt-records-tag.supplement{color:#9a3412;background:#fff7ed;border-color:#ffedd5}
.receipt-records-table .receipt-records-numeric{text-align:right}.receipt-records-table .receipt-records-quantity{font-size:17px;color:#0f766e;font-weight:650;font-variant-numeric:tabular-nums;white-space:normal}.receipt-records-quantity small{font-size:12px;color:#64748b;font-weight:400}
.receipt-records-table .receipt-records-action-cell{text-align:right;white-space:nowrap}.receipt-records-detail-button{display:inline-flex;align-items:center;gap:3px;min-height:32px;padding:3px 0;color:#0f766e;font-size:13px;font-weight:600;white-space:nowrap}.receipt-records-detail-button:hover{text-decoration:underline;text-underline-offset:4px}
.receipt-records-legacy{min-width:1450px;table-layout:auto}
.receipt-records-state{display:flex;flex-direction:column;align-items:center;gap:12px;padding:52px 24px;text-align:center;border-top:1px solid #e2e8f0;color:#94a3b8}.receipt-records-state strong{font-size:15px;color:#334155;font-weight:600}.receipt-records-state p{max-width:500px;font-size:13px;color:#64748b;overflow-wrap:anywhere}.receipt-records-error>svg{color:#b45309}
.receipt-records-footer{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;border-top:1px solid #e2e8f0;padding:16px 24px;font-size:12px;color:#64748b}.receipt-records-footer>div{display:flex;align-items:center;gap:14px}.receipt-records-footer>div>span{font-variant-numeric:tabular-nums}
.receipt-records-note{border-top:1px solid #f1f5f9;background:#fafcfd;color:#94a3b8;font-size:11px;line-height:1.8;padding:12px 24px}.receipt-records-note a{color:#64748b;text-decoration:underline;text-underline-offset:3px;margin-left:3px}
.receipt-records-mobile{display:none}.receipt-records-spinning{animation:receipt-spin 1s linear infinite}@keyframes receipt-spin{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.receipt-records-spinning{animation:none}}
@media(max-width:760px){.receipt-records-heading{padding:20px 16px 16px;gap:14px}.receipt-records-title h2{font-size:18px}.receipt-records-actions{gap:4px}.receipt-records-toolbar{padding:0 16px 16px;flex-wrap:wrap}.receipt-records-order{display:none}.receipt-records-search{min-width:0;max-width:none;flex-basis:calc(100% - 72px)}.receipt-records-toolbar>button:last-of-type{display:none}.receipt-records-desktop{display:none}.receipt-records-filter{padding:0 16px 12px}.receipt-records-mobile{display:block;border-top:1px solid #e2e8f0}.receipt-records-mobile article{padding:18px 16px;border-bottom:1px solid #e2e8f0}.receipt-records-mobile article:last-child{border-bottom:0}.receipt-records-mobile header,.receipt-records-mobile footer{display:flex;align-items:center;justify-content:space-between;gap:16px}.receipt-records-mobile header{font-size:12px;color:#64748b}.receipt-records-mobile header strong{font-weight:500}.receipt-records-mobile header span{padding:1px 6px;border-radius:4px;background:#f1f5f9}.receipt-records-mobile h3{font-size:15px;font-weight:600;margin-top:12px;overflow-wrap:anywhere}.receipt-records-mobile p{font-size:12px;color:#94a3b8;margin-top:4px}.receipt-records-mobile dl{display:grid;gap:7px;margin-top:14px;font-size:12px}.receipt-records-mobile dl>div{display:grid;grid-template-columns:48px 1fr;gap:12px}.receipt-records-mobile dt{color:#94a3b8}.receipt-records-mobile dd{color:#475569;overflow-wrap:anywhere}.receipt-records-mobile footer{margin-top:12px}.receipt-records-mobile footer strong{font-size:19px;color:#0f766e;font-variant-numeric:tabular-nums}.receipt-records-mobile footer small{font-size:12px;font-weight:400;color:#64748b}.receipt-records-footer{padding:14px 16px}.receipt-records-note{padding:12px 16px}.receipt-records-state{padding:40px 16px}}
</style>
