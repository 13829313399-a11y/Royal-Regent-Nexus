<script setup lang="ts">
import {
  ArrowRight,
  CheckCircle2,
  CircleDollarSign,
  Clock3,
  Copy,
  Eye,
  FileCheck2,
  Filter,
  Plus,
  RotateCcw,
  Search,
  Settings2,
  TriangleAlert,
} from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import InternalQuoteCreateDialog from './InternalQuoteCreateDialog.vue'
import InternalQuoteBaselineDialog from './InternalQuoteBaselineDialog.vue'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import type { InternalQuotePricingBaselineUpdateRequest } from '@/api/internalQuote'
import type { InternalQuote, InternalQuoteCreatePayload, InternalQuoteStatus } from '@/types/internalQuoteDesk'

const router = useRouter()
const quoteStore = useInternalQuoteDeskStore()
const appStore = useAppStore()
const authStore = useAuthStore()
const query = ref('')
const statusFilter = ref<'all' | InternalQuoteStatus>('all')
const customerFilter = ref('all')
const createDialogOpen = ref(false)
const dialogMode = ref<'create' | 'clone'>('create')
const cloneSource = ref<InternalQuote>()
const dialogError = ref('')
const baselineDialogOpen = ref(false)
const baselineDialogError = ref('')
const activeFactoryId = computed(() => appStore.activeProductionFactory?.id ?? 'huaxing')
const activeWorkshopCode = computed(() => `${activeFactoryId.value}-workshop`)
const canViewPricingBaseline = computed(() => authStore.can('internal_quote:baseline_read', activeFactoryId.value, 'sales-business'))
const canManagePricingBaseline = computed(() => authStore.can('internal_quote:baseline_manage', activeFactoryId.value, 'sales-business'))

const statusMeta: Record<InternalQuoteStatus, { label: string; tone: string }> = {
  drafting: { label: '协作草稿', tone: 'slate' },
  pending_review: { label: '待分段审核', tone: 'amber' },
  rejected: { label: '已退回', tone: 'red' },
  fully_approved: { label: '待最终提交', tone: 'teal' },
  final_pending: { label: '待最终放行', tone: 'blue' },
  released: { label: '已放行', tone: 'green' },
  exported: { label: '已导出', tone: 'green' },
  archived: { label: '已归档', tone: 'slate' },
}

const customers = computed(() => [...new Set(quoteStore.quotes.map((quote) => quote.customer))])
const filteredQuotes = computed(() => {
  const keyword = query.value.trim().toLowerCase()
  return quoteStore.quotes.filter((quote) => {
    const matchesKeyword = !keyword || [quote.quoteNo, quote.productName, quote.customer, quote.versionLabel, quote.initiatorName]
      .some((value) => value.toLowerCase().includes(keyword))
    const matchesStatus = statusFilter.value === 'all' || quote.status === statusFilter.value
    const matchesCustomer = customerFilter.value === 'all' || quote.customer === customerFilter.value
    return matchesKeyword && matchesStatus && matchesCustomer
  })
})

const kpis = computed(() => [
  { label: '协作中', value: quoteStore.quotes.filter((quote) => ['drafting', 'pending_review'].includes(quote.status)).length, detail: '草稿与分段待审', icon: Clock3, tone: 'blue' },
  { label: '待我审核', value: quoteStore.quotes.reduce((sum, quote) => sum + quote.sections.filter((section) => section.isRequired && ['pending_review', 'na_pending'].includes(section.status)).length, 0), detail: '按参与分段进入', icon: FileCheck2, tone: 'amber' },
  { label: '退回 / 重开', value: quoteStore.quotes.filter((quote) => quote.status === 'rejected').length, detail: '需要补充原因或资料', icon: TriangleAlert, tone: 'red' },
  { label: '待最终放行', value: quoteStore.quotes.filter((quote) => ['fully_approved', 'final_pending'].includes(quote.status)).length, detail: '业务部两人复核', icon: CheckCircle2, tone: 'teal' },
  { label: '已导出', value: quoteStore.quotes.filter((quote) => quote.status === 'exported').length, detail: '受控 XLSX 已留存', icon: CircleDollarSign, tone: 'green' },
])

function openCreate() {
  dialogMode.value = 'create'
  cloneSource.value = undefined
  dialogError.value = ''
  createDialogOpen.value = true
}

function openClone(quote: InternalQuote) {
  dialogMode.value = 'clone'
  cloneSource.value = quote
  dialogError.value = ''
  createDialogOpen.value = true
}

async function handleConfirm(payload: InternalQuoteCreatePayload) {
  dialogError.value = ''
  try {
    const quote = dialogMode.value === 'clone' && cloneSource.value
      ? await quoteStore.cloneQuote(cloneSource.value.id, payload)
      : await quoteStore.createQuote(payload)
    createDialogOpen.value = false
    void router.push(`/modules/sales-business/internal-quote-desk/${quote.id}/collaboration`)
  } catch (error) {
    dialogError.value = getApiErrorMessage(error)
  }
}

function openQuote(quote: InternalQuote) {
  const target = ['fully_approved', 'final_pending', 'released', 'exported'].includes(quote.status) ? 'summary' : 'collaboration'
  void router.push(`/modules/sales-business/internal-quote-desk/${quote.id}/${target}`)
}

function approvedCount(quote: InternalQuote) {
  return quote.sections.filter((section) => section.isRequired && ['approved', 'not_applicable'].includes(section.status)).length
}

async function openPricingBaseline() {
  baselineDialogOpen.value = true
  baselineDialogError.value = ''
  try {
    await quoteStore.loadPricingBaseline(activeFactoryId.value, activeWorkshopCode.value)
  } catch (error) {
    baselineDialogError.value = getApiErrorMessage(error)
  }
}

async function savePricingBaseline(payload: InternalQuotePricingBaselineUpdateRequest) {
  baselineDialogError.value = ''
  try {
    await quoteStore.updatePricingBaseline(activeFactoryId.value, activeWorkshopCode.value, payload)
    baselineDialogOpen.value = false
  } catch (error) {
    baselineDialogError.value = getApiErrorMessage(error)
  }
}

function requiredCount(quote: InternalQuote) {
  return quote.sections.filter((section) => section.isRequired).length
}

function clearFilters() {
  query.value = ''
  statusFilter.value = 'all'
  customerFilter.value = 'all'
}

async function loadPage() {
  await Promise.all([
    quoteStore.loadQuotes(activeFactoryId.value),
    quoteStore.loadBusinessOwners(activeFactoryId.value),
  ])
}

onMounted(() => { void loadPage() })
watch(activeFactoryId, () => { void loadPage() })
</script>

<template>
  <div class="quote-home">
    <section class="quote-home-heading">
      <div>
        <div class="quote-eyebrow"><span />业务部 · 内部成本协作</div>
        <h1>内部报价台</h1>
        <p>业务部与工程部均可新建或复制报价，业务部、工程部、装配部固定参与，其余部门按项目需要选择。</p>
      </div>
      <div class="quote-heading-actions">
        <button v-if="canViewPricingBaseline" type="button" class="quote-baseline-button" :disabled="quoteStore.baselineLoading" @click="openPricingBaseline">
          <Settings2 aria-hidden="true" />调整报价基数
        </button>
        <button type="button" class="quote-new-button" :disabled="quoteStore.listLoading" @click="openCreate">
          <Plus aria-hidden="true" />新建内部报价
        </button>
      </div>
    </section>

    <div class="quote-stage-notice">
      <span>真实 API</span>{{ quoteStore.frontendNotice }}
    </div>

    <p v-if="quoteStore.errorMessage" class="quote-page-message error" role="alert">{{ quoteStore.errorMessage }}</p>

    <section class="quote-kpi-grid" aria-label="内部报价指标">
      <article v-for="kpi in kpis" :key="kpi.label" :class="`tone-${kpi.tone}`">
        <div><component :is="kpi.icon" aria-hidden="true" /><span>{{ kpi.label }}</span></div>
        <strong>{{ kpi.value }}</strong>
        <p>{{ kpi.detail }}</p>
      </article>
    </section>

    <section class="quote-list-panel">
      <header class="quote-list-toolbar">
        <label class="quote-search-box">
          <Search aria-hidden="true" />
          <input v-model="query" type="search" placeholder="搜索报价号、产品、客户、版本或创建人" aria-label="搜索内部报价">
        </label>
        <div class="quote-filters">
          <Filter aria-hidden="true" />
          <select v-model="statusFilter" aria-label="报价状态">
            <option value="all">全部状态</option>
            <option v-for="(meta, value) in statusMeta" :key="value" :value="value">{{ meta.label }}</option>
          </select>
          <select v-model="customerFilter" aria-label="客户筛选">
            <option value="all">全部客户</option>
            <option v-for="customer in customers" :key="customer">{{ customer }}</option>
          </select>
          <button type="button" class="quote-clear-filter" title="重置筛选" @click="clearFilters"><RotateCcw aria-hidden="true" /></button>
        </div>
      </header>

      <div class="quote-table-scroll">
        <table class="quote-table">
          <thead><tr><th>报价号</th><th>产品 / 客户</th><th>发起</th><th>版本</th><th>状态</th><th>分段进度</th><th>更新时间</th><th><span class="sr-only">操作</span></th></tr></thead>
          <tbody>
            <tr v-for="quote in filteredQuotes" :key="quote.id" @dblclick="openQuote(quote)">
              <td><button type="button" class="quote-number" @click="openQuote(quote)">{{ quote.quoteNo }}</button></td>
              <td><strong>{{ quote.productName }}</strong><span>{{ quote.customer }}</span></td>
              <td><span class="quote-initiator">{{ quote.initiatorDepartment === 'engineering' ? '工程部' : '业务部' }}</span><small>{{ quote.initiatorName }}</small></td>
              <td><span class="quote-version">{{ quote.versionLabel }}</span></td>
              <td><span class="quote-status" :class="`tone-${statusMeta[quote.status].tone}`"><i />{{ statusMeta[quote.status].label }}</span></td>
              <td>
                <div class="quote-progress-cell"><div><span :style="{ width: `${requiredCount(quote) ? approvedCount(quote) / requiredCount(quote) * 100 : 0}%` }" /></div><strong>{{ approvedCount(quote) }}/{{ requiredCount(quote) }}</strong></div>
              </td>
              <td><span class="quote-date">{{ quote.updatedAt }}</span></td>
              <td>
                <div class="quote-row-actions">
                  <button type="button" title="查看报价" aria-label="查看报价" @click="openQuote(quote)"><Eye aria-hidden="true" /></button>
                  <button type="button" title="复制报价" aria-label="复制报价" @click="openClone(quote)"><Copy aria-hidden="true" /></button>
                  <button type="button" class="primary" title="进入报价" aria-label="进入报价" @click="openQuote(quote)"><ArrowRight aria-hidden="true" /></button>
                </div>
              </td>
            </tr>
            <tr v-if="quoteStore.listLoading"><td colspan="8" class="quote-empty">正在读取内部报价…</td></tr>
            <tr v-else-if="!filteredQuotes.length"><td colspan="8" class="quote-empty">没有符合筛选条件的内部报价。</td></tr>
          </tbody>
        </table>
      </div>
      <footer class="quote-table-footer">
        <span>共 {{ filteredQuotes.length }} 条 · 当前厂区：华兴</span>
        <span>数据来自受权限和厂区范围保护的后端接口</span>
      </footer>
    </section>

    <InternalQuoteCreateDialog
      :open="createDialogOpen"
      :mode="dialogMode"
      :source-quote="cloneSource"
      :business-owners="quoteStore.businessOwners"
      :busy="quoteStore.submitting"
      :external-error="dialogError"
      @close="createDialogOpen = false"
      @confirm="handleConfirm"
    />
    <InternalQuoteBaselineDialog
      :open="baselineDialogOpen"
      :baseline="quoteStore.pricingBaseline"
      :busy="quoteStore.baselineLoading || quoteStore.baselineSaving"
      :can-edit="canManagePricingBaseline"
      :external-error="baselineDialogError"
      @close="baselineDialogOpen = false"
      @save="savePricingBaseline"
    />
  </div>
</template>

<style scoped>
.quote-home{display:grid;gap:18px;padding-bottom:28px}.quote-home-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;padding-top:5px}.quote-home-heading h1{margin:6px 0 0;color:#0f172a;font-size:clamp(30px,3vw,46px);font-weight:950;letter-spacing:-.045em}.quote-home-heading p{max-width:820px;margin:10px 0 0;color:#64748b;font-size:13px;line-height:1.75}.quote-eyebrow{display:flex;align-items:center;gap:7px;color:#0f766e;font-size:11px;font-weight:900;letter-spacing:.08em}.quote-eyebrow span{width:22px;height:2px;border-radius:2px;background:#0d9488}.quote-heading-actions{display:flex;flex:0 0 auto;align-items:center;gap:10px}.quote-new-button,.quote-baseline-button{display:inline-flex;min-height:44px;align-items:center;gap:8px;border-radius:11px;padding:0 18px;font-size:13px;font-weight:900}.quote-new-button{border:1px solid #0f766e;background:#0f766e;color:#fff;box-shadow:0 10px 24px rgb(15 118 110/.2)}.quote-new-button:hover{background:#115e59}.quote-baseline-button{border:1px solid #99f6e4;background:#fff;color:#0f766e;box-shadow:0 8px 20px rgb(15 118 110/.08)}.quote-baseline-button:hover{border-color:#2dd4bf;background:#f0fdfa}.quote-new-button svg,.quote-baseline-button svg{width:18px}
.quote-stage-notice{display:flex;align-items:center;gap:8px;border:1px solid #bae6fd;border-radius:10px;background:#f0f9ff;padding:8px 11px;color:#0369a1;font-size:11px}.quote-stage-notice span{border-radius:999px;background:#0284c7;padding:3px 7px;color:#fff;font-size:9px;font-weight:900;letter-spacing:.08em}
.quote-page-message{margin:0;border-radius:9px;padding:9px 12px;font-size:11px}.quote-page-message.error{border:1px solid #fecaca;background:#fef2f2;color:#b91c1c}
.quote-kpi-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}.quote-kpi-grid article{position:relative;overflow:hidden;border:1px solid #dbe5ea;border-radius:12px;background:#fff;padding:14px;box-shadow:0 7px 24px rgb(15 23 42/.04)}.quote-kpi-grid article::after{position:absolute;inset:0 auto 0 0;width:3px;background:var(--tone);content:''}.quote-kpi-grid article>div{display:flex;align-items:center;gap:7px;color:#64748b;font-size:10px;font-weight:900;letter-spacing:.05em}.quote-kpi-grid svg{width:15px;color:var(--tone)}.quote-kpi-grid strong{display:block;margin-top:12px;color:#0f172a;font-size:28px;line-height:1}.quote-kpi-grid p{margin:7px 0 0;color:#94a3b8;font-size:10px}.tone-blue{--tone:#2563eb}.tone-amber{--tone:#d97706}.tone-red{--tone:#dc2626}.tone-teal{--tone:#0f766e}.tone-green{--tone:#059669}.tone-slate{--tone:#64748b}
.quote-list-panel{overflow:hidden;border:1px solid #dbe5ea;border-radius:14px;background:#fff;box-shadow:0 16px 38px rgb(15 23 42/.05)}.quote-list-toolbar{display:flex;align-items:center;gap:14px;padding:13px;border-bottom:1px solid #e2e8f0}.quote-search-box{display:flex;min-width:280px;flex:1;align-items:center;gap:8px;border:1px solid #dbe5ea;border-radius:9px;background:#f8fafc;padding:0 11px;color:#94a3b8}.quote-search-box:focus-within{border-color:#14b8a6;background:#fff;box-shadow:0 0 0 3px rgb(20 184 166/.08)}.quote-search-box svg{width:16px}.quote-search-box input{min-width:0;flex:1;border:0;background:transparent;padding:9px 0;color:#0f172a;font-size:12px;outline:0}.quote-filters{display:flex;align-items:center;gap:8px;color:#94a3b8}.quote-filters>svg{width:16px}.quote-filters select{height:36px;border:1px solid #dbe5ea;border-radius:9px;background:#fff;padding:0 28px 0 10px;color:#475569;font-size:11px;font-weight:700}.quote-clear-filter{display:grid;width:36px;height:36px;place-items:center;border:1px solid #dbe5ea;border-radius:9px;background:#fff;color:#64748b}.quote-clear-filter:hover{border-color:#99f6e4;background:#f0fdfa;color:#0f766e}.quote-clear-filter svg{width:15px}
.quote-table-scroll{overflow:auto}.quote-table{width:100%;min-width:1080px;border-collapse:collapse;text-align:left}.quote-table th{background:#f1f5f9;padding:10px 12px;color:#64748b;font-size:9px;font-weight:900;letter-spacing:.08em;text-transform:uppercase}.quote-table td{border-top:1px solid #eef2f6;padding:11px 12px;color:#334155;font-size:11px;vertical-align:middle}.quote-table tbody tr{transition:background .15s}.quote-table tbody tr:hover{background:#f8fafc}.quote-table td:nth-child(2) strong{display:block;color:#0f172a;font-size:12px}.quote-table td:nth-child(2) span,.quote-table small{display:block;margin-top:3px;color:#94a3b8;font-size:10px}.quote-number{border:0;background:transparent;padding:0;color:#0f766e;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px;font-weight:900}.quote-number:hover{text-decoration:underline}.quote-initiator,.quote-version{display:inline-flex;border-radius:999px;background:#f1f5f9;padding:4px 7px;color:#475569;font-size:9px;font-weight:900}.quote-status{display:inline-flex;align-items:center;gap:6px;border-radius:999px;background:color-mix(in srgb,var(--tone) 10%,white);padding:5px 8px;color:var(--tone);font-size:9px;font-weight:900;white-space:nowrap}.quote-status i{width:6px;height:6px;border-radius:99px;background:currentColor}.quote-progress-cell{display:flex;min-width:120px;align-items:center;gap:8px}.quote-progress-cell>div{height:6px;flex:1;overflow:hidden;border-radius:99px;background:#e2e8f0}.quote-progress-cell>div span{display:block;height:100%;border-radius:99px;background:#0d9488}.quote-progress-cell strong{color:#475569;font-size:10px}.quote-date{color:#64748b;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:10px;white-space:nowrap}.quote-row-actions{display:flex;justify-content:flex-end;gap:5px}.quote-row-actions button{display:grid;width:30px;height:30px;place-items:center;border:1px solid #e2e8f0;border-radius:8px;background:#fff;color:#64748b}.quote-row-actions button:hover{border-color:#99f6e4;background:#f0fdfa;color:#0f766e}.quote-row-actions button.primary{border-color:#0f766e;background:#0f766e;color:#fff}.quote-row-actions svg{width:14px}.quote-empty{padding:40px!important;text-align:center;color:#94a3b8!important}.quote-table-footer{display:flex;justify-content:space-between;gap:12px;border-top:1px solid #e2e8f0;background:#f8fafc;padding:10px 13px;color:#64748b;font-size:10px}
@media(max-width:1100px){.quote-kpi-grid{grid-template-columns:repeat(3,1fr)}.quote-list-toolbar{align-items:stretch;flex-direction:column}.quote-filters{flex-wrap:wrap}.quote-filters select{flex:1}.quote-clear-filter{flex:0 0 auto}}
@media(max-width:700px){.quote-home-heading{align-items:stretch;flex-direction:column}.quote-heading-actions{display:grid;grid-template-columns:1fr 1fr}.quote-new-button,.quote-baseline-button{justify-content:center}.quote-kpi-grid{grid-template-columns:repeat(2,1fr)}.quote-search-box{min-width:0}.quote-filters>svg{display:none}.quote-table-footer{flex-direction:column}.quote-stage-notice{align-items:flex-start}}
</style>
