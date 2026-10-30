<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { BellRing, CalendarClock, ClipboardList, Database, FileInput, PackageCheck, RotateCcw } from '@lucide/vue'
import MaterialsPanel from './MaterialsPanel.vue'
import ContractPlanEditor from './ContractPlanEditor.vue'
import { planningInfo, contractDemands } from './planning'
import DemandWorkspace from './DemandWorkspace.vue'
import { draftKind } from './draftPersistence'
import { showStatus } from './forms'
import { hasReceiptRisk, readyMaterials } from './presentation'
import { useMaterials } from './workspace'
import { focusFollowup } from './focusFollowup'
const props = withDefaults(defineProps<{ search?: string }>(), { search: '' })
const emit = defineEmits<{ navigate: [id: string]; search: [value: string] }>()
const ws = useMaterials()
watch(() => ws.restoreTarget, id => { if (id && draftKind(id) === 'demand') ws.boardStage = 'demand' })
const query = ref(props.search)
watch(() => props.search, value => { query.value = value })
watch(query, value => { emit('search', value) })
const state = ref('')
const customer = ref('')
const recipient = ref('')
const expanded = ref('')
const planEditor = ref<InstanceType<typeof ContractPlanEditor> | null>(null)
const planInfo = (row: typeof ws.board[number]) => planningInfo(row, ws.records)
const demandRows = computed(() => new Map(ws.board.map(row => [row.id, contractDemands(row, ws.records)])))
const detailDemands = (row: typeof ws.board[number]) => demandRows.value.get(row.id) ?? []
function openPlan(id: string) {
  const row = ws.board.find(item => item.id === id)
  if (row && planInfo(row).missingMaster) { ws.followup('master', id); return }
  return planEditor.value?.open(id)
}
watch(() => ws.restoreTarget, id => { if (id && draftKind(id) === 'planning') ws.boardStage = 'board' })
const root = ref<HTMLElement | null>(null)
function toggleDetail(id: string) { planEditor.value?.hide(); expanded.value = expanded.value === id ? '' : id }
watch([query, state, customer, recipient], () => planEditor.value?.hide(), { flush: 'sync' })
watch(() => ws.followupTarget, async target => {
  if (target?.kind !== 'board' && target?.kind !== 'plan') return
  inspect(target.orderId)
  await nextTick()
  if (ws.followupTarget === target && target.kind === 'plan') { await openPlan(target.orderId); return }
  if (ws.followupTarget === target) focusFollowup(root.value?.querySelector<HTMLElement>('.im-contract-detail'))
})
const customers = computed(() => [...new Set(ws.board.map(row => row.customer))].sort())
const risks = computed(() => ws.board.filter(hasReceiptRisk))
const missing = computed(() => ws.board.filter(row => planInfo(row).needs))
const complete = computed(() => ws.board.filter(row => row.status === 'complete').length)
const rows = computed(() => ws.board.filter(row =>
  (!state.value || (state.value === 'risk' ? hasReceiptRisk(row) : state.value === 'missing' ? planInfo(row).needs : row.status === state.value)) &&
  (!customer.value || row.customer === customer.value) && (!recipient.value || row.recipient === recipient.value) &&
  `${row.customer} ${row.contract_no} ${row.po_no} ${row.item_no} ${row.batch} ${row.recipient}`.toLowerCase().includes(query.value.toLowerCase())
).slice().sort((a, b) => a.delivery_date.localeCompare(b.delivery_date)))
function reset() { state.value = ''; customer.value = ''; recipient.value = ''; query.value = '' }
function inspect(id: string) { reset(); expanded.value = id }
const shortDate = (value?: string | null) => value ? value.replaceAll('-', '/') : '待计算'
</script>
<template>
  <div ref="root" class="im-stack">
    <div class="im-toolbar" aria-label="合同查看方式"><button type="button" :aria-pressed="ws.boardStage === 'board'" @click="ws.boardStage = 'board'">查看回料期限与缺口</button><button id="im-tab-demand" type="button" :aria-selected="ws.boardStage === 'demand'" @click="ws.boardStage = 'demand'">维护合同需求</button></div>
    <div v-show="ws.boardStage === 'board'" class="im-stack">
    <details class="im-priority-details"><summary>待办提醒 · 回料风险 {{ risks.length }} · 待补资料 {{ missing.length }}</summary><section class="im-priorities" aria-label="合同待办提醒">
      <div class="im-priority-heading"><div class="im-page-title"><span class="im-alert-icon"><BellRing :size="19" /></span><div><h2>今日待办 · 先看这里</h2><p>先处理回料风险，再补齐影响需求与倒排的基础资料</p></div></div><div class="im-inline"><span class="im-tag im-tag-red">回料风险 {{ risks.length }}</span><span class="im-tag im-tag-amber">资料待补 {{ missing.length }}</span></div></div>
      <div class="im-priority-grid"><div><h3>供应商回料风险</h3><template v-if="risks.length"><article v-for="row in risks.slice(0, 2)" :key="row.id"><div><strong>{{ row.customer }} · {{ row.contract_no }}</strong><small>{{ row.item_no }} · PO {{ row.po_no || '未填写' }} · 要求回料 {{ shortDate(row.plan?.required_date) }}</small></div><button type="button" class="im-text-button" @click="inspect(row.id)">查看合同 →</button></article></template><p v-else class="im-note">{{ ws.board.length ? '当前没有供应商回复延期的合同。' : '导入合同后，自动提示供应商回复延期风险。' }}</p></div><div><h3>基础资料与计划参数</h3><template v-if="missing.length"><article v-for="row in missing.slice(0, 2)" :key="row.id"><div><strong>{{ row.item_no }} · {{ planInfo(row).label }}</strong><small>{{ row.customer }} / {{ row.contract_no }} · PO {{ row.po_no || '未填写' }}</small></div><button type="button" class="im-text-button" :disabled="!ws.canWrite || ws.locked" @click="openPlan(row.id)">补充计划资料 →</button></article></template><p v-else class="im-note">{{ ws.board.length ? '当前合同暂无待补的基础资料或计划参数。' : '维护货号用量与日产能，供合同自动计算需求。' }}</p></div></div>
    </section></details>
    <MaterialsPanel title="合同需求台账" subtitle="按印尼成品出货日期排序；点击明细查看倒排与每项物料的缺口。">
      <template #action><button id="im-tab-import" type="button" :disabled="!ws.canWrite || ws.locked" @click="emit('navigate', 'import')"><FileInput :size="15" />统一排期导入</button><button type="button" class="im-primary" @click="emit('navigate', 'demand')">维护合同需求</button></template>
      <div class="im-filter-bar"><label class="im-field"><span>客户</span><select v-model="customer"><option value="">全部客户</option><option v-for="name in customers" :key="name">{{ name }}</option></select></label><label class="im-field"><span>接收方</span><select v-model="recipient"><option value="">全部接收方</option><option>RRI</option><option>RRM</option></select></label><label class="im-field"><span>齐料与跟进状态</span><select v-model="state"><option value="">全部状态</option><option value="risk">回料风险</option><option value="missing">待补资料</option><option value="shortage">尚未齐料</option><option value="complete">河源已齐料</option></select></label><label class="im-field im-search-field"><span>客户／合同／PO／货号</span><input v-model="query" type="search" placeholder="筛选当前厂区合同"></label><button type="button" @click="reset"><RotateCcw :size="14" />重置</button></div>
      <div v-if="!ws.board.length" class="im-onboarding"><span class="im-empty-icon"><ClipboardList :size="28" /></span><h3>从第一张合同开始跟进</h3><p>先维护物料和货号用量，再导入统一排期或新增合同需求。</p><div class="im-toolbar"><button type="button" @click="emit('navigate', 'master')"><Database :size="15" />维护基础资料</button><button type="button" class="im-primary" :disabled="!ws.canWrite || ws.locked" @click="emit('navigate', 'import')"><FileInput :size="15" />导入统一排期</button></div></div>
      <p v-else-if="!rows.length" class="im-empty">没有符合筛选条件的合同。</p>
      <div v-else class="im-scroll im-board-table"><table><thead><tr><th>客户 / 合同</th><th>货号 / 合同数量</th><th>接收方</th><th>河源最迟回料</th><th>印尼成品出货</th><th>物料齐套进度</th><th>状态</th><th>操作</th></tr></thead><tbody>
        <template v-for="row in rows" :key="row.id"><tr :class="{ 'im-selected-row': expanded === row.id }"><td><strong>{{ row.contract_no }}</strong><small>{{ row.customer }}</small><small v-if="row.po_no">PO {{ row.po_no }}</small></td><td><strong>{{ row.item_no }}</strong><small>{{ row.quantity }} {{ row.unit }}</small></td><td><span class="im-tag im-tag-neutral">{{ row.recipient }}</span></td><td>{{ shortDate(row.plan?.required_date) }}</td><td>{{ shortDate(row.delivery_date) }}</td><td><template v-if="detailDemands(row).length"><span class="im-nowrap">{{ readyMaterials(row) }} / {{ detailDemands(row).length }} 项齐料</span><div class="im-progress" role="progressbar" :aria-label="`${row.contract_no} 物料齐料进度`" :aria-valuenow="readyMaterials(row)" :aria-valuemax="detailDemands(row).length" :aria-valuemin="0"><span :style="{ width: `${readyMaterials(row) / detailDemands(row).length * 100}%` }" /></div></template><span v-else class="im-note">待生成需求</span></td><td><button v-if="planInfo(row).needs" type="button" class="im-text-button" :disabled="!ws.canWrite || ws.locked" @click="openPlan(row.id)">{{ planInfo(row).label }} →</button><span v-else class="im-tag" :class="row.status === 'complete' ? '' : hasReceiptRisk(row) ? 'im-tag-red' : 'im-tag-amber'">{{ hasReceiptRisk(row) ? '回料风险' : showStatus(row.status) }}</span></td><td><button type="button" class="im-text-button" :aria-expanded="expanded === row.id" :aria-controls="`im-detail-${row.id}`" @click="toggleDetail(row.id)">{{ expanded === row.id ? '收起 ↑' : '明细 ↓' }}</button></td></tr>
          <tr v-if="expanded === row.id"><td :id="`im-detail-${row.id}`" colspan="8" class="im-expanded"><div class="im-contract-detail"><div :id="`im-plan-slot-${row.id}`" /><div class="im-section-label"><h3>合同倒排与物料明细</h3><span v-if="row.plan" class="im-note">生产 {{ row.plan.production_days }} 个工作日 · 周一至周五</span></div><div v-if="row.plan" class="im-timeline"><div><i /><strong>{{ shortDate(row.plan.required_date) }}</strong><span>河源最迟回料</span></div><div><i /><strong>{{ shortDate(row.plan.dispatch_date) }}</strong><span>河源发出</span><small>整理 {{ row.plan.preparation_days }} 天</small></div><div><i /><strong>{{ shortDate(row.plan.start_date) }}</strong><span>到达印尼工厂 / 开工</span><small>运输 {{ row.plan.transport_days }} 个自然日</small></div><div><i /><strong>{{ shortDate(row.delivery_date) }}</strong><span>印尼成品出货</span></div></div><p v-else class="im-message">{{ showStatus(row.planning_status || 'missing_parameters') }}：补齐资料后，由业务重新生成需求。</p><div v-if="detailDemands(row).length" class="im-scroll"><table><thead><tr><th>物料</th><th>最终需求</th><th>已绑定</th><th>已入库覆盖</th><th>已发出</th><th>缺口</th><th>采购开始</th><th>供应商回复</th><th>已确认回料日期</th><th>风险</th></tr></thead><tbody><tr v-for="demand in detailDemands(row)" :key="demand.id" :data-pending-material="demand.pending || undefined"><td><strong>{{ demand.code }}</strong><small>{{ demand.name }}</small><small v-if="demand.pending" class="im-danger-text">新增，待同步</small></td><td>{{ demand.quantity }} {{ demand.unit }}</td><td>{{ demand.allocated }}</td><td>{{ demand.coverage }}</td><td>{{ demand.shipped }}</td><td>{{ demand.shortage }}</td><td><button type="button" class="im-text-button" :disabled="!ws.canWrite || ws.locked" :aria-label="`维护 ${demand.code} 的采购周期`" @click="openPlan(row.id)">{{ demand.purchase_start || (demand.procurement_days == null ? '待补采购周期' : '待补计划参数') }} →</button><small v-if="demand.procurement_days != null">备料 {{ demand.procurement_days }} 个自然日</small></td><td><button type="button" class="im-text-button" :disabled="demand.pending || !ws.canWrite || ws.locked" :aria-label="`维护 ${demand.code} 的供应商回复`" @click="ws.followup('reply', row.id, demand.material_id)">{{ demand.pending ? '待同步' : demand.promised_date || '待回复' }} →</button></td><td>{{ demand.actual_date || '未确认' }}</td><td><span :class="{ 'im-danger-text': demand.risk === 'late' }">{{ demand.pending ? '保存本合同后生效' : showStatus(demand.risk) }}</span></td></tr></tbody></table></div><p v-else class="im-note">该合同尚无有效物料需求，请核对基础资料并重新生成需求。</p><div class="im-actions"><button type="button" :disabled="!ws.canWrite || ws.locked" @click="openPlan(row.id)">填写／更新本合同计划</button></div><p class="im-table-note">计划参数在本合同内保存并更新；供应商回复不代表实际入库。</p></div></td></tr>
        </template>
      </tbody></table></div><div v-if="ws.board.length" class="im-table-footer">当前 {{ rows.length }} 条 · 共 {{ ws.board.length }} 条</div>
    </MaterialsPanel>
    </div><ContractPlanEditor ref="planEditor" @select="inspect" /><div id="im-panel-demand" v-show="ws.boardStage === 'demand'"><DemandWorkspace /></div>
  </div>
</template>
