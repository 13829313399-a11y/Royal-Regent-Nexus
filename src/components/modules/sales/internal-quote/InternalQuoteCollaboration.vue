<script setup lang="ts">
import { ArrowLeft, BarChart3, Building2, CalendarDays, CheckCircle2, ChevronRight, CircleUserRound, Layers3, Maximize2, Minimize2, Pencil, RefreshCw, UserPlus } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import InternalQuoteActivityPanel from './InternalQuoteActivityPanel.vue'
import InternalQuoteHeaderDialog from './InternalQuoteHeaderDialog.vue'
import InternalQuoteSectionEditor from './InternalQuoteSectionEditor.vue'
import InternalQuoteSectionRail from './InternalQuoteSectionRail.vue'
import { getFactoryScopedRoute, isFactoryContextId } from '@/data/enterpriseMock'
import { internalQuoteSectionDefinitions } from '@/data/internalQuoteDeskConfig'
import { canReviewInternalQuoteSections, isForeignFactory, isInternalQuoteReadOnly } from '@/lib/internalQuoteAccess'
import { cloneInternalQuotePayload } from '@/lib/internalQuoteSectionPayload'
import { internalQuoteApi, type InternalQuoteHeaderUpdateRequest } from '@/api/internalQuote'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import type { InternalQuoteSectionCode } from '@/types/internalQuoteDesk'

const route = useRoute()
const router = useRouter()
const quoteStore = useInternalQuoteDeskStore()
const authStore = useAuthStore()
const appStore = useAppStore()
const message = ref('')
const errorMessage = ref('')
const syncPanelOpen = ref(false)
const syncReason = ref('')
const participationPanelOpen = ref(false)
const selectedParticipation = ref<InternalQuoteSectionCode[]>([])
const focusEntryMode = ref(true)
const sectionEditor = ref<InstanceType<typeof InternalQuoteSectionEditor> | null>(null)
const markupMessage = ref('')
const markupError = ref('')
const headerDialogOpen = ref(false)
const headerDialogBusy = ref(false)
const headerDialogError = ref('')
const headerBusinessOwners = ref<Array<{ id: string; username: string; displayName: string }>>([])
const headerCustomers = ref<string[]>([])

const quoteId = computed(() => String(route.params.quoteId ?? ''))
const loadedQuote = computed(() => quoteStore.getQuoteById(quoteId.value))
const quote = computed(() => loadedQuote.value ?? quoteStore.placeholderQuote)
const selectedFactoryId = computed(() => appStore.activeFactory.id === 'group'
  ? appStore.activeProductionFactory.id
  : appStore.activeFactory.id)
const participatingSections = computed(() => quote.value.sections.filter((section) => section.isRequired))
const optionalSectionCodes: InternalQuoteSectionCode[] = ['electronic', 'molding', 'painting', 'slush', 'sewing']
const availableOptionalSections = computed(() => quote.value.sections.filter((section) => !section.isRequired && optionalSectionCodes.includes(section.code)))
const activeSectionCode = computed<InternalQuoteSectionCode>(() => {
  const requested = String(route.query.section ?? '') as InternalQuoteSectionCode
  return participatingSections.value.some((section) => section.code === requested)
    ? requested
    : participatingSections.value[0]?.code ?? 'sales'
})
const activeSection = computed(() => participatingSections.value.find((section) => section.code === activeSectionCode.value) ?? participatingSections.value[0] ?? quote.value.sections[0])
const approvedCount = computed(() => participatingSections.value.filter((section) => ['approved', 'not_applicable'].includes(section.status)).length)
const progressPercent = computed(() => participatingSections.value.length ? approvedCount.value / participatingSections.value.length * 100 : 0)
const activeDefinition = computed(() => internalQuoteSectionDefinitions.find((item) => item.code === activeSectionCode.value))
const canEditActive = computed(() => (activeDefinition.value?.departments ?? []).some((department) => authStore.can(`internal_quote:${activeSectionCode.value}_edit`, quote.value.factoryId, department)))
const canReviewActive = computed(() => canReviewInternalQuoteSections(
  authStore,
  quote.value.factoryId,
  quote.value.businessOwnerId,
))
const canSyncReference = computed(() => ['sales-business', 'engineering'].some((department) => authStore.can('internal_quote:reference_manage', quote.value.factoryId, department)))
const canEditFx = computed(() => quote.value.status !== 'archived' && authStore.can('internal_quote:sales_edit', quote.value.factoryId, 'sales-business'))
const salesSection = computed(() => quote.value.sections.find((section) => section.code === 'sales'))
const canEditMarkup = computed(() => canEditFx.value)
const markupBlockedReason = computed(() => {
  if (!canEditMarkup.value) return ''
  if (!salesSection.value) return '业务部分段不存在，暂时无法保存码数。'
  if (['draft', 'rejected'].includes(salesSection.value.status)) return ''
  return '业务部已提交或审核完成；请先重开业务部分段，再保存新的码数。'
})
const canManageParticipation = computed(() => quote.value.status !== 'archived' && ['sales-business', 'engineering'].some((department) => authStore.can('internal_quote:create', quote.value.factoryId, department)))
const canEditHeader = computed(() => (
  !['final_pending', 'released', 'exported', 'archived'].includes(quote.value.status)
  && participatingSections.value.every((section) => section.status === 'draft' && section.revision === 1)
  && authStore.can('internal_quote:header_edit', quote.value.factoryId, 'sales-business')
))
const canRemoveActive = computed(() => canManageParticipation.value && optionalSectionCodes.includes(activeSectionCode.value))
const isReadOnly = computed(() => isInternalQuoteReadOnly(authStore, quote.value.factoryId))
const isForeignReadOnly = computed(() => isReadOnly.value && isForeignFactory(authStore, quote.value.factoryId))
const getQuoteRoute = (path: string) => getFactoryScopedRoute(
  path,
  isFactoryContextId(quote.value.factoryId) ? quote.value.factoryId : 'huaxing',
)

function selectSection(code: InternalQuoteSectionCode) { void router.replace({ query: { ...route.query, section: code } }) }

async function loadQuote() {
  message.value = ''
  errorMessage.value = ''
  quoteStore.conflictMessage = ''
  await quoteStore.loadQuote(quoteId.value)
}

async function syncReference() {
  if (!canSyncReference.value) {
    syncPanelOpen.value = false
    errorMessage.value = '当前账号没有该厂区的参考资料同步权限。'
    return
  }
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

async function updateReferenceFx(payload: { rmbHkd: string; hkdUsd: string }) {
  message.value = ''
  errorMessage.value = ''
  try {
    await quoteStore.updateReferenceFx(
      quote.value.id,
      quote.value.headerRevision,
      payload.rmbHkd,
      payload.hkdUsd,
    )
    message.value = '汇率已保存为新的冻结参考快照；该报价已按新汇率重算。'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '保存汇率失败。'
  }
}

async function updateQuoteMarkup(payload: { markup: string }) {
  markupMessage.value = ''
  markupError.value = ''
  message.value = ''
  errorMessage.value = ''
  if (!canEditMarkup.value || markupBlockedReason.value) {
    markupError.value = markupBlockedReason.value || '当前账号没有该厂区的业务部编辑权限。'
    return
  }
  const markup = Number(payload.markup)
  if (!Number.isFinite(markup) || markup < .01 || markup > 9.99) {
    markupError.value = '码数必须在 0.01 至 9.99 之间。'
    return
  }
  try {
    if (activeSectionCode.value === 'sales' && sectionEditor.value) {
      await sectionEditor.value.saveSalesMarkup(markup)
      markupMessage.value = '码数及当前业务部草稿已保存，并已重新计算报价。'
    } else {
      const section = salesSection.value
      if (!section) throw new Error('业务部分段不存在，暂时无法保存码数。')
      const sourceShipping = section.payload.shipping && typeof section.payload.shipping === 'object' && !Array.isArray(section.payload.shipping)
        ? section.payload.shipping as Record<string, unknown>
        : {}
      const nextPayload = cloneInternalQuotePayload('sales', {
        ...section.payload,
        shipping: { ...sourceShipping, markup_x: Number(markup.toFixed(2)) },
      })
      await quoteStore.saveSection(quote.value.id, 'sales', section.revision, nextPayload, '在协作侧栏保存报价码数')
      markupMessage.value = '码数已保存为业务部新 revision，并已重新计算报价。'
    }
    message.value = markupMessage.value
  } catch (error) {
    markupError.value = error instanceof Error ? error.message : '保存码数失败。'
  }
}

function toggleParticipationPanel() {
  selectedParticipation.value = []
  participationPanelOpen.value = !participationPanelOpen.value
}

async function addParticipation() {
  if (!selectedParticipation.value.length) return
  message.value = ''
  errorMessage.value = ''
  const firstAdded = selectedParticipation.value[0]
  try {
    await quoteStore.addParticipation(quote.value.id, quote.value.headerRevision, selectedParticipation.value)
    message.value = '参与部门已添加；新部门已收到填写任务并纳入协作进度与最终放行。'
    selectedParticipation.value = []
    participationPanelOpen.value = false
    if (firstAdded) selectSection(firstAdded)
  } catch (error) { errorMessage.value = error instanceof Error ? error.message : '添加参与部门失败。' }
}

async function removeParticipation(sectionCode: InternalQuoteSectionCode) {
  if (!canManageParticipation.value || !optionalSectionCodes.includes(sectionCode)) return
  message.value = ''
  errorMessage.value = ''
  const sectionLabel = quote.value.sections.find((section) => section.code === sectionCode)?.label ?? '该部门'
  try {
    await quoteStore.removeParticipation(quote.value.id, quote.value.headerRevision, [sectionCode])
    message.value = `${sectionLabel}已移出当前报价；已不再计入进度、成本汇总和最终放行。`
    const fallbackSection = participatingSections.value[0]?.code ?? 'sales'
    await router.replace({ query: { ...route.query, section: fallbackSection } })
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '移除参与部门失败。'
  }
}

async function openHeaderDialog() {
  if (!canEditHeader.value || !quote.value.id) return
  const requestedQuoteId = quote.value.id
  const requestedFactoryId = quote.value.factoryId
  headerDialogOpen.value = true
  headerDialogBusy.value = true
  headerDialogError.value = ''
  try {
    const [owners, customers] = await Promise.all([
      internalQuoteApi.listBusinessOwners(requestedFactoryId),
      internalQuoteApi.listCustomers(requestedFactoryId),
    ])
    if (!headerDialogOpen.value || quote.value.id !== requestedQuoteId) return
    headerBusinessOwners.value = owners.map((owner) => ({ id: owner.id, username: owner.username, displayName: owner.display_name }))
    headerCustomers.value = Array.from(new Set([quote.value.customer, ...customers.map((customer) => customer.name)]))
  } catch (error) {
    if (headerDialogOpen.value && quote.value.id === requestedQuoteId) {
      headerDialogError.value = error instanceof Error ? error.message : '读取当前厂区客户和业务负责人失败。'
    }
  } finally {
    if (headerDialogOpen.value && quote.value.id === requestedQuoteId) headerDialogBusy.value = false
  }
}

function closeHeaderDialog() {
  if (headerDialogBusy.value) return
  headerDialogOpen.value = false
  headerDialogError.value = ''
}

async function saveHeader(payload: InternalQuoteHeaderUpdateRequest) {
  if (!canEditHeader.value) return
  headerDialogBusy.value = true
  headerDialogError.value = ''
  try {
    await quoteStore.updateHeader(quote.value.id, payload)
    headerDialogOpen.value = false
    message.value = '报价资料已保存为新的报价头 revision。'
  } catch (error) {
    headerDialogError.value = error instanceof Error ? error.message : '保存报价资料失败。'
  } finally {
    headerDialogBusy.value = false
  }
}

onMounted(loadQuote)
watch(quoteId, loadQuote)
watch([selectedFactoryId, () => loadedQuote.value?.factoryId], ([factoryId, quoteFactoryId]) => {
  if (!quoteFactoryId || quoteFactoryId === factoryId || !isFactoryContextId(factoryId)) return
  void router.replace(getFactoryScopedRoute('/modules/sales-business/internal-quote-desk', factoryId))
})
watch([quoteId, canSyncReference], () => {
  syncPanelOpen.value = false
  syncReason.value = ''
})
watch(quoteId, () => {
  markupMessage.value = ''
  markupError.value = ''
})
</script>

<template>
  <div class="quote-collaboration-page">
    <nav class="quote-breadcrumb" aria-label="内部报价导航"><RouterLink :to="getQuoteRoute('/modules/sales-business/internal-quote-desk')"><ArrowLeft />报价首页</RouterLink><ChevronRight /><span>{{ quote.quoteNo }}</span><ChevronRight /><strong>部门协作</strong></nav>

    <header class="quote-collaboration-head">
      <div class="quote-head-main"><div class="quote-title-row"><h1>{{ quote.productName }}</h1><span>{{ quote.status === 'rejected' ? '存在退回' : '协作进行中' }}</span></div><p>{{ quote.quoteNo }} · {{ quote.customer }} · {{ quote.versionLabel }}</p><div class="quote-head-meta"><span><Building2 />{{ quote.factoryName }} / {{ quote.workshopName }}</span><span><CircleUserRound />{{ quote.initiatorDepartment === 'engineering' ? '工程部' : '业务部' }}发起 · {{ quote.initiatorName }}</span><span><CircleUserRound />全部分段审核 · {{ quote.businessOwner }}</span><span><CalendarDays />目标 {{ quote.targetDate }}</span></div></div>
      <div class="quote-head-progress"><div><span>参与分段进度</span><strong>{{ approvedCount }}/{{ participatingSections.length }}</strong></div><div class="quote-progress-bar"><span :style="{ width: `${progressPercent}%` }" /></div><button type="button" class="focus-entry-toggle" :aria-pressed="focusEntryMode" @click="focusEntryMode = !focusEntryMode"><Maximize2 v-if="focusEntryMode" /><Minimize2 v-else />{{ focusEntryMode ? '显示两侧栏' : '专注填报' }}</button><RouterLink :to="getQuoteRoute(`/modules/sales-business/internal-quote-desk/${quote.id}/summary`)"><BarChart3 />查看汇总与放行</RouterLink><button v-if="canEditHeader" type="button" @click="openHeaderDialog"><Pencil />修改报价资料</button><button v-if="canManageParticipation && availableOptionalSections.length" type="button" @click="toggleParticipationPanel"><UserPlus />添加参与部门</button><button type="button" :disabled="quoteStore.detailLoading" @click="loadQuote"><RefreshCw />重新读取最新 revision</button></div>
    </header>

    <p v-if="isReadOnly" class="quote-readonly-banner"><Building2 aria-hidden="true" />{{ isForeignReadOnly ? '当前为跨厂只读视图；分段编辑、审核、参考同步及其他业务操作仅允许在所属厂区执行。' : '当前账号仅可查看该报价，没有可用的分段编辑、审核或参考同步权限。' }}</p>

    <div class="quote-snapshot-banner"><Layers3 /><span><strong>参考快照已冻结</strong>{{ quote.referenceSnapshotId }} · RMB→HKD {{ quote.fxRmbHkd.toFixed(2) }} · HKD→USD {{ quote.fxHkdUsd.toFixed(2) }}</span><em>同步最新参考表将产生新 revision，并使受影响审批失效</em><button v-if="canSyncReference" type="button" @click="syncPanelOpen = !syncPanelOpen">同步最新参考表</button></div>
    <section v-if="syncPanelOpen && canSyncReference" class="quote-sync-panel"><div><strong>同步最新参考表</strong><span>将重算已填写分段，并使受影响的审批、最终放行和 artifact 失效。</span></div><textarea v-model="syncReason" rows="2" placeholder="必须填写同步原因" /><button type="button" class="secondary" @click="syncPanelOpen = false">取消</button><button type="button" class="primary" :disabled="!syncReason.trim() || quoteStore.submitting || !canSyncReference" @click="syncReference">确认同步</button></section>
    <section v-if="participationPanelOpen" class="quote-participation-panel">
      <div class="quote-participation-copy"><UserPlus /><span><strong>添加参与部门</strong><small>添加后会立即生成填写任务并纳入审批与最终放行；可选部门也可由业务或工程在其明细底部移除。</small></span></div>
      <div class="quote-participation-options">
        <label v-for="section in availableOptionalSections" :key="section.code" :class="{ active: selectedParticipation.includes(section.code) }">
          <input v-model="selectedParticipation" type="checkbox" :value="section.code">
          <CheckCircle2 />
          <span>{{ section.label }}</span>
        </label>
      </div>
      <div class="quote-participation-actions"><button type="button" class="secondary" @click="toggleParticipationPanel">取消</button><button type="button" class="primary" :disabled="!selectedParticipation.length || quoteStore.submitting" @click="addParticipation">确认添加 {{ selectedParticipation.length ? `(${selectedParticipation.length})` : '' }}</button></div>
    </section>

    <p v-if="message" class="quote-page-message success">{{ message }}</p><p v-if="errorMessage" class="quote-page-message error">{{ errorMessage }}</p><p v-if="quoteStore.errorMessage" class="quote-page-message error">{{ quoteStore.errorMessage }}</p>
    <p v-if="quoteStore.conflictMessage" class="quote-page-message conflict"><span>{{ quoteStore.conflictMessage }}</span><button type="button" @click="loadQuote">放弃本地表单并重新读取</button></p>

    <div class="quote-collaboration-grid" :class="{ 'focus-entry-mode': focusEntryMode }">
      <InternalQuoteSectionRail :sections="participatingSections" :active-code="activeSectionCode" @select="selectSection" />
      <InternalQuoteSectionEditor ref="sectionEditor" :quote="quote" :section="activeSection" :can-edit="canEditActive" :can-review="canReviewActive" :can-remove="canRemoveActive" @remove="removeParticipation" />
      <InternalQuoteActivityPanel :quote="quote" read-only :can-edit-fx="canEditFx" :can-edit-markup="canEditMarkup" :markup-blocked-reason="markupBlockedReason" :markup-message="markupMessage" :markup-error="markupError" :busy="quoteStore.submitting" @update-fx="updateReferenceFx" @update-markup="updateQuoteMarkup" />
    </div>
    <button
      type="button"
      class="focus-entry-float"
      :aria-label="focusEntryMode ? '显示两侧栏' : '切换为专注填报'"
      :aria-pressed="focusEntryMode"
      :data-label="focusEntryMode ? '显示两侧栏' : '专注填报'"
      :title="focusEntryMode ? '显示两侧栏' : '专注填报'"
      @click="focusEntryMode = !focusEntryMode"
    >
      <Maximize2 v-if="focusEntryMode" aria-hidden="true" />
      <Minimize2 v-else aria-hidden="true" />
    </button>
    <InternalQuoteHeaderDialog
      :open="headerDialogOpen"
      :quote="quote"
      :business-owners="headerBusinessOwners"
      :customers="headerCustomers"
      :busy="headerDialogBusy"
      :external-error="headerDialogError"
      @close="closeHeaderDialog"
      @confirm="saveHeader"
    />
  </div>
</template>

<style scoped>
.quote-collaboration-page{display:grid;gap:13px;padding-bottom:28px}.quote-breadcrumb{display:flex;align-items:center;gap:7px;color:#94a3b8;font-size:11px}.quote-breadcrumb a{display:inline-flex;align-items:center;gap:5px;color:#475569;font-weight:800}.quote-breadcrumb a:hover{color:#0f766e}.quote-breadcrumb svg{width:13px;height:13px}.quote-breadcrumb strong{color:#0f766e}.quote-collaboration-head{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;border:1px solid #dbe5ea;border-radius:14px;background:#fff;padding:18px;box-shadow:0 12px 28px rgb(15 23 42/.05)}.quote-title-row{display:flex;flex-wrap:wrap;align-items:center;gap:8px}.quote-title-row h1{margin:0;color:#0f172a;font-size:24px;font-weight:950;letter-spacing:-.035em}.quote-title-row>span{border-radius:999px;background:#fef3c7;padding:5px 8px;color:#b45309;font-size:11px;font-weight:900}.quote-head-main>p{margin:6px 0 0;color:#64748b;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px}.quote-head-meta{display:flex;flex-wrap:wrap;gap:11px;margin-top:12px}.quote-head-meta span{display:flex;align-items:center;gap:5px;color:#475569;font-size:11px}.quote-head-meta svg{width:14px;color:#0d9488}.quote-head-progress{display:grid;width:min(330px,35%);gap:8px}.quote-head-progress>div:first-child{display:flex;align-items:end;justify-content:space-between}.quote-head-progress span{color:#64748b;font-size:11px}.quote-head-progress strong{color:#0f766e;font-size:18px}.quote-progress-bar{height:7px;overflow:hidden;border-radius:99px;background:#e2e8f0}.quote-progress-bar span{display:block;height:100%;border-radius:99px;background:#0d9488}.quote-head-progress a,.quote-head-progress button{display:inline-flex;align-items:center;justify-content:center;gap:6px;border:1px solid #99f6e4;border-radius:8px;background:#f0fdfa;padding:8px;color:#0f766e;font-size:11px;font-weight:900}.quote-head-progress a:hover,.quote-head-progress button:hover{background:#ccfbf1}.quote-head-progress a svg,.quote-head-progress button svg{width:14px}.quote-head-progress button:disabled{opacity:.45}.quote-readonly-banner{display:flex;align-items:center;gap:7px;margin:0;border:1px solid #99f6e4;border-radius:9px;background:#f0fdfa;padding:9px 11px;color:#0f766e;font-size:11px}.quote-readonly-banner svg{width:15px;flex:0 0 auto}
.quote-snapshot-banner{display:flex;align-items:center;gap:8px;border:1px solid #bae6fd;border-radius:10px;background:#f0f9ff;padding:9px 12px;color:#0369a1}.quote-snapshot-banner>svg{width:16px;flex:0 0 auto}.quote-snapshot-banner>span{display:flex;gap:7px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px}.quote-snapshot-banner strong{font-family:'Microsoft YaHei','PingFang SC',sans-serif}.quote-snapshot-banner em{margin-left:auto;color:#0284c7;font-size:11px;font-style:normal}.quote-snapshot-banner button{border:1px solid #7dd3fc;border-radius:7px;background:#fff;padding:6px 9px;color:#0369a1;font-size:11px;font-weight:900}.quote-sync-panel{display:grid;grid-template-columns:minmax(200px,1fr) minmax(260px,2fr) auto auto;align-items:center;gap:9px;border:1px solid #bae6fd;border-radius:10px;background:#f0f9ff;padding:10px 12px}.quote-sync-panel>div{display:grid}.quote-sync-panel strong{color:#075985;font-size:12px}.quote-sync-panel span{margin-top:2px;color:#0369a1;font-size:11px}.quote-sync-panel textarea{border:1px solid #7dd3fc;border-radius:7px;padding:7px 9px;font-size:13px;resize:none}.quote-sync-panel button{height:32px;border-radius:7px;padding:0 10px;font-size:11px;font-weight:900}.quote-sync-panel .secondary{border:1px solid #7dd3fc;background:#fff;color:#0369a1}.quote-sync-panel .primary{border:1px solid #0369a1;background:#0369a1;color:#fff}.quote-page-message{margin:0;border-radius:8px;padding:8px 11px;font-size:11px}.quote-page-message.success{border:1px solid #a7f3d0;background:#ecfdf5;color:#047857}.quote-page-message.error{border:1px solid #fecaca;background:#fef2f2;color:#b91c1c}.quote-page-message.conflict{display:flex;align-items:center;justify-content:space-between;gap:10px;border:1px solid #fdba74;background:#fff7ed;color:#9a3412}.quote-page-message.conflict button{border:1px solid #fb923c;border-radius:7px;background:#fff;padding:6px 9px;color:#9a3412;font-size:11px;font-weight:900}.quote-collaboration-grid{display:grid;grid-template-columns:185px minmax(0,1fr) 270px;align-items:start;gap:11px}.quote-collaboration-grid.focus-entry-mode{grid-template-columns:minmax(0,1fr)}.quote-collaboration-grid.focus-entry-mode>:first-child,.quote-collaboration-grid.focus-entry-mode>:last-child{display:none}.focus-entry-toggle{border-color:#0f766e!important;background:#0f766e!important;color:#fff!important}.focus-entry-toggle[aria-pressed="true"]{border-color:#99f6e4!important;background:#f0fdfa!important;color:#0f766e!important}
.quote-collaboration-grid.focus-entry-mode :deep(.payload-table-scroll),.quote-collaboration-grid.focus-entry-mode :deep(.snapshot-table-scroll){overflow:visible}.quote-collaboration-grid.focus-entry-mode :deep(.payload-table-scroll table),.quote-collaboration-grid.focus-entry-mode :deep(.snapshot-table-scroll table),.quote-collaboration-grid.focus-entry-mode :deep(.calculation-snapshot table){width:100%;min-width:0!important;table-layout:fixed}.quote-collaboration-grid.focus-entry-mode :deep(.payload-table-scroll th),.quote-collaboration-grid.focus-entry-mode :deep(.payload-table-scroll td),.quote-collaboration-grid.focus-entry-mode :deep(.snapshot-table-scroll th),.quote-collaboration-grid.focus-entry-mode :deep(.snapshot-table-scroll td){width:auto!important;min-width:0!important;padding:5px 4px;white-space:normal;overflow-wrap:anywhere}.quote-collaboration-grid.focus-entry-mode :deep(.payload-table-scroll input),.quote-collaboration-grid.focus-entry-mode :deep(.payload-table-scroll select),.quote-collaboration-grid.focus-entry-mode :deep(.payload-table-scroll textarea){min-width:0;padding-inline:5px;font-size:11px}.quote-collaboration-grid.focus-entry-mode :deep(.payload-table-scroll textarea){min-height:44px}.quote-collaboration-grid.focus-entry-mode :deep(.snapshot-cell){font-size:10px;white-space:normal}.quote-collaboration-grid.focus-entry-mode :deep(.row-number){width:28px!important}.quote-collaboration-grid.focus-entry-mode :deep(.icon){width:26px;min-height:28px;padding:0}
.focus-entry-float{position:fixed;right:22px;bottom:24px;z-index:60;display:grid;width:40px;height:40px;place-items:center;border:1px solid #0f766e;border-radius:11px;background:rgb(15 118 110/.94);padding:0;color:#fff;box-shadow:0 10px 24px rgb(15 23 42/.2);backdrop-filter:blur(10px);cursor:pointer;transition:transform .18s ease,box-shadow .18s ease,background-color .18s ease}.focus-entry-float svg{width:17px;height:17px}.focus-entry-float[aria-pressed="true"]{border-color:#5eead4;background:rgb(255 255 255/.9);color:#0f766e}.focus-entry-float:hover,.focus-entry-float:focus-visible{transform:translateY(-2px);box-shadow:0 13px 28px rgb(15 23 42/.24)}.focus-entry-float:focus-visible{outline:3px solid rgb(45 212 191/.3);outline-offset:2px}.focus-entry-float::after{position:absolute;right:48px;top:50%;border-radius:7px;background:rgb(15 23 42/.9);padding:6px 8px;color:#fff;content:attr(data-label);font-size:10px;font-weight:800;opacity:0;pointer-events:none;transform:translate(5px,-50%);transition:opacity .16s ease,transform .16s ease;white-space:nowrap}.focus-entry-float:hover::after,.focus-entry-float:focus-visible::after{opacity:1;transform:translate(0,-50%)}
.quote-participation-panel{display:grid;grid-template-columns:minmax(240px,1.2fr) minmax(320px,2fr) auto;align-items:center;gap:14px;border:1px solid #99f6e4;border-radius:12px;background:#f0fdfa;padding:13px 14px;box-shadow:0 10px 22px rgb(15 118 110/.07)}.quote-participation-copy{display:flex;align-items:flex-start;gap:9px}.quote-participation-copy>svg{width:19px;flex:0 0 auto;color:#0f766e}.quote-participation-copy span{display:grid}.quote-participation-copy strong{color:#134e4a;font-size:13px}.quote-participation-copy small{margin-top:3px;color:#47716d;font-size:11px;line-height:1.45}.quote-participation-options{display:flex;flex-wrap:wrap;gap:7px}.quote-participation-options label{position:relative;display:inline-flex;align-items:center;gap:5px;border:1px solid #bae6df;border-radius:999px;background:#fff;padding:7px 10px;color:#475569;font-size:12px;font-weight:900;cursor:pointer;transition:border-color .18s ease,background-color .18s ease,color .18s ease,transform .18s ease}.quote-participation-options label:hover{border-color:#2dd4bf;transform:translateY(-1px)}.quote-participation-options label.active{border-color:#0d9488;background:#ccfbf1;color:#0f766e}.quote-participation-options input{position:absolute;opacity:0}.quote-participation-options svg{width:14px;height:14px;color:#cbd5e1}.quote-participation-options label.active svg{color:#0f766e}.quote-participation-actions{display:flex;gap:7px}.quote-participation-actions button{height:34px;border-radius:8px;padding:0 11px;font-size:12px;font-weight:900}.quote-participation-actions .secondary{border:1px solid #99f6e4;background:#fff;color:#0f766e}.quote-participation-actions .primary{border:1px solid #0f766e;background:#0f766e;color:#fff}.quote-participation-actions .primary:disabled{opacity:.45}
@media(max-width:1280px){.quote-collaboration-grid{grid-template-columns:185px minmax(0,1fr)}.quote-collaboration-grid>*:last-child{grid-column:1/-1}.quote-participation-panel{grid-template-columns:1fr 1.6fr}.quote-participation-actions{grid-column:1/-1;justify-content:flex-end}}@media(max-width:980px){.quote-collaboration-grid{grid-template-columns:1fr}.quote-collaboration-grid>*:last-child{grid-column:auto}.quote-collaboration-head{align-items:stretch;flex-direction:column}.quote-head-progress{width:100%}.quote-snapshot-banner{align-items:flex-start;flex-wrap:wrap}.quote-snapshot-banner em{width:100%;margin-left:24px}.quote-sync-panel,.quote-participation-panel{grid-template-columns:1fr}.quote-participation-actions{grid-column:auto}}@media(max-width:600px){.focus-entry-float{right:12px;bottom:14px;width:36px;height:36px;border-radius:10px}.focus-entry-float::after{right:44px}}
</style>
