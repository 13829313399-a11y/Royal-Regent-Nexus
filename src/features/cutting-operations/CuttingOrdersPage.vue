<script setup lang="ts">
import PageHeader from '@/components/common/PageHeader.vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import { onBeforeRouteLeave, RouterLink } from 'vue-router'
import { ChevronLeft, ChevronRight, ClipboardList, Search } from '@lucide/vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { Button } from '@/components/ui/button'
import { cuttingApi, errorMessage, type Access, type BomData, type MasterRecord, type Command } from './api'
import { ordersApi, type CuttingOrder, type OrderAction, type OrderCommand, type OrderRevision, type EtaBatch, type DemandInput } from './ordersApi'
import { CUTTING_FACTORY, type CuttingWorkspace } from './navigation'
import CuttingPlanEditor from './CuttingPlanEditor.vue'
import CuttingPlanSummary from './CuttingPlanSummary.vue'
import CuttingPlanDiff from './CuttingPlanDiff.vue'
import CuttingMaterialRequests from './CuttingMaterialRequests.vue'
import CuttingMaterialUsage from './CuttingMaterialUsage.vue'
import CuttingProductionSummary from './CuttingProductionSummary.vue'
import { taskInput, type PlanTaskInput } from './planning'
import { orderHistoryTime, orderProductName, unclassifiedStyle, unclassifiedStyleHint } from './orderDisplay'
import { cuttingDestination, useCuttingLocation, type CuttingLocation } from './location'
import CuttingLocationNotice from './CuttingLocationNotice.vue'
import CuttingPlanningMetrics from './CuttingPlanningMetrics.vue'
import CuttingInventory from './CuttingInventory.vue'
import CuttingActivityPage from './CuttingActivityPage.vue'
import CuttingSubnav from './CuttingSubnav.vue'
import CuttingScheduleImport from './CuttingScheduleImport.vue'
import CuttingOrderReceipt from './CuttingOrderReceipt.vue'
import CuttingPurchaseReplyEvidence from './CuttingPurchaseReplyEvidence.vue'

const props=defineProps<{ workspace: CuttingWorkspace }>()
const filterId=`cutting-orders-${useId()}`
const editorId = (name: string, row?: number) => `${filterId}-editor-${name}${row === undefined ? '' : `-${row}`}`
const materialsView=ref('inventory')
const manualLocation=ref<CuttingLocation>()
const appliedQuery=ref(''),appliedStatus=ref(''),appliedPlanStatus=ref(''),summaryRefresh=ref(0)
const materialTabs=[{id:'inventory',label:'库存台账'},{id:'orders',label:'订单领用汇总'},{id:'movements',label:'收发记录'},{id:'requests',label:'领料申请'},{id:'usage',label:'耗用与余料'},{id:'eta',label:'采购交期'}]
async function openMaterial(lineId:string,issueId:string){
  if(!discard())return
  const ticket=++generation;loading.value=true;error.value=''
  try{const row=await ordersApi.read(lineId);if(alive&&ticket===generation){
    selected.value=row;action.value=null;history.value=[];historyTotal.value=0;historyGeneration++;searchGeneration++
    manualLocation.value={lineId,...(issueId?{kind:'issue' as const,id:issueId}:{})};materialsView.value='usage'
  }}
  catch(e){if(alive&&ticket===generation)error.value=errorMessage(e)}
  finally{if(alive&&ticket===generation)loading.value=false}
}
const materialEditor = ref<InstanceType<typeof CuttingMaterialRequests>>()
const scheduleImporter = ref<InstanceType<typeof CuttingScheduleImport>>()
const usageEditor = ref<InstanceType<typeof CuttingMaterialUsage>>()
const materialEditing=ref(false),usageEditing=ref(false)
const access = ref<Access | null>(null), loading = ref(true), saving = ref(false), needsLogin = ref(false)
const error = ref(''), notice = ref(''), query = ref(''), page = ref(1), total = ref(0)
const readFailureStatus=ref<number>()
const statusFilter = ref('')
const planStatusFilter = ref('')
const planStatusLabels: Record<string,string> = { unplanned:'未排',partial:'部分排期',published:'已发布',pending_actual:'待实际核定',review:'待复核' }
const rows = ref<CuttingOrder[]>([]), selected = ref<CuttingOrder | null>(null)
const action = ref<OrderAction | null>(null), reason = ref(''), targetSets = ref(1), quantityBasis = ref('')
const bomMatchBasis = ref('')
const chosenBom = ref<MasterRecord | null>(null), bomQuery = ref(''), bomRows = ref<MasterRecord[]>([])
const bomPage = ref(1), bomTotal = ref(0), versionPage = ref(1), versionTotal = ref(0), versionId = ref(''), versions = ref<MasterRecord[]>([])
const demands = ref<DemandInput[]>([]), batches = ref<EtaBatch[]>([])
const disposition = ref<'' | 'not_ordered' | 'cancelled_or_reallocated'>(''), evidence = ref(''), allHandled = ref(false)
const orderEditor = ref<HTMLFormElement>()
const history = ref<OrderRevision[]>([]), historyPage = ref(1), historyTotal = ref(0)
const pending = ref<{ id: string; action: OrderAction; body: OrderCommand } | null>(null), uncertain = ref(false)
const planTasks = ref<PlanTaskInput[]>([])
const removedTaskReasons = ref<Record<string,string>>({})
const baseline = ref('')
const snapshot = () => JSON.stringify([reason.value, targetSets.value, quantityBasis.value, bomMatchBasis.value, chosenBom.value, demands.value, batches.value, disposition.value, evidence.value, allHandled.value, planTasks.value,removedTaskReasons.value])
const dirty = computed(() => !!action.value && snapshot() !== baseline.value)
const available = computed(() => access.value?.enabled && access.value?.orders_schema_ready)
const data = computed(() => selected.value?.current?.data)
const hasPurchaseEvidence = computed(() => {
  const original = selected.value?.pending_purchase
  return original?.has_purchase_evidence ?? !!original?.batches.length
})
const receiveLabel = computed(() => selected.value?.current ? '确认订单变更' : '签收订单版本')
const publishedPlan = computed(() => data.value?.planning?.published)
const singlePublishedTask = computed(() => publishedPlan.value?.tasks.length === 1 ? publishedPlan.value.tasks[0] : undefined)
const adjustingPlan = computed(() => (action.value === 'plan' || action.value === 'plan-publish') && !!data.value?.planning?.published)
const publishLabel = computed(() => selected.value?.snapshot.intake_kind==='cutting-schedule-v1'&&!data.value?.planning?.draft?.tasks.some(t=>t.days.length) ? '发布领料任务（暂不排日计划）' : '发布生产预排')
const requirements = computed(() => (data.value?.bom?.data as BomData | undefined)?.requirements ?? [])
const writable = computed(() => selected.value && !selected.value.needs_receipt && selected.value.snapshot.status === 'active')
const can = (permission: string) => access.value?.permissions.includes(permission) ?? false
const labels: Record<OrderAction, string> = { receive: '签收订单版本', bom: '工程关联 BOM', requisition: '工程提交物料需求', eta: '采购回复分批交期', withdraw: '工程申请撤回／修订', reconcile: '采购核对旧需求', plan: '编制任务与日计划', 'plan-publish': '发布生产预排' }
const statusLabels: Record<string, string> = { awaiting_receipt: '待签收新版本', cancelled_receipt: '取消待签收', cancelled: '已取消', reconciliation: '旧需求待采购核对', awaiting_bom: '待关联 BOM', awaiting_submission: '待工程提交需求', awaiting_reply: '待采购回复', partial_reply: '采购部分回复', complete_reply: '采购全部回复', no_purchase: '本次无需采购' }
let alive = true, generation = 0, searchGeneration = 0, historyGeneration = 0
function discard() {
  if (scheduleImporter.value && !scheduleImporter.value.discard()) return false
  if (usageEditor.value && !usageEditor.value.discard()) return false
  if (materialEditor.value && !materialEditor.value.discard()) return false
  if (saving.value || pending.value) { error.value = '保存结果尚未确认，请先重试原操作。'; return false }
  return !dirty.value || window.confirm('有尚未保存的内容，离开将放弃这些内容。确定继续？')
}
onBeforeRouteLeave(discard)
const location = useCuttingLocation(discard, () => { void load(1, true, true) })
function beforeUnload(e: BeforeUnloadEvent) { if (dirty.value || pending.value || saving.value) { e.preventDefault(); e.returnValue = '' } }
onMounted(() => { window.addEventListener('beforeunload', beforeUnload); void load(1, false, true) })
onBeforeUnmount(() => { alive = false; generation++; searchGeneration++; historyGeneration++; window.removeEventListener('beforeunload', beforeUnload) })
watch(bomQuery, () => { searchGeneration++; bomRows.value = []; versions.value = []; versionId.value = '' }, { flush: 'sync' })

async function load(nextPage = page.value, navigation = false, followLocation = false, apply = false) {
  if (!navigation && !discard()) return
  if(apply){appliedQuery.value=query.value;appliedStatus.value=statusFilter.value;appliedPlanStatus.value=planStatusFilter.value;nextPage=1}
  const request = ++generation
  manualLocation.value=undefined
  selected.value = null; action.value = null; history.value = []; rows.value = []; historyGeneration++; searchGeneration++
  loading.value = true; error.value = ''; readFailureStatus.value=undefined
  try {
    const rights = await cuttingApi.access()
    if (!alive || request !== generation) return
    access.value = rights
    if (!available.value) return
    summaryRefresh.value++
    const target = followLocation ? location.value : undefined
    if (target) {
      const order = await ordersApi.read(target.lineId)
      if (!alive || request !== generation) return
      rows.value = [order]; total.value = 1; page.value = 1; selected.value = order
      if(props.workspace.path==='materials')materialsView.value=target.kind==='usage'||target.kind==='issue'?'usage':'requests'
      return
    }
    const result = await ordersApi.list(nextPage, appliedQuery.value, appliedStatus.value, appliedPlanStatus.value)
    if (!alive || request !== generation) return
    rows.value = result.data; total.value = result.total; page.value = nextPage
  } catch (e) { if (alive && request === generation) { error.value = errorMessage(e); readFailureStatus.value=(e as {response?:{status?:number}}).response?.status; access.value = null } }
  finally { if (alive && request === generation) loading.value = false }
}
function select(row: CuttingOrder) {
  if (!discard()) return
  selected.value = row; action.value = null; history.value = []; historyTotal.value = 0; historyGeneration++; searchGeneration++
  notice.value = ''; error.value = ''
}
function edit(next: OrderAction) {
  if (!discard()) return
  const previousFocus = document.activeElement
  const lineId = selected.value?.line_id
  searchGeneration++; action.value = next; reason.value = ''; chosenBom.value = null; bomQuery.value = ''; bomRows.value = []; versions.value = []
  removedTaskReasons.value = {}
  if (next === 'plan-publish' && data.value?.planning?.published) reason.value = data.value.planning.draft?.adjustment_reason ?? ''
  targetSets.value = data.value?.target_sets ?? 1; quantityBasis.value = data.value?.quantity_basis ?? ''
  bomMatchBasis.value = data.value?.bom_match_basis ?? ''
  demands.value = requirements.value.map((_, row) => ({ row, quantity: '', purchase_mode: 'purchase', no_purchase_reason: '' }))
  disposition.value = ''; evidence.value = ''; allHandled.value = false
  batches.value = structuredClone(data.value?.batches ? JSON.parse(JSON.stringify(data.value.batches)) : [])
  planTasks.value = (data.value?.planning?.draft ?? data.value?.planning?.published)?.tasks.map(taskInput) ?? []
  if (next === 'plan' && (data.value?.planning?.draft ? selected.value?.planning_summary?.draft_stale : selected.value?.planning_summary?.published_stale)) {
    // Revalidate estimates against the latest BOM; never carry an old row-index mapping into a new BOM silently.
    for (const task of planTasks.value) {
      task.materials = requirements.value.flatMap((r, row) => r.required_for_cutting ? [{ row, expected_date: null }] : [])
      task.date_basis = 'estimated'; task.actual_prerequisite_date = null; task.actual_prerequisite_reference = ''; task.actual_issue_date = null; task.actual_issue_reference = ''; task.material_receipt_ids = []; task.readiness_basis = ''; task.prerequisite_date = null; task.prerequisite_basis = ''
    }
    notice.value = '旧计划依据已变更：保留任务和日计划，预计物料、实际领料及前置条件须重新核对填写。'
  }
  baseline.value = snapshot()
  void nextTick(() => {
    if (!alive || action.value !== next || selected.value?.line_id !== lineId ||
        (document.activeElement !== previousFocus && document.activeElement !== document.body)) return
    const editor = orderEditor.value
    const firstField = editor?.querySelector<HTMLElement>('input:not([type="hidden"]):not(:disabled), select:not(:disabled), textarea:not(:disabled)')
    const target = firstField ?? editor?.querySelector('h3')
    target?.focus()
  })
}
function cancel() {
  if (!discard() || !action.value) return
  const trigger = editorId(`open-${action.value}`)
  const lineId = selected.value?.line_id
  const previousFocus = document.activeElement
  action.value = null; searchGeneration++
  void nextTick(() => {
    if (alive && !action.value && selected.value?.line_id === lineId &&
        (document.activeElement === previousFocus || document.activeElement === document.body)) {
      document.getElementById(trigger)?.focus()
    }
  })
}
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
  if (action.value === 'reconcile' && selected.value?.pending_purchase?.requisition) {
    if (!disposition.value || (hasPurchaseEvidence.value && disposition.value === 'not_ordered')) {
      error.value = '请选择适用的旧采购处理结果。'
      return null
    }
    return { ...common, requisition_version: selected.value.pending_purchase.requisition.version, disposition: disposition.value, evidence: evidence.value, all_handled: allHandled.value }
  }
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
  const current=row.current?.data
  if(row.snapshot.intake_kind==='cutting-schedule-v1'&&!row.needs_receipt&&row.snapshot.status==='active'&&
    (!row.workflow_status||row.workflow_status==='awaiting_submission')&&current?.bom&&!current.requisition&&!current.purchase_reconciliation_required){
    if(row.planning_summary?.published_stale) return '已关联 BOM（计划待复核）'
    if(current.planning?.published?.publication_kind==='task_only') return '领料任务已发布'
    return current.planning?.published?'计划已发布（采购未办理）':'已关联 BOM（采购未办理）'
  }
  if (row.workflow_status) return statusLabels[row.workflow_status] ?? row.workflow_status
  if (row.needs_receipt) return row.snapshot.status === 'cancelled' ? '取消待签收' : '待签收新版本'
  if (row.snapshot.status === 'cancelled') return '已取消'
  if (row.current?.data.purchase_reconciliation_required) return '旧需求待采购核对'
  if (row.current?.data.requisition) return '已提交需求'
  return row.current?.data.bom ? '待工程提交需求' : '待关联 BOM'
}
</script>

<template>
  <section v-if="!available" class="cutting-page">
    <PageHeader :title="workspace.title" description="按当前厂区和岗位授权读取裁床订单。" />
    <p v-if="loading" role="status">正在读取订单并核验裁床接单权限…</p>
    <div v-else-if="error" class="cutting-notice" role="alert">
      <div><p>{{readFailureStatus===401?'登录已失效，请重新登录。':readFailureStatus===403?'当前账号无权读取裁床订单，请联系授权负责人。':'订单读取失败，请重试。'}}</p><p>{{error}}</p>
        <Button type="button" variant="outline" @click="load(1,false,true)">{{readFailureStatus===401||readFailureStatus===403?'重新核验权限':'重新读取订单'}}</Button>
        <a v-if="readFailureStatus===401" href="/login" target="_blank" rel="noopener">重新登录</a>
      </div>
    </div>
    <p v-else-if="access&&!access.enabled" class="cutting-notice">裁床订单模块尚未启用，请联系系统负责人。</p>
    <p v-else class="cutting-notice">裁床订单结构尚未就绪，请先完成显式迁移；当前不读取或录入业务数据。</p>
  </section>
  <section v-else class="cutting-page cutting-review-page orders-page">
    <CuttingLocationNotice :location="manualLocation??location" :selected-id="selected?.line_id" />
    <PageHeader :title="workspace.title" :description="workspace.path === 'materials' ? '本厂现场、外发在外物料与订单领用，按原实发追溯。' : '订单、工程需求与生产预排'"/>
    <SectionPanel v-if="selected?.snapshot.intake_kind==='cutting-schedule-v1'" title="业务排期来源" class="cutting-content-panel">
      <p>排期直接导入：{{selected.snapshot.intake_file_name}} · {{selected.snapshot.intake_sheet}} 第 {{selected.snapshot.intake_row}} 行 · 来源 V{{selected.source_version}}</p>
      <p>原订单单位：{{selected.snapshot.order_unit}}；目标套数仍由工程按 BOM 明确核定。</p>
      <details><summary>批次与原文件指纹</summary><p style="overflow-wrap:anywhere">{{selected.snapshot.intake_batch}}<br>{{selected.snapshot.intake_sha256}}</p></details>
    </SectionPanel>
    <CuttingSubnav v-if="workspace.path==='materials'" v-model="materialsView" :items="materialTabs" label="物料库存工作视图" />
    <p v-if="workspace.path==='materials'" class="cutting-muted">领料申请与实发签收已对接布料仓。现场及外发余料按原实发核对，计价以已确认批次成本为准。</p>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
    <p v-if="needsLogin" role="alert">登录已失效，请在新标签页重新登录后重试。<a href="/login" target="_blank" rel="noopener">重新登录</a></p>
    <Button variant="outline" v-if="pending" :disabled="saving" @click="save">{{ saving ? '正在保存…' : '重试原操作' }}</Button>
    <Button variant="outline" v-if="pending" :disabled="saving" @click="recover">核对保存结果／停止未执行操作</Button>
    <template v-if="!needsLogin">
      <CuttingInventory v-if="workspace.path==='materials'" v-show="materialsView==='inventory'||materialsView==='orders'" :summary="materialsView==='orders'" @open="openMaterial" />
      <CuttingActivityPage v-if="workspace.path==='materials'&&materialsView==='movements'" embedded initial-source="warehouse" />
      <div v-show="workspace.path!=='materials'||!['inventory','orders','movements'].includes(materialsView)" class="cutting-overview">
      <div class="cutting-review-filters">
        <form class="order-toolbar order-filters" @submit.prevent="load(1,false,false,true)">
          <label class="order-filter-field" :for="`${filterId}-query`">
            <span>订单号／货号</span>
            <input :id="`${filterId}-query`" name="order_q" v-model="query" class="order-filter-control" maxlength="80" placeholder="输入订单号或货号" />
          </label>
          <label class="order-filter-field" :for="`${filterId}-status`">
            <span>办理状态</span>
            <select :id="`${filterId}-status`" name="status" v-model="statusFilter" class="order-filter-control" aria-label="办理状态筛选">
              <option value="">全部状态</option>
              <option v-for="(label, value) in statusLabels" :key="value" :value="value">{{ label }}</option>
            </select>
          </label>
          <label v-if="workspace.path === 'planning'" class="order-filter-field" :for="`${filterId}-plan-status`">
            <span>排期状态</span>
            <select :id="`${filterId}-plan-status`" name="plan_status" v-model="planStatusFilter" class="order-filter-control" aria-label="排期状态筛选">
              <option value="">全部排期</option>
              <option v-for="(label,value) in planStatusLabels" :key="value" :value="value">{{ label }}</option>
            </select>
          </label>
          <Button type="submit" class="order-query-button" :disabled="loading || saving || !!pending">
            <Search aria-hidden="true" />查询／刷新
          </Button>
        </form>
      </div>
      <CuttingPlanningMetrics v-if="workspace.path==='planning'" :query="appliedQuery" :status="appliedStatus" :plan-status="appliedPlanStatus" :refresh="summaryRefresh" />
      <SectionPanel v-if="workspace.path==='planning' && selected" title="当前订单排期摘要" :subtitle="`${selected.snapshot.reference_no} · ${selected.snapshot.product_no}`" class="cutting-content-panel">
        <dl class="cutting-review-grid cutting-review-facts">
          <div><dt>关联 BOM</dt><dd>{{ data?.bom ? `${data.bom.code} V${data.bom.version}` : '待关联' }}</dd></div>
          <div><dt>发布计划</dt><dd>{{ publishedPlan ? `V${publishedPlan.version}${selected.planning_summary?.published_stale ? ' · 待复核' : ''}` : '未发布' }}</dd></div>
          <div><dt>预计供数</dt><dd>{{ singlePublishedTask?.estimated_supply_date ?? (publishedPlan && !singlePublishedTask ? '按任务核对' : '待核定') }}</dd></div>
          <div><dt>实际领料</dt><dd>{{ singlePublishedTask?.actual_issue_date ?? (publishedPlan && !singlePublishedTask ? '按任务核对' : '待核定') }}</dd></div>
          <div><dt>计划完成</dt><dd>{{ singlePublishedTask?.completion_date ?? (publishedPlan && !singlePublishedTask ? '按任务核对' : '未排完') }}</dd></div>
        </dl>
      </SectionPanel>
      <CuttingScheduleImport v-if="workspace.path==='planning'&&can('order_receive')" ref="scheduleImporter" @imported="load(1,false,false)" />
      <SectionPanel class="order-ledger min-w-0" :title="workspace.path === 'materials' ? materialsView==='eta'?'采购交期':'选择领用订单' : '订单总台账'">
        <div class="order-ledger-grid">
          <div class="cutting-table-scroll" role="region" aria-label="订单总台账，可横向滚动" tabindex="0">
            <table class="order-ledger-table" :aria-busy="loading">
              <caption class="sr-only">{{ workspace.path === 'materials' ? '采购交期' : '订单总台账' }}</caption>
              <thead><tr><th scope="col">客户</th><th scope="col">订单号</th><th scope="col">货号</th><th scope="col">货名</th><th scope="col">款式分类</th><th scope="col" class="order-number">订单数量</th><th scope="col">办理状态</th><th scope="col" class="order-actions">操作</th></tr></thead>
              <tbody>
                <tr v-for="row in rows" :key="row.line_id">
                  <td>{{ row.snapshot.customer_name }}</td><td class="tabular-nums">{{ row.snapshot.reference_no }}</td><td>{{ row.snapshot.product_no }}</td>
                  <td class="cutting-order-product-name">{{ orderProductName(row.snapshot) }}</td><td :title="unclassifiedStyleHint">{{ unclassifiedStyle }}</td>
                  <td class="order-number tabular-nums">{{ row.snapshot.quantity }}</td>
                  <td><StatusPill :label="status(row)" compact /><p v-if="workspace.path === 'planning'" class="order-cell-note">{{ row.planning_summary?.states?.map(s => planStatusLabels[s]).join(' · ') }}</p><p v-if="row.expected_date_passed" class="order-cell-note">预计日期已过，实收待核实</p></td>
                  <td class="order-actions"><Button type="button" variant="outline" size="sm" :disabled="saving || !!pending" @click="select(row)">查看</Button></td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="!rows.length" class="order-ledger-empty" role="status">
            <ClipboardList :size="28" aria-hidden="true" />
            <p class="order-empty-title">{{ loading ? '正在读取订单…' : '暂无订单记录' }}</p>
            <p>{{ loading ? '请稍候，正在获取订单台账。' : appliedQuery||appliedStatus||appliedPlanStatus ? '当前筛选无匹配订单，请清除筛选后查看。' : '暂无已下发订单，请由华康C业务在订单中心选择裁床部下发。' }}</p>
            <Button v-if="!loading&&(appliedQuery||appliedStatus||appliedPlanStatus)" type="button" variant="outline" @click="query='';statusFilter='';planStatusFilter='';load(1,false,false,true)">清除筛选</Button>
          </div>
        </div>
        <nav class="order-pagination" aria-label="订单分页">
          <p class="tabular-nums" aria-live="polite">第 {{ page }} 页 · 共 {{ total }} 条</p>
          <div class="order-pagination-actions">
            <Button type="button" variant="outline" size="sm" :disabled="page <= 1 || loading" @click="load(page-1)"><ChevronLeft aria-hidden="true" />上一页</Button>
            <Button type="button" variant="outline" size="sm" :disabled="page*50 >= total || loading" @click="load(page+1)">下一页<ChevronRight aria-hidden="true" /></Button>
          </div>
        </nav>
      </SectionPanel>
      <SectionPanel v-if="workspace.path === 'planning' && selected" title="领料办理" class="cutting-content-panel">
        <p>领料申请与实发签收已对接布料仓。申请、仓库回传与分批签收在物料库存工作区办理。</p>
        <div class="order-toolbar">
          <Button as-child variant="outline"><RouterLink :to="cuttingDestination(selected.line_id, location?.month ?? '', 'materials')">前往物料库存办理领料</RouterLink></Button>
        </div>
      </SectionPanel>
      <CuttingMaterialRequests v-if="workspace.path === 'materials' && selected && selected.current" v-show="materialsView!=='usage'&&materialsView!=='eta'" ref="materialEditor" :key="selected.line_id" :order="selected" :permissions="access?.permissions ?? []" :blocked="saving || !!pending || !!action || usageEditing" @editing="materialEditing=$event" @refreshed="r => { if(selected?.line_id===r.line_id){selected=r;rows=rows.map(old=>old.line_id===r.line_id?r:old)} }" />
      <CuttingMaterialUsage v-if="workspace.path==='materials'&&selected?.current&&access?.usage_schema_ready" v-show="materialsView==='usage'" ref="usageEditor" :key="`usage-${selected.line_id}`" :line-id="selected.line_id" :permissions="access.permissions" :blocked="saving||!!pending||!!action||materialEditing" @editing="usageEditing=$event" />
      <SectionPanel v-if="selected" class="cutting-content-panel" :title="`${selected.snapshot.reference_no} · ${selected.snapshot.product_no}`">
        <p>货名：{{ orderProductName(selected.snapshot) }} · 款式分类：<span :title="unclassifiedStyleHint">{{ unclassifiedStyle }}</span></p>
        <p>{{ status(selected) }} · 裁床记录 V{{ selected.current?.version ?? 0 }}</p>
        <details v-if="selected.current?.data.receipt?.mode === 'note_only'">
          <summary>已接收备注对照</summary>
          <CuttingOrderReceipt :receipt="selected.current.data.receipt" :record-version="selected.current.version" />
        </details>
        <p v-if="selected.snapshot.status === 'cancelled'" role="alert">来源订单已取消，仅可签收取消通知及核对旧采购需求。</p>
        <div v-if="selected.needs_receipt" class="cutting-notice">
          <div v-if="selected.current">
            <p>订单变更待确认 · 已接 V{{ data?.receipt?.source_version ?? data?.order.version ?? '—' }} → 待确认 V{{ selected.source_version }}</p>
            <p v-if="data?.order.quantity!==selected.snapshot.quantity">订单数量 {{ data?.order.quantity ?? '—' }} → {{ selected.snapshot.quantity ?? '—' }}</p>
            <p v-if="data?.order.requested_ship_date!==selected.snapshot.requested_ship_date">交期 {{ data?.order.requested_ship_date ?? '—' }} → {{ selected.snapshot.requested_ship_date ?? '—' }}</p>
            <p v-if="selected.snapshot.change_reason">变更说明 {{ selected.snapshot.change_reason }}</p>
            <p>确认后需重新核对 BOM 和需求。原采购单及计划依据保留，已有采购需求须先核对。</p>
          </div>
          <p v-else>此订单尚未接单，请先确认下发版本。</p>
        </div>
        <p v-if="data?.purchase_reconciliation_required" role="alert">原需求待采购核对，期间不能继续回复交期或重新提交。核对整张旧需求的采购处置后，工程可修订并重新提交。</p>
        <p v-if="data?.reconciliation_request">核对原因：{{ data.reconciliation_request.reason }}</p>
        <p v-if="data?.reconciliation">采购已核对需求 V{{ data.reconciliation.requisition_version }}：{{ data.reconciliation.evidence }}。此次记录不自动撤销外部采购单。</p>
        <details v-if="selected.pending_purchase"><summary>查看待核对的原需求 V{{ selected.pending_purchase.requisition?.version }}</summary>
          <p>原订单：{{ selected.pending_purchase.order.reference_no }} · 数量 {{ selected.pending_purchase.order.quantity }} · BOM {{ selected.pending_purchase.bom?.code }} V{{ selected.pending_purchase.bom?.version }}</p>
          <ul><li v-for="r in selected.pending_purchase.requisition?.lines" :key="r.row">{{ r.row+1 }} · {{ r.material.name }} / {{ r.stage }} · {{ r.quantity }} {{ r.unit }} <span v-if="r.purchase_mode === 'no_purchase'">本次不采购：{{ r.no_purchase_reason }}</span></li></ul>
          <CuttingPurchaseReplyEvidence :purchase="selected.pending_purchase" />
        </details>
        <p v-if="data?.bom">已关联 {{ data.bom.code }} V{{ data.bom.version }} · 裁床目标 {{ data.target_sets }} 套 · 数量依据：{{ data.quantity_basis }}</p>
        <div class="order-toolbar" v-if="!action">
          <template v-if="workspace.path === 'planning' && writable && data?.bom && !data.purchase_reconciliation_required">
            <Button variant="outline" v-if="can('plan_write')" :id="editorId('open-plan')" @click="edit('plan')">编制任务与日计划</Button>
            <Button variant="outline" v-if="can('plan_publish') && data.planning?.draft" :id="editorId('open-plan-publish')" :disabled="selected.planning_summary?.draft_stale" @click="edit('plan-publish')">{{publishLabel}}</Button>
          </template>
          <Button variant="outline" v-if="selected.needs_receipt && can('order_receive')" :id="editorId('open-receive')" @click="edit('receive')">{{ receiveLabel }}</Button>
          <Button variant="outline" v-if="writable && !data?.requisition && can('bom_write')" :id="editorId('open-bom')" @click="edit('bom')">工程关联 BOM</Button>
          <Button variant="outline" v-if="writable && data?.bom && !data.requisition && !data.purchase_reconciliation_required && can('requisition_submit')" :id="editorId('open-requisition')" @click="edit('requisition')">工程提交物料需求</Button>
          <Button variant="outline" v-if="writable && data?.requisition && !data.purchase_reconciliation_required && can('eta_write') && data.requisition.lines.some(r => r.purchase_mode !== 'no_purchase')" :id="editorId('open-eta')" @click="edit('eta')">采购回复分批交期</Button>
          <Button variant="outline" v-if="writable && data?.requisition && !data.purchase_reconciliation_required && can('requisition_submit')" :id="editorId('open-withdraw')" @click="edit('withdraw')">工程申请撤回／修订</Button>
          <Button variant="outline" v-if="!selected.needs_receipt && data?.purchase_reconciliation_required && can('requisition_reconcile')" :id="editorId('open-reconcile')" @click="edit('reconcile')">采购核对旧需求</Button>
        </div>
        <div v-if="data?.requisition" class="cutting-table-scroll"><table><caption>需求版本 V{{ data.requisition.version }}；无交期批次表示尚待回复</caption><thead><tr><th>需求行／物料</th><th>阶段／部件</th><th>裁剪必需</th><th>理论净用量</th><th>工程需求量</th><th>已回复／待回复</th><th>预计交期批次</th></tr></thead><tbody>
          <tr v-for="r in data.requisition.lines" :key="r.row"><td>{{ r.row + 1 }} · {{ r.material.code }} {{ r.material.name }}</td><td>{{ r.stage }} / {{ r.part_codes.join('、') }}</td><td>{{ r.required_for_cutting ? '是' : '否' }}</td><td>{{ r.theoretical_quantity }} {{ r.unit }}</td><td>{{ r.quantity }} {{ r.unit }}<p v-if="r.purchase_mode === 'no_purchase'">本次不采购：{{ r.no_purchase_reason }}</p></td><td>{{ r.replied_quantity }} / {{ r.awaiting_reply_quantity }} {{ r.unit }}</td><td><p v-for="(b, i) in data.batches.filter(b => b.row === r.row)" :key="i">{{ b.expected_date }} / {{ b.quantity }} {{ r.unit }} / {{ b.supplier }} / {{ b.purchase_reference }}</p><span v-if="r.purchase_mode === 'no_purchase'">无需采购交期</span><span v-else-if="!data.batches.some(b => b.row === r.row)">待回复</span></td></tr>
        </tbody></table></div>
        <template v-if="workspace.path === 'planning' && data?.planning">
          <CuttingProductionSummary v-if="access?.reporting_schema_ready && selected.current" :key="selected.current.version" :line-id="selected.line_id" />
          <CuttingPlanSummary v-if="data.planning.published" :plan="data.planning.published" title="当前发布计划" :stale="selected.planning_summary?.published_stale" />
          <CuttingPlanSummary v-if="data.planning.draft" :plan="data.planning.draft" title="待发布草稿" :stale="selected.planning_summary?.draft_stale" />
          <details v-if="data.planning.baseline"><summary>首次基准计划</summary><CuttingPlanSummary :plan="data.planning.baseline" title="首次基准" /></details>
        </template>
        <form v-if="action" ref="orderEditor" class="order-form" @submit.prevent="save">
          <h3 tabindex="-1">{{ action==='plan-publish'?publishLabel:action==='receive'?receiveLabel:labels[action] }}</h3>
          <fieldset :disabled="saving || !!pending">
            <CuttingPlanEditor v-if="action === 'plan' && data" v-model="planTasks" v-model:removed-task-reasons="removedTaskReasons" :data="data" :line-id="selected.line_id" />
            <CuttingPlanDiff v-if="adjustingPlan && data?.planning?.published" :previous="data.planning.published" :tasks="action === 'plan' ? planTasks : data.planning.draft?.tasks ?? []" :removed-reasons="action === 'plan' ? removedTaskReasons : data.planning.draft?.removed_task_reasons" />
            <p v-if="action === 'plan-publish'">发布当前草稿后形成新计划版本，首次基准和历史调整仍保留。预排不代表物料已可用或允许实际开工。</p>
            <p v-if="action==='plan-publish'&&publishLabel!=='发布生产预排'" class="cutting-notice">本次仅发布任务供领料使用，不增加已排期订单数，不生成日计划或完成数量。领料后调整已发布任务仍须填写原因。</p>
            <template v-if="action === 'bom'">
              <div class="order-toolbar"><label>BOM 编码／货号／名称／款式／颜色 <input :id="editorId('bom_query')" name="bom_query" v-model="bomQuery" maxlength="80" /></label><Button variant="outline" type="button" @click="searchBoms()">查找 BOM</Button></div>
              <ul><li v-for="b in bomRows" :key="b.id">{{ b.code }} · {{ b.data.name }} <Button variant="outline" type="button" @click="loadVersions(b.id)">查看发布版本</Button></li></ul>
              <div v-if="bomTotal" class="order-toolbar"><Button variant="outline" type="button" :disabled="bomPage <= 1" @click="searchBoms(bomPage-1)">BOM 上一页</Button><Button variant="outline" type="button" :disabled="bomPage*50 >= bomTotal" @click="searchBoms(bomPage+1)">BOM 下一页</Button></div>
              <ul><li v-for="b in versions" :key="b.version">{{ b.code }} V{{ b.version }} · {{ (b.data as BomData).item_no }} · {{ (b.data as BomData).style }} / {{ (b.data as BomData).color }} <Button variant="outline" type="button" @click="chosenBom = b">选择此发布版</Button></li></ul>
              <p v-if="versionId && !versions.length">此页没有发布版本。</p>
              <div v-if="versionId" class="order-toolbar"><Button variant="outline" type="button" :disabled="versionPage <= 1" @click="loadVersions(versionId, versionPage-1)">版本上一页</Button><Button variant="outline" type="button" :disabled="versionPage*50 >= versionTotal" @click="loadVersions(versionId, versionPage+1)">版本下一页</Button></div>
              <p>已选择：{{ chosenBom ? `${chosenBom.code} V${chosenBom.version}` : '尚未选择' }}。新发布版本不会自动替换本订单。</p>
              <label>裁床目标套数 <input :id="editorId('target_sets')" name="target_sets" v-model.number="targetSets" type="number" min="1" max="1000000000" step="1" required /></label>
              <label>数量口径／换算依据 <textarea :id="editorId('quantity_basis')" name="quantity_basis" v-model="quantityBasis" maxlength="500" required placeholder="确认订单数量是否为套；如换算，请填写依据" /></label>
              <label>BOM 对应依据 <textarea :id="editorId('bom_match_basis')" name="bom_match_basis" v-model="bomMatchBasis" maxlength="500" placeholder="订单货号与 BOM 货号不同时，必须说明对应依据" /></label>
            </template>
            <template v-if="action === 'requisition'">
              <p>逐行核定正式需求量。理论净用量不包含损耗，也未抵扣库存；请在提交依据中说明差异。</p>
              <div v-for="(r, i) in requirements" :key="i" class="demand-row">
                <p>{{ i+1 }} · {{ materialName(i) }} / {{ r.stage }} / {{ r.part_codes.join('、') }} · {{ r.required_for_cutting ? '裁剪必需' : '非当前必需' }} · 每套 {{ r.quantity_per_set }} {{ r.unit }}</p>
                <label>本次采购方式 <select :id="editorId('purchase_mode',i)" :name="`lines[${i}].purchase_mode`" v-model="demands[i]!.purchase_mode" :aria-label="`采购方式${i+1}`" @change="purchaseModeChanged(demands[i]!)"><option value="purchase">需要采购</option><option value="no_purchase">本次不采购</option></select></label>
                <label>需求数量 <input :id="editorId('demand_quantity',i)" :name="`lines[${i}].quantity`" v-model="demands[i]!.quantity" :readonly="demands[i]!.purchase_mode === 'no_purchase'" inputmode="decimal" required :aria-label="`需求数量${i+1}`" /> {{ r.unit }}</label>
                <label v-if="demands[i]!.purchase_mode === 'no_purchase'">不采购原因 <input :id="editorId('no_purchase_reason',i)" :name="`lines[${i}].no_purchase_reason`" v-model="demands[i]!.no_purchase_reason" maxlength="500" required :aria-label="`不采购原因${i+1}`" /></label>
              </div><p>“本次不采购”只说明采购安排，不代表已有库存、可用或到料。</p>
            </template>
            <template v-if="action === 'eta'">
              <p>保存将形成新的完整交期版本；未覆盖数量仍待回复。删除批次只修订预计交期，不撤销采购单。</p>
              <div v-for="(b, i) in batches" :key="i" class="eta-row">
                <label>需求行 <select :id="editorId('batch_row',i)" :name="`batches[${i}].row`" v-model.number="b.row"><option v-for="r in data?.requisition?.lines.filter(r => r.purchase_mode !== 'no_purchase')" :key="r.row" :value="r.row">{{ r.row+1 }} · {{ r.material.code }} {{ r.material.name }} / {{ r.stage }} / {{ r.part_codes.join('、') }} / {{ r.unit }}</option></select></label>
                <label>批次数量 <input :id="editorId('batch_quantity',i)" :name="`batches[${i}].quantity`" v-model="b.quantity" inputmode="decimal" required /></label>
                <label>预计到料 <input :id="editorId('expected_date',i)" :name="`batches[${i}].expected_date`" v-model="b.expected_date" type="date" required /></label>
                <label>供应商 <input :id="editorId('supplier',i)" :name="`batches[${i}].supplier`" v-model="b.supplier" maxlength="120" required /></label>
                <label>采购来源单号 <input :id="editorId('purchase_reference',i)" :name="`batches[${i}].purchase_reference`" v-model="b.purchase_reference" maxlength="120" required /></label>
                <Button variant="outline" type="button" @click="batches.splice(i, 1)">移除此批次</Button>
              </div><Button variant="outline" type="button" @click="addBatch">增加交期批次</Button>
            </template>
            <p v-if="action === 'withdraw'">申请后暂停原需求交期办理。无论是否填写过交期，都须由采购确认旧需求处置；核对完成后可修订数量、BOM 并重新提交。</p>
            <template v-if="action === 'reconcile'">
              <label :for="editorId('disposition')">旧采购处理结果
                <select :id="editorId('disposition')" name="disposition" v-model="disposition" required :aria-describedby="hasPurchaseEvidence ? editorId('disposition-help') : undefined">
                  <option value="" disabled>请选择核对结果</option>
                  <option value="not_ordered" :disabled="hasPurchaseEvidence">已核实整张旧需求尚未采购</option>
                  <option value="cancelled_or_reallocated">旧采购已取消／转用并完成核对</option>
                </select>
              </label>
              <p v-if="hasPurchaseEvidence" :id="editorId('disposition-help')" class="cutting-notice">原需求已有采购交期记录，不能选择「尚未采购」。请核对取消或转用凭据后，再选择处理结果。</p>
              <details v-if="hasPurchaseEvidence && selected.pending_purchase">
                <summary>查看原交期凭据</summary>
                <CuttingPurchaseReplyEvidence :purchase="selected.pending_purchase" />
              </details>
              <label>处置依据 <textarea :id="editorId('evidence')" name="evidence" v-model="evidence" minlength="4" maxlength="500" required placeholder="注明核对人、原采购单号、取消／转用凭据及数量；不得遗留未处理承诺量" /></label>
              <label><input :id="editorId('all_handled')" name="all_handled" v-model="allHandled" type="checkbox" required />确认整张旧需求均已核对处置，没有未处理采购承诺；此处不会自动操作外部采购单。</label>
            </template>
            <label v-if="adjustingPlan" :for="editorId('reason')">已发布计划调整原因 <textarea :id="editorId('reason')" name="reason" v-model="reason" maxlength="500" required /></label>
            <p v-if="adjustingPlan">本次调整将形成新版本，首次基准和原发布版本保留；发布时带入已保存的调整原因，可核对修改。</p>
            <label v-else-if="action !== 'plan' && action !== 'plan-publish'" :for="editorId('reason')">本次操作依据 <textarea :id="editorId('reason')" name="reason" v-model="reason" maxlength="500" required /></label>
            <Button type="submit">确认保存</Button><Button variant="outline" type="button" @click="cancel">取消编辑</Button>
          </fieldset>
        </form>
        <div class="order-toolbar"><Button variant="outline" :disabled="!selected.current" @click="loadHistory()">查看历史版本</Button><template v-if="historyTotal"><Button variant="outline" :disabled="historyPage <= 1" @click="loadHistory(historyPage-1)">历史上一页</Button><span>{{ historyPage }} / {{ Math.ceil(historyTotal/50) }}</span><Button variant="outline" :disabled="historyPage*50 >= historyTotal" @click="loadHistory(historyPage+1)">历史下一页</Button></template></div>
        <details v-for="r in history" :key="r.version"><summary>V{{ r.version }} · <time :datetime="r.created_at">{{ orderHistoryTime(r.created_at) }}</time> · {{ r.actor_id==='system:cutting-auto-receipt'?'系统':r.actor_id }} · {{ r.reason }}</summary>
          <CuttingOrderReceipt v-if="r.data.receipt?.mode === 'note_only'" :receipt="r.data.receipt" :record-version="r.version" />
          <p>订单：{{ r.data.order.reference_no }} / {{ r.data.order.product_no }} · 订单数量 {{ r.data.order.quantity }} · {{ r.data.order.status === 'cancelled' ? '已取消' : '有效' }}</p>
          <p>货名：{{ orderProductName(r.data.order) }} · 款式分类：<span :title="unclassifiedStyleHint">{{ unclassifiedStyle }}</span></p>
          <p>BOM：{{ r.data.bom ? `${r.data.bom.code} V${r.data.bom.version}` : '未关联' }} · 目标 {{ r.data.target_sets ?? '待确认' }} 套 · {{ r.data.quantity_basis }} · {{ r.data.bom_match_basis }}</p>
          <CuttingPlanSummary v-if="r.data.planning?.published" :plan="r.data.planning.published" title="该版本发布计划" />
          <CuttingPlanSummary v-if="r.data.planning?.draft" :plan="r.data.planning.draft" title="该版本计划草稿" />
          <p v-if="r.data.purchase_reconciliation_required">旧采购需求待核对</p>
          <p v-if="r.data.reconciliation_request">申请依据：{{ r.data.reconciliation_request.reason }}</p><p v-if="r.data.reconciliation">需求 V{{ r.data.reconciliation.requisition_version }} 采购核对依据：{{ r.data.reconciliation.evidence }}</p>
          <ul><li v-for="line in r.data.requisition?.lines" :key="line.row">{{ line.row+1 }} · {{ line.material.name }} / {{ line.stage }} · 需求 {{ line.quantity }} {{ line.unit }}<span v-if="line.purchase_mode === 'no_purchase'"> · 本次不采购：{{ line.no_purchase_reason }}</span></li></ul>
          <ul><li v-for="(batch, i) in r.data.batches" :key="i">需求行 {{ batch.row+1 }} · {{ batch.expected_date }} / {{ batch.quantity }} / {{ batch.supplier }} / {{ batch.purchase_reference }}</li></ul>
        </details>
      </SectionPanel>
      </div>
    </template>
  </section>
</template>

<style scoped>
.order-toolbar { display: flex; align-items: end; flex-wrap: wrap; gap: .75rem; margin: 1rem 0; }
.order-filters { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 180px), 1fr)); align-items: end; gap: 12px; margin: 0; }
.order-filter-field { display: flex; flex-direction: column; gap: 6px; min-width: 0; font-size: 14px; line-height: 20px; font-weight: 500; }
.order-filter-control { width: 100%; min-width: 0; height: 36px; border: 1px solid var(--input); border-radius: var(--radius); padding: 6px 10px; background: var(--card); color: var(--foreground); font-size: 14px; font-weight: 400; }
.order-filter-control::placeholder { color: var(--muted-foreground); }
.order-query-button { justify-self: start; }
.order-ledger-grid { overflow: hidden; border: 1px solid var(--border); border-radius: var(--radius); }
.order-ledger-table { min-width: 900px; font-size: 14px; line-height: 20px; }
.order-ledger-table tbody tr:last-child td { border-bottom: 0; }
.order-ledger-table tbody tr:hover { background: var(--muted); }
.order-cell-note { margin-top: 6px; color: var(--muted-foreground); font-size: 12px; line-height: 18px; }
.order-ledger-empty { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 36px 20px; text-align: center; color: var(--muted-foreground); font-size: 14px; line-height: 22px; }
.order-empty-title { color: var(--foreground); font-weight: 600; }
.order-pagination { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; margin-top: 16px; color: var(--muted-foreground); font-size: 13px; }
.order-pagination-actions { display: flex; align-items: center; gap: 8px; }
@media (max-width: 639px) {
  .order-filter-control { height: 44px; }
  .order-ledger :deep([data-slot='button']) { min-height: 44px; }
  .order-query-button { width: 100%; }
}
.order-form { border-top: 1px solid var(--border); margin-top: 1rem; padding-top: 1rem; }
.order-form fieldset { border: 0; display: grid; gap: 1rem; padding: 0; }
.eta-row { display: flex; flex-wrap: wrap; gap: .75rem; padding: .75rem; background: var(--muted); }
pre { max-height: 24rem; overflow: auto; white-space: pre-wrap; word-break: break-word; }
</style>
