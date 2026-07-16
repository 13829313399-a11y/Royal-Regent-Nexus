<script setup lang="ts">
import { ArrowLeft, BarChart3, Building2, CalendarDays, ChevronRight, CircleUserRound, Layers3, RefreshCw } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import InternalQuoteActivityPanel from './InternalQuoteActivityPanel.vue'
import InternalQuoteSectionEditor from './InternalQuoteSectionEditor.vue'
import InternalQuoteSectionRail from './InternalQuoteSectionRail.vue'
import { internalQuoteSectionDefinitions } from '@/data/internalQuoteDeskConfig'
import { useAuthStore } from '@/stores/auth'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import type { InternalQuoteSectionCode } from '@/types/internalQuoteDesk'

const route = useRoute()
const router = useRouter()
const quoteStore = useInternalQuoteDeskStore()
const authStore = useAuthStore()
const message = ref('')
const errorMessage = ref('')
const syncPanelOpen = ref(false)
const syncReason = ref('')

const quoteId = computed(() => String(route.params.quoteId ?? ''))
const quote = computed(() => quoteStore.getQuoteById(quoteId.value) ?? quoteStore.placeholderQuote)
const activeSectionCode = computed<InternalQuoteSectionCode>(() => {
  const requested = String(route.query.section ?? '') as InternalQuoteSectionCode
  return quote.value.sections.some((section) => section.code === requested) ? requested : quote.value.sections[0].code
})
const activeSection = computed(() => quote.value.sections.find((section) => section.code === activeSectionCode.value) ?? quote.value.sections[0])
const approvedCount = computed(() => quote.value.sections.filter((section) => ['approved', 'not_applicable'].includes(section.status)).length)
const activeDefinition = computed(() => internalQuoteSectionDefinitions.find((item) => item.code === activeSectionCode.value))
const canEditActive = computed(() => (activeDefinition.value?.departments ?? []).some((department) => authStore.can(`internal_quote:${activeSectionCode.value}_edit`, quote.value.factoryId, department)))
const canReviewActive = computed(() => (activeDefinition.value?.departments ?? []).some((department) => authStore.can(`internal_quote:${activeSectionCode.value}_review`, quote.value.factoryId, department)))
const canSyncReference = computed(() => ['sales-business', 'engineering'].some((department) => authStore.can('internal_quote:reference_manage', quote.value.factoryId, department)))

function selectSection(code: InternalQuoteSectionCode) { void router.replace({ query: { ...route.query, section: code } }) }

async function loadQuote() {
  message.value = ''
  errorMessage.value = ''
  quoteStore.conflictMessage = ''
  await quoteStore.loadQuote(quoteId.value)
}

async function syncReference() {
  if (!syncReason.value.trim()) return
  message.value = ''
  errorMessage.value = ''
  try {
    await quoteStore.syncReferenceSnapshot(quote.value.id, quote.value.headerRevision, syncReason.value.trim())
    message.value = '参考快照已同步；受影响分段已重算或标记依赖失效。'
    syncReason.value = ''
    syncPanelOpen.value = false
  } catch (error) { errorMessage.value = error instanceof Error ? error.message : '同步参考快照失败。' }
}

onMounted(loadQuote)
watch(quoteId, loadQuote)
</script>

<template>
  <div class="quote-collaboration-page">
    <nav class="quote-breadcrumb" aria-label="内部报价导航"><RouterLink to="/modules/sales-business/internal-quote-desk"><ArrowLeft />报价首页</RouterLink><ChevronRight /><span>{{ quote.quoteNo }}</span><ChevronRight /><strong>部门协作</strong></nav>

    <header class="quote-collaboration-head">
      <div class="quote-head-main"><div class="quote-title-row"><h1>{{ quote.productName }}</h1><span>{{ quote.status === 'rejected' ? '存在退回' : '协作进行中' }}</span></div><p>{{ quote.quoteNo }} · {{ quote.customer }} · {{ quote.versionLabel }}</p><div class="quote-head-meta"><span><Building2 />{{ quote.factoryName }} / {{ quote.workshopName }}</span><span><CircleUserRound />{{ quote.initiatorDepartment === 'engineering' ? '工程部' : '业务部' }}发起 · {{ quote.initiatorName }}</span><span><CalendarDays />目标 {{ quote.targetDate }}</span></div></div>
      <div class="quote-head-progress"><div><span>责任分段进度</span><strong>{{ approvedCount }}/{{ quote.sections.length }}</strong></div><div class="quote-progress-bar"><span :style="{ width: `${approvedCount / quote.sections.length * 100}%` }" /></div><RouterLink :to="`/modules/sales-business/internal-quote-desk/${quote.id}/summary`"><BarChart3 />查看汇总与放行</RouterLink><button type="button" :disabled="quoteStore.detailLoading" @click="loadQuote"><RefreshCw />重新读取最新 revision</button></div>
    </header>

    <div class="quote-snapshot-banner"><Layers3 /><span><strong>参考快照已冻结</strong>{{ quote.referenceSnapshotId }} · RMB→HKD {{ quote.fxRmbHkd }} · HKD→USD {{ quote.fxHkdUsd }}</span><em>同步最新参考表将产生新 revision，并使受影响审批失效</em><button v-if="canSyncReference" type="button" @click="syncPanelOpen = !syncPanelOpen">同步最新参考表</button></div>
    <section v-if="syncPanelOpen" class="quote-sync-panel"><div><strong>同步最新参考表</strong><span>将重算已填写分段，并使受影响的审批、最终放行和 artifact 失效。</span></div><textarea v-model="syncReason" rows="2" placeholder="必须填写同步原因" /><button type="button" class="secondary" @click="syncPanelOpen = false">取消</button><button type="button" class="primary" :disabled="!syncReason.trim() || quoteStore.submitting" @click="syncReference">确认同步</button></section>

    <p v-if="message" class="quote-page-message success">{{ message }}</p><p v-if="errorMessage" class="quote-page-message error">{{ errorMessage }}</p><p v-if="quoteStore.errorMessage" class="quote-page-message error">{{ quoteStore.errorMessage }}</p>
    <p v-if="quoteStore.conflictMessage" class="quote-page-message conflict"><span>{{ quoteStore.conflictMessage }}</span><button type="button" @click="loadQuote">放弃本地表单并重新读取</button></p>

    <div class="quote-collaboration-grid">
      <InternalQuoteSectionRail :sections="quote.sections" :active-code="activeSectionCode" @select="selectSection" />
      <InternalQuoteSectionEditor :quote="quote" :section="activeSection" :can-edit="canEditActive" :can-review="canReviewActive" />
      <InternalQuoteActivityPanel :quote="quote" read-only />
    </div>
  </div>
</template>

<style scoped>
.quote-collaboration-page{display:grid;gap:13px;padding-bottom:28px}.quote-breadcrumb{display:flex;align-items:center;gap:7px;color:#94a3b8;font-size:11px}.quote-breadcrumb a{display:inline-flex;align-items:center;gap:5px;color:#475569;font-weight:800}.quote-breadcrumb a:hover{color:#0f766e}.quote-breadcrumb svg{width:13px;height:13px}.quote-breadcrumb strong{color:#0f766e}.quote-collaboration-head{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;border:1px solid #dbe5ea;border-radius:14px;background:#fff;padding:18px;box-shadow:0 12px 28px rgb(15 23 42/.05)}.quote-title-row{display:flex;flex-wrap:wrap;align-items:center;gap:8px}.quote-title-row h1{margin:0;color:#0f172a;font-size:24px;font-weight:950;letter-spacing:-.035em}.quote-title-row>span{border-radius:999px;background:#fef3c7;padding:5px 8px;color:#b45309;font-size:11px;font-weight:900}.quote-head-main>p{margin:6px 0 0;color:#64748b;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px}.quote-head-meta{display:flex;flex-wrap:wrap;gap:11px;margin-top:12px}.quote-head-meta span{display:flex;align-items:center;gap:5px;color:#475569;font-size:11px}.quote-head-meta svg{width:14px;color:#0d9488}.quote-head-progress{display:grid;width:min(330px,35%);gap:8px}.quote-head-progress>div:first-child{display:flex;align-items:end;justify-content:space-between}.quote-head-progress span{color:#64748b;font-size:11px}.quote-head-progress strong{color:#0f766e;font-size:18px}.quote-progress-bar{height:7px;overflow:hidden;border-radius:99px;background:#e2e8f0}.quote-progress-bar span{display:block;height:100%;border-radius:99px;background:#0d9488}.quote-head-progress a,.quote-head-progress button{display:inline-flex;align-items:center;justify-content:center;gap:6px;border:1px solid #99f6e4;border-radius:8px;background:#f0fdfa;padding:8px;color:#0f766e;font-size:11px;font-weight:900}.quote-head-progress a:hover,.quote-head-progress button:hover{background:#ccfbf1}.quote-head-progress a svg,.quote-head-progress button svg{width:14px}.quote-head-progress button:disabled{opacity:.45}
.quote-snapshot-banner{display:flex;align-items:center;gap:8px;border:1px solid #bae6fd;border-radius:10px;background:#f0f9ff;padding:9px 12px;color:#0369a1}.quote-snapshot-banner>svg{width:16px;flex:0 0 auto}.quote-snapshot-banner>span{display:flex;gap:7px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px}.quote-snapshot-banner strong{font-family:'Microsoft YaHei','PingFang SC',sans-serif}.quote-snapshot-banner em{margin-left:auto;color:#0284c7;font-size:11px;font-style:normal}.quote-snapshot-banner button{border:1px solid #7dd3fc;border-radius:7px;background:#fff;padding:6px 9px;color:#0369a1;font-size:11px;font-weight:900}.quote-sync-panel{display:grid;grid-template-columns:minmax(200px,1fr) minmax(260px,2fr) auto auto;align-items:center;gap:9px;border:1px solid #bae6fd;border-radius:10px;background:#f0f9ff;padding:10px 12px}.quote-sync-panel>div{display:grid}.quote-sync-panel strong{color:#075985;font-size:12px}.quote-sync-panel span{margin-top:2px;color:#0369a1;font-size:11px}.quote-sync-panel textarea{border:1px solid #7dd3fc;border-radius:7px;padding:7px 9px;font-size:13px;resize:none}.quote-sync-panel button{height:32px;border-radius:7px;padding:0 10px;font-size:11px;font-weight:900}.quote-sync-panel .secondary{border:1px solid #7dd3fc;background:#fff;color:#0369a1}.quote-sync-panel .primary{border:1px solid #0369a1;background:#0369a1;color:#fff}.quote-page-message{margin:0;border-radius:8px;padding:8px 11px;font-size:11px}.quote-page-message.success{border:1px solid #a7f3d0;background:#ecfdf5;color:#047857}.quote-page-message.error{border:1px solid #fecaca;background:#fef2f2;color:#b91c1c}.quote-page-message.conflict{display:flex;align-items:center;justify-content:space-between;gap:10px;border:1px solid #fdba74;background:#fff7ed;color:#9a3412}.quote-page-message.conflict button{border:1px solid #fb923c;border-radius:7px;background:#fff;padding:6px 9px;color:#9a3412;font-size:11px;font-weight:900}.quote-collaboration-grid{display:grid;grid-template-columns:185px minmax(0,1fr) 270px;align-items:start;gap:11px}
@media(max-width:1280px){.quote-collaboration-grid{grid-template-columns:185px minmax(0,1fr)}.quote-collaboration-grid>*:last-child{grid-column:1/-1}}@media(max-width:980px){.quote-collaboration-grid{grid-template-columns:1fr}.quote-collaboration-grid>*:last-child{grid-column:auto}.quote-collaboration-head{align-items:stretch;flex-direction:column}.quote-head-progress{width:100%}.quote-snapshot-banner{align-items:flex-start;flex-wrap:wrap}.quote-snapshot-banner em{width:100%;margin-left:24px}.quote-sync-panel{grid-template-columns:1fr}}
</style>
