<script setup lang="ts">
import { Activity, Calculator, Clock3, Eye, LoaderCircle, MessageSquare, Pencil, Save, Send, ShieldCheck, Sparkles, UserRound, X } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import { createDefaultSalesMarkupTiers, salesMarkupTierForQuantity, type SalesMarkupTier } from '@/lib/internalQuoteSectionPayload'
import type { InternalQuote } from '@/types/internalQuoteDesk'

const props = defineProps<{
  quote: InternalQuote
  readOnly?: boolean
  canEditFx?: boolean
  canEditMarkup?: boolean
  markupBlockedReason?: string
  markupMessage?: string
  markupError?: string
  busy?: boolean
}>()
const emit = defineEmits<{
  updateFx: [payload: { rmbHkd: string; hkdUsd: string }]
  updateMarkup: [payload: { markupTiers: Array<{ moq: string; markup: string }>; selectedMoq: string; miscRatio: string }]
}>()
const quoteStore = useInternalQuoteDeskStore()
const activeTab = ref<'summary' | 'activity' | 'views'>('summary')
const commentText = ref('')
const fxEditing = ref(false)
const formatFx = (value: number) => value.toFixed(2)
const fxRmbHkd = ref(formatFx(props.quote.fxRmbHkd))
const fxHkdUsd = ref(formatFx(props.quote.fxHkdUsd))
const savedMarkup = computed(() => {
  const value = Number(props.quote.rr2CostSummary?.shippingPricing.markup)
  return Number.isFinite(value) && value > 0 ? value : 1.2
})
const savedMarkupTiers = computed<SalesMarkupTier[]>(() => {
  const rows = props.quote.rr2CostSummary?.shippingPricing.markupTiers ?? []
  if (rows.length) return rows.map((row) => ({ moq: row.moq, markup_x: row.markup }))
  return createDefaultSalesMarkupTiers(savedMarkup.value)
})
const savedMiscRatio = computed(() => {
  const value = Number(props.quote.rr2CostSummary?.shippingPricing.miscRatio)
  return Number.isFinite(value) && value >= 0 && value <= 1 ? value : .02
})
const quoteMarkupTiers = ref(savedMarkupTiers.value.map((tier) => ({
  moq: String(tier.moq),
  markup: tier.markup_x.toFixed(2),
})))
const quoteMiscPercent = ref((savedMiscRatio.value * 100).toFixed(2))
const livePreview = computed(() => (
  quoteStore.livePreviewQuoteId === props.quote.id ? quoteStore.liveCostPreview : null
))
const previewReady = computed(() => livePreview.value?.calculation_status === 'valid')
const previewBusy = computed(() => quoteStore.livePreviewQuoteId === props.quote.id && quoteStore.livePreviewLoading)
const previewError = computed(() => (
  quoteStore.livePreviewQuoteId === props.quote.id ? quoteStore.livePreviewErrorMessage : ''
))
const savedTotalHkd = computed(() => Number(livePreview.value?.saved_factory_price_hkd ?? props.quote.factoryPriceHkd) || 0)
const costHkd = computed(() => previewReady.value
  ? Number(livePreview.value?.preview_factory_price_hkd ?? props.quote.factoryPriceHkd) || 0
  : savedTotalHkd.value)
const editableMarkupTiers = computed<SalesMarkupTier[]>(() => quoteMarkupTiers.value.map((tier) => ({
  moq: Number(tier.moq),
  markup_x: Number(tier.markup),
})))
const quoteQuantity = computed(() => {
  const value = Number(props.quote.quantity)
  return Number.isFinite(value) && value > 0 ? value : 10000
})
const savedActiveMarkupTierIndex = computed(() => {
  const summaryRows = props.quote.rr2CostSummary?.shippingPricing.markupTiers ?? []
  const summaryIndex = summaryRows.findIndex((tier) => tier.isActive)
  if (summaryIndex >= 0) return summaryIndex
  const activeMoq = Number(props.quote.rr2CostSummary?.shippingPricing.activeMarkupMoq)
  const matchedIndex = savedMarkupTiers.value.findIndex((tier) => tier.moq === activeMoq)
  if (matchedIndex >= 0) return matchedIndex
  const automatic = salesMarkupTierForQuantity(savedMarkupTiers.value, quoteQuantity.value)
  return Math.max(savedMarkupTiers.value.findIndex((tier) => tier.moq === automatic.moq), 0)
})
const selectedMarkupTierIndex = ref(savedActiveMarkupTierIndex.value)
const activeMarkupTier = computed(() => (
  editableMarkupTiers.value[selectedMarkupTierIndex.value]
  ?? salesMarkupTierForQuantity(editableMarkupTiers.value, quoteQuantity.value)
))
const normalizedMarkup = computed(() => {
  const value = activeMarkupTier.value.markup_x
  return Number.isFinite(value) && value > 0 ? Math.min(value, 9.99) : savedMarkup.value
})
const activeMarkupTierIndex = computed(() => selectedMarkupTierIndex.value)
const markupValidationMessage = computed(() => {
  if (quoteMarkupTiers.value.length !== 3) return '分段码数必须保留 3 档。'
  let previousMoq = 0
  for (const [index, tier] of quoteMarkupTiers.value.entries()) {
    const moq = String(tier.moq).trim()
    const markup = String(tier.markup).trim()
    if (!moq) return `请填写第 ${index + 1} 档 MOQ。`
    if (!/^\d+$/.test(moq) || Number(moq) < 1 || Number(moq) > 100000000) return `第 ${index + 1} 档 MOQ 必须是 1 至 100,000,000 的整数。`
    if (Number(moq) <= previousMoq) return 'MOQ 区间必须由小到大排列，且不能重复。'
    previousMoq = Number(moq)
    if (!markup) return `请填写第 ${index + 1} 档码数。`
    const parsed = Number(markup)
    if (!Number.isFinite(parsed) || parsed < .01 || parsed > 9.99) return `第 ${index + 1} 档码数必须在 0.01 至 9.99 之间。`
    if (!/^\d+(?:\.\d{1,2})?$/.test(markup)) return '码数最多保留 2 位小数。'
  }
  return ''
})
const markupDirty = computed(() => (
  !markupValidationMessage.value && (
    selectedMarkupTierIndex.value !== savedActiveMarkupTierIndex.value
    || quoteMarkupTiers.value.some((tier, index) => (
      Number(tier.moq) !== savedMarkupTiers.value[index]?.moq
      || Number(tier.markup) !== Number(savedMarkupTiers.value[index]?.markup_x.toFixed(2))
    ))
  )
))
const miscValidationMessage = computed(() => {
  const value = String(quoteMiscPercent.value).trim()
  if (!value) return '请填写杂项系数。'
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 100) return '杂项系数必须在 0% 至 100% 之间。'
  if (!/^\d+(?:\.\d{1,2})?$/.test(value)) return '杂项系数最多保留 2 位小数。'
  return ''
})
const miscDirty = computed(() => (
  !miscValidationMessage.value && Number(quoteMiscPercent.value) !== Number((savedMiscRatio.value * 100).toFixed(2))
))
const pricingValidationMessage = computed(() => markupValidationMessage.value || miscValidationMessage.value)
const pricingDirty = computed(() => markupDirty.value || miscDirty.value)
const quoteHkd = computed(() => costHkd.value * normalizedMarkup.value)
const quoteRmb = computed(() => quoteHkd.value * props.quote.fxRmbHkd)
const quoteUsd = computed(() => props.quote.fxHkdUsd ? quoteHkd.value / props.quote.fxHkdUsd : 0)
const previewDeltaHkd = computed(() => Number(livePreview.value?.delta_hkd ?? 0) || 0)
const previewStatus = computed(() => {
  if (previewBusy.value) return '正在实时试算'
  if (previewReady.value) return '实时试算 · 未保存'
  if (livePreview.value && livePreview.value.calculation_status !== 'valid') return '字段待完善'
  return '最近保存金额'
})

type TargetPrice = { currency: 'HKD' | 'RMB' | 'USD'; amount: number }
function parseTargetPrice(value: string): TargetPrice | null {
  const normalized = value.trim().toUpperCase()
  if (!normalized || ['无', 'NONE', 'N/A', 'NA'].includes(normalized)) return null
  const token = '(HKD|HK\\$|HKS|USD|US\\$|RMB|CNY|¥|￥)'
  const prefix = normalized.match(new RegExp(`${token}\\s*([0-9]+(?:\\.[0-9]+)?)`))
  const suffix = normalized.match(new RegExp(`([0-9]+(?:\\.[0-9]+)?)\\s*${token}`))
  const currencyToken = prefix?.[1] ?? suffix?.[2]
  const amountToken = prefix?.[2] ?? suffix?.[1]
  const amount = Number(amountToken)
  if (!currencyToken || !Number.isFinite(amount)) return null
  const currency = currencyToken.includes('USD') || currencyToken === 'US$'
    ? 'USD'
    : currencyToken === 'RMB' || currencyToken === 'CNY' || ['¥', '￥'].includes(currencyToken)
      ? 'RMB'
      : 'HKD'
  return { currency, amount }
}
const targetComparison = computed(() => {
  const target = parseTargetPrice(props.quote.targetCustomerPrice)
  if (!target) return null
  const previewAmount = target.currency === 'HKD' ? quoteHkd.value : target.currency === 'RMB' ? quoteRmb.value : quoteUsd.value
  const difference = target.amount - previewAmount
  const proximity = target.amount > 0 ? Math.max(0, 1 - Math.abs(difference) / target.amount) : 0
  const tone = proximity >= .98 ? 4 : proximity >= .9 ? 3 : proximity >= .75 ? 2 : proximity >= .5 ? 1 : 0
  return {
    currency: target.currency,
    targetAmount: target.amount,
    previewAmount,
    difference,
    proximity,
    tone,
    label: difference >= 0
      ? `目标余量 ${target.currency} ${difference.toFixed(2)}`
      : `已超目标 ${target.currency} ${Math.abs(difference).toFixed(2)}`,
  }
})
const proximityClass = computed(() => targetComparison.value
  ? [`proximity-${targetComparison.value.tone}`, { over: targetComparison.value.difference < 0 }]
  : [])
const fxValidationMessage = computed(() => {
  const values = [
    ['RMB→HKD', String(fxRmbHkd.value).trim()],
    ['HKD→USD', String(fxHkdUsd.value).trim()],
  ] as const
  for (const [label, value] of values) {
    if (!value) return `请填写${label}汇率。`
    const parsed = Number(value)
    if (!Number.isFinite(parsed) || parsed <= 0) return `${label}汇率必须大于 0。`
    if (parsed > 1000) return `${label}汇率不能大于 1000。`
    if (!/^\d+(?:\.\d{1,2})?$/.test(value)) return `${label}汇率最多保留 2 位小数。`
  }
  return ''
})
const fxDirty = computed(() => (
  Number(fxRmbHkd.value) !== props.quote.fxRmbHkd
  || Number(fxHkdUsd.value) !== props.quote.fxHkdUsd
))

function resetFxEditor(close = true) {
  fxRmbHkd.value = formatFx(props.quote.fxRmbHkd)
  fxHkdUsd.value = formatFx(props.quote.fxHkdUsd)
  if (close) fxEditing.value = false
}

function beginFxEdit() {
  resetFxEditor(false)
  fxEditing.value = true
}

function normalizeMarkupInput(index: number) {
  const row = quoteMarkupTiers.value[index]
  if (!row) return
  const value = Number(row.markup)
  const saved = savedMarkupTiers.value[index]?.markup_x ?? savedMarkup.value
  row.markup = (Number.isFinite(value) && value > 0
    ? Math.min(Math.max(value, .01), 9.99)
    : saved).toFixed(2)
}

function normalizeMarkupMoq(index: number) {
  const row = quoteMarkupTiers.value[index]
  if (!row) return
  const value = Number(row.moq)
  const saved = savedMarkupTiers.value[index]?.moq ?? createDefaultSalesMarkupTiers()[index]?.moq ?? 1
  row.moq = String(Number.isFinite(value) && value > 0
    ? Math.min(Math.max(Math.round(value), 1), 100000000)
    : saved)
}

function normalizeMiscInput() {
  const value = Number(quoteMiscPercent.value)
  quoteMiscPercent.value = (Number.isFinite(value) && value >= 0
    ? Math.min(value, 100)
    : savedMiscRatio.value * 100).toFixed(2)
}

function selectMarkupTier(index: number) {
  if (index < 0 || index >= quoteMarkupTiers.value.length || !props.canEditMarkup || props.markupBlockedReason || props.busy) return
  selectedMarkupTierIndex.value = index
}

function saveFx() {
  if (!props.canEditFx || fxValidationMessage.value || !fxDirty.value || props.busy) return
  emit('updateFx', {
    rmbHkd: Number(fxRmbHkd.value).toFixed(2),
    hkdUsd: Number(fxHkdUsd.value).toFixed(2),
  })
}

function saveMarkup() {
  if (!props.canEditMarkup || pricingValidationMessage.value || !pricingDirty.value || props.markupBlockedReason || props.busy) return
  emit('updateMarkup', {
    markupTiers: quoteMarkupTiers.value.map((tier) => ({
      moq: String(Math.round(Number(tier.moq))),
      markup: Number(tier.markup).toFixed(2),
    })),
    selectedMoq: String(Math.round(Number(quoteMarkupTiers.value[selectedMarkupTierIndex.value]?.moq))),
    miscRatio: (Number(quoteMiscPercent.value) / 100).toFixed(4),
  })
}

watch(() => props.quote.referenceSnapshotId, () => resetFxEditor())
watch(() => [props.quote.id, JSON.stringify(savedMarkupTiers.value), savedActiveMarkupTierIndex.value, savedMiscRatio.value] as const, () => {
  quoteMarkupTiers.value = savedMarkupTiers.value.map((tier) => ({
    moq: String(tier.moq),
    markup: tier.markup_x.toFixed(2),
  }))
  selectedMarkupTierIndex.value = savedActiveMarkupTierIndex.value
  quoteMiscPercent.value = (savedMiscRatio.value * 100).toFixed(2)
})

function addComment() {
  if (props.readOnly) return
  quoteStore.addComment(props.quote.id, commentText.value)
  commentText.value = ''
}
</script>

<template>
  <aside class="quote-activity-panel">
    <nav class="quote-activity-tabs" aria-label="报价侧栏信息">
      <button type="button" :class="{ active: activeTab === 'summary' }" @click="activeTab = 'summary'"><Calculator aria-hidden="true" />成本</button>
      <button type="button" :class="{ active: activeTab === 'activity' }" @click="activeTab = 'activity'"><Activity aria-hidden="true" />协作</button>
      <button type="button" :class="{ active: activeTab === 'views' }" @click="activeTab = 'views'"><Eye aria-hidden="true" />浏览记录</button>
    </nav>

    <div v-if="activeTab === 'summary'" class="quote-activity-body">
      <section class="quote-live-cost" :class="[{ 'has-live-preview': previewReady }, proximityClass]">
        <div class="quote-live-heading">
          <span>{{ previewReady || previewBusy ? '实时报价试算' : '报价预览' }}</span>
          <em :class="{ live: previewReady, busy: previewBusy }">
            <LoaderCircle v-if="previewBusy" class="spin" aria-hidden="true" />
            <Sparkles v-else-if="previewReady" aria-hidden="true" />
            {{ previewStatus }}
          </em>
        </div>
        <span class="quote-live-main-label">预览报价（根据实时成本与本单设置计算）</span>
        <strong data-testid="live-quote-hkd">HKD {{ quoteHkd.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</strong>
        <div class="quote-live-conversions"><span>RMB {{ quoteRmb.toFixed(2) }}</span><span>USD {{ quoteUsd.toFixed(2) }}</span></div>
        <div class="quote-markup-tier-control">
          <header><span>分段码数</span><small>本单数量 {{ quoteQuantity.toLocaleString('zh-CN') }} PCS（仅参考）</small></header>
          <div
            v-for="(tier, index) in quoteMarkupTiers"
            :key="index"
            class="quote-markup-tier-row"
            :class="{ active: activeMarkupTierIndex === index }"
          >
            <label :for="`quote-live-moq-${index}`">MOQ</label>
            <input
              :id="`quote-live-moq-${index}`"
              v-model="tier.moq"
              :data-testid="`live-quote-markup-moq-${index}`"
              type="number"
              min="1"
              max="100000000"
              step="1"
              inputmode="numeric"
              :disabled="!canEditMarkup || busy || !!markupBlockedReason"
              @blur="normalizeMarkupMoq(index)"
            >
            <span>倍率</span>
            <input
              :id="`quote-live-markup-${index}`"
              v-model="tier.markup"
              :data-testid="`live-quote-markup-${index}`"
              type="number"
              min="0.01"
              max="9.99"
              step="0.01"
              inputmode="decimal"
              :disabled="!canEditMarkup || busy || !!markupBlockedReason"
              @blur="normalizeMarkupInput(index)"
            >
            <button
              type="button"
              class="quote-markup-tier-select"
              :class="{ selected: activeMarkupTierIndex === index }"
              :data-testid="`select-quote-markup-tier-${index}`"
              :aria-pressed="activeMarkupTierIndex === index"
              :disabled="!canEditMarkup || busy || !!markupBlockedReason"
              @click="selectMarkupTier(index)"
            >{{ activeMarkupTierIndex === index ? '本单采用' : '选择此档' }}</button>
          </div>
        </div>
        <div class="quote-markup-control quote-misc-control">
          <label for="quote-live-misc"><span>杂项</span><small>当前保存 {{ (savedMiscRatio * 100).toFixed(2) }}%</small></label>
          <div class="quote-markup-input"><input id="quote-live-misc" v-model="quoteMiscPercent" data-testid="live-quote-misc" type="number" min="0" max="100" step="0.01" inputmode="decimal" :disabled="!canEditMarkup || busy || !!markupBlockedReason" @blur="normalizeMiscInput"><span>%</span></div>
        </div>
        <button
          v-if="canEditMarkup"
          type="button"
          class="quote-markup-save"
          data-testid="save-quote-markup"
          :disabled="busy || !!pricingValidationMessage || !pricingDirty || !!markupBlockedReason"
          @click="saveMarkup"
        ><Save aria-hidden="true" />{{ busy ? '保存中…' : '保存分段码数与杂项' }}</button>
        <p v-if="pricingValidationMessage" class="quote-markup-feedback error">{{ pricingValidationMessage }}</p>
        <p v-else-if="markupBlockedReason" class="quote-markup-feedback blocked">{{ markupBlockedReason }}</p>
        <p v-else-if="markupError" class="quote-markup-feedback error">{{ markupError }}</p>
        <p v-else-if="markupMessage" class="quote-markup-feedback success">{{ markupMessage }}</p>
        <div class="quote-live-cost-base"><span>{{ previewReady ? '实时整单成本' : '最近保存成本' }}</span><strong data-testid="live-cost-hkd">HKD {{ costHkd.toFixed(2) }}</strong></div>
        <div v-if="targetComparison" class="quote-live-comparison">
          <div class="quote-live-price-cell preview"><span>预览价</span><strong>{{ targetComparison.currency }} {{ targetComparison.previewAmount.toFixed(2) }}</strong></div>
          <div class="quote-live-price-cell target"><span>目标价</span><strong>{{ targetComparison.currency }} {{ targetComparison.targetAmount.toFixed(2) }}</strong></div>
          <div class="quote-live-price-cell gap" :class="{ over: targetComparison.difference < 0 }" data-testid="target-price-gap">
            <span>两者差值 · 接近度 {{ (targetComparison.proximity * 100).toFixed(0) }}%</span><strong>{{ targetComparison.label }}</strong>
          </div>
        </div>
        <div v-else class="quote-live-target"><span>客人目标价</span><strong>{{ quote.targetCustomerPrice }}</strong></div>
        <p v-if="previewReady" class="quote-live-baseline">
          已保存成本 HKD {{ savedTotalHkd.toFixed(2) }} · 成本变化 {{ previewDeltaHkd >= 0 ? '+' : '' }}{{ previewDeltaHkd.toFixed(2) }}
        </p>
        <p v-else-if="previewError" class="quote-live-preview-warning">实时试算暂不可用，当前显示最近保存金额。</p>
        <p v-else-if="livePreview && livePreview.calculation_status !== 'valid'" class="quote-live-preview-warning">当前字段尚未完整，暂显示最近保存金额。</p>
        <p class="quote-live-preview-note">跟客可主动选择本单采用的 MOQ 档，也可调整三档 MOQ 区间和码数；旧报价首次显示时会按本单数量给出初始档。保存后会生成业务部新 revision、重新计算并用于后续导出。</p>
      </section>
      <section class="quote-side-section">
        <h3 class="quote-fx-heading"><span><ShieldCheck aria-hidden="true" />冻结参考快照</span><button v-if="canEditFx && !fxEditing" type="button" data-testid="edit-reference-fx" @click="beginFxEdit"><Pencil aria-hidden="true" />调整汇率</button></h3>
        <div v-if="fxEditing" class="quote-fx-editor">
          <label><span>RMB → HKD</span><input v-model="fxRmbHkd" data-testid="fx-rmb-hkd" type="number" min="0.01" max="1000" step="0.01" inputmode="decimal"></label>
          <label><span>HKD → USD</span><input v-model="fxHkdUsd" data-testid="fx-hkd-usd" type="number" min="0.01" max="1000" step="0.01" inputmode="decimal"></label>
          <p v-if="fxValidationMessage" class="quote-fx-error">{{ fxValidationMessage }}</p>
          <p class="quote-fx-warning">保存会生成新 revision，重算本报价，并使受影响审批失效。</p>
          <div class="quote-fx-actions"><button type="button" :disabled="busy" @click="resetFxEditor()"><X aria-hidden="true" />取消</button><button type="button" class="primary" data-testid="save-reference-fx" :disabled="busy || !!fxValidationMessage || !fxDirty" @click="saveFx"><Save aria-hidden="true" />{{ busy ? '保存中…' : '保存汇率' }}</button></div>
        </div>
        <dl>
          <div><dt>公式版本</dt><dd>{{ quote.formulaVersion }}</dd></div>
          <div v-if="!fxEditing"><dt>RMB → HKD</dt><dd>{{ formatFx(quote.fxRmbHkd) }}</dd></div>
          <div v-if="!fxEditing"><dt>HKD → USD</dt><dd>{{ formatFx(quote.fxHkdUsd) }}</dd></div>
          <div><dt>快照编号</dt><dd class="hash">{{ quote.referenceSnapshotId }}</dd></div>
        </dl>
      </section>
      <section class="quote-side-section">
        <h3><Clock3 aria-hidden="true" />最近业务操作</h3>
        <ol class="quote-mini-timeline">
          <li v-for="activity in quote.activities.slice(0, 4)" :key="activity.id">
            <i /><div><strong>{{ activity.title }}</strong><span>{{ activity.actor }} · {{ activity.createdAt }}</span></div>
          </li>
        </ol>
      </section>
    </div>

    <div v-else-if="activeTab === 'activity'" class="quote-activity-body">
      <section class="quote-side-section quote-collaboration">
        <h3><MessageSquare aria-hidden="true" />协作评论</h3>
        <div class="quote-comment-list">
          <article v-for="comment in quote.comments" :key="comment.id">
            <span>{{ comment.author.slice(0, 1) }}</span>
            <div><header><strong>{{ comment.author }}</strong><small>{{ comment.department }} · {{ comment.createdAt }}</small></header><p>{{ comment.content }}</p></div>
          </article>
        </div>
        <p v-if="readOnly" class="quote-side-hint">评论接口尚未实施；请使用保存原因、退回原因和审核意见形成服务端留痕。</p>
        <form v-else class="quote-comment-form" @submit.prevent="addComment">
          <input v-model="commentText" type="text" placeholder="补充协作评论…" aria-label="协作评论">
          <button type="submit" :disabled="!commentText.trim()" aria-label="发送评论"><Send aria-hidden="true" /></button>
        </form>
      </section>
      <section class="quote-side-section">
        <h3><Activity aria-hidden="true" />业务操作时间线</h3>
        <ol class="quote-full-timeline">
          <li v-for="activity in quote.activities" :key="activity.id">
            <i /><div><strong>{{ activity.title }}</strong><p>{{ activity.detail }}</p><span>{{ activity.department }} · {{ activity.actor }} · {{ activity.createdAt }}</span></div>
          </li>
        </ol>
      </section>
    </div>

    <div v-else class="quote-activity-body">
      <section class="quote-side-section quote-view-records">
        <h3><Eye aria-hidden="true" />浏览记录</h3>
        <p class="quote-side-hint">同一用户短时间刷新会去重；浏览记录与业务操作时间线分开展示。</p>
        <article v-for="record in quote.viewRecords" :key="record.id">
          <span class="quote-view-avatar"><UserRound aria-hidden="true" /></span>
          <div><strong>{{ record.viewer }}</strong><p>{{ record.department }} · {{ record.device }}</p><small>{{ record.viewedAt }} · {{ record.ipAddress }}</small></div>
        </article>
      </section>
    </div>
  </aside>
</template>

<style scoped>
.quote-activity-panel{position:sticky;top:82px;align-self:start;overflow:hidden;border:1px solid #dbe5ea;border-radius:13px;background:#fff;box-shadow:0 12px 28px rgb(15 23 42/.05)}.quote-activity-tabs{display:grid;grid-template-columns:repeat(3,1fr);border-bottom:1px solid #e2e8f0;background:#f8fafc;padding:6px}.quote-activity-tabs button{display:flex;align-items:center;justify-content:center;gap:4px;border:0;border-radius:8px;background:transparent;padding:8px 4px;color:#64748b;font-size:9px;font-weight:900}.quote-activity-tabs button.active{background:#fff;color:#0f766e;box-shadow:0 2px 8px rgb(15 23 42/.06)}.quote-activity-tabs svg{width:13px;height:13px}.quote-activity-body{display:grid;max-height:calc(100vh - 132px);overflow:auto}.quote-live-cost{display:grid;gap:7px;padding:18px;background:linear-gradient(145deg,#0f766e,#0d9488);color:#fff;transition:background .22s ease}.quote-live-cost.has-live-preview{background:linear-gradient(145deg,#115e59,#0f9f91)}.quote-live-heading{display:flex;align-items:center;justify-content:space-between;gap:8px}.quote-live-heading>span{font-size:10px;font-weight:900;letter-spacing:.06em}.quote-live-heading em{display:inline-flex;align-items:center;gap:3px;border:1px solid rgb(255 255 255/.24);border-radius:99px;background:rgb(255 255 255/.1);padding:3px 6px;color:#d1fae5;font-size:7px;font-style:normal;font-weight:900;white-space:nowrap}.quote-live-heading em.live{border-color:#99f6e4;background:#ecfdf5;color:#047857}.quote-live-heading em.busy{color:#fff}.quote-live-heading svg{width:9px;height:9px}.quote-live-heading .spin{animation:quote-live-spin .8s linear infinite}.quote-live-cost>strong{font-size:24px;letter-spacing:-.025em}.quote-live-conversions{display:flex;gap:12px;color:#ccfbf1;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:9px}.quote-live-target,.quote-live-target-gap{display:flex;align-items:center;justify-content:space-between;gap:10px}.quote-live-target{margin-top:4px;border-top:1px solid rgb(204 251 241/.35);padding-top:9px}.quote-live-target span,.quote-live-target-gap span{color:#ccfbf1;font-size:9px;font-weight:800}.quote-live-target strong,.quote-live-target-gap strong{overflow-wrap:anywhere;color:#fff;font-size:12px;text-align:right}.quote-live-target-gap{border-radius:7px;background:rgb(236 253 245/.13);padding:6px 7px}.quote-live-target-gap strong{color:#d1fae5;font-size:9px}.quote-live-target-gap.over{background:rgb(254 226 226/.16)}.quote-live-target-gap.over strong{color:#fecaca}.quote-live-baseline,.quote-live-preview-warning,.quote-live-preview-note{margin:0;line-height:1.45}.quote-live-baseline{color:#d1fae5;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:7.5px}.quote-live-preview-warning{border-radius:6px;background:rgb(254 226 226/.16);padding:5px 6px;color:#fee2e2;font-size:8px}.quote-live-preview-note{color:#a7f3d0;font-size:7px}.quote-side-section{padding:15px;border-bottom:1px solid #eef2f6}.quote-side-section h3{display:flex;align-items:center;gap:6px;margin:0 0 12px;color:#334155;font-size:10px;font-weight:900;letter-spacing:.05em}.quote-side-section h3 svg{width:14px;color:#0f766e}.quote-side-section dl{display:grid;gap:8px;margin:0}.quote-side-section dl div{display:flex;justify-content:space-between;gap:10px}.quote-side-section dt{color:#94a3b8;font-size:9px}.quote-side-section dd{margin:0;color:#334155;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:9px;text-align:right}.quote-side-section dd.hash{max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.quote-fx-heading{justify-content:space-between}.quote-fx-heading>span{display:inline-flex;align-items:center;gap:6px}.quote-fx-heading>button{display:inline-flex;align-items:center;gap:4px;border:1px solid #99f6e4;border-radius:7px;background:#f0fdfa;padding:5px 7px;color:#0f766e;font-size:9px;font-weight:900;letter-spacing:0;transition:transform .18s ease,background-color .18s ease}.quote-fx-heading>button:hover{background:#ccfbf1;transform:translateY(-1px)}.quote-fx-heading>button svg{width:11px}.quote-fx-editor{display:grid;gap:8px;margin-bottom:11px;border:1px solid #99f6e4;border-radius:9px;background:#f0fdfa;padding:9px}.quote-fx-editor label{display:grid;grid-template-columns:1fr 92px;align-items:center;gap:7px;color:#475569;font-size:9px;font-weight:800}.quote-fx-editor input{min-width:0;border:1px solid #94a3b8;border-radius:6px;background:#fff;padding:6px 7px;color:#0f172a;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:10px}.quote-fx-editor input:focus{border-color:#0d9488;outline:3px solid rgb(45 212 191/.16)}.quote-fx-error,.quote-fx-warning{margin:0;font-size:8px;line-height:1.45}.quote-fx-error{color:#b91c1c}.quote-fx-warning{color:#64748b}.quote-fx-actions{display:flex;justify-content:flex-end;gap:6px}.quote-fx-actions button{display:inline-flex;align-items:center;gap:3px;border:1px solid #cbd5e1;border-radius:6px;background:#fff;padding:5px 7px;color:#475569;font-size:8px;font-weight:900}.quote-fx-actions button.primary{border-color:#0f766e;background:#0f766e;color:#fff}.quote-fx-actions button:disabled{cursor:not-allowed;opacity:.45}.quote-fx-actions svg{width:11px}
@keyframes quote-live-spin{to{transform:rotate(360deg)}}
.quote-live-main-label{color:#a7f3d0;font-size:8px;font-weight:800}.quote-markup-control{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:4px;border-top:1px solid rgb(204 251 241/.28);padding-top:9px}.quote-markup-control label{display:grid;gap:1px;color:#fff;font-size:10px;font-weight:900}.quote-markup-control label small{color:#a7f3d0;font-size:7px;font-weight:700}.quote-markup-input{display:flex;align-items:center;gap:4px;border:1px solid rgb(255 255 255/.35);border-radius:8px;background:rgb(255 255 255/.12);padding:3px 5px 3px 7px;color:#d1fae5;font-size:11px;font-weight:900}.quote-markup-input input{width:62px;border:0;border-radius:5px;background:#fff;padding:5px 4px;color:#115e59;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px;font-weight:900;text-align:right}.quote-markup-input input:focus{outline:3px solid rgb(167 243 208/.35)}.quote-markup-save{display:flex;align-items:center;justify-content:center;gap:5px;width:100%;border:1px solid rgb(255 255 255/.65);border-radius:8px;background:#fff;padding:7px 9px;color:#0f766e;font-size:9px;font-weight:950;box-shadow:0 4px 12px rgb(6 78 59/.16);transition:transform .18s ease,box-shadow .18s ease}.quote-markup-save:not(:disabled):hover{transform:translateY(-1px);box-shadow:0 7px 16px rgb(6 78 59/.2)}.quote-markup-save:disabled{cursor:not-allowed;opacity:.5}.quote-markup-save svg{width:12px;height:12px}.quote-markup-feedback{margin:0;border-radius:6px;padding:5px 7px;font-size:7.5px;line-height:1.45}.quote-markup-feedback.success{background:rgb(236 253 245/.18);color:#d1fae5}.quote-markup-feedback.error{background:rgb(254 226 226/.18);color:#fee2e2}.quote-markup-feedback.blocked{background:rgb(255 247 237/.18);color:#ffedd5}.quote-live-cost-base{display:flex;align-items:center;justify-content:space-between;gap:8px;border-radius:7px;background:rgb(6 78 59/.22);padding:6px 8px}.quote-live-cost-base span{color:#a7f3d0;font-size:8px;font-weight:800}.quote-live-cost-base strong{color:#ecfdf5;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:9px}.quote-live-comparison{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-top:2px}.quote-live-price-cell{display:grid;gap:3px;min-width:0;border:1px solid var(--proximity-border,#d1fae5);border-radius:7px;background:var(--proximity-surface,#ecfdf5);padding:7px;color:var(--proximity-ink,#065f46);transition:background-color .2s ease,border-color .2s ease,color .2s ease}.quote-live-price-cell span{font-size:7px;font-weight:800;opacity:.78}.quote-live-price-cell strong{overflow-wrap:anywhere;font-size:9px;line-height:1.3}.quote-live-price-cell.gap{grid-column:1/-1;grid-template-columns:1fr auto;align-items:center}.quote-live-price-cell.gap strong{text-align:right}.quote-live-cost.proximity-0{--proximity-surface:#f0fdfa;--proximity-border:#ccfbf1;--proximity-ink:#0f766e}.quote-live-cost.proximity-1{--proximity-surface:#ccfbf1;--proximity-border:#99f6e4;--proximity-ink:#0f766e}.quote-live-cost.proximity-2{--proximity-surface:#99f6e4;--proximity-border:#5eead4;--proximity-ink:#115e59}.quote-live-cost.proximity-3{--proximity-surface:#2dd4bf;--proximity-border:#14b8a6;--proximity-ink:#134e4a}.quote-live-cost.proximity-4{--proximity-surface:#115e59;--proximity-border:#0f766e;--proximity-ink:#fff}.quote-live-cost.over.proximity-0{--proximity-surface:#fff7ed;--proximity-border:#ffedd5;--proximity-ink:#9a3412}.quote-live-cost.over.proximity-1{--proximity-surface:#ffedd5;--proximity-border:#fed7aa;--proximity-ink:#9a3412}.quote-live-cost.over.proximity-2{--proximity-surface:#fed7aa;--proximity-border:#fdba74;--proximity-ink:#9a3412}.quote-live-cost.over.proximity-3{--proximity-surface:#fb923c;--proximity-border:#f97316;--proximity-ink:#7c2d12}.quote-live-cost.over.proximity-4{--proximity-surface:#c2410c;--proximity-border:#9a3412;--proximity-ink:#fff}
.quote-markup-tier-control{display:grid;gap:5px;margin-top:4px;border-top:1px solid rgb(204 251 241/.28);padding-top:9px}.quote-markup-tier-control>header{display:flex;align-items:center;justify-content:space-between;gap:8px}.quote-markup-tier-control>header span{font-size:10px;font-weight:900}.quote-markup-tier-control>header small{color:#a7f3d0;font-size:7px;font-weight:700}.quote-markup-tier-row{display:grid;grid-template-columns:auto minmax(54px,1fr) auto minmax(48px,.75fr) auto;align-items:center;gap:4px;border:1px solid rgb(255 255 255/.2);border-radius:7px;background:rgb(255 255 255/.08);padding:4px 5px}.quote-markup-tier-row.active{border-color:#a7f3d0;background:rgb(236 253 245/.18);box-shadow:inset 3px 0 #a7f3d0}.quote-markup-tier-row label,.quote-markup-tier-row>span{color:#d1fae5;font-size:8px;font-weight:900}.quote-markup-tier-row input{min-width:0;width:100%;border:0;border-radius:5px;background:#fff;padding:5px 4px;color:#115e59;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:9px;font-weight:900;text-align:right}.quote-markup-tier-row input:focus{outline:3px solid rgb(167 243 208/.35)}.quote-markup-tier-select{border:1px solid rgb(255 255 255/.38);border-radius:99px;background:rgb(255 255 255/.1);padding:3px 5px;color:#d1fae5;font-size:6px;font-weight:950;white-space:nowrap}.quote-markup-tier-select.selected{border-color:#ecfdf5;background:#ecfdf5;color:#047857}.quote-markup-tier-select:not(:disabled):hover{background:#fff;color:#047857}.quote-markup-tier-select:disabled{opacity:.55}
.quote-mini-timeline,.quote-full-timeline{display:grid;gap:0;margin:0;padding:0;list-style:none}.quote-mini-timeline li,.quote-full-timeline li{position:relative;display:grid;grid-template-columns:12px 1fr;gap:8px;padding-bottom:13px}.quote-mini-timeline li:not(:last-child)::before,.quote-full-timeline li:not(:last-child)::before{position:absolute;top:8px;bottom:-1px;left:4px;width:1px;background:#cbd5e1;content:''}.quote-mini-timeline i,.quote-full-timeline i{z-index:1;width:9px;height:9px;margin-top:2px;border:2px solid #fff;border-radius:99px;background:#0d9488;box-shadow:0 0 0 1px #99f6e4}.quote-mini-timeline div,.quote-full-timeline div{display:grid}.quote-mini-timeline strong,.quote-full-timeline strong{color:#334155;font-size:9px}.quote-mini-timeline span,.quote-full-timeline span{margin-top:3px;color:#94a3b8;font-size:8px}.quote-full-timeline p{margin:4px 0 0;color:#64748b;font-size:9px;line-height:1.45}
.quote-comment-list{display:grid;gap:11px}.quote-comment-list article{display:flex;align-items:flex-start;gap:8px}.quote-comment-list article>span{display:grid;width:25px;height:25px;flex:0 0 auto;place-items:center;border-radius:8px;background:#ccfbf1;color:#0f766e;font-size:9px;font-weight:900}.quote-comment-list article>div{min-width:0;flex:1}.quote-comment-list header{display:flex;justify-content:space-between;gap:6px}.quote-comment-list strong{color:#334155;font-size:9px}.quote-comment-list small{color:#94a3b8;font-size:8px}.quote-comment-list p{margin:4px 0 0;border-radius:0 8px 8px 8px;background:#f1f5f9;padding:7px;color:#475569;font-size:9px;line-height:1.5}.quote-comment-form{display:flex;gap:6px;margin-top:12px}.quote-comment-form input{min-width:0;flex:1;border:1px solid #dbe5ea;border-radius:8px;padding:7px 8px;font-size:9px}.quote-comment-form button{display:grid;width:31px;height:31px;place-items:center;border:0;border-radius:8px;background:#0f766e;color:#fff}.quote-comment-form button:disabled{cursor:not-allowed;opacity:.4}.quote-comment-form svg{width:13px}.quote-side-hint{margin:-4px 0 12px;color:#94a3b8;font-size:8px;line-height:1.5}.quote-view-records article{display:flex;gap:9px;border-top:1px solid #f1f5f9;padding:11px 0}.quote-view-avatar{display:grid;width:30px;height:30px;flex:0 0 auto;place-items:center;border-radius:9px;background:#f1f5f9;color:#64748b}.quote-view-avatar svg{width:14px}.quote-view-records article div{min-width:0}.quote-view-records article strong{color:#334155;font-size:10px}.quote-view-records article p{margin:3px 0;color:#64748b;font-size:8px}.quote-view-records article small{color:#94a3b8;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:8px}
@media(max-width:1280px){.quote-activity-panel{position:static}.quote-activity-body{max-height:none}}
</style>
