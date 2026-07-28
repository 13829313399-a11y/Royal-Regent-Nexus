<script setup lang="ts">
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  Download,
  FileClock,
  FileSpreadsheet,
  LockKeyhole,
  Rocket,
  Ship,
} from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { ApiInternalQuoteVersionComparison } from '@/api/internalQuote'
import { getFactoryScopedRoute, isFactoryContextId } from '@/data/enterpriseMock'
import { isForeignFactory, isInternalQuoteReadOnly } from '@/lib/internalQuoteAccess'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import type { InternalQuoteSectionStatus } from '@/types/internalQuoteDesk'

const route = useRoute()
const router = useRouter()
const quoteStore = useInternalQuoteDeskStore()
const authStore = useAuthStore()
const appStore = useAppStore()
const message = ref('')
const errorMessage = ref('')
const finalRejectOpen = ref(false)
const finalReason = ref('')
const finalRejectError = ref('')
const versionBaseId = ref('')
const comparison = ref<ApiInternalQuoteVersionComparison>()
const quoteId = computed(() => String(route.params.quoteId ?? ''))
const loadedQuote = computed(() => quoteStore.getQuoteById(quoteId.value))
const quote = computed(() => loadedQuote.value ?? quoteStore.placeholderQuote)
const selectedFactoryId = computed(() => appStore.activeFactory.id === 'group'
  ? appStore.activeProductionFactory.id
  : appStore.activeFactory.id)
const totalHkd = computed(() => quote.value.factoryPriceHkd)
const participatingSections = computed(() => quote.value.sections.filter((section) => section.isRequired))
const missingSections = computed(() => participatingSections.value.filter((section) => !['approved', 'not_applicable'].includes(section.status)))
const allSectionsReady = computed(() => missingSections.value.length === 0)
const isReleased = computed(() => ['released', 'exported'].includes(quote.value.status))
const canExport = computed(() => authStore.can('internal_quote:export', quote.value.factoryId, 'sales-business'))
const canOpenExport = computed(() => isReleased.value && canExport.value)
const canFinalSubmit = computed(() => authStore.can('internal_quote:final_submit', quote.value.factoryId, 'sales-business'))
const canFinalApprove = computed(() => authStore.can('internal_quote:final_approve', quote.value.factoryId, 'sales-business'))
const salesSection = computed(() => quote.value.sections.find((section) => section.code === 'sales'))
const responsibleFollowupId = computed(() => salesSection.value?.submittedById || quote.value.createdById)
const canResponsibleRelease = computed(() => (
  canFinalSubmit.value
  && Boolean(responsibleFollowupId.value)
  && responsibleFollowupId.value === authStore.currentUser?.id
))
const isReadOnly = computed(() => isInternalQuoteReadOnly(authStore, quote.value.factoryId))
const isForeignQuote = computed(() => isForeignFactory(authStore, quote.value.factoryId))
const isForeignReadOnly = computed(() => isReadOnly.value && isForeignQuote.value)
const getQuoteRoute = (path: string) => getFactoryScopedRoute(
  path,
  isFactoryContextId(quote.value.factoryId) ? quote.value.factoryId : 'huaxing',
)
const versionCandidates = computed(() => quoteStore.versionCandidates[quote.value.id] ?? [])
const componentLabels: Record<string, string> = {
  molding_hkd: '啤机', painting_hkd: '喷油', electronic_hkd: '电子', hardware_hkd: '五金', auxiliary_hkd: '辅料',
  packaging_material_hkd: '包装材料', assembly_hkd: '组装人工', packing_labor_hkd: '包装人工', indonesia_freight_hkd: '印尼运费',
  slush_hkd: '搪胶', sewing_hkd: '车缝', hair_hkd: '车发', carton_hkd: '纸箱',
}
const costColors = ['#0f766e', '#14b8a6', '#2563eb', '#7c3aed', '#d97706', '#dc2626', '#0891b2', '#65a30d', '#475569', '#c2410c', '#0d9488', '#64748b']
const departmentColors: Record<string, string> = {
  sales: '#0f766e', engineering: '#2563eb', electronic: '#7c3aed', molding: '#d97706',
  painting: '#dc2626', slush: '#0891b2', sewing: '#65a30d', hair: '#c2410c', assembly: '#475569',
}
const componentEntries = computed(() => Object.entries(quote.value.summaryComponents)
  .map(([key, amount], index) => ({ key, label: componentLabels[key] ?? key, amount, color: costColors[index % costColors.length] }))
  .filter((item) => item.amount !== 0))
const departmentEntries = computed(() => quote.value.sections.map((section, index) => ({
  key: section.code,
  label: section.label,
  amount: section.isRequired && section.calculationStatus === 'valid' ? section.totalHkd : 0,
  color: departmentColors[section.code] ?? costColors[index % costColors.length],
  isRequired: section.isRequired,
})))
function distributionDonutStyle(entries: Array<{ amount: number; color: string }>) {
  const total = entries.reduce((sum, item) => sum + Math.max(item.amount, 0), 0)
  if (!total) return { background: 'conic-gradient(#cbd5e1 0 100%)' }
  let cursor = 0
  const stops = entries.filter((item) => item.amount > 0).map((item) => {
    const start = cursor
    cursor += Math.max(item.amount, 0) / total * 100
    return `${item.color} ${start.toFixed(2)}% ${cursor.toFixed(2)}%`
  })
  return { background: `conic-gradient(${stops.join(',')})` }
}
const componentDonutStyle = computed(() => distributionDonutStyle(componentEntries.value))
const departmentDonutStyle = computed(() => distributionDonutStyle(departmentEntries.value))
const departmentTotalHkd = computed(() => departmentEntries.value.reduce((sum, item) => sum + item.amount, 0))
const costSummary = computed(() => quote.value.rr2CostSummary)
const shippingPricing = computed(() => costSummary.value.shippingPricing)

function summaryValue(value: number, format?: string, blankWhenZero = false) {
  if (blankWhenZero && value === 0) return ''
  return format === 'percent' ? `${value.toFixed(1)}%` : value.toFixed(4)
}

const directLaborKeys = new Set(['injection_labor', 'painting_labor', 'paint_material', 'assembly_labor'])

const statusMeta: Record<InternalQuoteSectionStatus, { label: string; tone: string }> = {
  draft: { label: '草稿', tone: 'slate' },
  pending_review: { label: '待审核', tone: 'amber' },
  approved: { label: '已通过', tone: 'green' },
  rejected: { label: '已退回', tone: 'red' },
  na_pending: { label: '不适用待审', tone: 'amber' },
  not_applicable: { label: '不适用', tone: 'slate' },
}

async function runFinalAction() {
  message.value = ''
  errorMessage.value = ''
  try {
    if (canOpenExport.value) {
      void router.push(getQuoteRoute(`/modules/sales-business/internal-quote-desk/${quote.value.id}/export`))
      return
    }
    if (isReleased.value && !canExport.value) {
      throw new Error(isForeignQuote.value ? '跨厂报价仅供查看，不能导出。' : '当前账号没有受控导出权限。')
    }
    if (quote.value.status === 'fully_approved') {
      if (!canResponsibleRelease.value) throw new Error('仅负责本单的业务跟客可确认最终放行。')
      await quoteStore.submitFinal(quote.value.id, quote.value.headerRevision)
      message.value = '负责跟客已确认最终放行，P4 受控文件和客价交接 artifact 已由服务端生成。'
      return
    }
    if (quote.value.status === 'final_pending') {
      if (!canResponsibleRelease.value) throw new Error('仅负责本单的业务跟客可确认最终放行。')
      await quoteStore.reviewFinal(quote.value.id, quote.value.headerRevision, 'approve')
      message.value = '负责跟客已确认历史待审单放行，P4 受控文件和客价交接 artifact 已由服务端生成。'
      return
    }
    throw new Error('当前报价尚未满足最终放行条件。')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '操作失败。'
  }
}

async function rejectFinal() {
  if (!finalReason.value.trim()) {
    finalRejectError.value = '必须填写退回原因。'
    return
  }
  if (!canFinalApprove.value) {
    finalRejectOpen.value = false
    errorMessage.value = '当前账号没有该厂区的最终放行审核权限。'
    return
  }
  message.value = ''
  errorMessage.value = ''
  finalRejectError.value = ''
  try {
    await quoteStore.reviewFinal(quote.value.id, quote.value.headerRevision, 'reject', finalReason.value.trim())
    message.value = '最终放行已退回并留存原因。'
    finalRejectOpen.value = false
    finalReason.value = ''
  } catch (error) {
    const detail = error instanceof Error ? error.message : '最终放行退回失败。'
    errorMessage.value = detail
    finalRejectError.value = detail
  }
}

function toggleFinalReject() {
  finalRejectOpen.value = !finalRejectOpen.value
  finalRejectError.value = ''
}

async function compareSelectedVersion() {
  if (!versionBaseId.value) return
  errorMessage.value = ''
  try { comparison.value = await quoteStore.compareVersion(quote.value.id, versionBaseId.value) }
  catch (error) { errorMessage.value = error instanceof Error ? error.message : '版本对比失败。' }
}

function finalActionLabel() {
  if (quote.value.status === 'fully_approved') return canResponsibleRelease.value ? '负责跟客确认放行' : '仅负责跟客可放行'
  if (quote.value.status === 'final_pending') return canResponsibleRelease.value ? '负责跟客确认放行' : '等待负责跟客放行'
  if (canOpenExport.value) return '进入导出汇总'
  if (isReleased.value && !canExport.value) return isForeignQuote.value ? '跨厂只读，不能导出' : '无受控导出权限'
  return '尚未满足放行条件'
}

async function loadQuote() {
  await quoteStore.loadQuote(quoteId.value)
  await quoteStore.loadVersionCandidates(quoteId.value).catch(() => [])
}

onMounted(loadQuote)
watch(quoteId, loadQuote)
watch([selectedFactoryId, () => loadedQuote.value?.factoryId], ([factoryId, quoteFactoryId]) => {
  if (!quoteFactoryId || quoteFactoryId === factoryId || !isFactoryContextId(factoryId)) return
  void router.replace(getFactoryScopedRoute('/modules/sales-business/internal-quote-desk', factoryId))
})
watch([quoteId, canFinalApprove], () => {
  finalRejectOpen.value = false
  finalReason.value = ''
  finalRejectError.value = ''
})
</script>

<template>
  <div class="quote-summary-page">
    <nav class="quote-breadcrumb" aria-label="内部报价导航">
      <RouterLink :to="getQuoteRoute('/modules/sales-business/internal-quote-desk')"><ArrowLeft aria-hidden="true" />报价首页</RouterLink>
      <ChevronRight aria-hidden="true" />
      <RouterLink :to="getQuoteRoute(`/modules/sales-business/internal-quote-desk/${quote.id}/collaboration`)">{{ quote.quoteNo }} · 协作</RouterLink>
      <ChevronRight aria-hidden="true" /><strong>汇总与放行</strong>
    </nav>

    <header class="quote-summary-head">
      <div><span class="quote-eyebrow">内部成本汇总</span><h1>汇总与最终放行</h1><p>{{ quote.quoteNo }} · {{ quote.productName }} · {{ quote.customer }} · {{ quote.versionLabel }}</p></div>
      <div class="quote-total-card"><span>整单工厂成本</span><strong>HKD {{ totalHkd.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</strong><small>RMB {{ (totalHkd * quote.fxRmbHkd).toFixed(2) }} · USD {{ (totalHkd / quote.fxHkdUsd).toFixed(2) }}</small></div>
    </header>

    <p v-if="message" class="quote-page-message success">{{ message }}</p>
    <p v-if="errorMessage" class="quote-page-message error">{{ errorMessage }}</p>
    <p v-if="quoteStore.errorMessage" class="quote-page-message error">{{ quoteStore.errorMessage }}</p>
    <p v-if="isReadOnly" class="quote-readonly-banner"><LockKeyhole aria-hidden="true" />{{ isForeignReadOnly ? '当前为跨厂只读视图；审核、最终放行及受控导出仅允许在所属厂区执行。' : '当前账号仅可查看该报价，没有可用的审核、最终放行或受控导出权限。' }}</p>

    <section class="quote-cost-overview">
      <header><div><CircleDollarSign aria-hidden="true" /><span><strong>权威成本分布</strong><small>分部门金额与成本项目并列展示；正式数据均读取服务端计算快照</small></span></div><em>{{ quote.formulaVersion }}</em></header>
      <div class="quote-cost-overview-body">
        <article class="quote-distribution-card department-distribution-card">
          <header><span><strong>部门金额分布</strong><small>九个责任分段固定展示，未参与或尚未形成有效计算时金额为 0</small></span><em>HKD / PCS</em></header>
          <div class="quote-donut-wrap"><div class="quote-donut" :style="departmentDonutStyle"><span><b>部门合计</b>{{ departmentTotalHkd.toFixed(2) }}</span></div></div>
          <dl class="compact-cost-list"><div v-for="item in departmentEntries" :key="item.key" :class="{ inactive: !item.isRequired || item.amount === 0 }"><dt><i :style="{ background: item.color }" />{{ item.label }}<small v-if="!item.isRequired">未参与</small></dt><dd>{{ item.amount.toFixed(4) }}</dd></div></dl>
        </article>
        <article class="quote-distribution-card component-distribution-card">
          <header><span><strong>成本项目分布</strong><small>保留包装、纸箱、人工、加工等服务端成本组成</small></span><em>HKD / PCS</em></header>
          <div class="quote-donut-wrap"><div class="quote-donut" :style="componentDonutStyle"><span><b>整单成本</b>{{ totalHkd.toFixed(2) }}</span></div></div>
          <dl class="compact-cost-list"><div v-for="item in componentEntries" :key="item.key"><dt><i :style="{ background: item.color }" />{{ item.label }}</dt><dd>{{ item.amount.toFixed(4) }}</dd></div><div v-if="!componentEntries.length"><dt>尚无有效成本组件</dt><dd>0.0000</dd></div></dl>
        </article>
        <div class="cost-snapshot-note"><LockKeyhole aria-hidden="true" /><span><strong>冻结参考快照</strong><small>{{ quote.referenceSnapshotId }}</small></span></div>
      </div>
    </section>

    <section v-if="shippingPricing.enabled" class="quote-logistics-panel">
      <header><div><Ship aria-hidden="true" /><span><strong>出货价算价</strong><small>已启用：{{ [shippingPricing.freightEnabled ? '运费' : '', shippingPricing.liftingEnabled ? '吊柜费' : ''].filter(Boolean).join('、') }}</small></span></div><em>出货数量 {{ quote.quantity.toLocaleString('zh-CN') }} PCS</em></header>
      <p class="shipping-formula">出货底价 = 出厂价 {{ shippingPricing.factoryPriceHkd.toFixed(4) }} + 附加税 {{ shippingPricing.additionalTaxHkd.toFixed(4) }} = <b>{{ shippingPricing.shippingFloorHkd.toFixed(4) }} HKD</b>；各场景再 × 码点 ÷ 找数，模具分摊在 USD 层加入。</p>
      <div class="business-table-scroll shipping-price-scroll"><table class="business-summary-table shipping-price-table"><thead><tr><th>项</th><th v-for="row in shippingPricing.rows" :key="row.name">{{ row.name }}</th></tr></thead><tbody>
        <tr><th>出货底价 HKD</th><td v-for="row in shippingPricing.rows" :key="`floor-${row.name}`">{{ row.shippingFloorHkd.toFixed(4) }}</td></tr>
        <tr v-if="shippingPricing.freightEnabled"><th>运费（{{ shippingPricing.freightSharePercent.toFixed(2) }}%）</th><td v-for="row in shippingPricing.rows" :key="`freight-${row.name}`">{{ row.freightHkd.toFixed(4) }}</td></tr>
        <tr v-if="shippingPricing.liftingEnabled"><th>吊柜费（{{ shippingPricing.liftSharePercent.toFixed(2) }}%）</th><td v-for="row in shippingPricing.rows" :key="`lift-${row.name}`">{{ row.liftHkd.toFixed(4) }}</td></tr>
        <tr class="calculated"><th>含运 HKD</th><td v-for="row in shippingPricing.rows" :key="`ship-${row.name}`">{{ row.withFreightHkd.toFixed(4) }}</td></tr>
        <tr><th>码点 ×（{{ shippingPricing.markup.toFixed(4) }}）</th><td v-for="row in shippingPricing.rows" :key="`markup-${row.name}`">{{ row.afterMarkupHkd.toFixed(4) }}</td></tr>
        <tr><th>找数 ÷（{{ shippingPricing.settlement.toFixed(4) }}）</th><td v-for="row in shippingPricing.rows" :key="`settlement-${row.name}`">{{ row.afterSettlementHkd.toFixed(4) }}</td></tr>
        <tr class="calculated"><th>TOTAL（HKD）</th><td v-for="row in shippingPricing.rows" :key="`hkd-${row.name}`">{{ row.totalHkd.toFixed(4) }}</td></tr>
        <tr><th>（USD）= HKD / {{ shippingPricing.hkdUsd.toFixed(2) }}</th><td v-for="row in shippingPricing.rows" :key="`usd-${row.name}`">{{ row.totalUsd.toFixed(4) }}</td></tr>
        <tr><th>模具分摊（USD）</th><td v-for="row in shippingPricing.rows" :key="`mold-${row.name}`">{{ row.moldAmortizationUsd.toFixed(4) }}</td></tr>
        <tr class="calculated"><th>TOTAL（USD）</th><td v-for="row in shippingPricing.rows" :key="`total-usd-${row.name}`">{{ row.totalWithMoldUsd.toFixed(4) }}</td></tr>
      </tbody></table></div>
    </section>

    <section class="quote-tax-summary-panel">
      <header><div><FileSpreadsheet aria-hidden="true" /><span><strong>减税明细 / 成本汇总</strong><small>字段顺序和公式与 rr2 汇总页一致；金额由服务端按分段快照生成</small></span></div><em>HKD / PCS</em></header>
      <div class="indonesia-freight-note"><strong>印尼运费（HKD）</strong><b>{{ summaryValue(costSummary.indonesiaFreightHkd, undefined, true) }}</b><span>杂项 = 印尼运费 + 附加税</span></div>

      <article class="business-summary-block"><h3>一、出厂货价核</h3><div class="business-table-scroll"><table class="business-summary-table"><thead><tr><th v-for="item in costSummary.t1" :key="item.key">{{ item.label }}</th></tr></thead><tbody><tr><td v-for="item in costSummary.t1" :key="item.key">{{ summaryValue(item.value, item.format, true) }}</td></tr></tbody></table></div></article>
      <article class="business-summary-block"><h3>二、包装 / 外购</h3><div class="business-table-scroll"><table class="business-summary-table"><thead><tr><th v-for="item in costSummary.t2" :key="item.key">{{ item.label }}</th></tr></thead><tbody><tr><td v-for="item in costSummary.t2" :key="item.key">{{ summaryValue(item.value, item.format, true) }}</td></tr></tbody></table></div></article>
      <article class="business-summary-block"><h3>三、人工 &amp; 成本汇总</h3><div class="business-table-scroll"><table class="business-summary-table"><thead><tr><th v-for="item in costSummary.t3" :key="item.key" :class="{ emphasized: item.key === 'no_labor_cost' }">{{ item.label }}</th></tr></thead><tbody><tr><td v-for="item in costSummary.t3" :key="item.key" :class="{ calculated: ['no_labor_cost','total_cost'].includes(item.key) }">{{ summaryValue(item.value, item.format, directLaborKeys.has(item.key)) }}</td></tr></tbody></table></div></article>
      <article class="business-summary-block tax-detail-block"><h3>四、减税明细 <small>1 = 金额；2 = 税率%；3 = 减税额 = 金额 × 税率；合计减税 = Σ减税额；减税后成本 = 总成本 − 合计减税</small></h3><div class="business-table-scroll"><table class="business-summary-table"><thead><tr><th v-for="item in costSummary.t4" :key="item.key">{{ item.label }}</th><th class="total">合计减税</th><th class="after-tax">减税后成本</th></tr></thead><tbody>
        <tr><td v-for="item in costSummary.t4" :key="`amount-${item.key}`">{{ summaryValue(item.amountHkd, undefined, true) }}</td><td /><td /></tr>
        <tr><td v-for="item in costSummary.t4" :key="`rate-${item.key}`">{{ item.ratePercent == null ? '' : `${item.ratePercent.toFixed(2)}%` }}</td><td /><td /></tr>
        <tr class="calculated"><td v-for="item in costSummary.t4" :key="`deduction-${item.key}`">{{ item.deductionHkd == null ? '—' : item.deductionHkd.toFixed(4) }}</td><td class="total">{{ costSummary.totalDeductionHkd.toFixed(4) }}</td><td class="after-tax">{{ costSummary.afterDeductionCostHkd.toFixed(4) }}</td></tr>
      </tbody></table></div></article>
    </section>

    <section v-if="versionCandidates.length" class="quote-version-panel"><header><div><FileClock aria-hidden="true" /><span><strong>报价版本对比</strong><small>仅允许同报价或复制版本链，金额差异由服务端计算</small></span></div><div><select v-model="versionBaseId"><option value="">选择基准版本</option><option v-for="candidate in versionCandidates" :key="candidate.id" :value="candidate.id">{{ candidate.quote_no }} · {{ candidate.version_label }} · {{ candidate.updated_at }}</option></select><button type="button" :disabled="!versionBaseId" @click="compareSelectedVersion">开始对比</button></div></header><div v-if="comparison" class="quote-comparison"><article><span>基准成本</span><strong>HKD {{ Number(comparison.total_before_hkd).toFixed(4) }}</strong></article><article><span>当前成本</span><strong>HKD {{ Number(comparison.total_after_hkd).toFixed(4) }}</strong></article><article><span>金额差异</span><strong>HKD {{ Number(comparison.total_delta_hkd).toFixed(4) }}</strong></article><div><p v-for="section in comparison.sections" :key="section.section_code"><span>{{ section.section_name }} · r{{ section.before_revision }} → r{{ section.after_revision }}</span><b>{{ Number(section.delta_hkd).toFixed(4) }}</b></p></div></div></section>

    <section class="quote-release-status">
      <header><div><CheckCircle2 aria-hidden="true" /><span><strong>分段放行状态</strong><small>{{ allSectionsReady ? `${participatingSections.length} 个参与分段已完成` : `还有 ${missingSections.length} 个参与分段未完成` }}</small></span></div><RouterLink :to="getQuoteRoute(`/modules/sales-business/internal-quote-desk/${quote.id}/collaboration`)">返回协作页</RouterLink></header>
      <div class="quote-release-grid"><article v-for="section in participatingSections" :key="section.code" :class="section.status"><span><Check v-if="['approved','not_applicable'].includes(section.status)" aria-hidden="true" /><AlertTriangle v-else aria-hidden="true" /></span><div><strong>{{ section.label }}</strong><small>{{ statusMeta[section.status].label }} · {{ section.reviewer ?? section.submittedBy ?? '尚未提交' }}</small></div><em>r{{ section.revision }}</em></article></div>
      <div v-if="missingSections.length" class="quote-release-warning"><AlertTriangle aria-hidden="true" /><span><strong>暂不可最终放行或导出</strong>{{ missingSections.map((section) => `${section.label}（${statusMeta[section.status].label}）`).join('、') }}</span></div>
    </section>

    <section class="quote-final-grid">
      <article class="quote-export-history"><header><FileClock aria-hidden="true" /><span><strong>受控导出记录</strong><small>重开后旧文件保留但标记已取代</small></span></header><div v-if="quote.exports.length"><p v-for="record in quote.exports" :key="record.id"><FileSpreadsheet aria-hidden="true" /><span><strong>{{ record.fileName }}</strong><small>{{ record.exportedBy }} · {{ record.exportedAt }}</small></span><em :class="record.status">{{ record.status === 'current' ? '当前版本' : '已取代' }}</em></p></div><div v-else class="empty">最终放行后才可生成受控 XLSX。</div></article>
      <article class="quote-final-release" :class="{ ready: allSectionsReady }"><Rocket aria-hidden="true" /><div><span>业务跟客最终放行</span><h2>{{ allSectionsReady ? (quote.status === 'final_pending' ? '等待负责跟客确认放行' : canOpenExport ? '已放行，可查看受控导出' : isReleased && !canExport ? (isForeignQuote ? '已放行，跨厂仅供查看' : '已放行，当前账号无受控导出权限') : '整单已准备就绪') : '等待全部责任分段完成' }}</h2><p>全部参与分段完成审批后，由业务部分段的提交跟客一人确认放行；请求携带报价头 revision，服务端冻结完整放行清单并生成受控文件。</p><div v-if="quote.finalReleaseStatus === 'rejected'" class="final-rejected">上一轮最终放行已退回，可修正后由负责跟客重新放行。</div></div><div class="final-buttons"><button v-if="quote.status === 'final_pending' && canFinalApprove" type="button" class="reject" @click="toggleFinalReject">退回历史待审放行</button><button type="button" :disabled="!allSectionsReady || (['fully_approved','final_pending'].includes(quote.status) && !canResponsibleRelease) || (isReleased && !canExport)" @click="runFinalAction"><Download v-if="canOpenExport" aria-hidden="true" /><Rocket v-else aria-hidden="true" />{{ finalActionLabel() }}</button></div></article>
    </section>
    <section v-if="finalRejectOpen && canFinalApprove" class="quote-final-reason"><div><strong>退回最终放行</strong><span>原因将写入不可变最终审核记录并通知提交人。</span></div><textarea v-model="finalReason" rows="2" placeholder="必须填写退回原因" /><button type="button" @click="finalRejectOpen = false">取消</button><button type="button" class="primary" :disabled="!finalReason.trim() || quoteStore.submitting || !canFinalApprove" @click="rejectFinal">{{ quoteStore.submitting ? '退回中…' : '确认退回' }}</button><p v-if="finalRejectError" class="quote-final-inline-error" role="alert">{{ finalRejectError }}</p></section>
  </div>
</template>

<style scoped>
.quote-summary-page{display:grid;gap:14px;padding-bottom:32px}.quote-breadcrumb{display:flex;align-items:center;gap:7px;color:#94a3b8;font-size:9px}.quote-breadcrumb a{display:inline-flex;align-items:center;gap:5px;color:#475569;font-weight:800}.quote-breadcrumb a:hover{color:#0f766e}.quote-breadcrumb svg{width:12px}.quote-breadcrumb strong{color:#0f766e}.quote-summary-head{display:flex;align-items:flex-end;justify-content:space-between;gap:20px}.quote-eyebrow{color:#0f766e;font-size:10px;font-weight:900;letter-spacing:.08em}.quote-summary-head h1{margin:5px 0 0;color:#0f172a;font-size:30px;font-weight:950;letter-spacing:-.04em}.quote-summary-head p{margin:7px 0 0;color:#64748b;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:10px}.quote-total-card{display:grid;min-width:280px;border:1px solid #99f6e4;border-radius:13px;background:#f0fdfa;padding:13px 16px;text-align:right}.quote-total-card span{color:#0f766e;font-size:9px;font-weight:900}.quote-total-card strong{margin-top:5px;color:#115e59;font-size:21px}.quote-total-card small{margin-top:4px;color:#0f766e;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:8px}.quote-page-message{margin:0;border-radius:8px;padding:8px 11px;font-size:9px}.quote-page-message.success{border:1px solid #a7f3d0;background:#ecfdf5;color:#047857}.quote-page-message.error{border:1px solid #fecaca;background:#fef2f2;color:#b91c1c}.quote-readonly-banner{display:flex;align-items:center;gap:7px;margin:0;border:1px solid #99f6e4;border-radius:9px;background:#f0fdfa;padding:9px 11px;color:#0f766e;font-size:11px}.quote-readonly-banner svg{width:15px;flex:0 0 auto}
.quote-summary-grid{display:grid;grid-template-columns:minmax(0,2fr) minmax(250px,.7fr);gap:12px}.quote-cost-table-panel,.quote-distribution-panel,.quote-logistics-panel,.quote-release-status,.quote-export-history,.quote-final-release{overflow:hidden;border:1px solid #dbe5ea;border-radius:13px;background:#fff;box-shadow:0 10px 28px rgb(15 23 42/.045)}.quote-cost-table-panel>header,.quote-logistics-panel>header,.quote-release-status>header,.quote-export-history>header{display:flex;align-items:center;justify-content:space-between;gap:10px;border-bottom:1px solid #e2e8f0;padding:13px 15px;background:#f8fafc}.quote-cost-table-panel>header>div,.quote-logistics-panel>header>div,.quote-release-status>header>div,.quote-export-history>header{display:flex;align-items:center;gap:8px}.quote-cost-table-panel header svg,.quote-logistics-panel header svg,.quote-release-status header svg,.quote-export-history header svg{width:17px;color:#0f766e}.quote-cost-table-panel header span,.quote-logistics-panel header span,.quote-release-status header span,.quote-export-history header span{display:grid}.quote-cost-table-panel header strong,.quote-logistics-panel header strong,.quote-release-status header strong,.quote-export-history header strong{color:#334155;font-size:11px}.quote-cost-table-panel header small,.quote-logistics-panel header small,.quote-release-status header small,.quote-export-history header small{margin-top:2px;color:#94a3b8;font-size:8px}.quote-cost-table-panel>header>span{color:#64748b;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:8px}.quote-summary-table-scroll{overflow:auto}.quote-cost-table-panel table{width:100%;min-width:750px;border-collapse:collapse}.quote-cost-table-panel th{background:#eef2f6;padding:8px;color:#64748b;font-size:8px;text-align:left}.quote-cost-table-panel td{border-top:1px solid #eef2f6;padding:8px;color:#475569;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:8px}.quote-cost-table-panel td:first-child strong{display:block;color:#334155;font-family:'Microsoft YaHei','PingFang SC',sans-serif;font-size:9px}.quote-cost-table-panel td:first-child span{display:block;margin-top:2px;color:#94a3b8;font-family:'Microsoft YaHei','PingFang SC',sans-serif;font-size:7px}.quote-cost-table-panel .money{color:#0f172a;font-weight:900;text-align:right}.quote-cost-table-panel tfoot td{background:#f8fafc;color:#0f766e;font-weight:900}.section-status{display:inline-flex;align-items:center;gap:4px;border-radius:999px;background:color-mix(in srgb,var(--tone) 10%,white);padding:4px 6px;color:var(--tone);font-family:'Microsoft YaHei','PingFang SC',sans-serif;font-size:7px;font-weight:900}.section-status i{width:5px;height:5px;border-radius:99px;background:currentColor}.tone-slate{--tone:#64748b}.tone-amber{--tone:#d97706}.tone-green{--tone:#059669}.tone-red{--tone:#dc2626}.tone-blue{--tone:#2563eb}.tone-teal{--tone:#0f766e}
.quote-distribution-panel{padding:15px}.quote-distribution-panel>header{display:flex;justify-content:space-between}.quote-distribution-panel header strong{color:#334155;font-size:11px}.quote-distribution-panel header span{color:#94a3b8;font-size:8px}.quote-donut-wrap{display:grid;place-items:center;padding:18px 0}.quote-donut{display:grid;width:150px;height:150px;place-items:center;border-radius:50%;background:conic-gradient(#0f766e 0 64%,#475569 64% 88%,#cbd5e1 88% 100%);box-shadow:inset 0 0 0 23px #fff}.quote-donut span{display:grid;color:#0f172a;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:14px;font-weight:900;text-align:center}.quote-donut b{color:#94a3b8;font-size:8px}.quote-distribution-panel dl{display:grid;gap:7px;margin:0}.quote-distribution-panel dl div{display:flex;justify-content:space-between;gap:8px}.quote-distribution-panel dt{display:flex;align-items:center;gap:6px;color:#64748b;font-size:8px}.quote-distribution-panel dd{margin:0;color:#334155;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:8px}.quote-distribution-panel i{width:7px;height:7px;border-radius:99px}.quote-distribution-panel i.material{background:#0f766e}.quote-distribution-panel i.labor{background:#475569}.quote-distribution-panel i.overhead{background:#cbd5e1}.quote-distribution-panel>section{display:flex;align-items:center;gap:8px;margin-top:14px;border-radius:9px;background:#f1f5f9;padding:9px}.quote-distribution-panel section svg{width:16px;color:#64748b}.quote-distribution-panel section div{display:grid;min-width:0}.quote-distribution-panel section strong{color:#475569;font-size:8px}.quote-distribution-panel section span{overflow:hidden;margin-top:2px;color:#94a3b8;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:7px;text-overflow:ellipsis;white-space:nowrap}
.quote-cost-overview,.quote-tax-summary-panel{overflow:hidden;border:1px solid #dbe5ea;border-radius:13px;background:#fff;box-shadow:0 10px 28px rgb(15 23 42/.045)}.quote-cost-overview>header,.quote-tax-summary-panel>header{display:flex;align-items:center;justify-content:space-between;gap:10px;border-bottom:1px solid #e2e8f0;background:#f8fafc;padding:12px 15px}.quote-cost-overview>header>div,.quote-tax-summary-panel>header>div{display:flex;align-items:center;gap:8px}.quote-cost-overview header svg,.quote-tax-summary-panel header svg{width:17px;color:#0f766e}.quote-cost-overview header span,.quote-tax-summary-panel header span{display:grid}.quote-cost-overview header strong,.quote-tax-summary-panel header strong{color:#334155;font-size:12px}.quote-cost-overview header small,.quote-tax-summary-panel header small{margin-top:2px;color:#94a3b8;font-size:9px}.quote-cost-overview header em,.quote-tax-summary-panel header em{color:#64748b;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:9px;font-style:normal}.quote-cost-overview-body{display:grid;grid-template-columns:190px minmax(0,1fr) 230px;align-items:center;gap:16px;padding:12px 15px}.quote-cost-overview .quote-donut-wrap{padding:0}.quote-cost-overview .quote-donut{width:132px;height:132px;box-shadow:inset 0 0 0 22px #fff}.quote-cost-overview .quote-donut span{font-size:12px}.compact-cost-list{display:grid;grid-template-columns:repeat(4,minmax(120px,1fr));gap:6px;margin:0}.compact-cost-list>div{display:flex;align-items:center;justify-content:space-between;gap:8px;border:1px solid #eef2f6;border-radius:7px;background:#fafcfd;padding:7px 8px}.compact-cost-list dt{display:flex;align-items:center;gap:6px;min-width:0;color:#475569;font-size:10px}.compact-cost-list dt i{width:7px;height:7px;flex:0 0 auto;border-radius:99px}.compact-cost-list dd{margin:0;color:#0f172a;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:10px;font-weight:900}.cost-snapshot-note{display:flex;align-items:center;gap:9px;border-radius:9px;background:#f1f5f9;padding:10px}.cost-snapshot-note>svg{width:17px;flex:0 0 auto;color:#64748b}.cost-snapshot-note>span{display:grid;min-width:0}.cost-snapshot-note strong{color:#475569;font-size:10px}.cost-snapshot-note small{overflow:hidden;margin-top:3px;color:#94a3b8;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:8px;text-overflow:ellipsis;white-space:nowrap}
/* Department and component distributions use separate authoritative totals and donuts. */
.quote-cost-overview-body{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-items:stretch;gap:10px;padding:12px 15px}.quote-distribution-card{display:grid;grid-template-columns:112px minmax(0,1fr);align-items:center;gap:10px;border:1px solid #e2e8f0;border-radius:10px;background:#fff;padding:10px}.quote-distribution-card>header{display:flex;grid-column:1/-1;align-items:flex-start;justify-content:space-between;gap:10px;border-bottom:1px solid #eef2f6;padding:0 1px 8px}.quote-distribution-card>header span{display:grid}.quote-distribution-card>header strong{color:#334155;font-size:11px}.quote-distribution-card>header small{margin-top:2px;color:#94a3b8;font-size:8px}.quote-distribution-card>header em{flex:0 0 auto;color:#94a3b8;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:8px;font-style:normal}.quote-cost-overview .quote-donut-wrap{padding:0}.quote-cost-overview .quote-donut{width:104px;height:104px;box-shadow:inset 0 0 0 17px #fff}.quote-cost-overview .quote-donut span{font-size:11px}.quote-cost-overview .quote-donut b{font-size:7px}.compact-cost-list{display:grid;grid-template-columns:repeat(2,minmax(105px,1fr));gap:5px;margin:0}.compact-cost-list>div{display:flex;align-items:center;justify-content:space-between;gap:6px;min-width:0;border:1px solid #eef2f6;border-radius:7px;background:#fafcfd;padding:5px 6px}.compact-cost-list>div.inactive{opacity:.55}.compact-cost-list dt{display:flex;align-items:center;gap:5px;min-width:0;color:#475569;font-size:9px;white-space:nowrap}.compact-cost-list dt i{width:6px;height:6px;flex:0 0 auto;border-radius:99px}.compact-cost-list dt small{border-radius:999px;background:#e2e8f0;padding:1px 4px;color:#64748b;font-size:7px}.compact-cost-list dd{margin:0;color:#0f172a;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:9px;font-weight:900}.cost-snapshot-note{display:flex;grid-column:1/-1;align-items:center;gap:9px;border-radius:9px;background:#f1f5f9;padding:8px 10px}.cost-snapshot-note>svg{width:15px;flex:0 0 auto;color:#64748b}.cost-snapshot-note>span{display:flex;min-width:0;align-items:center;gap:8px}.cost-snapshot-note strong{color:#475569;font-size:9px}.cost-snapshot-note small{overflow:hidden;margin-top:0;color:#94a3b8;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:8px;text-overflow:ellipsis;white-space:nowrap}
.shipping-formula{margin:0;border-bottom:1px solid #e2e8f0;background:#f0fdfa;padding:10px 14px;color:#475569;font-size:10px;line-height:1.6}.shipping-formula b{color:#0f766e}.business-table-scroll{overflow:auto}.shipping-price-scroll{padding:12px}.business-summary-table{width:100%;min-width:1040px;border-collapse:collapse}.business-summary-table th,.business-summary-table td{border:1px solid #e2e8f0;padding:8px 9px;text-align:center;white-space:nowrap}.business-summary-table thead th{background:#eef2f6;color:#475569;font-size:10px;font-weight:900}.business-summary-table tbody th{position:sticky;left:0;z-index:1;background:#f8fafc;color:#475569;font-size:10px;text-align:left}.business-summary-table td{color:#334155;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:10px;font-weight:700}.business-summary-table tr.calculated th,.business-summary-table tr.calculated td,.business-summary-table td.calculated{background:#eff6ff;color:#1d4ed8;font-weight:900}.shipping-price-table{min-width:1700px}.shipping-price-table th:first-child{min-width:190px}.shipping-price-table thead th:not(:first-child){min-width:145px}
.indonesia-freight-note{display:flex;align-items:center;gap:14px;margin:12px 14px 0;border:1px solid #fde68a;border-radius:8px;background:#fffbeb;padding:9px 12px;color:#475569;font-size:10px}.indonesia-freight-note strong{color:#92400e}.indonesia-freight-note b{display:inline-block;min-width:72px;min-height:28px;border:1px solid #dbe5ea;border-radius:6px;background:#fff;padding:6px 8px;color:#0f766e;font-family:ui-monospace,SFMono-Regular,Consolas,monospace}.indonesia-freight-note span{color:#78716c}.business-summary-block{padding:12px 14px 0}.business-summary-block:last-child{padding-bottom:14px}.business-summary-block h3{margin:0 0 7px;color:#334155;font-size:11px}.business-summary-block h3 small{margin-left:6px;color:#94a3b8;font-size:9px;font-weight:500}.business-summary-block .business-table-scroll{border-radius:7px}.business-summary-block .business-summary-table{min-width:1180px}.business-summary-block .business-summary-table th.emphasized{background:#fef3c7}.tax-detail-block .business-summary-table{min-width:1320px}.tax-detail-block th.total,.tax-detail-block td.total{background:#fef3c7!important;color:#92400e!important;font-weight:900}.tax-detail-block th.after-tax,.tax-detail-block td.after-tax{background:#dcfce7!important;color:#166534!important;font-weight:900}
.quote-logistics-panel>header em{color:#64748b;font-size:8px;font-style:normal}.quote-logistics-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;padding:12px}.quote-logistics-grid article{display:grid;grid-template-columns:32px 1fr;gap:8px;border:1px solid #e2e8f0;border-left:3px solid var(--tone);border-radius:9px;padding:11px}.quote-logistics-grid article>svg{width:20px;color:var(--tone)}.quote-logistics-grid article>div{display:grid}.quote-logistics-grid article strong{color:#334155;font-size:10px}.quote-logistics-grid article span{margin-top:2px;color:#94a3b8;font-size:7px}.quote-logistics-grid dl{grid-column:1/-1;display:grid;grid-template-columns:1fr auto;gap:5px;margin:4px 0 0;border-top:1px solid #eef2f6;padding-top:8px}.quote-logistics-grid dt{color:#64748b;font-size:8px}.quote-logistics-grid dd{margin:0;color:#334155;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:8px;font-weight:900}.quote-logistics-empty{margin:0;padding:22px;color:#94a3b8;font-size:11px;text-align:center}.quote-version-panel{overflow:hidden;border:1px solid #dbe5ea;border-radius:13px;background:#fff;box-shadow:0 10px 28px rgb(15 23 42/.045)}.quote-version-panel>header{display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid #e2e8f0;background:#f8fafc;padding:12px 14px}.quote-version-panel>header>div{display:flex;align-items:center;gap:8px}.quote-version-panel header svg{width:17px;color:#0f766e}.quote-version-panel header span{display:grid}.quote-version-panel header strong{color:#334155;font-size:11px}.quote-version-panel header small{margin-top:2px;color:#94a3b8;font-size:8px}.quote-version-panel select{height:34px;border:1px solid #dbe5ea;border-radius:7px;background:#fff;padding:0 8px;font-size:11px}.quote-version-panel button{height:34px;border:1px solid #0f766e;border-radius:7px;background:#0f766e;padding:0 10px;color:#fff;font-size:11px;font-weight:900}.quote-version-panel button:disabled{opacity:.4}.quote-comparison{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;padding:12px}.quote-comparison>article{display:grid;border:1px solid #e2e8f0;border-radius:8px;padding:10px}.quote-comparison article span{color:#64748b;font-size:10px}.quote-comparison article strong{margin-top:4px;color:#0f172a;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:13px}.quote-comparison>div{grid-column:1/-1;display:grid;grid-template-columns:repeat(4,1fr);gap:6px}.quote-comparison p{display:flex;justify-content:space-between;gap:8px;margin:0;border-radius:7px;background:#f8fafc;padding:8px;color:#475569;font-size:10px}.quote-comparison p b{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}
.quote-release-status>header a{color:#0f766e;font-size:8px;font-weight:900}.quote-release-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;padding:12px}.quote-release-grid article{display:grid;grid-template-columns:28px 1fr auto;align-items:center;gap:7px;border:1px solid #e2e8f0;border-radius:9px;padding:9px}.quote-release-grid article>span{display:grid;width:26px;height:26px;place-items:center;border-radius:8px;background:#fef3c7;color:#d97706}.quote-release-grid article.approved>span,.quote-release-grid article.not_applicable>span{background:#d1fae5;color:#059669}.quote-release-grid article svg{width:13px}.quote-release-grid article div{display:grid}.quote-release-grid strong{color:#334155;font-size:9px}.quote-release-grid small{margin-top:2px;color:#94a3b8;font-size:7px}.quote-release-grid em{color:#64748b;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:8px;font-style:normal}.quote-release-warning{display:flex;align-items:flex-start;gap:8px;border-top:1px solid #fed7aa;background:#fff7ed;padding:10px 13px;color:#9a3412}.quote-release-warning svg{width:15px}.quote-release-warning span{display:grid;font-size:8px}.quote-release-warning strong{font-size:9px}
.quote-final-grid{display:grid;grid-template-columns:minmax(0,.85fr) minmax(0,1.15fr);gap:12px}.quote-export-history>div{padding:12px}.quote-export-history p{display:flex;align-items:center;gap:8px;margin:0 0 7px;border:1px solid #e2e8f0;border-radius:8px;padding:8px}.quote-export-history p>svg{width:16px;color:#0f766e}.quote-export-history p>span{display:grid;min-width:0;flex:1}.quote-export-history p strong{overflow:hidden;color:#334155;font-size:8px;text-overflow:ellipsis;white-space:nowrap}.quote-export-history p small{margin-top:2px;color:#94a3b8;font-size:7px}.quote-export-history p em{border-radius:999px;padding:3px 6px;font-size:7px;font-style:normal;font-weight:900}.quote-export-history p em.current{background:#d1fae5;color:#047857}.quote-export-history p em.superseded{background:#e2e8f0;color:#64748b}.quote-export-history .empty{color:#94a3b8;font-size:9px;text-align:center}.quote-final-release{display:grid;grid-template-columns:44px 1fr auto;align-items:center;gap:13px;border-style:dashed;padding:18px;background:#f8fafc}.quote-final-release.ready{border-color:#2dd4bf;background:#f0fdfa}.quote-final-release>svg{width:40px;color:#94a3b8}.quote-final-release.ready>svg{color:#0f766e}.quote-final-release>div>span{color:#0f766e;font-size:8px;font-weight:900}.quote-final-release h2{margin:4px 0 0;color:#0f172a;font-size:16px}.quote-final-release p{max-width:580px;margin:6px 0 0;color:#64748b;font-size:8px;line-height:1.6}.final-rejected{margin-top:7px;color:#b91c1c;font-size:10px}.final-buttons{display:flex!important;align-items:center;gap:7px}.quote-final-release button{display:inline-flex;min-height:38px;align-items:center;gap:6px;border:1px solid #0f766e;border-radius:9px;background:#0f766e;padding:0 13px;color:#fff;font-size:9px;font-weight:900}.quote-final-release button.reject{border-color:#fecaca;background:#fff;color:#dc2626}.quote-final-release button:disabled{cursor:not-allowed;border-color:#cbd5e1;background:#e2e8f0;color:#94a3b8}.quote-final-release button svg{width:14px}.quote-final-reason{display:grid;grid-template-columns:minmax(180px,1fr) minmax(260px,2fr) auto auto;align-items:center;gap:9px;border:1px solid #fecaca;border-radius:11px;background:#fef2f2;padding:11px 13px}.quote-final-reason>div{display:grid}.quote-final-reason strong{color:#991b1b;font-size:12px}.quote-final-reason span{margin-top:2px;color:#b91c1c;font-size:10px}.quote-final-reason textarea{border:1px solid #fca5a5;border-radius:7px;padding:7px 9px;font-size:13px;resize:none}.quote-final-reason button{height:33px;border:1px solid #fca5a5;border-radius:7px;background:#fff;padding:0 10px;color:#991b1b;font-size:11px;font-weight:900}.quote-final-reason button.primary{border-color:#b91c1c;background:#b91c1c;color:#fff}.quote-final-inline-error{grid-column:2/-1;margin:0;color:#b91c1c;font-size:10px;font-weight:700}
@media(max-width:1200px){.quote-cost-overview-body{grid-template-columns:1fr}.cost-snapshot-note{grid-column:1/-1}.compact-cost-list{grid-template-columns:repeat(3,minmax(105px,1fr))}}
@media(max-width:1000px){.quote-summary-grid,.quote-final-grid{grid-template-columns:1fr}.quote-logistics-grid{grid-template-columns:1fr}.quote-release-grid{grid-template-columns:repeat(2,1fr)}.quote-comparison>div{grid-template-columns:1fr 1fr}.quote-final-reason{grid-template-columns:1fr}.quote-final-inline-error{grid-column:1}.compact-cost-list{grid-template-columns:repeat(2,minmax(120px,1fr))}}
@media(max-width:700px){.quote-summary-head,.quote-final-release{align-items:stretch;grid-template-columns:1fr}.quote-summary-head{flex-direction:column}.quote-total-card{min-width:0;text-align:left}.quote-release-grid{grid-template-columns:1fr}.quote-final-release>svg{width:32px}.quote-cost-overview-body,.quote-distribution-card{grid-template-columns:1fr}.compact-cost-list{grid-template-columns:1fr}.cost-snapshot-note{grid-column:auto}.quote-cost-overview .quote-donut-wrap{display:none}.business-summary-block h3 small{display:block;margin:4px 0 0}.indonesia-freight-note{align-items:flex-start;flex-direction:column;gap:4px}}
</style>
