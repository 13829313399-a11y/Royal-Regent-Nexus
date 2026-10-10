<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { cuttingApi, errorMessage, type Access, type BomData, type MasterRecord, type Command } from './api'
import { ordersApi, type CuttingOrder, type OrderAction, type OrderCommand, type OrderRevision, type EtaBatch, type DemandInput } from './ordersApi'
import { CUTTING_FACTORY, type CuttingWorkspace } from './navigation'
import CuttingWorkspacePage from './CuttingWorkspacePage.vue'
import CuttingPlanEditor from './CuttingPlanEditor.vue'
import CuttingPlanSummary from './CuttingPlanSummary.vue'
import CuttingPlanDiff from './CuttingPlanDiff.vue'
import { taskInput, type PlanTaskInput } from './planning'

defineProps<{ workspace: CuttingWorkspace }>()
const access = ref<Access | null>(null), loading = ref(true), saving = ref(false), needsLogin = ref(false)
const error = ref(''), notice = ref(''), query = ref(''), page = ref(1), total = ref(0)
const statusFilter = ref('')
const planStatusFilter = ref('')
const planStatusLabels: Record<string,string> = { unplanned:'未排',partial:'部分排期',published:'已发布',pending_actual:'待实际核定',review:'待复核' }
const rows = ref<CuttingOrder[]>([]), selected = ref<CuttingOrder | null>(null)
const action = ref<OrderAction | null>(null), reason = ref(''), targetSets = ref(1), quantityBasis = ref('')
const bomMatchBasis = ref('')
const chosenBom = ref<MasterRecord | null>(null), bomQuery = ref(''), bomRows = ref<MasterRecord[]>([])
const bomPage = ref(1), bomTotal = ref(0), versionPage = ref(1), versionTotal = ref(0), versionId = ref(''), versions = ref<MasterRecord[]>([])
const demands = ref<DemandInput[]>([]), batches = ref<EtaBatch[]>([])
const disposition = ref<'not_ordered' | 'cancelled_or_reallocated'>('not_ordered'), evidence = ref(''), allHandled = ref(false)
const history = ref<OrderRevision[]>([]), historyPage = ref(1), historyTotal = ref(0)
const pending = ref<{ id: string; action: OrderAction; body: OrderCommand } | null>(null), uncertain = ref(false)
const planTasks = ref<PlanTaskInput[]>([])
const removedTaskReasons = ref<Record<string,string>>({})
const baseline = ref('')
const snapshot = () => JSON.stringify([reason.value, targetSets.value, quantityBasis.value, bomMatchBasis.value, chosenBom.value, demands.value, batches.value, disposition.value, evidence.value, allHandled.value, planTasks.value,removedTaskReasons.value])
const dirty = computed(() => !!action.value && snapshot() !== baseline.value)
const available = computed(() => access.value?.enabled && access.value?.orders_schema_ready)
const data = computed(() => selected.value?.current?.data)
const adjustingPlan = computed(() => (action.value === 'plan' || action.value === 'plan-publish') && !!data.value?.planning?.published)
const requirements = computed(() => (data.value?.bom?.data as BomData | undefined)?.requirements ?? [])
const writable = computed(() => selected.value && !selected.value.needs_receipt && selected.value.snapshot.status === 'active')
const can = (permission: string) => access.value?.permissions.includes(permission) ?? false
const labels: Record<OrderAction, string> = { receive: '签收订单版本', bom: '工程关联 BOM', requisition: '工程提交物料需求', eta: '采购回复分批交期', withdraw: '工程申请撤回／修订', reconcile: '采购核对旧需求', plan: '编制任务与日计划', 'plan-publish': '发布生产预排' }
const statusLabels: Record<string, string> = { awaiting_receipt: '待签收新版本', cancelled_receipt: '取消待签收', cancelled: '已取消', reconciliation: '旧需求待采购核对', awaiting_bom: '待关联 BOM', awaiting_submission: '待工程提交需求', awaiting_reply: '待采购回复', partial_reply: '采购部分回复', complete_reply: '采购全部回复', no_purchase: '本次无需采购' }
let alive = true, generation = 0, searchGeneration = 0, historyGeneration = 0
function discard() {
  if (saving.value || pending.value) { error.value = '保存结果尚未确认，请先重试原操作。'; return false }
  return !dirty.value || window.confirm('有尚未保存的内容，离开将放弃这些内容。确定继续？')
}
onBeforeRouteLeave(discard)
function beforeUnload(e: BeforeUnloadEvent) { if (dirty.value || pending.value || saving.value) { e.preventDefault(); e.returnValue = '' } }
onMounted(() => { window.addEventListener('beforeunload', beforeUnload); void load() })
onBeforeUnmount(() => { alive = false; generation++; searchGeneration++; historyGeneration++; window.removeEventListener('beforeunload', beforeUnload) })
watch(bomQuery, () => { searchGeneration++; bomRows.value = []; versions.value = []; versionId.value = '' }, { flush: 'sync' })

async function load(nextPage = page.value) {
  if (!discard()) return
  const request = ++generation
  selected.value = null; action.value = null; history.value = []; rows.value = []; historyGeneration++; searchGeneration++
  loading.value = true; error.value = ''
  try {
    const rights = await cuttingApi.access()
    if (!alive || request !== generation) return
    access.value = rights
    if (!available.value) return
    const result = await ordersApi.list(nextPage, query.value, statusFilter.value, planStatusFilter.value)
    if (!alive || request !== generation) return
    rows.value = result.data; total.value = result.total; page.value = nextPage
  } catch (e) { if (alive && request === generation) { error.value = errorMessage(e); access.value = null } }
  finally { if (alive && request === generation) loading.value = false }
}
function select(row: CuttingOrder) {
  if (!discard()) return
  selected.value = row; action.value = null; history.value = []; historyTotal.value = 0; historyGeneration++; searchGeneration++
  notice.value = ''; error.value = ''
}
function edit(next: OrderAction) {
  if (!discard()) return
  searchGeneration++; action.value = next; reason.value = ''; chosenBom.value = null; bomQuery.value = ''; bomRows.value = []; versions.value = []
  removedTaskReasons.value = {}
  if (next === 'plan-publish' && data.value?.planning?.published) reason.value = data.value.planning.draft?.adjustment_reason ?? ''
  targetSets.value = data.value?.target_sets ?? 1; quantityBasis.value = data.value?.quantity_basis ?? ''
  bomMatchBasis.value = data.value?.bom_match_basis ?? ''
  demands.value = requirements.value.map((_, row) => ({ row, quantity: '', purchase_mode: 'purchase', no_purchase_reason: '' }))
  disposition.value = 'not_ordered'; evidence.value = ''; allHandled.value = false
  batches.value = structuredClone(data.value?.batches ? JSON.parse(JSON.stringify(data.value.batches)) : [])
  planTasks.value = (data.value?.planning?.draft ?? data.value?.planning?.published)?.tasks.map(taskInput) ?? []
  if (next === 'plan' && (data.value?.planning?.draft ? selected.value?.planning_summary?.draft_stale : selected.value?.planning_summary?.published_stale)) {
    // Revalidate estimates against the latest BOM; never carry an old row-index mapping into a new BOM silently.
    for (const task of planTasks.value) {
      task.materials = requirements.value.flatMap((r, row) => r.required_for_cutting ? [{ row, expected_date: null }] : [])
      task.date_basis = 'estimated'; task.actual_prerequisite_date = null; task.actual_prerequisite_reference = ''; task.actual_issue_date = null; task.actual_issue_reference = ''; task.readiness_basis = ''; task.prerequisite_date = null; task.prerequisite_basis = ''
    }
    notice.value = '旧计划依据已变更：保留任务和日计划，预计物料、实际领料及前置条件须重新核对填写。'
  }
  baseline.value = snapshot()
}
function cancel() { if (discard()) { action.value = null; searchGeneration++ } }
async function searchBoms(nextPage = 1) {
  const request = ++searchGeneration
  bomRows.value = []; versions.value = []; versionId.value = ''
  try {
    const result = await cuttingApi.list('bom', nextPage, bomQuery.value)
    if (!alive || request !== searchGeneration || action.value !== 'bom') return
    bomRows.value = result.data; bomPage.value = nextPage; bomTotal.value = result.total
  } catch (e) { if (alive && request === searchGeneration) error.value = errorMessage(e) }
}
async function loadVersions(id: string, nextPage = 1) {
  const request = ++searchGeneration
  versions.value = []
  try {
    const result = await cuttingApi.versions(id, nextPage)
    if (!alive || request !== searchGeneration || action.value !== 'bom') return
    versions.value = result.data.filter(r => r.status === 'published'); versionId.value = id
    versionPage.value = nextPage; versionTotal.value = result.total
  } catch (e) { if (alive && request === searchGeneration) error.value = errorMessage(e) }
}
async function loadHistory(nextPage = 1) {
  if (!selected.value) return
  const id = selected.value.line_id, request = ++historyGeneration
  try {
    const result = await ordersApi.history(id, nextPage)
    if (!alive || request !== historyGeneration || selected.value?.line_id !== id) return
    history.value = result.data; historyPage.value = nextPage; historyTotal.value = result.total
  } catch (e) { if (alive && request === historyGeneration) error.value = errorMessage(e) }
}
function makeCommand(): OrderCommand | null {
  const common: Command = { factory_id: CUTTING_FACTORY, operation_id: crypto.randomUUID(), expected_version: selected.value?.current?.version ?? 0, reason: reason.value }
  if (action.value === 'plan') return { ...common, tasks: JSON.parse(JSON.stringify(planTasks.value)), removed_task_reasons: {...removedTaskReasons.value} }
  if (action.value === 'plan-publish' && data.value?.planning?.draft) return { ...common, draft_version: data.value.planning.draft.version }
  if (action.value === 'receive') return { ...common, dispatch_id: selected.value!.dispatch_id }
  if (action.value === 'bom' && chosenBom.value) return { ...common, bom_id: chosenBom.value.id, bom_version: chosenBom.value.version, target_sets: Number(targetSets.value), quantity_basis: quantityBasis.value, bom_match_basis: bomMatchBasis.value }
  if (action.value === 'requisition') return { ...common, lines: JSON.parse(JSON.stringify(demands.value)) }
  if (action.value === 'eta' && data.value?.requisition) return { ...common, requisition_version: data.value.requisition.version, batches: JSON.parse(JSON.stringify(batches.value)) }
  if (action.value === 'withdraw' && data.value?.requisition) return { ...common, requisition_version: data.value.requisition.version }
  if (action.value === 'reconcile' && selected.value?.pending_purchase?.requisition) return { ...common, requisition_version: selected.value.pending_purchase.requisition.version, disposition: disposition.value, evidence: evidence.value, all_handled: allHandled.value }
  error.value = '请明确选择一个已发布 BOM 版本。'; return null
}
async function save() {
  if (saving.value) return
  if (!pending.value) {
    if (!selected.value || !action.value) return
    const body = makeCommand(); if (!body) return
    pending.value = { id: selected.value.line_id, action: action.value, body }; uncertain.value = false
  }
  saving.value = true; error.value = ''
  try {
    const result = await ordersApi.command(pending.value.id, pending.value.action, pending.value.body)
    if (!alive) return
    selected.value = result; rows.value = rows.value.map(r => r.line_id === result.line_id ? result : r)
    pending.value = null; uncertain.value = false; needsLogin.value = false; action.value = null
    history.value = []; historyGeneration++; notice.value = '已保存，版本及操作依据已留存。'
    if (statusFilter.value || planStatusFilter.value) {
      saving.value = false
      await load()
    }
  } catch (e) {
    if (!alive) return
    const status = (e as { response?: { status?: number } }).response?.status
    error.value = errorMessage(e)
    if (status === 401) needsLogin.value = true
    else if (status && status >= 400 && status < 500) needsLogin.value = false
    if (!status || status >= 500 || status === 408) uncertain.value = true
    // A definitive 401 also keeps a retry entry: business forms are hidden until login.
    if (!uncertain.value && status && status >= 400 && status < 500 && status !== 408 && status !== 401) pending.value = null
  } finally { saving.value = false }
}
async function recover() {
  if (!pending.value || saving.value) return
  saving.value = true; error.value = ''
  try {
    const result = await ordersApi.recover(pending.value.id, pending.value.action, pending.value.body)
    if (!alive) return
    pending.value = null; uncertain.value = false; needsLogin.value = false
    if (result.state === 'committed') {
      action.value = null; saving.value = false
      await load()
      notice.value = '已核实原操作成功，已刷新最新订单，请重新选择查看。'
    } else notice.value = '已核实原操作未执行并停止，迟到请求也不会执行。草稿已保留，可修改后重新保存。'
  } catch (e) {
    if (alive) { error.value = errorMessage(e); if ((e as { response?: { status?: number } }).response?.status === 401) needsLogin.value = true }
  } finally { saving.value = false }
}
function purchaseModeChanged(row: DemandInput) { row.quantity = row.purchase_mode === 'no_purchase' ? '0' : ''; row.no_purchase_reason = '' }
function addBatch() { const first = data.value?.requisition?.lines.find(r => r.purchase_mode !== 'no_purchase'); if (first) batches.value.push({ row: first.row, quantity: '', expected_date: '', supplier: '', purchase_reference: '' }) }
function materialName(index: number) {
  const r = requirements.value[index]
  return r ? data.value?.bom?.material_references?.[`${r.material_id}:${r.material_version}`]?.name ?? r.material_id : ''
}
function status(row: CuttingOrder) {
  if (row.workflow_status) return statusLabels[row.workflow_status] ?? row.workflow_status
  if (row.needs_receipt) return row.snapshot.status === 'cancelled' ? '取消待签收' : '待签收新版本'
  if (row.snapshot.status === 'cancelled') return '已取消'
  if (row.current?.data.purchase_reconciliation_required) return '旧需求待采购核对'
  if (row.current?.data.requisition) return '已提交需求'
  return row.current?.data.bom ? '待工程提交需求' : '待关联 BOM'
}
</script>

<template>
  <template v-if="!available">
    <p v-if="loading" role="status">正在检查裁床接单权限…</p>
    <p v-else role="alert">{{ error || '订单与交期尚未启用，请完成迁移及独立授权后使用。' }}</p>
    <CuttingWorkspacePage :workspace="workspace" />
  </template>
  <section v-else class="cutting-page orders-page">
    <header class="cutting-page-heading"><div><p class="cutting-eyebrow">华康 C / 裁床部</p><h1>{{ workspace.title }}</h1><p>{{ workspace.path === 'materials' ? '采购分批交期与需求跟进' : '订单、工程需求与生产预排' }}</p></div><span class="cutting-status">订单与交期</span></header>
    <p class="cutting-notice">采购预计交期仅支持预排，不代表实收或库存可用；实际填数、领料和库存记账在后续阶段接入。</p>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
    <p v-if="needsLogin" role="alert">登录已失效，请在新标签页重新登录后重试。<a href="/login" target="_blank" rel="noopener">重新登录</a></p>
    <button v-if="pending" :disabled="saving" @click="save">{{ saving ? '正在保存…' : '重试原操作' }}</button>
    <button v-if="pending" :disabled="saving" @click="recover">核对保存结果／停止未执行操作</button>
    <template v-if="!needsLogin">
      <section class="cutting-panel">
        <h2>{{ workspace.path === 'materials' ? '采购交期' : '订单总台账' }}</h2>
        <form class="order-toolbar" @submit.prevent="load(1)"><label>订单号／货号 <input v-model="query" maxlength="80" /></label><label>办理状态 <select v-model="statusFilter" aria-label="办理状态筛选"><option value="">全部状态</option><option v-for="(label, value) in statusLabels" :key="value" :value="value">{{ label }}</option></select></label><label v-if="workspace.path === 'planning'">排期状态 <select v-model="planStatusFilter" aria-label="排期状态筛选"><option value="">全部排期</option><option v-for="(label,value) in planStatusLabels" :key="value" :value="value">{{ label }}</option></select></label><button :disabled="loading || saving || !!pending">查询／刷新</button></form>
        <div class="cutting-table-scroll"><table><thead><tr><th>洋行名</th><th>订单号</th><th>货号</th><th>来源数量</th><th>来源版本</th><th>办理状态</th><th>操作</th></tr></thead><tbody>
          <tr v-for="row in rows" :key="row.line_id"><td>{{ row.snapshot.customer_name }}</td><td>{{ row.snapshot.reference_no }}</td><td>{{ row.snapshot.product_no }}</td><td>{{ row.snapshot.quantity }}</td><td>V{{ row.source_version }}</td><td>{{ status(row) }}<p v-if="workspace.path === 'planning'">{{ row.planning_summary?.states?.map(s => planStatusLabels[s]).join(' · ') }}</p><p v-if="row.expected_date_passed">预计日期已过，实收待核实</p></td><td><button :disabled="saving || !!pending" @click="select(row)">查看</button></td></tr>
          <tr v-if="!rows.length"><td colspan="7">{{ loading ? '读取中…' : '暂无已下发订单，请由华康C业务在订单中心选择裁床部下发。' }}</td></tr>
        </tbody></table></div>
        <div class="order-toolbar"><button :disabled="page <= 1 || loading" @click="load(page-1)">上一页</button><span>第 {{ page }} 页 · 共 {{ total }} 条</span><button :disabled="page*50 >= total || loading" @click="load(page+1)">下一页</button></div>
      </section>
      <section v-if="selected" class="cutting-panel">
        <h2>{{ selected.snapshot.reference_no }} · {{ selected.snapshot.product_no }}</h2>
        <p>{{ status(selected) }} · 裁床记录 V{{ selected.current?.version ?? 0 }}</p>
        <p v-if="selected.snapshot.status === 'cancelled'" role="alert">来源订单已取消，仅可签收取消通知及核对旧采购需求。</p>
        <p v-if="selected.needs_receipt" class="cutting-notice">请先签收最新版本。重新签收会重置当前 BOM 和需求链；旧版保留历史，不会自动撤销采购单。</p>
        <p v-if="data?.purchase_reconciliation_required" role="alert">原需求待采购核对，期间不能继续回复交期或重新提交。核对整张旧需求的采购处置后，工程可修订并重新提交。</p>
        <p v-if="data?.reconciliation_request">核对原因：{{ data.reconciliation_request.reason }}</p>
        <p v-if="data?.reconciliation">采购已核对需求 V{{ data.reconciliation.requisition_version }}：{{ data.reconciliation.evidence }}。此次记录不自动撤销外部采购单。</p>
        <details v-if="selected.pending_purchase"><summary>查看待核对的原需求 V{{ selected.pending_purchase.requisition?.version }}</summary>
          <p>原订单：{{ selected.pending_purchase.order.reference_no }} · 数量 {{ selected.pending_purchase.order.quantity }} · BOM {{ selected.pending_purchase.bom?.code }} V{{ selected.pending_purchase.bom?.version }}</p>
          <ul><li v-for="r in selected.pending_purchase.requisition?.lines" :key="r.row">{{ r.row+1 }} · {{ r.material.name }} / {{ r.stage }} · {{ r.quantity }} {{ r.unit }} <span v-if="r.purchase_mode === 'no_purchase'">本次不采购：{{ r.no_purchase_reason }}</span></li></ul>
          <ul><li v-for="(b, i) in selected.pending_purchase.batches" :key="i">需求行 {{ b.row+1 }} · {{ b.quantity }} · {{ b.expected_date }} · {{ b.supplier }} · {{ b.purchase_reference }}</li></ul>
        </details>
        <p v-if="data?.bom">已关联 {{ data.bom.code }} V{{ data.bom.version }} · 裁床目标 {{ data.target_sets }} 套 · 数量依据：{{ data.quantity_basis }}</p>
        <div class="order-toolbar" v-if="!action">
          <template v-if="workspace.path === 'planning' && writable && data?.bom && !data.purchase_reconciliation_required">
            <button v-if="can('plan_write')" @click="edit('plan')">编制任务与日计划</button>
            <button v-if="can('plan_publish') && data.planning?.draft" :disabled="selected.planning_summary?.draft_stale" @click="edit('plan-publish')">发布生产预排</button>
          </template>
          <button v-if="selected.needs_receipt && can('order_receive')" @click="edit('receive')">签收订单版本</button>
          <button v-if="writable && !data?.requisition && can('bom_write')" @click="edit('bom')">工程关联 BOM</button>
          <button v-if="writable && data?.bom && !data.requisition && !data.purchase_reconciliation_required && can('requisition_submit')" @click="edit('requisition')">工程提交物料需求</button>
          <button v-if="writable && data?.requisition && !data.purchase_reconciliation_required && can('eta_write') && data.requisition.lines.some(r => r.purchase_mode !== 'no_purchase')" @click="edit('eta')">采购回复分批交期</button>
          <button v-if="writable && data?.requisition && !data.purchase_reconciliation_required && can('requisition_submit')" @click="edit('withdraw')">工程申请撤回／修订</button>
          <button v-if="!selected.needs_receipt && data?.purchase_reconciliation_required && can('requisition_reconcile')" @click="edit('reconcile')">采购核对旧需求</button>
        </div>
        <div v-if="data?.requisition" class="cutting-table-scroll"><table><caption>需求版本 V{{ data.requisition.version }}；无交期批次表示尚待回复</caption><thead><tr><th>需求行／物料</th><th>阶段／部件</th><th>裁剪必需</th><th>理论净用量</th><th>工程需求量</th><th>已回复／待回复</th><th>预计交期批次</th></tr></thead><tbody>
          <tr v-for="r in data.requisition.lines" :key="r.row"><td>{{ r.row + 1 }} · {{ r.material.code }} {{ r.material.name }}</td><td>{{ r.stage }} / {{ r.part_codes.join('、') }}</td><td>{{ r.required_for_cutting ? '是' : '否' }}</td><td>{{ r.theoretical_quantity }} {{ r.unit }}</td><td>{{ r.quantity }} {{ r.unit }}<p v-if="r.purchase_mode === 'no_purchase'">本次不采购：{{ r.no_purchase_reason }}</p></td><td>{{ r.replied_quantity }} / {{ r.awaiting_reply_quantity }} {{ r.unit }}</td><td><p v-for="(b, i) in data.batches.filter(b => b.row === r.row)" :key="i">{{ b.expected_date }} / {{ b.quantity }} {{ r.unit }} / {{ b.supplier }} / {{ b.purchase_reference }}</p><span v-if="r.purchase_mode === 'no_purchase'">无需采购交期</span><span v-else-if="!data.batches.some(b => b.row === r.row)">待回复</span></td></tr>
        </tbody></table></div>
        <template v-if="workspace.path === 'planning' && data?.planning">
          <CuttingPlanSummary v-if="data.planning.published" :plan="data.planning.published" title="当前发布计划" :stale="selected.planning_summary?.published_stale" />
          <CuttingPlanSummary v-if="data.planning.draft" :plan="data.planning.draft" title="待发布草稿" :stale="selected.planning_summary?.draft_stale" />
          <details v-if="data.planning.baseline"><summary>首次基准计划</summary><CuttingPlanSummary :plan="data.planning.baseline" title="首次基准" /></details>
        </template>
        <form v-if="action" class="order-form" @submit.prevent="save">
          <h3>{{ labels[action] }}</h3>
          <fieldset :disabled="saving || !!pending">
            <CuttingPlanEditor v-if="action === 'plan' && data" v-model="planTasks" v-model:removed-task-reasons="removedTaskReasons" :data="data" />
            <CuttingPlanDiff v-if="adjustingPlan && data?.planning?.published" :previous="data.planning.published" :tasks="action === 'plan' ? planTasks : data.planning.draft?.tasks ?? []" :removed-reasons="action === 'plan' ? removedTaskReasons : data.planning.draft?.removed_task_reasons" />
            <p v-if="action === 'plan-publish'">发布当前草稿后形成新计划版本，首次基准和历史调整仍保留。预排不代表物料已可用或允许实际开工。</p>
            <template v-if="action === 'bom'">
              <div class="order-toolbar"><label>BOM 编码／货号／名称／款式／颜色 <input v-model="bomQuery" maxlength="80" /></label><button type="button" @click="searchBoms()">查找 BOM</button></div>
              <ul><li v-for="b in bomRows" :key="b.id">{{ b.code }} · {{ b.data.name }} <button type="button" @click="loadVersions(b.id)">查看发布版本</button></li></ul>
              <div v-if="bomTotal" class="order-toolbar"><button type="button" :disabled="bomPage <= 1" @click="searchBoms(bomPage-1)">BOM 上一页</button><button type="button" :disabled="bomPage*50 >= bomTotal" @click="searchBoms(bomPage+1)">BOM 下一页</button></div>
              <ul><li v-for="b in versions" :key="b.version">{{ b.code }} V{{ b.version }} · {{ (b.data as BomData).item_no }} · {{ (b.data as BomData).style }} / {{ (b.data as BomData).color }} <button type="button" @click="chosenBom = b">选择此发布版</button></li></ul>
              <p v-if="versionId && !versions.length">此页没有发布版本。</p>
              <div v-if="versionId" class="order-toolbar"><button type="button" :disabled="versionPage <= 1" @click="loadVersions(versionId, versionPage-1)">版本上一页</button><button type="button" :disabled="versionPage*50 >= versionTotal" @click="loadVersions(versionId, versionPage+1)">版本下一页</button></div>
              <p>已选择：{{ chosenBom ? `${chosenBom.code} V${chosenBom.version}` : '尚未选择' }}。新发布版本不会自动替换本订单。</p>
              <label>裁床目标套数 <input v-model.number="targetSets" type="number" min="1" max="1000000000" step="1" required /></label>
              <label>数量口径／换算依据 <textarea v-model="quantityBasis" maxlength="500" required placeholder="确认订单数量是否为套；如换算，请填写依据" /></label>
              <label>BOM 对应依据 <textarea v-model="bomMatchBasis" maxlength="500" placeholder="订单货号与 BOM 货号不同时，必须说明对应依据" /></label>
            </template>
            <template v-if="action === 'requisition'">
              <p>逐行核定正式需求量。理论净用量不包含损耗，也未抵扣库存；请在提交依据中说明差异。</p>
              <div v-for="(r, i) in requirements" :key="i" class="demand-row">
                <p>{{ i+1 }} · {{ materialName(i) }} / {{ r.stage }} / {{ r.part_codes.join('、') }} · {{ r.required_for_cutting ? '裁剪必需' : '非当前必需' }} · 每套 {{ r.quantity_per_set }} {{ r.unit }}</p>
                <label>本次采购方式 <select v-model="demands[i]!.purchase_mode" :aria-label="`采购方式${i+1}`" @change="purchaseModeChanged(demands[i]!)"><option value="purchase">需要采购</option><option value="no_purchase">本次不采购</option></select></label>
                <label>需求数量 <input v-model="demands[i]!.quantity" :readonly="demands[i]!.purchase_mode === 'no_purchase'" inputmode="decimal" required :aria-label="`需求数量${i+1}`" /> {{ r.unit }}</label>
                <label v-if="demands[i]!.purchase_mode === 'no_purchase'">不采购原因 <input v-model="demands[i]!.no_purchase_reason" maxlength="500" required :aria-label="`不采购原因${i+1}`" /></label>
              </div><p>“本次不采购”只说明采购安排，不代表已有库存、可用或到料。</p>
            </template>
            <template v-if="action === 'eta'">
              <p>保存将形成新的完整交期版本；未覆盖数量仍待回复。删除批次只修订预计交期，不撤销采购单。</p>
              <div v-for="(b, i) in batches" :key="i" class="eta-row">
                <label>需求行 <select v-model.number="b.row"><option v-for="r in data?.requisition?.lines.filter(r => r.purchase_mode !== 'no_purchase')" :key="r.row" :value="r.row">{{ r.row+1 }} · {{ r.material.code }} {{ r.material.name }} / {{ r.stage }} / {{ r.part_codes.join('、') }} / {{ r.unit }}</option></select></label>
                <label>批次数量 <input v-model="b.quantity" inputmode="decimal" required /></label><label>预计到料 <input v-model="b.expected_date" type="date" required /></label><label>供应商 <input v-model="b.supplier" maxlength="120" required /></label><label>采购来源单号 <input v-model="b.purchase_reference" maxlength="120" required /></label><button type="button" @click="batches.splice(i, 1)">移除此批次</button>
              </div><button type="button" @click="addBatch">增加交期批次</button>
            </template>
            <p v-if="action === 'withdraw'">申请后暂停原需求交期办理。无论是否填写过交期，都须由采购确认旧需求处置；核对完成后可修订数量、BOM 并重新提交。</p>
            <template v-if="action === 'reconcile'">
              <label>旧采购处理结果 <select v-model="disposition" aria-label="旧采购处理结果"><option value="not_ordered">已核实整张旧需求尚未采购</option><option value="cancelled_or_reallocated">旧采购已取消／转用并完成核对</option></select></label>
              <label>处置依据 <textarea v-model="evidence" minlength="4" maxlength="500" required placeholder="注明核对人、原采购单号、取消／转用凭据及数量；不得遗留未处理承诺量" /></label>
              <label><input v-model="allHandled" type="checkbox" required />确认整张旧需求均已核对处置，没有未处理采购承诺；此处不会自动操作外部采购单。</label>
            </template>
            <label v-if="adjustingPlan">已发布计划调整原因 <textarea v-model="reason" maxlength="500" required /></label>
            <p v-if="adjustingPlan">本次调整将形成新版本，首次基准和原发布版本保留；发布时带入已保存的调整原因，可核对修改。</p>
            <label v-else-if="action !== 'plan' && action !== 'plan-publish'">本次操作依据 <textarea v-model="reason" maxlength="500" required /></label>
            <button type="submit">确认保存</button><button type="button" @click="cancel">取消编辑</button>
          </fieldset>
        </form>
        <div class="order-toolbar"><button :disabled="!selected.current" @click="loadHistory()">查看历史版本</button><template v-if="historyTotal"><button :disabled="historyPage <= 1" @click="loadHistory(historyPage-1)">历史上一页</button><span>{{ historyPage }} / {{ Math.ceil(historyTotal/50) }}</span><button :disabled="historyPage*50 >= historyTotal" @click="loadHistory(historyPage+1)">历史下一页</button></template></div>
        <details v-for="r in history" :key="r.version"><summary>V{{ r.version }} · {{ r.created_at }} · {{ r.actor_id }} · {{ r.reason }}</summary>
          <p>订单：{{ r.data.order.reference_no }} / {{ r.data.order.product_no }} · 来源数量 {{ r.data.order.quantity }} · {{ r.data.order.status === 'cancelled' ? '已取消' : '有效' }}</p>
          <p>BOM：{{ r.data.bom ? `${r.data.bom.code} V${r.data.bom.version}` : '未关联' }} · 目标 {{ r.data.target_sets ?? '待确认' }} 套 · {{ r.data.quantity_basis }} · {{ r.data.bom_match_basis }}</p>
          <CuttingPlanSummary v-if="r.data.planning?.published" :plan="r.data.planning.published" title="该版本发布计划" />
          <CuttingPlanSummary v-if="r.data.planning?.draft" :plan="r.data.planning.draft" title="该版本计划草稿" />
          <p v-if="r.data.purchase_reconciliation_required">旧采购需求待核对</p>
          <p v-if="r.data.reconciliation_request">申请依据：{{ r.data.reconciliation_request.reason }}</p><p v-if="r.data.reconciliation">需求 V{{ r.data.reconciliation.requisition_version }} 采购核对依据：{{ r.data.reconciliation.evidence }}</p>
          <ul><li v-for="line in r.data.requisition?.lines" :key="line.row">{{ line.row+1 }} · {{ line.material.name }} / {{ line.stage }} · 需求 {{ line.quantity }} {{ line.unit }}<span v-if="line.purchase_mode === 'no_purchase'"> · 本次不采购：{{ line.no_purchase_reason }}</span></li></ul>
          <ul><li v-for="(batch, i) in r.data.batches" :key="i">需求行 {{ batch.row+1 }} · {{ batch.expected_date }} / {{ batch.quantity }} / {{ batch.supplier }} / {{ batch.purchase_reference }}</li></ul>
        </details>
      </section>
    </template>
  </section>
</template>

<style scoped>
.order-toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: .75rem; margin: 1rem 0; }
.orders-page input,.orders-page select,.orders-page textarea { border: 1px solid #cbd5e1; border-radius: 6px; padding: .45rem; background: white; color: #0f172a; max-width: 100%; }
.orders-page button { border: 1px solid #a7c7c4; border-radius: 6px; padding: .4rem .7rem; color: #0f766e; background: #f0fdfa; cursor: pointer; }
.orders-page button:disabled { opacity: .5; cursor: default; }
.orders-page [role=alert] { color: #b91c1c; }
.order-form { border-top: 1px solid #e2e8f0; margin-top: 1rem; padding-top: 1rem; }
.order-form fieldset { border: 0; display: grid; gap: 1rem; padding: 0; }
.order-form label { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; }
.eta-row { display: flex; flex-wrap: wrap; gap: .75rem; padding: .75rem; background: #f8fafc; }
pre { max-height: 24rem; overflow: auto; white-space: pre-wrap; word-break: break-word; }
</style>
