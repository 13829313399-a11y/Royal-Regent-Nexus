<script setup lang="ts">
import { computed, shallowRef, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter, onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { ArrowUpRight, ClipboardList, Info, FileText } from '@lucide/vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { Button } from '@/components/ui/button'
import DateRangeFilter from '@/components/DateRangeFilter.vue'
import CartonSelectionSummary from '@/components/CartonSelectionSummary.vue'
import type { DateRange } from 'reka-ui'
import FabricProcurementWorkspace from './FabricProcurementWorkspace.vue'
import FabricDashboard from './FabricDashboard.vue'
import FabricReceivingRecords from './FabricReceivingRecords.vue'
import FabricMasterWorkspace from './FabricMasterWorkspace.vue'
import SemiLocationWorkspace from './SemiLocationWorkspace.vue'
import FabricSourcePlaceholder from './FabricSourcePlaceholder.vue'
import FabricMonthlyWorkspace from './FabricMonthlyWorkspace.vue'
import FabricOrderSummary from './FabricOrderSummary.vue'
import FabricInventorySetup from './FabricInventorySetup.vue'
import FabricActivityLog from './FabricActivityLog.vue'
import WarehouseOperationsWorkspace from './WarehouseOperationsWorkspace.vue'
import { operationsView } from './operations'
import WarehouseDocumentPreview from '@/features/warehouse-foundation/WarehouseDocumentPreview.vue'
import { warehouseDocumentSpec, type WarehousePreviewKind } from './documentPreviews'
import { FABRIC_RECORD_KIND_BY_VIEW, WAREHOUSE_FACTORY, warehousePath, type WarehouseWorkspace, type WarehouseSection, type WarehouseView } from './navigation'

const props = defineProps<{ warehouse: WarehouseWorkspace; section: WarehouseSection; rememberedView?: string }>()
const emit = defineEmits<{ viewChange: [path: string, view: string] }>()
const route = useRoute()
const router = useRouter()
const dates = shallowRef<DateRange>({ start: undefined, end: undefined })
const currentView = computed(() => {
  const requestedId = route.query.view === undefined ? props.rememberedView : route.query.view
  const id = props.warehouse.id === 'fabric-warehouse' && props.section.path === 'inventory' && typeof requestedId === 'string' && FABRIC_RECORD_KIND_BY_VIEW[requestedId] ? 'movements' : requestedId
  const fallback = props.warehouse.id === 'fabric-warehouse' && props.section.path === 'receipts'
    ? props.section.views.find(view => view.id === 'pending')! : props.section.views[0]!
  return props.section.views.find(view => view.id === id) ?? fallback
})
watch(() => currentView.value.id, id => emit('viewChange', warehousePath(props.warehouse, props.section.path), id), { immediate: true })
function selectView(view: WarehouseView) {
  if (currentView.value.id === view.id && !route.query.source) return
  return router.push({ path: route.path, query: { ...route.query, view: view.id, source: undefined, ...(fabricInventory.value ? { kind: undefined, record: undefined } : {}) } })
}
async function selectMobileView(event: Event) {
  const select = event.target as HTMLSelectElement
  const view = props.section.views.find(item => item.id === select.value)
  try { if (view) await selectView(view) }
  finally { select.value = currentView.value.id }
}
const semi = computed(() => props.warehouse.id === 'semi-finished-warehouse')
const liveOperations = computed(() => operationsView(semi.value ? 'semi' : 'fabric', props.section.path, currentView.value.id))
const inventoryPage = computed(() => props.section.path === 'inventory')
const fabricInventory = computed(() => inventoryPage.value && !semi.value)
const fabricActivity = computed(() => !semi.value && props.section.path === 'activity')
const fabricExceptions = computed(() => !semi.value && props.section.path === 'exceptions')
const navigationViews = computed(() => fabricInventory.value
  ? ['stock', 'order-summary', 'movements', 'pending-issues', 'opening', 'stocktake'].map(id => {
    const view = props.section.views.find(item => item.id === id)!
    return id === 'movements' ? { ...view, title: '收发记录' } : view
  }) : props.section.views)
function navigationActive(id: string) { return currentView.value.id === id }
const fabricReceipts = computed(() => !semi.value && props.section.path === 'receipts')
const masterMode = computed(() => !semi.value && props.section.path === 'master')
const monthlyView = computed(() => !semi.value && props.section.path === 'closing' && ['monthly', 'reconciliation', 'recipients'].includes(currentView.value.id) ? currentView.value.id as 'monthly' | 'reconciliation' | 'recipients' : undefined)
const fabricClosing = computed(() => !semi.value && props.section.path === 'closing')
const fabricClosingRecords = computed(() => !semi.value && props.section.path === 'closing' && currentView.value.id === 'records')
const semiLocations = computed(() => semi.value && props.section.path === 'master' && currentView.value.id === 'locations')
const sourcePlaceholder = computed(() => fabricReceipts.value && currentView.value.id === 'procurement-interface' ? 'interface' : undefined)
const previewKind = ref<WarehousePreviewKind>()
const preview = ref<InstanceType<typeof WarehouseDocumentPreview>>()
const previewSpec = computed(() => warehouseDocumentSpec(semi.value, previewKind.value ?? 'receipt'))
function leavePreview() {
  return !preview.value?.hasChanges() || window.confirm('当前填写仅用于预览，离开后将清空。确定离开？')
}
onBeforeRouteLeave(leavePreview)
onBeforeRouteUpdate(leavePreview)
watch(() => route.fullPath, () => { previewKind.value = undefined })
const previewActions = computed<{ kind: WarehousePreviewKind; label: string }[]>(() => {
  if (props.section.path === 'overview') return [{ kind: 'receipt', label: '预览收料单' }, { kind: 'issue', label: '预览发料单' }, { kind: 'stock', label: '预览库存详情' }]
  if (props.section.path === 'receipts') return [{ kind: 'receipt', label: '预览收料单' }]
  if (props.section.path === 'inventory') return [{ kind: 'stock', label: '预览库存详情' }, { kind: 'issue', label: '预览发料单' }]
  return []
})
const procurementMode = computed(() => {
  if (semi.value) return undefined
  if (props.section.path === 'receipts' && currentView.value.id === 'pending') return 'pending'
  if (props.section.path === 'receipts' && currentView.value.id === 'import-review') {
    return route.query.source === 'all' ? 'orders' : route.query.source === 'returned' ? 'returned' : 'import'
  }
  return undefined
})
const receivingMode = computed(() => {
  if (semi.value) return undefined
  if (props.section.path === 'receipts' && currentView.value.id === 'history') return 'receipts'
  if (props.section.path === 'inventory' && currentView.value.id === 'stock') return 'stock'
  if (props.section.path === 'inventory' && currentView.value.id === 'movements') return 'movements'
  return undefined
})
const filters = computed(() => {
  const id = currentView.value.id
  switch (props.section.path) {
    case 'orders': return id === 'demand' ? ['合同号', '物料', '跟进状态'] : id === 'purchases' ? ['供应商', semi.value ? '配件' : '物料', '到货状态'] : ['加工方', '工序', '办理状态']
    case 'receipts': return id === 'import-review' ? ['来源', '校验状态', '核对状态'] : [semi.value ? '加工方 / 供应商' : '供应商', '来源单据', id === 'history' || id === 'processing-returns' ? '质量状态' : '办理状态']
    case 'inventory': {
      if (id === 'processing') return ['加工方', '加工工序', '办理状态']
      if (id === 'packaging') return ['包装车间', '加工状态', '交接状态']
      if (id === 'pending-issues') return ['领用方', '用途', '办理状态']
      if (id === 'issues') return ['领料方', '仓位', '用途']
      if (id === 'returns') return ['退回方', '仓位', '质量状态']
      if (id === 'movements') return ['业务类型', '仓库 / 仓位', '经办人']
      return ['仓库', '仓位', id === 'stocktake' ? '盘点状态' : semi.value ? '加工状态' : '质量状态']
    }
    case 'exceptions': return ['异常类型', '责任人', '处理状态']
    case 'closing': return ['核对月份', '往来单位', '核对状态']
    case 'master': return ['资料类型', '启用状态']
    case 'activity': return ['操作人', '业务类型', '操作']
    default: return []
  }
})
const inventoryDates: Record<string, string> = { stock: '最近入库日期', 'pending-issues': '要求发料日期', issues: '发料日期', processing: '要求回期', packaging: '交接日期', summary: '统计期间', movements: '业务日期', returns: '退料日期', transfers: '移库日期', stocktake: '盘点日期' }
const dateLabel = computed(() => {
  switch (props.section.path) {
    case 'orders': return currentView.value.id === 'demand' ? '要求用料日期' : semi.value && currentView.value.id !== 'purchases' ? '要求回货日期' : '约定到货日期'
    case 'receipts': return currentView.value.id === 'import-review' ? '导入日期' : currentView.value.id === 'pending' ? '预计到货 / 回货日期' : '收货日期'
    case 'inventory': return inventoryDates[currentView.value.id]
    case 'exceptions': return '登记日期'
    case 'activity': return '操作日期'
    default: return undefined
  }
})
</script>

<template>
  <section class="warehouse-page" :class="{ 'fabric-receipts-page': fabricReceipts, 'fabric-master-page': masterMode, 'warehouse-inventory-page': inventoryPage, 'fabric-inventory-page': fabricInventory || fabricExceptions || fabricClosing }">
    <FabricDashboard v-if="!semi && section.path === 'overview'">
      <details class="fabric-receiving-help"><summary><FileText :size="17" />查看单据字段样式</summary><div class="fabric-receiving-help-content"><p>样式预览只用于查看字段。</p><Button v-for="action in previewActions" :key="action.kind" variant="outline" size="sm" @click="previewKind = action.kind">{{ action.label }}</Button></div></details>
    </FabricDashboard>
    <template v-else>
    <h1 v-if="fabricReceipts || masterMode || inventoryPage || fabricExceptions || fabricActivity || fabricClosing" class="sr-only">{{ section.title }}</h1>
    <header v-else class="warehouse-heading">
      <div><p class="warehouse-eyebrow">华康 C / {{ warehouse.title }}</p><h1>{{ section.title }}</h1><p>{{ section.description }}</p></div>
      <StatusPill :label="monthlyView ? '数量对账已接入' : masterMode || semiLocations ? '基础资料已启用' : sourcePlaceholder ? '入口预留 · 待接入' : liveOperations ? '收发与交接' : procurementMode || receivingMode ? '采购来源与实际入库已接入' : '待建设'" :tone="monthlyView || liveOperations || procurementMode || receivingMode || masterMode || semiLocations ? 'teal' : 'amber'" />
    </header>
    <div v-if="!fabricClosing && !fabricReceipts && !masterMode && !semiLocations && !liveOperations && !monthlyView && !['order-summary', 'opening', 'stocktake'].includes(currentView.id)" class="warehouse-notice" role="note"><Info :size="18" aria-hidden="true" /><p>{{ semi ? '加工任务、实收、加工发回和包装交接可在对应栏目登记。当前栏目尚待建设。' : '采购实收、出库、退料和调仓分别留痕。数量汇总、期初库存与盘点已开放；计价和正式月结确认尚待建设。' }}</p></div>

    <details v-if="previewActions.length && !fabricReceipts && !inventoryPage" class="fabric-receiving-help"><summary><FileText :size="17" />查看单据字段样式</summary><div class="fabric-receiving-help-content"><p>样式预览只用于查看字段；实际登记请使用下方业务操作。</p><Button v-for="action in previewActions" :key="action.kind" variant="outline" size="sm" @click="previewKind = action.kind">{{ action.label }}</Button></div></details>

    <template v-if="section.path === 'overview'">
      <section class="warehouse-panel warehouse-pending" aria-label="仓库待办入口">
        <div class="warehouse-pending-heading"><div><h2>仓库待办 · 先看这里</h2><p>按事项进入对应业务分区；待办数据接通后展示实际记录。</p></div><StatusPill label="待办待接入" tone="amber" /></div>
        <div class="warehouse-shortcuts">
          <RouterLink v-for="item in warehouse.pending" :key="item.title" :to="{ path: warehousePath(warehouse, item.section), query: { factory: WAREHOUSE_FACTORY, view: item.view } }">
            <div><h3>{{ item.title }}</h3><ArrowUpRight :size="18" aria-hidden="true" /></div><p>{{ item.description }}</p><span>{{ !semi && item.section === 'receipts' ? '查看采购来源' : '查看工作区' }}</span>
          </RouterLink>
        </div>
      </section>
      <section class="warehouse-panel warehouse-flow" aria-label="仓库业务流程"><h2>收发业务链</h2><ol><li v-for="(step, index) in warehouse.flow" :key="step"><span>{{ String(index + 1).padStart(2, '0') }}</span><strong>{{ step }}</strong></li></ol></section>
    </template>

    <section class="warehouse-panel" :class="{ 'fabric-receipts-panel': fabricReceipts, 'fabric-master-panel': masterMode }" :aria-label="section.title">
      <div :class="{ 'fabric-receipts-navigation': fabricReceipts || masterMode || fabricInventory || fabricExceptions || fabricClosing, 'fabric-inventory-navigation': fabricInventory || fabricExceptions || fabricClosing }">
      <div v-if="section.views.length > 1" class="warehouse-tabs" role="group" aria-label="业务分区">
        <button v-for="item in navigationViews" :key="item.id" type="button" :aria-pressed="navigationActive(item.id)" @click="selectView(item)">{{ item.title }}</button>
      </div>
      <label v-if="section.views.length > 1" class="warehouse-mobile-view">当前业务分区<select :value="currentView.id" aria-label="选择业务分区" @change="selectMobileView"><option v-for="item in navigationViews" :key="item.id" :value="item.id">{{ item.title }}</option></select></label>
      <details v-if="fabricReceipts" class="fabric-receiving-help">
        <summary><Info :size="15" aria-hidden="true" />收料说明</summary>
        <div class="fabric-receiving-help-content">
          <strong>按本次实物登记入库</strong>
          <p>正常采购与补数统一追货。导入订单和采购历史不增加库存；保存本次实收后增加对应批次库存。</p>
          <p>供应商上传的送货单可从“送货单入库”列表打开，也可用“扫码入库”快速定位。核对本次实物后才确认入库；选择对应采购待收明细后按实收量同步扣减欠货，同一批货只登记一次；缺少匹配采购来源时会明确提示。</p>
          <p>实收入库后在库存台账办理出库、退料和调仓，在月结对账统一汇总数量。质检由 QC 负责；历史期初在库存管理中导入，正式月结确认尚未开放。</p>
          <div class="fabric-receiving-preview"><span>单据样式预览 · 不保存业务</span><Button v-for="action in previewActions" :key="action.kind" variant="outline" size="sm" @click="previewKind = action.kind">{{ action.label }}</Button></div>
        </div>
      </details>
      <details v-if="fabricClosing" class="fabric-receiving-help"><summary><Info :size="15" />对账说明</summary><div class="fabric-receiving-help-content"><strong>按实际收发核对当月数量</strong><p>收发数量汇总看全貌，供应商收料和领用方发料分别核对；不同单位不相加。采购实收归入手动，车间退料扣减净发料，冲销按更正发生月份扣回。</p><p>期初库存、盘点和调仓不计入供应商进货或车间领料；库存结余到库存管理查看。参考价格保留原单依据，不计算应付金额。</p><p>裁床接口领料 · 待接入。供应商双方确认、应付结算和正式月结记录尚未开放。</p></div></details><details v-if="fabricExceptions" class="fabric-receiving-help"><summary><Info :size="15" />处理说明</summary><div class="fabric-receiving-help-content"><strong>按原业务核对，再办理更正</strong><p>录错数量或仓位时，从原入库单或收发记录发起冲销；核对原因、确认整单后保留原记录。</p><p>正常分批到货继续在待收料追货，车间退料在库存管理办理。物料缺资料到基础资料补齐。质量问题由 QC 负责，本页可查看历史受限批次，调仓不会解除限制。</p><p>短收、超收、责任分派与处理关闭的独立异常流程尚未接入。</p></div></details>
      <details v-if="masterMode" class="fabric-receiving-help"><summary><Info :size="15" />资料说明</summary><div class="fabric-receiving-help-content"><strong>基础资料已启用 · 先满足仓库收发</strong><p>仓库与仓位由仓库日常维护。工程、采购模块接入前，物料、计量单位和供应商资料先在这里补齐；当前供应商资料不包含客户或内部领料部门。</p><p>物料先确认编码、名称、分类和库存单位；规格、颜色、材质按已确认资料补充。供应商固定编号用于送货识别、专用入口和收料对账。单位换算只保存有依据的资料，不自动换算收发数量。</p><p>后续衔接工程和采购资料时，应沿用已有编号及对应关系，避免重复建档。资料可修改、停用，导入候选须人工确认后启用；历史单据保留当时资料。</p></div></details>
      </div>
      <div :class="{ 'fabric-receipts-content': fabricReceipts, 'fabric-master-content': masterMode, 'fabric-inventory-content': fabricInventory || fabricExceptions || fabricClosing }">
      <FabricActivityLog v-if="fabricActivity" />
      <FabricInventorySetup v-else-if="fabricInventory && (currentView.id === 'opening' || currentView.id === 'stocktake')" :key="currentView.id" :mode="currentView.id" />
      <FabricOrderSummary v-else-if="!semi && section.path === 'inventory' && currentView.id === 'order-summary'" />
      <WarehouseOperationsWorkspace v-else-if="liveOperations" :warehouse="semi ? 'semi' : 'fabric'" :section="section.path" :view="currentView.id" :title="currentView.title" :description="currentView.description" />
      <FabricProcurementWorkspace v-else-if="procurementMode" :mode="procurementMode" :tracking="typeof route.query.tracking === 'string' ? route.query.tracking : undefined" :order-no="typeof route.query.order_no === 'string' ? route.query.order_no : undefined" />
      <FabricReceivingRecords v-else-if="receivingMode" :mode="receivingMode" />
      <SemiLocationWorkspace v-else-if="semiLocations" /><FabricMasterWorkspace v-else-if="masterMode" :view="currentView.id" />
      <FabricSourcePlaceholder v-else-if="sourcePlaceholder" :mode="sourcePlaceholder" />
      <FabricMonthlyWorkspace v-else-if="monthlyView" :view="monthlyView" />
      <section v-else-if="fabricClosingRecords" class="fabric-closing-pending"><header class="warehouse-table-heading"><div><h2>月结记录</h2><p>正式月结确认与历史版本尚未开放。</p></div><StatusPill label="待开放" tone="amber" /></header><div class="warehouse-empty" role="status"><ClipboardList :size="30" aria-hidden="true" /><h3>当前可先核对、导出当月收发数量</h3><p>正式关账需要保存核对版本、确认人及差异处理依据，目前还不能确认或锁定月份。</p><Button variant="outline" @click="selectView(section.views[0]!)">查看收发数量汇总</Button></div></section><template v-else>
      <div class="warehouse-table-heading"><div><h2>{{ currentView.title }}</h2><p>{{ currentView.description }}</p></div></div>
      <div v-if="section.path !== 'overview'" class="warehouse-list-toolbar">
        <p class="warehouse-toolbar-note">筛选与操作预览 · 接通业务数据后可用</p>
        <fieldset class="warehouse-filter-fields" disabled aria-label="筛选预览，业务数据待接入">
          <label v-if="!fabricClosingRecords" class="warehouse-keyword">查找记录<input type="search" :placeholder="semi ? '单据 / 生产单 / 产品款式' : '单据 / 放产单 / 物料编码'" :aria-label="`${currentView.title}关键字筛选`" /></label>
          <label v-for="filter in filters" :key="filter">{{ filter }}<select :aria-label="`${currentView.title}${filter}筛选`"><option>全部{{ filter }}</option></select></label>
          <div v-if="dateLabel" class="warehouse-date-filter"><span>{{ dateLabel }}</span><DateRangeFilter v-model="dates" :label="`${currentView.title}日期范围`" /></div>
          <label>排序<select :aria-label="`${currentView.title}排序`"><option>默认顺序</option><option>编号顺序</option><option v-if="dateLabel">日期由早到晚</option><option v-if="dateLabel">日期由晚到早</option></select></label>
          <Button variant="outline" size="sm" disabled>清空筛选</Button>
        </fieldset>
        <div class="warehouse-actions"><Button v-for="action in currentView.actions" :key="action" variant="outline" size="sm" disabled :title="`${action}待接入业务功能`">{{ action }}</Button></div>
        <CartonSelectionSummary :rows="[]" :visible-ids="[]" />
      </div>
      <div class="warehouse-table-scroll" tabindex="0" role="region" :aria-label="`${currentView.title}字段预览，可横向滚动`">
        <table><caption class="sr-only">{{ currentView.title }}字段预览，非实际业务记录</caption><thead><tr><th v-for="column in currentView.columns" :key="column" scope="col">{{ column }}</th></tr></thead><tbody /></table>
      </div>
      <div class="warehouse-empty" role="status"><ClipboardList :size="30" aria-hidden="true" /><h3>{{ currentView.title }}待接入</h3><p>接通业务数据后，在这里查看和办理。当前没有加载记录，不代表实际数量为零。</p></div>
      <footer v-if="section.path !== 'overview'" class="warehouse-list-footer"><span>业务记录未接入 · 分页待开放</span><div><Button variant="outline" size="sm" disabled>上一页</Button><Button variant="outline" size="sm" disabled>下一页</Button></div></footer>
      </template>
      </div>
    </section>
    <p v-if="!fabricReceipts && !inventoryPage && !fabricExceptions && !fabricClosing" class="warehouse-footnote">{{ warehouse.title }}独立管理收发和库存 · 来源单据贯穿订单、收料、发料与对账</p>
    </template>
    <WarehouseDocumentPreview v-if="previewKind" :key="`${warehouse.id}:${previewKind}`" ref="preview" :spec="previewSpec" :warehouse-title="warehouse.title" @close="previewKind = undefined" />
  </section>
</template>
