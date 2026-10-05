<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Plus, Search, ArrowLeft, ArrowUpRight, X } from '@lucide/vue'
import { RouterLink } from 'vue-router'
import { Button } from '@/components/ui/button'
import { useSprayPage } from '../usePage'
import { SPRAY_BASE, FACTORY_NAMES, SPRAY_FACTORIES, documentNo, number, type Demand, type RouteVersion } from '../contracts'
import WorkspaceDialog from '../components/WorkspaceDialog.vue'
import WorkspaceState from '../components/WorkspaceState.vue'
const w = useSprayPage(['demands', 'routes'])
const orders = computed(() => w.items<Demand>('demands')), routes = computed(() => w.items<RouteVersion>('routes'))
const search = ref(''), page = ref(1), open = ref(false), saving = ref(false), error = ref('')
const header = reactive({ document_no: documentNo('SP'), counterparty: '', source_factory: '', source_ref: '', note: '' })
function newLine() { return { item_no: '', part: '', color: '', quantity: '', unit: '件', due_date: '', expected_arrival: '', route_id: '', priority: 0, split_allowed: true, commercial_price: '', currency: 'CNY', price_evidence: '' } }
const lines = ref([newLine()])
watch(header, () => { if (open.value) w.dirty.value = true })
watch(lines, () => { if (open.value) w.dirty.value = true }, { deep: true })
const amendOpen=ref(false),amending=ref<Demand|null>(null),change=reactive({line_id:'',quantity:'',due_date:'',priority:0,route_id:'',reason:''})
function editLine(order:Demand,line:Demand['lines'][number]){amending.value=order;Object.assign(change,{line_id:line.id,quantity:line.quantity,due_date:line.due_date,priority:line.priority,route_id:line.route_id??'',reason:''});amendOpen.value=true}
async function amend(){if(!amending.value)return;try{await w.command(`demands/${amending.value.id}/amend`,{...change,route_id:change.route_id||null,business_date:w.businessDate.value},amending.value.version);amendOpen.value=false;await w.load(['demands'])}catch(cause){error.value=w.explain(cause)}}
async function confirmOrder(order:Demand){try{await w.command(`demands/${order.id}/confirm`,{},order.version);await w.load(['demands'])}catch(cause){error.value=w.explain(cause)}}
function startNew() { header.document_no = documentNo('SP'); header.counterparty = ''; header.source_ref = ''; header.note = ''; lines.value = [newLine()]; open.value = true; error.value = '' }
async function close() { if (w.dirty.value && !(await w.confirmDiscard('放弃当前订单填写？'))) return; open.value = false; w.dirty.value = false }
async function save(confirm = true) {
  saving.value = true; error.value = ''
  try {
    const result = await w.command<Demand>('demands', { ...header, source_factory: header.source_factory || null, business_date: w.businessDate.value, confirm, lines: lines.value.map(line => ({ ...line, expected_arrival: line.expected_arrival || null, route_id: line.route_id || null, commercial_price: w.can('cost_write') && line.commercial_price !== '' ? line.commercial_price : null })) })
    open.value = false
    await w.load(['demands'])
    w.passportId.value = result.id
    return true
  } catch (cause) { error.value = w.explain(cause); return false } finally { saving.value = false }
}
watch(open, value => { w.saveDraft.value = value ? () => save(false) : null })
async function filter() { page.value = 1; await w.load(['demands'], { search: search.value, page: page.value, page_size: 50 }) }
async function next(delta: number) { page.value += delta; await w.load(['demands'], { search: search.value, page: page.value, page_size: 50 }) }
</script>
<template>
  <div class="spray-page">
    <header class="spray-page-heading"><div><RouterLink class="spray-back" :to="{ path: `${SPRAY_BASE}/planning`, query: { factory: w.factory.value } }"><ArrowLeft :size="14" />返回计划调度</RouterLink><h1>需求池</h1><p>每张订单保留独立身份，按部件接收来料、安排工序与交收。</p></div><Button v-if="w.can('plan')" @click="startNew"><Plus :size="16" />登记需求</Button></header>
    <WorkspaceState />
    <div class="spray-panel"><div class="spray-panel__header"><h3>待执行订单 <span class="spray-muted">{{ w.totals.demands ?? 0 }}</span></h3><form class="spray-search" @submit.prevent="filter"><Search :size="15" /><input v-model="search" aria-label="筛选订单" placeholder="按单号筛选" /></form></div>
      <div class="spray-table-wrap"><table class="spray-table"><thead><tr><th>订单 / 委托方</th><th>货号与部位</th><th>颜色</th><th class="numeric">需求量</th><th class="numeric">已收白件</th><th>交期</th><th>工艺</th><th>优先级</th><th>处理</th></tr></thead><tbody><template v-for="order in orders" :key="order.id"><tr v-for="line in order.lines" :key="line.id" @click="w.passportId.value = order.id"><td><button class="spray-text-button" @click.stop="w.passportId.value = order.id">{{ order.document_no }}</button><small>{{ order.counterparty }}</small></td><td><strong>{{ line.item_no }}</strong><small>{{ line.part }}</small></td><td>{{ line.color }}</td><td class="numeric">{{ number(line.quantity) }} {{ line.unit }}</td><td class="numeric">{{ number(line.received) }}</td><td>{{ line.due_date }}</td><td><span class="spray-badge" :class="{ 'spray-badge--amber': !line.route_id }">{{ line.route_id ? routes.find(r=>r.id === line.route_id)?.label ?? '已关联' : '待确认' }}</span></td><td><span :class="line.priority > 0 ? 'spray-badge spray-badge--amber' : 'spray-muted'">{{ line.priority > 0 ? `优先 ${line.priority}` : '常规' }}</span></td><td><button v-if="w.can('plan')" class="spray-text-button" @click.stop="editLine(order,line)">变更</button><button v-if="order.status==='draft'&&w.can('plan')" class="spray-text-button" @click.stop="confirmOrder(order)"> · 确认草稿</button></td></tr></template></tbody></table></div>
      <div v-if="!orders.length" class="spray-empty"><strong>从一张真实订单开始</strong><p>先登记需求与部件，来料可以分批接收，不必等全部齐料。</p><Button v-if="w.can('plan')" variant="outline" @click="startNew">登记第一张订单</Button></div>
      <div v-if="(w.totals.demands ?? 0) > 50" class="spray-pagination"><button class="spray-secondary" :disabled="page === 1" @click="next(-1)">上一页</button><span>第 {{ page }} 页 · 共 {{ w.totals.demands }} 张</span><button class="spray-secondary" :disabled="page * 50 >= (w.totals.demands ?? 0)" @click="next(1)">下一页</button></div>
    </div>
    <WorkspaceDialog :open="amendOpen" title="订单变更" @close="amendOpen=false"><form class="spray-form" @submit.prevent="amend" @input="w.dirty.value=true"><label>需求数量<input v-model="change.quantity" required /></label><label>承诺交期<input v-model="change.due_date" type="date" required /></label><label>优先级<input v-model.number="change.priority" type="number" min="0" max="100" /></label><label>工艺版本<select v-model="change.route_id"><option value="">保持未关联</option><option v-for="r in routes" :key="r.id" :value="r.id">{{r.label}} V{{r.revision}}</option></select></label><label class="wide">变更依据<textarea v-model="change.reason" required /></label><p v-if="error" class="spray-alert wide">{{error}}</p><Button type="submit">确认变更</Button></form></WorkspaceDialog>
    <WorkspaceDialog :open="open" title="登记生产需求" wide @close="close"><form id="spray-demand-form" class="spray-form" @submit.prevent="save(true)"><label>订单编号<input v-model="header.document_no" required /></label><label>委托方<input v-model="header.counterparty" required placeholder="独立于执行工厂" /></label><label>来源工厂<select v-model="header.source_factory"><option value="">外部 / 未指定</option><option v-for="factory in SPRAY_FACTORIES" :key="factory" :value="factory">{{ FACTORY_NAMES[factory] }}</option></select></label><label>原单 / 来源引用<input v-model="header.source_ref" placeholder="原订单号、文件或业务联系依据" /></label>
      <div class="wide spray-step-editor"><section v-for="(line,index) in lines" :key="index"><header><strong>部件 {{ index + 1 }}</strong><button v-if="lines.length > 1" type="button" class="spray-icon-button" aria-label="删除部件" @click="lines.splice(index,1)"><X :size="15" /></button></header><div class="spray-form"><label>货号<input v-model="line.item_no" required placeholder="保留前导零" /></label><label>部位<input v-model="line.part" required /></label><label>颜色与版本<input v-model="line.color" required /></label><label>需求数量<input v-model="line.quantity" required inputmode="numeric" /></label><label>单位<input v-model="line.unit" required /></label><label>承诺交期<input v-model="line.due_date" type="date" required /></label><label>预计来料日期<input v-model="line.expected_arrival" type="date" /></label><label>工艺版本<select v-model="line.route_id"><option value="">待确认</option><option v-for="r in routes" :key="r.id" :value="r.id">{{ r.label }} · V{{ r.revision }} · {{ r.status === 'confirmed' ? '已确认' : '草稿' }}</option></select></label><label>优先级（0 为常规）<input v-model.number="line.priority" type="number" min="0" max="100" /></label><label class="check"><input v-model="line.split_allowed" type="checkbox" />允许分批生产</label><template v-if="w.can('cost_write')"><label>交收单价<input v-model="line.commercial_price" inputmode="decimal" placeholder="未确认时留空" /></label><label>币种<select v-model="line.currency"><option>CNY</option><option>HKD</option><option>USD</option></select></label><label class="wide">定价依据<input v-model="line.price_evidence" :required="line.commercial_price !== ''" /></label></template></div></section><button class="spray-secondary" type="button" @click="lines.push(newLine())"><Plus :size="15" />增加部件</button></div>
      <label class="wide">备注<textarea v-model="header.note" /></label><p v-if="error" class="spray-alert wide" role="alert">{{ error }}</p></form><template #footer><Button variant="outline" @click="close">取消</Button><Button variant="outline" :disabled="saving" @click="save(false)">保存草稿</Button><Button type="submit" form="spray-demand-form" :disabled="saving">确认需求</Button></template></WorkspaceDialog>
  </div>
</template>
