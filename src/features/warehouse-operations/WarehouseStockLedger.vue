<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { FocusScope } from 'reka-ui'
import { Search, ArrowUpRight, MoveHorizontal, Package } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type { WarehouseBatch, WarehouseDomain } from '@/api/warehouseOperations'
import { sumQuantities } from './operations'

const props = defineProps<{ rows: WarehouseBatch[]; warehouse: WarehouseDomain; canOperate: boolean; canBind?: boolean; loading: boolean; title?: string }>()
const emit = defineEmits<{ action: [kind: 'ISSUE' | 'TRANSFER' | 'LOCATION_BIND', batchId: string]; refresh: []; bulk: [ids: string[]] }>()
const search = ref(''), location = ref(''), onlyStock = ref(true), page = ref(0), selected = ref<WarehouseBatch>()
const keyFor = (row: WarehouseBatch) => row.location_id || `unverified:${row.location}`
const locations = computed(() => [...new Map(props.rows.map(row => [keyFor(row), { id: keyFor(row), label: row.location_label || row.location }])).values()])
const checked = ref<string[]>([])
const masterPath = computed(() => `/modules/pmc-warehouse/${props.warehouse === 'fabric' ? 'fabric-warehouse' : 'semi-finished-warehouse'}/master?factory=huakang-c&view=locations`)
const inStock = computed(() => props.rows.filter(row => Number(row.quantity) > 0))
const materialCount = computed(() => new Set(inStock.value.map(row => JSON.stringify([row.item_code, row.unit, row.process_state]))).size)
const totals = computed(() => [...new Set(inStock.value.map(row => row.unit))].map(unit => ({ unit, quantity: sumQuantities(inStock.value.filter(row => row.unit === unit).map(row => row.quantity)) })))
const filtered = computed(() => props.rows.filter(row => (!onlyStock.value || Number(row.quantity) > 0)
  && (!location.value || location.value === keyFor(row))
  && [row.item_name, row.item_code, row.lot, row.roll_no, row.source_no, row.counterparty, row.production_no, row.id, row.process_state]
    .join(' ').toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase())))
const visible = computed(() => filtered.value.slice(page.value * 30, page.value * 30 + 30))
const pages = computed(() => Math.max(1, Math.ceil(filtered.value.length / 30)))
watch([search, location, onlyStock], () => { page.value = 0 })
watch(() => props.rows, () => { page.value = Math.min(page.value, pages.value - 1); selected.value = undefined; checked.value = checked.value.filter(id => props.rows.some(row => row.id === id && canIssue(row))) })
const restricted = (row: WarehouseBatch) => row.quality_status === 'HOLD' || row.quality_status === 'REJECTED'
const canIssue = (row: WarehouseBatch) => props.canOperate && row.location_verified && Number(row.quantity) > 0 && !restricted(row) && !props.loading
const canTransfer = (row: WarehouseBatch) => props.canOperate && row.location_verified && Number(row.quantity) > 0 && !props.loading
const selectable = computed(() => visible.value.filter(canIssue))
function selectVisible(event: Event) { const ids = selectable.value.map(row => row.id); checked.value = (event.target as HTMLInputElement).checked ? [...new Set([...checked.value, ...ids])] : checked.value.filter(id => !ids.includes(id)) }
function start(kind: 'ISSUE' | 'TRANSFER' | 'LOCATION_BIND', row: WarehouseBatch) {
  if (!(kind === 'LOCATION_BIND' ? props.canBind && !row.location_verified && Number(row.quantity) > 0 : kind === 'ISSUE' ? canIssue(row) : canTransfer(row))) return
  selected.value = undefined
  emit('action', kind, row.id)
}
const receiptsPath = computed(() => `/modules/pmc-warehouse/${props.warehouse === 'fabric' ? 'fabric-warehouse' : 'semi-finished-warehouse'}/receipts?factory=huakang-c&view=history`)
</script>

<template>
  <div class="stock-ledger">
    <header class="stock-heading">
      <div><h2>{{ title || '库存台账' }}</h2><p>查看已入库的{{ warehouse === 'fabric' ? '物料' : '半成品' }}，选择一行直接出库或调仓。</p></div>
      <div class="stock-heading-actions"><RouterLink :to="masterPath">仓位维护</RouterLink><RouterLink :to="receiptsPath">查看入库记录 <ArrowUpRight :size="14" /></RouterLink><Button variant="outline" :disabled="loading" @click="emit('refresh')">刷新</Button></div>
    </header>
    <div class="stock-totals" aria-label="当前库存概况">
      <div><span>在库{{ warehouse === 'fabric' ? '物料' : '产品状态' }}</span><strong>{{ materialCount }}<small>种</small></strong></div>
      <div><span>在库批次</span><strong>{{ inStock.length }}<small>批</small></strong></div>
      <div class="stock-total-quantity"><span>库存合计 · 按原单位</span><strong v-if="!totals.length">—</strong><strong v-for="total in totals" :key="total.unit">{{ total.quantity }}<small>{{ total.unit }}</small></strong></div>
    </div>
    <div class="stock-filters">
      <label class="stock-search"><span>查找物料</span><div><Search :size="16" /><input v-model="search" type="search" aria-label="查找库存物料" placeholder="物料名称、编码、缸号或送货单号" /></div></label>
      <label><span>仓位</span><select v-model="location" aria-label="库存仓位"><option value="">全部仓位</option><option v-for="value in locations" :key="value.id" :value="value.id">{{ value.label }}</option></select></label>
      <label class="stock-checkbox"><input v-model="onlyStock" type="checkbox" />只看有库存</label>
      <Button v-if="search || location || !onlyStock" variant="ghost" @click="search = ''; location = ''; onlyStock = true">清空筛选</Button>
    </div>
    <div v-if="rows.some(row => !row.location_verified && Number(row.quantity) > 0)" class="stock-location-notice">部分旧记录的仓位尚未核实，数量保留；请先建立仓位，再由有更正权限的人员点击“核实仓位”。</div>
    <div class="stock-selection"><span>已选 <b>{{ checked.length }}</b> 项库存</span><Button size="sm" :disabled="!checked.length || loading" @click="emit('bulk', checked)">登记所选库存出库</Button><Button size="sm" variant="ghost" :disabled="!checked.length" @click="checked = []">清空选择</Button></div>
    <div class="stock-table-wrap">
      <table class="stock-table" aria-label="库存物料与仓位">
        <thead><tr><th class="stock-check"><input type="checkbox" aria-label="选择当前页可出库库存" :checked="!!selectable.length && selectable.every(row => checked.includes(row.id))" :disabled="!selectable.length" @change="selectVisible" /></th><th>物料名称 / 编码</th><th v-if="warehouse === 'semi'">加工状态</th><th class="stock-number">当前库存</th><th>仓位</th><th>缸号 / 卷号</th><th>入账日期 / 送货依据</th><th class="stock-action-column">操作</th></tr></thead>
        <tbody><tr v-for="row in visible" :key="row.id">
          <td class="stock-check"><input v-model="checked" type="checkbox" :value="row.id" :disabled="!canIssue(row)" :aria-label="`选择库存 ${row.id}`" /></td>
          <td data-label="物料" class="stock-material"><strong>{{ row.item_name }}</strong><small>{{ row.item_code }}</small></td>
          <td v-if="warehouse === 'semi'" data-label="加工状态">{{ row.process_state || '—' }}</td>
          <td data-label="当前库存" class="stock-number"><strong>{{ row.quantity }}</strong><span class="stock-unit">{{ row.unit }}</span><small>累计入 {{ row.inbound_quantity ?? '—' }} · 出 {{ row.outbound_quantity ?? '—' }}</small><small v-if="row.transfer_quantity && Number(row.transfer_quantity)">调仓净额 {{ row.transfer_quantity }}</small><small v-if="restricted(row)" class="stock-restriction">{{ row.quality_status === 'HOLD' ? '暂停出库' : '不合格，暂不可出库' }}</small></td>
          <td data-label="仓位"><span class="stock-bin">{{ row.location_label || row.location || '未填仓位' }}</span><small v-if="!row.location_verified" class="stock-restriction">仓位待核实</small><small v-else-if="row.location_status !== 'ACTIVE'">仓位已停用 · 可出不可入</small></td>
          <td data-label="缸号 / 卷号"><span>{{ row.lot || '—' }}</span><small v-if="row.roll_no">卷号 {{ row.roll_no }}</small></td>
          <td data-label="入账日期 / 送货依据"><span>{{ row.received_on }}</span><small>{{ row.source_no || '系统收发单，见详情' }}</small></td>
          <td class="stock-actions"><Button v-if="!row.location_verified && Number(row.quantity) > 0" size="sm" :disabled="!canBind || loading" @click="start('LOCATION_BIND', row)">核实仓位</Button><template v-else><Button size="sm" :disabled="!canIssue(row)" :title="restricted(row) ? '已有暂停或不合格记录，请交 QC 处理' : ''" @click="start('ISSUE', row)">出库</Button><Button size="sm" variant="outline" :disabled="!canTransfer(row)" @click="start('TRANSFER', row)">调仓</Button></template><Button size="sm" variant="ghost" @click="selected = row">详情</Button></td>
        </tr></tbody>
      </table>
    </div>
    <div v-if="!filtered.length" class="stock-empty" role="status"><Package :size="28" /><strong>{{ rows.length ? '没有符合筛选条件的库存' : '还没有实际入库记录' }}</strong><p>{{ rows.length ? '清空筛选或取消“只看有库存”后重试。' : '实际收料保存后，物料和仓位会显示在这里。' }}</p></div>
    <footer class="stock-footer"><span>共 {{ filtered.length }} 个批次<span v-if="search || location"> · 筛选结果</span></span><div><Button size="sm" variant="outline" :disabled="page === 0" @click="page--">上一页</Button><span>{{ page + 1 }} / {{ pages }}</span><Button size="sm" variant="outline" :disabled="page + 1 >= pages" @click="page++">下一页</Button></div></footer>
    <p class="stock-footnote">数量来自系统已登记的实际收发；尚未登记的历史期初不计入。质检由 QC 模块负责。</p>
    <Teleport to="body"><div v-if="selected" class="stock-detail-overlay"><FocusScope as-child loop trapped><section class="stock-detail" role="dialog" aria-modal="true" aria-label="库存批次详情" @keydown.esc.prevent="selected = undefined">
      <header><div><h2>{{ selected.item_name }}</h2><p>{{ selected.item_code }}</p></div><Button variant="outline" @click="selected = undefined">关闭详情</Button></header>
      <dl><div><dt>当前库存</dt><dd>{{ selected.quantity }} {{ selected.unit }}</dd></div><div><dt>仓位</dt><dd>{{ selected.location_label || selected.location }}</dd></div><div><dt>缸号 / 批号</dt><dd>{{ selected.lot || '—' }}</dd></div><div><dt>卷号</dt><dd>{{ selected.roll_no || '—' }}</dd></div><div v-if="warehouse === 'semi'"><dt>加工状态</dt><dd>{{ selected.process_state }}</dd></div><div><dt>入账日期</dt><dd>{{ selected.received_on }}</dd></div><div><dt>来源单位</dt><dd>{{ selected.counterparty || '—' }}</dd></div><div><dt>送货依据</dt><dd>{{ selected.source_no || '未另填凭证' }}</dd></div><div><dt>生产 / 放产单</dt><dd>{{ selected.production_no || '—' }}</dd></div><div class="full"><dt>完整批次编号</dt><dd>{{ selected.id }}</dd></div><div class="full"><dt>来源记录编号</dt><dd>{{ selected.source_document }}</dd></div></dl>
      <footer><Button variant="outline" :disabled="!canTransfer(selected)" @click="start('TRANSFER', selected)"><MoveHorizontal :size="16" />调仓</Button><Button :disabled="!canIssue(selected)" @click="start('ISSUE', selected)">办理出库</Button></footer>
    </section></FocusScope></div></Teleport>
  </div>
</template>

<style scoped>
.stock-selection{display:flex;align-items:center;gap:12px;padding:0 24px 16px;font-size:12px;color:var(--muted-foreground)}.stock-location-notice{margin:0 24px 16px;padding:12px 14px;border:1px solid #fcd34d;border-radius:8px;background:#fffbeb;color:#92400e;font-size:13px}.stock-check{width:38px}.stock-check input{accent-color:var(--primary)}
.stock-ledger{color:var(--foreground);font-size:13px}.stock-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:22px 24px 18px}.stock-heading h2{font-size:18px;font-weight:650}.stock-heading p{color:var(--muted-foreground);margin-top:5px}.stock-heading-actions{display:flex;align-items:center;gap:18px}.stock-heading-actions a{display:flex;align-items:center;gap:4px;color:var(--primary);white-space:nowrap}.stock-totals{display:flex;gap:0;margin:0 24px 20px;padding:16px 0;background:var(--muted);border-radius:8px}.stock-totals>div{padding:0 24px;border-right:1px solid var(--border);min-width:140px}.stock-totals>div:last-child{border:0}.stock-totals span{display:block;color:var(--muted-foreground);font-size:12px;margin-bottom:3px}.stock-totals strong{display:inline-block;font-size:25px;font-weight:650;line-height:1.3;color:var(--primary);margin-right:16px;font-variant-numeric:tabular-nums}.stock-totals small{font-size:12px;font-weight:400;color:var(--muted-foreground);margin-left:6px}.stock-filters{display:flex;align-items:end;flex-wrap:wrap;gap:14px;padding:0 24px 20px}.stock-filters label>span{display:block;margin-bottom:6px;color:var(--muted-foreground);font-size:12px}.stock-search{flex:1;min-width:200px;max-width:540px}.stock-search>div{display:flex;align-items:center;border:1px solid var(--border);border-radius:7px;padding:0 10px;background:var(--card);gap:8px}.stock-search svg{color:var(--muted-foreground);flex-shrink:0}.stock-search input{border:0;outline:none;width:100%;padding:10px 0;background:transparent;font:inherit}.stock-search>div:focus-within{outline:2px solid var(--ring)}.stock-filters select{min-width:145px;background:var(--card);border:1px solid var(--border);border-radius:7px;padding:10px;font:inherit}.stock-checkbox{display:flex;align-items:center;gap:7px;min-height:40px;color:var(--muted-foreground)}.stock-checkbox input{accent-color:var(--primary)}.stock-table-wrap{overflow:auto}.stock-table{width:100%;border-collapse:collapse;text-align:left}.stock-table th{background:var(--muted);font-size:12px;font-weight:500;color:var(--muted-foreground);padding:12px 16px;white-space:nowrap}.stock-table td{padding:18px 16px;border-bottom:1px solid var(--border);vertical-align:middle}.stock-table th:first-child,.stock-table td:first-child{padding-left:24px}.stock-table tr:hover{background:color-mix(in srgb,var(--muted) 45%,transparent)}.stock-material{min-width:170px;max-width:320px}.stock-material strong{display:block;font-size:14px;font-weight:600;overflow-wrap:anywhere}.stock-table small{display:block;color:var(--muted-foreground);font-size:12px;margin-top:5px;overflow-wrap:anywhere}.stock-number{white-space:nowrap;text-align:right}.stock-number strong{font-size:20px;font-weight:650;font-variant-numeric:tabular-nums}.stock-unit{font-size:12px;margin-left:5px;color:var(--muted-foreground)}.stock-bin{background:var(--muted);padding:4px 9px;border-radius:4px;white-space:nowrap}.stock-table .stock-restriction{color:#b45309}.stock-action-column{width:200px}.stock-actions{white-space:nowrap}.stock-actions button+button{margin-left:6px}.stock-footer{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:16px 24px;color:var(--muted-foreground);font-size:12px}.stock-footer>div{display:flex;align-items:center;gap:12px}.stock-footnote{padding:0 24px 18px;font-size:12px;color:var(--muted-foreground)}.stock-empty{display:grid;justify-items:center;gap:8px;padding:36px;color:var(--muted-foreground)}.stock-detail-overlay{position:fixed;inset:0;z-index:90;background:#0f172a80;display:grid;place-items:center;padding:20px}.stock-detail{width:min(680px,100%);max-height:92dvh;overflow:auto;background:var(--card);border-radius:12px;color:var(--foreground)}.stock-detail header,.stock-detail footer{display:flex;align-items:center;justify-content:space-between;padding:20px 24px;gap:16px;border-bottom:1px solid var(--border)}.stock-detail header h2{font-size:18px;font-weight:650}.stock-detail header p,.stock-detail dt{font-size:12px;color:var(--muted-foreground)}.stock-detail dl{display:grid;grid-template-columns:1fr 1fr;gap:20px;padding:24px}.stock-detail dd{margin-top:4px;overflow-wrap:anywhere}.stock-detail .full{grid-column:1/-1}.stock-detail footer{justify-content:flex-end;border-top:1px solid var(--border);border-bottom:0}
@media(max-width:760px){.stock-heading{align-items:start;padding:18px;flex-wrap:wrap}.stock-heading-actions{width:100%;justify-content:space-between}.stock-totals{margin:0 16px 18px;flex-wrap:wrap;gap:12px}.stock-totals>div{min-width:0;padding:0 16px}.stock-totals strong{font-size:22px}.stock-filters{padding:0 16px 16px}.stock-search{flex-basis:100%;max-width:none}.stock-table,.stock-table tbody{display:block}.stock-table thead{display:none}.stock-table tr{display:grid;grid-template-columns:1fr 1fr;margin:0 16px 14px;border:1px solid var(--border);border-radius:8px;padding:14px;gap:12px}.stock-table td,.stock-table td:first-child{display:block;padding:0;border:0;text-align:left;min-width:0}.stock-table td::before{content:attr(data-label);display:block;font-size:11px;color:var(--muted-foreground);margin-bottom:3px}.stock-table .stock-material{grid-column:1/-1;max-width:none}.stock-check::before,.stock-material::before,.stock-actions::before{display:none!important}.stock-table .stock-actions{grid-column:1/-1;display:flex;border-top:1px solid var(--border);padding-top:12px}.stock-actions button{flex:1}.stock-footer{padding:12px 16px;flex-wrap:wrap}.stock-footnote{padding:0 16px 16px}.stock-detail dl{padding:18px;gap:16px}.stock-detail header,.stock-detail footer{padding:18px}}
</style>
