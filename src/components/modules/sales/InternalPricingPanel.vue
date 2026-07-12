<script setup lang="ts">
import {
  Calculator,
  CheckCircle2,
  History,
  LoaderCircle,
  Plus,
  RefreshCw,
  Save,
  ShieldCheck,
  Tags,
  Trash2,
} from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { pricingApi } from '@/api/pricing'
import { getApiErrorMessage } from '@/lib/http'
import { runPricing } from '@/lib/pricing'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import type { PricingContext, PricingLine, SavedPricingQuote } from '@/types/pricing'

const customers = [
  { id: 'buzzbee', name: 'BuzzBee' },
  { id: 'disney', name: '迪士尼' },
  { id: 'dicky', name: 'Dickie' },
  { id: 'caixing', name: '彩星' },
]

const appStore = useAppStore()
const authStore = useAuthStore()
const selectedCustomerId = ref(customers[0].id)
const projectName = ref('')
const context = ref<PricingContext | null>(null)
const lines = ref<PricingLine[]>([createLine(1), createLine(2)])
const savedQuotes = ref<SavedPricingQuote[]>([])
const isLoading = ref(false)
const isSaving = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

const factoryId = computed(() => appStore.activeProductionFactory.id)
const canCreate = computed(() => authStore.hasPermission('internal_pricing:create'))
const normalizedLines = computed(() => lines.value.map((line) => ({
  ...line,
  qty: Number(line.qty) || 0,
  unitPrice: Number(line.unitPrice) || 0,
})))
const validLines = computed(() => normalizedLines.value.filter((line) => line.sku.trim() && line.qty > 0 && line.unitPrice >= 0))
const result = computed(() => {
  if (!context.value || !normalizedLines.value.length) {
    return null
  }

  return runPricing({ customerId: selectedCustomerId.value, lines: normalizedLines.value }, context.value)
})
const canSubmit = computed(() => Boolean(
  canCreate.value
  && context.value
  && projectName.value.trim()
  && validLines.value.length === lines.value.length
  && result.value,
))
const ruleById = computed(() => new Map(context.value?.rules.map((rule) => [rule.id, rule]) ?? []))

function createLine(index: number): PricingLine {
  return {
    sku: `ITEM-${String(index).padStart(3, '0')}`,
    description: '',
    qty: 1000,
    unitPrice: 0,
    productLine: index === 1 ? '塑胶' : '包装',
  }
}

function addLine() {
  lines.value.push(createLine(lines.value.length + 1))
}

function removeLine(index: number) {
  if (lines.value.length <= 1) {
    return
  }
  lines.value.splice(index, 1)
}

function formatMoney(value: number, currency = context.value?.currency ?? 'HKD') {
  return new Intl.NumberFormat('zh-HK', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
  }).format(value)
}

function formatRule(ruleId: string) {
  return ruleById.value.get(ruleId)?.label || ruleId
}

function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

async function loadWorkspace() {
  isLoading.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const [nextContext, quotes] = await Promise.all([
      pricingApi.getContext(selectedCustomerId.value, factoryId.value),
      pricingApi.listQuotes(factoryId.value, selectedCustomerId.value),
    ])
    context.value = nextContext
    savedQuotes.value = quotes
  } catch (error) {
    context.value = null
    savedQuotes.value = []
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isLoading.value = false
  }
}

async function saveQuote() {
  if (!canSubmit.value || !result.value) {
    return
  }

  isSaving.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const quote = await pricingApi.createQuote({
      factoryId: factoryId.value,
      projectName: projectName.value.trim(),
      input: { customerId: selectedCustomerId.value, lines: normalizedLines.value },
      localResult: result.value,
    })
    savedQuotes.value = [quote, ...savedQuotes.value.filter((item) => item.id !== quote.id)]
    successMessage.value = `${quote.id} 已通过服务器复算并保存`
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isSaving.value = false
  }
}

watch([selectedCustomerId, factoryId], () => {
  void loadWorkspace()
})

onMounted(() => {
  void loadWorkspace()
})
</script>

<template>
  <section class="internal-pricing-panel">
    <header class="pricing-command-bar">
      <div>
        <p class="eyebrow"><Calculator class="size-4" /> 纯函数实时测算</p>
        <h2>内部报价工作台</h2>
        <p>选客户、填写行项，系统实时应用客户规则；保存时由服务器重新计算，最终以服务器结果为准。</p>
      </div>
      <div class="customer-switcher" aria-label="内部报价客户">
        <button
          v-for="customer in customers"
          :key="customer.id"
          type="button"
          :class="{ active: customer.id === selectedCustomerId }"
          @click="selectedCustomerId = customer.id"
        >
          {{ customer.name }}
        </button>
      </div>
    </header>

    <div v-if="errorMessage" class="feedback error">{{ errorMessage }}</div>
    <div v-if="successMessage" class="feedback success"><CheckCircle2 class="size-4" />{{ successMessage }}</div>

    <div v-if="isLoading" class="loading-state">
      <LoaderCircle class="size-6 animate-spin" />
      正在读取客户定价上下文…
    </div>

    <template v-else-if="context">
      <div class="pricing-context-strip">
        <article>
          <span>当前客户</span>
          <strong>{{ context.customerName }}</strong>
          <small>{{ context.currency }} 结算</small>
        </article>
        <article>
          <span>行级规则</span>
          <strong>{{ context.rules.length }} 条</strong>
          <small>加价 → 百分比折扣 → 固定减免</small>
        </article>
        <article>
          <span>返点档位</span>
          <strong>{{ context.rebateTiers.length }} 档</strong>
          <small>命中不超过小计的最高档</small>
        </article>
        <article>
          <span>税率</span>
          <strong>{{ context.taxRate }}%</strong>
          <small>税基 = 小计 − 返点</small>
        </article>
      </div>

      <div class="pricing-grid">
        <div class="pricing-editor">
          <div class="editor-head">
            <div>
              <h3>报价行项</h3>
              <p>金额变化会在本页立即重算，无需等待服务器。</p>
            </div>
            <button type="button" class="secondary-button" @click="addLine">
              <Plus class="size-4" /> 添加行
            </button>
          </div>

          <label class="project-field">
            <span>项目 / 产品名称</span>
            <input v-model="projectName" type="text" maxlength="255" placeholder="例如：露营火堆套装" />
          </label>

          <div class="line-table-wrap">
            <table class="line-table">
              <thead>
                <tr>
                  <th>#</th><th>SKU / 编号</th><th>说明</th><th>产品线</th><th>数量</th><th>内部单价</th><th>基础金额</th><th>规则后金额</th><th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(line, index) in lines" :key="index">
                  <td>{{ index + 1 }}</td>
                  <td><input v-model="line.sku" aria-label="SKU" /></td>
                  <td><input v-model="line.description" aria-label="说明" placeholder="部件或费用说明" /></td>
                  <td><input v-model="line.productLine" aria-label="产品线" placeholder="塑胶 / 包装" /></td>
                  <td><input v-model.number="line.qty" aria-label="数量" type="number" min="0.01" step="1" /></td>
                  <td><input v-model.number="line.unitPrice" aria-label="内部单价" type="number" min="0" step="0.01" /></td>
                  <td class="money-cell">{{ formatMoney(result?.lines[index]?.gross ?? 0) }}</td>
                  <td class="money-cell result-cell">
                    {{ formatMoney(result?.lines[index]?.afterDiscount ?? 0) }}
                    <span v-if="result?.lines[index]?.appliedRules.length" class="rule-count">
                      {{ result.lines[index].appliedRules.length }} 条规则
                    </span>
                  </td>
                  <td>
                    <button type="button" class="icon-button" :disabled="lines.length <= 1" aria-label="删除行" @click="removeLine(index)">
                      <Trash2 class="size-4" />
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="rules-panel">
            <div class="rules-title"><Tags class="size-4" /> 当前客户规则</div>
            <div class="rule-list">
              <span v-for="rule in context.rules" :key="rule.id">
                {{ rule.label || rule.id }} ·
                {{ rule.kind === 'percent' ? `${rule.value}%` : formatMoney(rule.value) }}
                <template v-if="rule.productLine"> · {{ rule.productLine }}</template>
                <template v-if="rule.minQty !== undefined"> · MOQ {{ rule.minQty }}</template>
              </span>
            </div>
          </div>
        </div>

        <aside class="pricing-summary">
          <div class="summary-head">
            <div><span>实时结果</span><strong>{{ context.currency }}</strong></div>
            <RefreshCw class="size-5 text-teal-600" />
          </div>

          <div class="summary-lines">
            <div><span>规则后小计</span><strong>{{ formatMoney(result?.subtotal ?? 0) }}</strong></div>
            <div>
              <span>阶梯返点</span>
              <strong class="deduction">− {{ formatMoney(result?.rebate.amount ?? 0) }}</strong>
            </div>
            <div><span>税费（{{ result?.tax.rate ?? context.taxRate }}%）</span><strong>+ {{ formatMoney(result?.tax.amount ?? 0) }}</strong></div>
          </div>

          <div class="grand-total">
            <span>内部报价总额</span>
            <strong>{{ formatMoney(result?.total ?? 0) }}</strong>
            <small v-if="result?.rebate.tier">已命中 {{ result.rebate.tier.threshold }} / {{ result.rebate.tier.rate }}% 返点档</small>
            <small v-else>当前小计未命中返点档位</small>
          </div>

          <div v-if="result?.lines.some((line) => line.appliedRules.length)" class="trace-panel">
            <p>计算溯源</p>
            <div v-for="line in result.lines.filter((item) => item.appliedRules.length)" :key="line.sku">
              <strong>{{ line.sku }}</strong>
              <span>{{ line.appliedRules.map(formatRule).join(' → ') }}</span>
            </div>
          </div>

          <div class="server-check">
            <ShieldCheck class="size-5" />
            <div><strong>双端复算校验</strong><span>提交时服务器按同一客户规则重新计算；结果不一致将拒绝保存。</span></div>
          </div>

          <button type="button" class="save-button" :disabled="!canSubmit || isSaving" @click="saveQuote">
            <LoaderCircle v-if="isSaving" class="size-4 animate-spin" />
            <Save v-else class="size-4" />
            {{ isSaving ? '服务器复算中…' : '复算并保存内部报价' }}
          </button>
          <p v-if="!canCreate" class="permission-hint">当前账号只有查看权限，不能保存内部报价。</p>
          <p v-else-if="!projectName.trim()" class="permission-hint">填写项目名称后可保存。</p>
        </aside>
      </div>

      <section class="quote-history">
        <header><div><History class="size-5" /><span><strong>已保存报价</strong><small>服务器校验通过的报价快照</small></span></div><b>{{ savedQuotes.length }}</b></header>
        <div v-if="savedQuotes.length" class="history-list">
          <article v-for="quote in savedQuotes" :key="quote.id">
            <div><strong>{{ quote.projectName }}</strong><span>{{ quote.id }} · {{ formatDate(quote.createdAt) }}</span></div>
            <span class="status-chip">已保存</span>
            <b>{{ formatMoney(quote.result.total, quote.result.currency) }}</b>
          </article>
        </div>
        <div v-else class="history-empty">当前客户还没有已保存的内部报价。</div>
      </section>
    </template>
  </section>
</template>

<style scoped>
.internal-pricing-panel { display: grid; gap: 16px; }
.pricing-command-bar { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; border: 1px solid #dbe5ea; border-radius: 14px; background: rgba(255,255,255,.94); padding: 20px 22px; box-shadow: 0 16px 34px rgba(15,23,42,.05); }
.eyebrow { display: flex; align-items: center; gap: 7px; margin: 0 0 7px; color: #0f766e; font-size: 12px; font-weight: 900; letter-spacing: .06em; }
.pricing-command-bar h2 { margin: 0; font-size: 23px; font-weight: 900; }
.pricing-command-bar p:not(.eyebrow) { margin: 7px 0 0; color: #64748b; font-size: 13px; line-height: 1.6; }
.customer-switcher { display: flex; flex-wrap: wrap; gap: 6px; justify-content: flex-end; }
.customer-switcher button { border: 1px solid #dbe5ea; border-radius: 999px; background: #fff; padding: 8px 13px; color: #475569; font-size: 12px; font-weight: 800; }
.customer-switcher button.active { border-color: #0f766e; background: #0f766e; color: #fff; box-shadow: 0 6px 16px rgba(15,118,110,.2); }
.feedback { display: flex; align-items: center; gap: 7px; border-radius: 10px; padding: 11px 14px; font-size: 13px; font-weight: 700; }
.feedback.error { border: 1px solid #fecaca; background: #fef2f2; color: #b91c1c; }
.feedback.success { border: 1px solid #a7f3d0; background: #ecfdf5; color: #047857; }
.loading-state { display: flex; min-height: 240px; align-items: center; justify-content: center; gap: 10px; border: 1px solid #dbe5ea; border-radius: 14px; background: #fff; color: #64748b; font-size: 14px; font-weight: 700; }
.pricing-context-strip { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 10px; }
.pricing-context-strip article { border: 1px solid #dbe5ea; border-radius: 12px; background: rgba(255,255,255,.9); padding: 14px 16px; }
.pricing-context-strip span, .pricing-context-strip small { display: block; color: #64748b; font-size: 11px; }
.pricing-context-strip strong { display: block; margin: 6px 0 5px; font-size: 18px; }
.pricing-grid { display: grid; grid-template-columns: minmax(0,1fr) 330px; gap: 16px; align-items: start; }
.pricing-editor, .pricing-summary, .quote-history { border: 1px solid #dbe5ea; border-radius: 14px; background: rgba(255,255,255,.96); box-shadow: 0 14px 30px rgba(15,23,42,.04); }
.pricing-editor { min-width: 0; padding: 20px; }
.editor-head { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.editor-head h3 { margin: 0; font-size: 17px; font-weight: 900; }
.editor-head p { margin: 5px 0 0; color: #64748b; font-size: 12px; }
.secondary-button { display: inline-flex; align-items: center; gap: 6px; border: 1px solid #99f6e4; border-radius: 9px; background: #f0fdfa; padding: 8px 11px; color: #0f766e; font-size: 12px; font-weight: 800; }
.project-field { display: grid; gap: 6px; margin-top: 18px; }
.project-field span { color: #475569; font-size: 12px; font-weight: 800; }
.project-field input, .line-table input { border: 1px solid #dbe5ea; border-radius: 8px; background: #fff; color: #0f172a; outline: none; }
.project-field input { height: 40px; padding: 0 11px; }
.project-field input:focus, .line-table input:focus { border-color: #14b8a6; box-shadow: 0 0 0 3px rgba(20,184,166,.1); }
.line-table-wrap { margin-top: 14px; overflow-x: auto; border: 1px solid #e2e8f0; border-radius: 10px; }
.line-table { width: 100%; min-width: 980px; border-collapse: collapse; font-size: 12px; }
.line-table th { background: #f8fafc; padding: 10px 8px; color: #64748b; text-align: left; font-size: 10px; letter-spacing: .04em; white-space: nowrap; }
.line-table td { border-top: 1px solid #eef2f7; padding: 8px; vertical-align: top; }
.line-table input { width: 100%; min-width: 82px; height: 34px; padding: 0 8px; }
.money-cell { white-space: nowrap; color: #334155; font-variant-numeric: tabular-nums; }
.result-cell { color: #0f766e; font-weight: 900; }
.rule-count { display: block; margin-top: 3px; color: #64748b; font-size: 10px; font-weight: 600; }
.icon-button { display: grid; width: 32px; height: 32px; place-items: center; border-radius: 8px; color: #94a3b8; }
.icon-button:hover:not(:disabled) { background: #fef2f2; color: #dc2626; }
.icon-button:disabled { opacity: .35; }
.rules-panel { margin-top: 14px; border: 1px solid #ccfbf1; border-radius: 10px; background: #f0fdfa; padding: 12px; }
.rules-title { display: flex; align-items: center; gap: 6px; color: #0f766e; font-size: 12px; font-weight: 900; }
.rule-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 9px; }
.rule-list span { border: 1px solid #99f6e4; border-radius: 999px; background: #fff; padding: 5px 8px; color: #115e59; font-size: 10px; font-weight: 700; }
.pricing-summary { position: sticky; top: 78px; padding: 18px; }
.summary-head { display: flex; align-items: center; justify-content: space-between; }
.summary-head div { display: flex; align-items: baseline; gap: 7px; }
.summary-head span { font-size: 14px; font-weight: 900; }
.summary-head strong { color: #64748b; font-size: 11px; }
.summary-lines { display: grid; gap: 11px; margin-top: 18px; padding: 16px 0; border-top: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0; }
.summary-lines div { display: flex; justify-content: space-between; gap: 12px; color: #64748b; font-size: 12px; }
.summary-lines strong { color: #334155; font-variant-numeric: tabular-nums; }
.summary-lines .deduction { color: #059669; }
.grand-total { padding: 17px 0 5px; }
.grand-total span, .grand-total small { display: block; color: #64748b; font-size: 11px; }
.grand-total strong { display: block; margin: 7px 0; color: #0f766e; font-size: 29px; font-weight: 950; letter-spacing: -.03em; }
.trace-panel { display: grid; gap: 7px; margin-top: 13px; border-radius: 9px; background: #f8fafc; padding: 11px; }
.trace-panel p { margin: 0 0 2px; color: #475569; font-size: 11px; font-weight: 900; }
.trace-panel div { display: grid; gap: 2px; }
.trace-panel strong { font-size: 10px; }
.trace-panel span { overflow: hidden; color: #64748b; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.server-check { display: flex; gap: 9px; margin-top: 14px; border: 1px solid #bfdbfe; border-radius: 9px; background: #eff6ff; padding: 11px; color: #1d4ed8; }
.server-check svg { flex: 0 0 auto; }
.server-check strong, .server-check span { display: block; font-size: 10px; }
.server-check span { margin-top: 3px; color: #475569; line-height: 1.5; }
.save-button { display: flex; width: 100%; height: 42px; margin-top: 14px; align-items: center; justify-content: center; gap: 7px; border-radius: 9px; background: #0f766e; color: #fff; font-size: 12px; font-weight: 900; box-shadow: 0 8px 18px rgba(15,118,110,.22); }
.save-button:disabled { cursor: not-allowed; background: #94a3b8; box-shadow: none; }
.permission-hint { margin: 8px 0 0; color: #94a3b8; text-align: center; font-size: 10px; }
.quote-history { overflow: hidden; }
.quote-history > header { display: flex; align-items: center; justify-content: space-between; padding: 15px 18px; border-bottom: 1px solid #e2e8f0; }
.quote-history > header > div { display: flex; align-items: center; gap: 9px; color: #0f766e; }
.quote-history header span { display: grid; }
.quote-history header strong { color: #0f172a; font-size: 13px; }
.quote-history header small { margin-top: 2px; color: #64748b; font-size: 10px; }
.quote-history header b { display: grid; min-width: 28px; height: 28px; place-items: center; border-radius: 999px; background: #f0fdfa; color: #0f766e; font-size: 12px; }
.history-list { display: grid; }
.history-list article { display: grid; grid-template-columns: minmax(0,1fr) auto 140px; gap: 16px; align-items: center; padding: 13px 18px; border-top: 1px solid #f1f5f9; }
.history-list article:first-child { border-top: 0; }
.history-list article div { display: grid; gap: 3px; }
.history-list article strong { font-size: 12px; }
.history-list article span { color: #64748b; font-size: 10px; }
.history-list article > b { text-align: right; font-size: 13px; font-variant-numeric: tabular-nums; }
.status-chip { border: 1px solid #a7f3d0; border-radius: 999px; background: #ecfdf5; padding: 4px 8px; color: #047857 !important; font-weight: 800; }
.history-empty { padding: 28px; color: #94a3b8; text-align: center; font-size: 12px; }
@media (max-width: 1100px) { .pricing-context-strip { grid-template-columns: repeat(2,1fr); } .pricing-grid { grid-template-columns: 1fr; } .pricing-summary { position: static; } }
@media (max-width: 720px) { .pricing-command-bar { align-items: flex-start; flex-direction: column; } .customer-switcher { justify-content: flex-start; } .pricing-context-strip { grid-template-columns: 1fr; } .pricing-editor { padding: 15px; } .history-list article { grid-template-columns: minmax(0,1fr) auto; } .history-list article > b { grid-column: 1 / -1; text-align: left; } }
</style>
