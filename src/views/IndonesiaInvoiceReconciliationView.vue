<script setup lang="ts">
import {
  ArrowLeft,
  CheckCircle2,
  ClipboardCheck,
  FileText,
  ShieldCheck,
} from '@lucide/vue'
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import {
  indonesiaInvoiceApi,
  type RriInvoiceDocument,
  type RriInvoiceLineCheck,
  type RriInvoiceReconciliationResponse,
} from '@/api/indonesiaInvoice'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import { getDepartmentRoute, getFactoryScopedRoute } from '@/data/enterpriseMock'
import { getApiErrorMessage } from '@/lib/http'
import { useAppStore } from '@/stores/app'

type InvoiceStatus = '已核对' | '待复核' | '待补资料' | '核对异常'
type InvoiceFileSide = 'a' | 'b'

const appStore = useAppStore()
const accountingDepartmentRoute = computed(() => getFactoryScopedRoute(
  getDepartmentRoute('accounting'),
  appStore.activeProductionFactory.id,
))

interface InvoicePair {
  id: string
  customerInvoice: string
  supplierInvoice: string
  customer: string
  amount: number
  status: InvoiceStatus
  detail: string
}

const activeSection = ref('overview')
const invoiceAFile = ref<File | null>(null)
const invoiceBFile = ref<File | null>(null)
const invoiceAFileName = ref('')
const invoiceBFileName = ref('')
const dragOverSide = ref<InvoiceFileSide | null>(null)
const hasStartedReview = ref(false)
const isReconciling = ref(false)
const reconciliationError = ref('')
const reconciliationResult = ref<RriInvoiceReconciliationResponse | null>(null)

const sampleInvoicePairs: InvoicePair[] = [
  {
    id: 'INV-240601-018',
    customerInvoice: '施信（Faith Jet）客户发票',
    supplierInvoice: 'Royal Regent 供应商发票',
    customer: '施信（Faith Jet）',
    amount: 28540.6,
    status: '已核对',
    detail: '单号、SKU、数量与金额一致',
  },
  {
    id: 'SMC00040',
    customerInvoice: '施信（Faith Jet）客户发票',
    supplierInvoice: 'Royal Regent 供应商发票',
    customer: '施信（Faith Jet）',
    amount: 19680,
    status: '待复核',
    detail: '供应商单价需按 × 0.98 规则确认',
  },
]

const invoicePairs = computed<InvoicePair[]>(() => sampleInvoicePairs)
const completedCount = computed(() => reconciliationResult.value?.summary.matched_line_count ?? invoicePairs.value.filter((pair) => pair.status === '已核对').length)
const reviewCount = computed(() => (reconciliationResult.value?.summary.mismatch_line_count ?? 0) + (reconciliationResult.value?.summary.missing_supplier_line_count ?? invoicePairs.value.filter((pair) => pair.status === '待复核').length))
const missingCount = computed(() => reconciliationResult.value?.summary.missing_supplier_line_count ?? invoicePairs.value.filter((pair) => pair.status === '待补资料').length)
const totalAmount = computed(() => reconciliationResult.value?.summary.supplier_declared_total_hkd ?? invoicePairs.value.reduce((sum, pair) => sum + pair.amount, 0))
const formattedTotalAmount = computed(() => `${reconciliationResult.value ? 'HKD' : 'US$'} ${totalAmount.value.toLocaleString('en-US', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})}`)
const canStartReview = computed(() => Boolean(invoiceAFile.value && invoiceBFile.value) && !isReconciling.value)
const resultLineChecks = computed(() => reconciliationResult.value?.line_checks ?? [])
const issueLineChecks = computed(() => resultLineChecks.value.filter((line) => line.status !== 'matched'))
const sortedLineChecks = computed(() => [...resultLineChecks.value].sort((first, second) => {
  return Number(first.status === 'matched') - Number(second.status === 'matched')
}))
const issueHeaderChecks = computed(() => reconciliationResult.value?.header_checks.filter((check) => check.status !== 'matched') ?? [])
const totalIssueCount = computed(() => issueLineChecks.value.length + issueHeaderChecks.value.length)

const overviewCards = computed(() => [
  {
    label: '票据组数',
    value: String(reconciliationResult.value?.summary.customer_line_count ?? invoicePairs.value.length),
    detail: reconciliationResult.value ? '本次客户票核对明细行' : '施信客户规则的示例明细',
    tone: 'teal',
  },
  {
    label: '已完成核对',
    value: String(completedCount.value),
    detail: reconciliationResult.value ? '单价、金额与票头均已校验' : '字段与金额已确认',
    tone: 'blue',
  },
  {
    label: '待人工复核',
    value: String(reviewCount.value),
    detail: `待补资料 ${missingCount.value} 行`,
    tone: 'red',
  },
  {
    label: '票据金额汇总',
    value: formattedTotalAmount.value,
    detail: reconciliationResult.value ? '换算后供应商票总额' : '当前前端样例汇总',
    tone: 'amber',
  },
])

const invoiceFormats = [
  { customer: '施信客户', kind: '客户票', title: '施信（Faith Jet）客户发票', detail: '1 页 · 英文表格', fields: '发票号 / PO / 日期 / SKU / 数量 / 单价 / 总额' },
  { customer: '施信客户', kind: '供应商票', title: 'Royal Regent 供应商发票', detail: '2 页 · 中英双语', fields: '发票号 / S/N / 日期 / 货号 / 数量 / 单价 / 总额' },
]

function selectSection(section: string) {
  activeSection.value = section
  document.getElementById(section)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function clearPreviousReconciliation() {
  hasStartedReview.value = false
  reconciliationResult.value = null
  reconciliationError.value = ''
}

function isPdfFile(file: File) {
  return file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
}

function selectInvoiceFile(side: InvoiceFileSide, file: File | null) {
  if (!file) {
    return
  }

  if (!isPdfFile(file)) {
    reconciliationError.value = '仅支持导入 PDF 文件，请重新选择或拖入 PDF。'
    return
  }

  if (side === 'a') {
    invoiceAFile.value = file
    invoiceAFileName.value = file.name
  }
  else {
    invoiceBFile.value = file
    invoiceBFileName.value = file.name
  }

  clearPreviousReconciliation()
}

function updateSelectedFile(side: InvoiceFileSide, event: Event) {
  const input = event.target as HTMLInputElement
  selectInvoiceFile(side, input.files?.[0] ?? null)
}

function dropFile(side: InvoiceFileSide, event: DragEvent) {
  dragOverSide.value = null
  selectInvoiceFile(side, event.dataTransfer?.files?.[0] ?? null)
}

async function startReview() {
  if (!invoiceAFile.value || !invoiceBFile.value || isReconciling.value) {
    return
  }

  isReconciling.value = true
  reconciliationError.value = ''
  try {
    reconciliationResult.value = await indonesiaInvoiceApi.reconcileRri({
      invoiceA: invoiceAFile.value,
      invoiceB: invoiceBFile.value,
    })
    hasStartedReview.value = true
  }
  catch (error) {
    reconciliationError.value = getApiErrorMessage(error)
    hasStartedReview.value = false
  }
  finally {
    isReconciling.value = false
  }
}

function inputSlotLabel(document: RriInvoiceDocument) {
  return document.input_slot ? `PDF ${document.input_slot}` : '已识别 PDF'
}

function inputFileName(document: RriInvoiceDocument) {
  if (document.input_slot === 'A') {
    return invoiceAFileName.value || 'PDF 文件 A'
  }
  if (document.input_slot === 'B') {
    return invoiceBFileName.value || 'PDF 文件 B'
  }
  return '已识别 PDF'
}

function formatHkd(value: number | null, decimals = 2) {
  if (value === null) {
    return '未识别'
  }
  return `HKD ${value.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`
}

function lineIssueLabels(line: RriInvoiceLineCheck) {
  if (line.status === 'missing_supplier_line') {
    return ['供应商票缺少对应明细']
  }

  const labels: string[] = []
  if (line.price_status === 'mismatch') {
    labels.push('供应商单价异常')
  }
  if (line.amount_status === 'mismatch') {
    labels.push('供应商行金额异常')
  }
  return labels.length ? labels : ['逐项一致']
}

function lineStatusLabel(line: RriInvoiceLineCheck) {
  return line.status === 'matched'
    ? '一致'
    : line.status === 'missing_supplier_line'
      ? '缺少供应商明细'
      : '存在差异'
}

function statusClass(status: InvoiceStatus) {
  if (status === '已核对') {
    return 'status-complete'
  }

  if (status === '待复核') {
    return 'status-review'
  }

  return status === '待补资料' ? 'status-missing' : 'status-review'
}
</script>

<template>
  <main class="invoice-workspace">
    <header class="invoice-topbar">
      <div class="invoice-topbar-inner">
        <div class="invoice-brand">
          <span class="invoice-brand-mark">票</span>
          <span>票审</span>
        </div>

        <nav class="invoice-step-nav" aria-label="印尼票据核对页面导航">
          <button
            v-for="(item, index) in [
              { id: 'overview', label: '核对总览' },
              { id: 'import-files', label: 'PDF 导入' },
              { id: 'invoice-records', label: '核对记录' },
            ]"
            :key="item.id"
            type="button"
            class="invoice-step-tab"
            :class="{ active: activeSection === item.id }"
            @click="selectSection(item.id)"
          >
            <span class="step-no">{{ index + 1 }}</span>
            {{ item.label }}
          </button>
        </nav>

        <div class="browser-only-note">
          <span class="live-dot" aria-hidden="true" />
          PDF 仅用于本次核对，完成后不保存
        </div>

        <div class="invoice-topbar-right">
          <span class="workspace-badge">全车间共享</span>
          <AccountMenu />
        </div>
      </div>
    </header>

    <div class="invoice-page">
      <section id="overview" class="workspace-head">
        <RouterLink :to="accountingDepartmentRoute" class="back-link">
          <ArrowLeft class="size-4" aria-hidden="true" />
          会计部模块中心
        </RouterLink>

        <div class="workspace-heading-row">
          <div>
            <p class="eyebrow"><span /> PDF · 双票核对</p>
            <div class="title-line">
              <h1>印尼票据核对</h1>
              <span class="workspace-pill"><span class="live-dot" /> 当前工作台</span>
            </div>
            <p class="workspace-subtitle">全车间共用的票据核对工具，按客户规则识别；导入任意顺序的两份 PDF 后，系统自动判断客户票与供应商票并进行核对。</p>
          </div>

          <div class="head-summary-card">
            <p>当前客户规则</p>
            <strong>{{ reconciliationResult?.customer_name ?? '施信' }}</strong>
            <span>全车间共享 · 当前已接入施信客户票据逻辑</span>
          </div>
        </div>
      </section>

      <section class="overview-metrics" aria-label="票据核对汇总">
        <article v-for="metric in overviewCards" :key="metric.label" class="metric-card" :class="`metric-${metric.tone}`">
          <p>{{ metric.label }}</p>
          <strong>{{ metric.value }}</strong>
          <span>{{ metric.detail }}</span>
        </article>
      </section>

      <section id="import-files" class="workflow-card">
        <div class="section-heading">
          <span class="section-number">01</span>
          <div>
            <h2>导入两份 PDF</h2>
            <p>PDF A、B 不分客户票或供应商票；任选两个框导入，系统会自动识别票据角色并即时核对。</p>
          </div>
          <span class="file-limit">单个文件建议不超过 20MB</span>
        </div>

        <div class="file-grid">
          <label
            class="file-picker"
            :class="{ selected: invoiceAFileName, 'drop-active': dragOverSide === 'a' }"
            @dragenter.prevent="dragOverSide = 'a'"
            @dragover.prevent="dragOverSide = 'a'"
            @dragleave.prevent="dragOverSide = null"
            @drop.prevent="dropFile('a', $event)"
          >
            <input type="file" accept="application/pdf,.pdf" @change="updateSelectedFile('a', $event)">
            <span class="file-letter">A</span>
            <span class="file-copy">
              <strong>导入 PDF 文件 A</strong>
              <small>{{ invoiceAFileName || '任意票据 · 点击选择或拖拽 PDF 至此' }}</small>
            </span>
            <span class="choose-file">{{ invoiceAFileName ? '替换文件' : '选择文件' }}</span>
          </label>

          <label
            class="file-picker"
            :class="{ selected: invoiceBFileName, 'drop-active': dragOverSide === 'b' }"
            @dragenter.prevent="dragOverSide = 'b'"
            @dragover.prevent="dragOverSide = 'b'"
            @dragleave.prevent="dragOverSide = null"
            @drop.prevent="dropFile('b', $event)"
          >
            <input type="file" accept="application/pdf,.pdf" @change="updateSelectedFile('b', $event)">
            <span class="file-letter">B</span>
            <span class="file-copy">
              <strong>导入 PDF 文件 B</strong>
              <small>{{ invoiceBFileName || '任意票据 · 点击选择或拖拽 PDF 至此' }}</small>
            </span>
            <span class="choose-file">{{ invoiceBFileName ? '替换文件' : '选择文件' }}</span>
          </label>
        </div>

        <div class="import-footer">
          <p v-if="hasStartedReview" class="front-end-notice">
            <CheckCircle2 class="size-4" aria-hidden="true" />
            已自动识别：{{ inputSlotLabel(reconciliationResult!.customer_invoice) }} 为客户票，{{ inputSlotLabel(reconciliationResult!.supplier_invoice) }} 为供应商票；{{ reconciliationResult?.summary.matched_line_count }} / {{ reconciliationResult?.summary.customer_line_count }} 行一致。
          </p>
          <p v-else-if="reconciliationError" class="import-error">{{ reconciliationError }}</p>
          <p v-else>将两份票据随意放入 A、B 框，系统会自动区分客户票与供应商票。</p>
          <button type="button" class="start-review-button" :disabled="!canStartReview" @click="startReview">
            <ClipboardCheck class="size-4" aria-hidden="true" />
            {{ isReconciling ? '核对中…' : '开始核对' }}
          </button>
        </div>
      </section>

      <section class="rule-band">
        <div>
          <p class="eyebrow"><span /> 施信客户核对规则</p>
          <h2>客户单价 <strong>× 0.98</strong> = 供应商单价</h2>
        </div>
        <p>单价先保留 4 位小数，再乘数量并保留 2 位金额；总额取所有换算后行金额之和。客户票 PO、供应商票 S/N、发票号和日期也必须一致。</p>
      </section>

      <section class="format-section" aria-labelledby="format-title">
        <div class="section-heading compact-heading">
          <span class="section-number">02</span>
          <div>
            <h2 id="format-title">施信客户两种票据版式已接入</h2>
            <p>已按提供的 Faith Jet 客户票与 Royal Regent 供应商票建立逐行核对；后续其他客户按各自票据版式接入，不按车间区分。</p>
          </div>
        </div>

        <div class="format-grid">
          <article v-for="format in invoiceFormats" :key="`${format.customer}-${format.kind}`" class="format-card">
            <div class="invoice-paper" aria-hidden="true">
              <strong>INVOICE</strong>
              <span /><span /><span /><span />
            </div>
            <div class="format-copy">
              <p>{{ format.customer }} · {{ format.kind }}</p>
              <h3>{{ format.title }}</h3>
              <span>{{ format.detail }}</span>
              <small>{{ format.fields }}</small>
            </div>
            <span class="recognized-badge"><CheckCircle2 class="size-3.5" aria-hidden="true" /> 已接入</span>
          </article>
        </div>
      </section>

      <section id="invoice-records" class="records-section">
        <template v-if="reconciliationResult">
          <div class="comparison-heading">
            <div>
              <p class="eyebrow"><span /> 本次核对结论</p>
              <h2>先看差异，再看全部明细</h2>
              <p>{{ reconciliationResult.rounding_rule }}</p>
              <p class="customer-rule-note">当前客户规则：<strong>{{ reconciliationResult.customer_name }}</strong> · 全车间共享</p>
            </div>
            <span class="reconciliation-status" :class="{ issue: totalIssueCount > 0 }">
              {{ totalIssueCount > 0 ? `发现 ${totalIssueCount} 项差异` : '核对无差异' }}
            </span>
          </div>

          <div class="source-document-grid" aria-label="自动识别的票据来源">
            <article class="source-document-card customer-document">
              <p>客户票 · 自动识别</p>
              <h3>{{ inputSlotLabel(reconciliationResult.customer_invoice) }}</h3>
              <small>{{ inputFileName(reconciliationResult.customer_invoice) }}</small>
              <dl>
                <div><dt>发票号</dt><dd>{{ reconciliationResult.customer_invoice.invoice_no || '未识别' }}</dd></div>
                <div><dt>PO</dt><dd>{{ reconciliationResult.customer_invoice.po_no || '未识别' }}</dd></div>
                <div><dt>日期</dt><dd>{{ reconciliationResult.customer_invoice.date || '未识别' }}</dd></div>
                <div><dt>票面总额</dt><dd>{{ formatHkd(reconciliationResult.customer_invoice.declared_total_hkd) }}</dd></div>
              </dl>
            </article>
            <article class="source-document-card supplier-document">
              <p>供应商票 · 自动识别</p>
              <h3>{{ inputSlotLabel(reconciliationResult.supplier_invoice) }}</h3>
              <small>{{ inputFileName(reconciliationResult.supplier_invoice) }}</small>
              <dl>
                <div><dt>发票号</dt><dd>{{ reconciliationResult.supplier_invoice.invoice_no || '未识别' }}</dd></div>
                <div><dt>S/N</dt><dd>{{ reconciliationResult.supplier_invoice.po_no || '未识别' }}</dd></div>
                <div><dt>日期</dt><dd>{{ reconciliationResult.supplier_invoice.date || '未识别' }}</dd></div>
                <div><dt>票面总额</dt><dd>{{ formatHkd(reconciliationResult.supplier_invoice.declared_total_hkd) }}</dd></div>
              </dl>
            </article>
          </div>

          <section class="header-check-section" aria-labelledby="header-check-title">
            <div class="comparison-section-heading">
              <div>
                <p class="eyebrow"><span /> 票头对照</p>
                <h3 id="header-check-title">哪一张票的字段不一致，一眼可见</h3>
              </div>
              <span>{{ issueHeaderChecks.length ? `${issueHeaderChecks.length} 个票头字段异常` : '票头字段一致' }}</span>
            </div>
            <div class="header-check-grid">
              <article
                v-for="check in reconciliationResult.header_checks"
                :key="check.field"
                class="header-check-card"
                :class="{ mismatch: check.status !== 'matched' }"
              >
                <div class="header-check-title">
                  <strong>{{ check.field }}</strong>
                  <span>{{ check.status === 'matched' ? '一致' : '不一致' }}</span>
                </div>
                <div class="header-check-values">
                  <p><small>客户票 · {{ inputSlotLabel(reconciliationResult.customer_invoice) }}</small><b>{{ check.customer_value || '未识别' }}</b></p>
                  <p><small>供应商票 · {{ inputSlotLabel(reconciliationResult.supplier_invoice) }}</small><b>{{ check.supplier_value || '未识别' }}</b></p>
                </div>
                <small class="header-check-note">{{ check.status === 'matched' ? '两张票据字段一致。' : check.note || '请检查两张票据对应字段。' }}</small>
              </article>
            </div>
          </section>

          <section class="line-check-section" aria-labelledby="line-check-title">
            <div class="comparison-section-heading">
              <div>
                <p class="eyebrow"><span /> 明细逐行对照</p>
                <h3 id="line-check-title">差异行置顶，直接定位到单价或金额</h3>
              </div>
              <span>{{ issueLineChecks.length ? `${issueLineChecks.length} 行需要复核` : `${resultLineChecks.length} 行全部一致` }}</span>
            </div>

            <div v-if="issueLineChecks.length" class="difference-callout">
              <strong>差异清单</strong>
              <span>红色行优先展示；可直接看到是供应商票缺行、供应商单价异常，还是供应商行金额异常。</span>
            </div>

            <div class="comparison-table-wrap">
              <table class="comparison-table">
                <thead>
                  <tr>
                    <th>客户票明细 · {{ inputSlotLabel(reconciliationResult.customer_invoice) }}</th>
                    <th>客户票实际值</th>
                    <th>预期供应商值（× {{ reconciliationResult.factor }}）</th>
                    <th>供应商票实际值 · {{ inputSlotLabel(reconciliationResult.supplier_invoice) }}</th>
                    <th>核对结论</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="line in sortedLineChecks" :key="`${line.customer_sku}-${line.description}-${line.quantity}`" :class="{ 'issue-row': line.status !== 'matched' }">
                    <td class="line-product-cell">
                      <strong>{{ line.customer_sku }}</strong>
                      <span>{{ line.description }}</span>
                      <small>数量 {{ line.quantity }}</small>
                    </td>
                    <td class="line-money-cell">
                      <span>单价 {{ formatHkd(line.customer_unit_price_hkd, 4) }}</span>
                      <small>行金额 {{ formatHkd(line.customer_amount_hkd) }}</small>
                    </td>
                    <td class="line-money-cell expected-cell">
                      <span>单价 {{ formatHkd(line.expected_supplier_unit_price_hkd, 4) }}</span>
                      <small>行金额 {{ formatHkd(line.expected_supplier_amount_hkd) }}</small>
                    </td>
                    <td class="line-money-cell" :class="{ missing: !line.supplier_sku }">
                      <template v-if="line.supplier_sku">
                        <strong>货号 {{ line.supplier_sku }}</strong>
                        <span>单价 {{ formatHkd(line.supplier_unit_price_hkd, 4) }}</span>
                        <small>行金额 {{ formatHkd(line.supplier_amount_hkd) }}</small>
                      </template>
                      <strong v-else>未找到对应供应商明细</strong>
                    </td>
                    <td class="line-result-cell">
                      <span class="line-status" :class="{ issue: line.status !== 'matched' }">{{ lineStatusLabel(line) }}</span>
                      <div class="line-issue-labels">
                        <span v-for="label in lineIssueLabels(line)" :key="label" :class="{ issue: line.status !== 'matched' }">{{ label }}</span>
                      </div>
                      <small>{{ line.note || '客户票与供应商票的单价、金额均一致。' }}</small>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </template>

        <template v-else>
          <div class="records-heading">
            <div>
              <p class="eyebrow"><span /> 核对记录</p>
              <h2>当前票据汇总</h2>
              <p>以下为施信客户规则示例；完成 PDF 核对后将替换为本次的字段级结果。</p>
            </div>
          </div>

          <div class="records-table-wrap">
            <table class="records-table">
              <thead>
                <tr>
                  <th>票据组</th>
                  <th>客户</th>
                  <th>客户票 / 供应商票</th>
                  <th>金额</th>
                  <th>核对状态</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="pair in invoicePairs" :key="pair.id">
                  <td><strong>{{ pair.id }}</strong></td>
                  <td><span class="customer-chip">{{ pair.customer }}</span></td>
                  <td>
                    <div class="invoice-names">
                      <span>{{ pair.customerInvoice }}</span>
                      <small>{{ pair.supplierInvoice }}</small>
                    </div>
                  </td>
                  <td>US$ {{ pair.amount.toLocaleString('en-US', { minimumFractionDigits: 2 }) }}</td>
                  <td>
                    <span class="status-badge" :class="statusClass(pair.status)">{{ pair.status }}</span>
                    <small class="status-detail">{{ pair.detail }}</small>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </section>

      <footer class="workspace-footer">
        <span><ShieldCheck class="size-4" aria-hidden="true" /> 印尼票据核对 · 独立前端工作台</span>
        <span><FileText class="size-4" aria-hidden="true" /> PDF 仅即时解析；不保存文件或核对记录</span>
      </footer>
    </div>
  </main>
</template>

<style scoped>
.invoice-workspace {
  min-height: 100vh;
  background:
    radial-gradient(circle at 74% 0%, rgba(207, 250, 232, 0.5), transparent 26rem),
    #f7f8f4;
  color: #17241f;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.invoice-topbar {
  position: sticky;
  top: 0;
  z-index: 40;
  border-bottom: 1px solid #e2e8e4;
  background: rgba(250, 251, 248, 0.92);
  backdrop-filter: blur(12px) saturate(1.3);
}

.invoice-topbar-inner {
  display: flex;
  min-height: 64px;
  max-width: 1600px;
  align-items: center;
  gap: 22px;
  margin: 0 auto;
  padding: 10px 30px;
}

.invoice-brand,
.invoice-topbar-right,
.browser-only-note,
.invoice-step-nav,
.workspace-pill,
.back-link,
.eyebrow,
.front-end-notice,
.recognized-badge,
.workspace-footer,
.record-search {
  display: flex;
  align-items: center;
}

.invoice-brand {
  flex: 0 0 auto;
  gap: 10px;
  color: #10251e;
  font-size: 18px;
  font-weight: 800;
}

.invoice-brand-mark {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 8px;
  background: #17664f;
  color: #fff;
  box-shadow: 0 7px 16px rgba(23, 102, 79, 0.24);
}

.invoice-step-nav {
  min-width: 0;
  flex: 1 1 auto;
  gap: 5px;
  overflow-x: auto;
}

.invoice-step-tab {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  border: 0;
  border-radius: 999px;
  background: transparent;
  padding: 8px 13px;
  color: #6b7c76;
  font-size: 13px;
  font-weight: 750;
  white-space: nowrap;
  transition: 0.16s ease;
}

.invoice-step-tab:hover { background: #edf4ef; color: #174b3b; }
.invoice-step-tab.active { background: #17664f; color: #fff; box-shadow: 0 5px 12px rgba(23, 102, 79, 0.18); }

.step-no {
  display: inline-grid;
  width: 19px;
  height: 19px;
  place-items: center;
  margin-right: 6px;
  border-radius: 999px;
  background: #edf2ef;
  color: #6f8179;
  font-size: 11px;
  font-weight: 800;
}
.invoice-step-tab.active .step-no { background: rgba(255, 255, 255, 0.18); color: #fff; }

.browser-only-note { flex: 0 0 auto; gap: 8px; color: #71817a; font-size: 13px; }
.live-dot { width: 8px; height: 8px; flex: 0 0 auto; border-radius: 999px; background: #45bf82; box-shadow: 0 0 0 4px rgba(69, 191, 130, 0.13); }
.invoice-topbar-right { flex: 0 0 auto; gap: 14px; }
.workspace-badge { color: #17664f; font-size: 13px; font-weight: 800; white-space: nowrap; }

.invoice-page { max-width: 1600px; margin: 0 auto; padding: 34px 30px 64px; }
.workspace-head { scroll-margin-top: 94px; }
.back-link { width: fit-content; gap: 7px; color: #61726a; font-size: 13px; font-weight: 750; transition: color .16s ease; }
.back-link:hover { color: #17664f; }

.workspace-heading-row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(280px, 400px); gap: 32px; align-items: end; margin-top: 34px; }
.eyebrow { gap: 11px; color: #176e58; font-size: 12px; font-weight: 850; letter-spacing: .12em; text-transform: uppercase; }
.eyebrow > span { width: 34px; height: 2px; background: #176e58; }
.title-line { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; margin-top: 14px; }
.title-line h1 { margin: 0; color: #10251e; font-size: clamp(36px, 4.3vw, 62px); font-weight: 850; letter-spacing: -.07em; line-height: 1.05; }
.workspace-pill { gap: 7px; border: 1px solid #b7ead7; border-radius: 999px; background: #edfff7; padding: 7px 11px; color: #177559; font-size: 12px; font-weight: 800; }
.workspace-pill .live-dot { width: 6px; height: 6px; box-shadow: none; }
.workspace-subtitle { max-width: 770px; margin: 18px 0 0; color: #677a72; font-size: 16px; line-height: 1.75; }

.head-summary-card { position: relative; overflow: hidden; min-height: 172px; border-radius: 28px; background: #17664f; padding: 26px 30px; color: #edfff8; box-shadow: 0 26px 44px rgba(23, 102, 79, 0.2); }
.head-summary-card::after { position: absolute; top: -70px; right: -22px; width: 190px; height: 190px; border: 1px solid rgba(255, 255, 255, .14); border-radius: 50%; box-shadow: 0 0 0 32px rgba(255, 255, 255, .04), 0 0 0 65px rgba(255, 255, 255, .035); content: ''; }
.head-summary-card p, .head-summary-card span { position: relative; z-index: 1; margin: 0; font-size: 13px; font-weight: 750; }
.head-summary-card strong { position: relative; z-index: 1; display: block; margin: 15px 0 6px; font-size: 42px; letter-spacing: -.05em; }
.head-summary-card span { color: #bfe4d6; font-weight: 500; }

.overview-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-top: 28px; }
.metric-card { min-height: 145px; border: 1px solid; border-radius: 16px; padding: 18px 20px; box-shadow: 0 8px 22px rgba(20, 55, 43, .035); }
.metric-card p, .metric-card span { margin: 0; color: #61726a; font-size: 12px; }
.metric-card strong { display: block; margin: 11px 0 5px; color: #10251e; font-size: clamp(24px, 2.4vw, 33px); letter-spacing: -.05em; line-height: 1.05; }
.metric-teal { border-color: #a9f0d3; background: #f0fdf7; }
.metric-blue { border-color: #cbdcff; background: #f3f7ff; }
.metric-red { border-color: #ffd3d4; background: #fff6f5; }
.metric-amber { border-color: #f6e5a4; background: #fffcf0; }

.workflow-card, .records-section { scroll-margin-top: 88px; margin-top: 34px; border: 1px solid #e0e7e2; border-radius: 24px; background: #fffefa; box-shadow: 0 18px 48px rgba(20, 55, 43, .06); }
.workflow-card { padding: 32px; }
.section-heading { display: flex; align-items: center; gap: 16px; }
.section-number { display: inline-grid; width: 44px; height: 44px; flex: 0 0 auto; place-items: center; border-radius: 999px; background: #e5ffad; color: #285c4b; font-size: 13px; font-weight: 900; }
.section-heading h2, .records-heading h2, .rule-band h2 { margin: 0; color: #122820; font-size: 23px; letter-spacing: -.035em; }
.section-heading p, .records-heading > div > p { margin: 5px 0 0; color: #73837c; font-size: 14px; line-height: 1.55; }
.file-limit { margin-left: auto; color: #8b9892; font-size: 12px; }

.file-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; margin-top: 28px; }
.file-picker { display: flex; min-height: 134px; align-items: center; gap: 16px; border: 1.5px dashed #b9d2c7; border-radius: 15px; background: #fbfdf9; padding: 22px 24px; cursor: pointer; transition: .16s ease; }
.file-picker:hover, .file-picker.selected { border-color: #43aa83; background: #f5fff9; box-shadow: 0 7px 16px rgba(49, 144, 106, .07); }
.file-picker.drop-active { border-color: #17664f; background: #ebfff4; box-shadow: 0 0 0 4px rgba(67, 170, 131, .16); }
.file-picker.drop-active .choose-file { border-color: #9edfc5; background: #fff; }
.file-picker input { position: absolute; width: 1px; height: 1px; overflow: hidden; opacity: 0; pointer-events: none; }
.file-letter { display: grid; width: 50px; height: 50px; flex: 0 0 auto; place-items: center; border-radius: 12px; background: #17251f; box-shadow: 7px 7px 0 #e5ffad; color: #fff; font-family: Georgia, serif; font-size: 22px; }
.file-copy { min-width: 0; flex: 1; }
.file-copy strong, .file-copy small { display: block; }
.file-copy strong { color: #172b23; font-size: 15px; }
.file-copy small { margin-top: 7px; overflow: hidden; color: #75847d; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.choose-file { border: 1px solid #dbe7df; border-radius: 999px; background: #fff; padding: 8px 12px; color: #17664f; font-size: 12px; font-weight: 800; white-space: nowrap; }
.import-footer { display: flex; align-items: center; justify-content: space-between; gap: 18px; margin-top: 24px; border-top: 1px solid #edf0ec; padding-top: 20px; }
.import-footer > p { margin: 0; color: #72827a; font-size: 13px; }
.front-end-notice { gap: 8px; color: #237457 !important; }
.import-error { color: #b84e4e !important; font-weight: 700; }
.start-review-button { display: inline-flex; flex: 0 0 auto; align-items: center; gap: 8px; border: 0; border-radius: 10px; background: #17664f; padding: 11px 16px; color: #fff; font-size: 13px; font-weight: 800; box-shadow: 0 8px 15px rgba(23, 102, 79, .18); transition: .16s ease; }
.start-review-button:hover:not(:disabled) { background: #104f3d; transform: translateY(-1px); }
.start-review-button:disabled { background: #bbcbc3; box-shadow: none; cursor: not-allowed; }

.rule-band { display: grid; grid-template-columns: minmax(360px, .8fr) minmax(0, 1.2fr); gap: 28px; align-items: center; margin-top: 28px; border-radius: 20px; background: #edf5df; padding: 27px 32px; }
.rule-band h2 { margin-top: 14px; font-family: Georgia, "Noto Serif SC", serif; font-size: clamp(20px, 2.1vw, 30px); font-weight: 500; }
.rule-band h2 strong { color: #17664f; font-weight: 700; }
.rule-band > p { margin: 0; color: #687a70; font-size: 14px; line-height: 1.75; }

.format-section { margin-top: 40px; }
.compact-heading { margin-bottom: 20px; }
.format-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
.format-card { position: relative; display: flex; min-height: 196px; align-items: center; gap: 26px; overflow: hidden; border: 1px solid #e0e7e2; border-radius: 16px; background: #fffefa; padding: 24px 38px; }
.invoice-paper { display: flex; width: 112px; height: 142px; flex: 0 0 auto; flex-direction: column; align-items: center; gap: 10px; border: 1px solid #d8dfd9; background: #fff; padding: 21px 15px; box-shadow: 12px 12px 0 #e7ece5; color: #273f34; }
.invoice-paper strong { font-family: Georgia, serif; font-size: 11px; }
.invoice-paper span { width: 100%; height: 4px; background: #d6ddd7; }
.invoice-paper span:nth-of-type(2) { width: 72%; margin-top: 9px; }
.format-copy { min-width: 0; }
.format-copy p, .format-copy span, .format-copy small { display: block; }
.format-copy p { margin: 0; color: #177057; font-size: 12px; font-weight: 850; letter-spacing: .08em; }
.format-copy h3 { margin: 13px 0 8px; color: #192c24; font-size: 20px; letter-spacing: -.03em; }
.format-copy span { color: #77877f; font-size: 14px; }
.format-copy small { margin-top: 22px; color: #89958f; font-size: 12px; }
.recognized-badge { position: absolute; top: 24px; right: 26px; gap: 5px; border-radius: 999px; background: #edf9ef; padding: 7px 10px; color: #3f8a66; font-size: 11px; font-weight: 800; }
.recognized-badge.pending { background: #f2f4f2; color: #849189; }

.comparison-heading { display: flex; align-items: end; justify-content: space-between; gap: 24px; padding: 30px 32px 25px; border-bottom: 1px solid #e8ede9; }
.comparison-heading h2, .comparison-section-heading h3 { margin: 10px 0 0; color: #122820; font-size: 23px; letter-spacing: -.035em; }
.comparison-heading > div > p:last-child { margin: 8px 0 0; color: #73837c; font-size: 13px; line-height: 1.6; }
.customer-rule-note strong { color: #17664f; }
.reconciliation-status { flex: 0 0 auto; border: 1px solid #b7ead7; border-radius: 999px; background: #edfff7; padding: 8px 12px; color: #177559; font-size: 12px; font-weight: 850; }
.reconciliation-status.issue { border-color: #ffc7c4; background: #fff1ef; color: #bd4f49; }
.source-document-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; padding: 24px 32px; background: #fbfdfb; }
.source-document-card { border: 1px solid #dce8e0; border-radius: 16px; background: #fffefa; padding: 20px 22px; }
.source-document-card.customer-document { border-top: 4px solid #278c69; }
.source-document-card.supplier-document { border-top: 4px solid #487fbe; }
.source-document-card > p { margin: 0; color: #63766d; font-size: 12px; font-weight: 850; letter-spacing: .08em; }
.source-document-card h3 { margin: 8px 0 3px; color: #173127; font-size: 20px; }
.source-document-card > small { display: block; overflow: hidden; color: #829088; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.source-document-card dl { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 20px 0 0; }
.source-document-card dl div { min-width: 0; border-left: 1px solid #e7ede8; padding-left: 11px; }
.source-document-card dt { color: #8a9891; font-size: 11px; }
.source-document-card dd { margin: 5px 0 0; overflow: hidden; color: #31483c; font-size: 12px; font-weight: 800; text-overflow: ellipsis; white-space: nowrap; }
.header-check-section, .line-check-section { border-top: 1px solid #e8ede9; padding: 26px 32px 30px; }
.comparison-section-heading { display: flex; align-items: end; justify-content: space-between; gap: 20px; }
.comparison-section-heading > span { color: #71817a; font-size: 12px; font-weight: 800; }
.header-check-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 13px; margin-top: 19px; }
.header-check-card { min-width: 0; border: 1px solid #dce8e0; border-radius: 14px; background: #fbfdfb; padding: 15px; }
.header-check-card.mismatch { border-color: #f2aaa7; background: #fff6f5; box-shadow: inset 4px 0 0 #d7635e; }
.header-check-title { display: flex; align-items: center; justify-content: space-between; gap: 9px; }
.header-check-title strong { color: #20382d; font-size: 13px; }
.header-check-title span { border-radius: 999px; background: #eaf8ef; padding: 4px 7px; color: #31805e; font-size: 10px; font-weight: 850; }
.mismatch .header-check-title span { background: #ffe2df; color: #bd4f49; }
.header-check-values { display: grid; gap: 9px; margin-top: 14px; }
.header-check-values p { margin: 0; }
.header-check-values small, .header-check-values b { display: block; }
.header-check-values small { color: #89968f; font-size: 10px; }
.header-check-values b { margin-top: 3px; overflow: hidden; color: #33493e; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.header-check-note { display: block; min-height: 30px; margin-top: 12px; color: #7e8d85; font-size: 11px; line-height: 1.45; }
.mismatch .header-check-note { color: #ad5a55; font-weight: 700; }
.difference-callout { display: flex; align-items: center; gap: 11px; margin: 18px 0 0; border: 1px solid #f2bfbc; border-radius: 12px; background: #fff5f4; padding: 11px 13px; color: #aa534e; font-size: 12px; }
.difference-callout strong { flex: 0 0 auto; }
.comparison-table-wrap { margin-top: 18px; overflow-x: auto; border: 1px solid #e1e9e3; border-radius: 14px; }
.comparison-table { width: 100%; min-width: 1220px; border-collapse: collapse; text-align: left; }
.comparison-table th { padding: 13px 16px; background: #f4f8f5; color: #718178; font-size: 11px; font-weight: 850; letter-spacing: .045em; }
.comparison-table td { border-top: 1px solid #e9eeea; padding: 15px 16px; color: #55675e; font-size: 12px; vertical-align: top; }
.comparison-table tbody tr:first-child td { border-top: 0; }
.comparison-table tbody tr.issue-row td { background: #fff7f6; }
.comparison-table tbody tr.issue-row td:first-child { box-shadow: inset 4px 0 0 #d7635e; }
.line-product-cell { min-width: 260px; }
.line-product-cell strong, .line-product-cell span, .line-product-cell small, .line-money-cell span, .line-money-cell small, .line-money-cell strong, .line-result-cell small { display: block; }
.line-product-cell strong { color: #173127; font-size: 13px; }
.line-product-cell span { max-width: 320px; margin-top: 5px; color: #33493e; font-weight: 750; line-height: 1.4; }
.line-product-cell small, .line-money-cell small { margin-top: 5px; color: #89978f; }
.line-money-cell { min-width: 180px; }
.line-money-cell span, .line-money-cell strong { color: #31483c; font-weight: 750; }
.line-money-cell.expected-cell { background: #f7fbf7; }
.line-money-cell.missing strong { color: #bd5752; }
.line-result-cell { min-width: 235px; }
.line-status { display: inline-block; border-radius: 999px; background: #eaf8ef; padding: 5px 8px; color: #31805e; font-size: 11px; font-weight: 850; }
.line-status.issue { background: #ffe2df; color: #bd4f49; }
.line-issue-labels { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
.line-issue-labels span { border: 1px solid #d8e8dd; border-radius: 999px; background: #f2faf4; padding: 3px 6px; color: #478265; font-size: 10px; font-weight: 800; }
.line-issue-labels span.issue { border-color: #f4c1bd; background: #fff0ee; color: #b7554f; }
.line-result-cell small { margin-top: 8px; color: #7d8c84; line-height: 1.5; }

.records-section { padding: 30px 0 0; overflow: hidden; }
.records-heading { display: flex; align-items: end; justify-content: space-between; gap: 24px; padding: 0 32px 25px; }
.record-search { min-width: 270px; gap: 8px; border: 1px solid #dfe8e2; border-radius: 999px; background: #fbfdfb; padding: 10px 14px; color: #8a9991; font-size: 12px; }
.records-table-wrap { overflow-x: auto; border-top: 1px solid #e8ede9; }
.records-table { width: 100%; min-width: 960px; border-collapse: collapse; text-align: left; }
.records-table th { padding: 13px 32px; background: #f7faf7; color: #829088; font-size: 11px; font-weight: 850; letter-spacing: .08em; text-transform: uppercase; }
.records-table td { border-top: 1px solid #edf0ed; padding: 16px 32px; color: #53655c; font-size: 13px; vertical-align: middle; }
.records-table tbody tr:hover { background: #fbfdfb; }
.records-table td > strong { color: #173127; font-size: 13px; }
.customer-chip { border-radius: 999px; background: #edf7f0; padding: 5px 9px; color: #297056; font-size: 11px; font-weight: 850; }
.invoice-names span, .invoice-names small, .status-detail { display: block; }
.invoice-names span { color: #263c32; font-weight: 700; }
.invoice-names small, .status-detail { margin-top: 4px; color: #8a9891; font-size: 12px; }
.status-badge { display: inline-block; border-radius: 999px; padding: 5px 9px; font-size: 11px; font-weight: 850; }
.status-complete { background: #eaf8ef; color: #31805e; }
.status-review { background: #fff6dc; color: #ac7515; }
.status-missing { background: #fff0ef; color: #bd5752; }

.workspace-footer { justify-content: space-between; gap: 18px; margin-top: 28px; color: #84918b; font-size: 12px; }
.workspace-footer span { display: inline-flex; align-items: center; gap: 7px; }

@media (max-width: 1120px) {
  .invoice-topbar-inner { flex-wrap: wrap; gap: 11px 16px; padding: 10px 22px; }
  .invoice-step-nav { order: 4; flex-basis: 100%; }
  .browser-only-note { margin-left: auto; }
  .workspace-heading-row, .rule-band { grid-template-columns: 1fr; }
  .head-summary-card { max-width: 450px; }
  .overview-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .header-check-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .source-document-card dl { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 760px) {
  .invoice-page { padding: 24px 16px 42px; }
  .invoice-topbar-inner { padding: 10px 16px; }
  .browser-only-note { display: none; }
  .invoice-topbar-right { margin-left: auto; }
  .workspace-heading-row { margin-top: 26px; gap: 22px; }
  .workspace-subtitle { font-size: 14px; }
  .overview-metrics, .file-grid, .format-grid { grid-template-columns: 1fr; }
  .workflow-card { padding: 24px 18px; }
  .section-heading { align-items: flex-start; }
  .file-limit { display: none; }
  .file-picker { min-height: 120px; padding: 18px; }
  .choose-file { display: none; }
  .import-footer, .records-heading, .workspace-footer { align-items: flex-start; flex-direction: column; }
  .rule-band { gap: 18px; padding: 24px; }
  .format-card { min-height: 174px; gap: 18px; padding: 18px; }
  .invoice-paper { width: 82px; height: 112px; padding: 14px 11px; }
  .recognized-badge { top: 15px; right: 15px; }
  .format-copy h3 { max-width: 210px; font-size: 16px; }
  .format-copy small { display: none; }
  .records-section { margin-top: 26px; }
  .records-heading { padding: 0 18px 20px; }
  .record-search { width: 100%; min-width: 0; }
  .comparison-heading, .header-check-section, .line-check-section { padding-right: 18px; padding-left: 18px; }
  .comparison-heading, .comparison-section-heading { align-items: flex-start; flex-direction: column; }
  .source-document-grid { grid-template-columns: 1fr; padding: 18px; }
  .header-check-grid { grid-template-columns: 1fr; }
  .source-document-card dl { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .difference-callout { align-items: flex-start; flex-direction: column; }
}
</style>
