<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  AlertTriangle,
  ArrowLeft,
  Bot,
  Boxes,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleDollarSign,
  Database,
  Gauge,
  House,
  Info,
  Plus,
  RefreshCw,
  Search,
  Server,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
} from '@lucide/vue'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import { useAuthStore } from '@/stores/auth'
import {
  createSharedMoldProposal,
  getSharedMoldDetail,
  listSharedMoldCatalog,
  type SharedMoldCatalogItem,
  type SharedMoldCatalogPage,
  type SharedMoldDetail,
  type SharedMoldProposalInput,
} from './api/injectionSchedulingV2Api'
import './injection-scheduling-v2.css'
import './styles/tokens.css'
import './styles/polish.css'
import './shared-mold-database.css'

const factoryNames: Record<string, string> = {
  huaxing: '华兴',
  'huakang-a': '华康 A',
  'huakang-b': '华康 B',
  'huakang-c': '华康 C',
  'huakang-d': '华康 D',
  huadeng: '华登',
}
const schedulingDepartments = ['production', 'molding', 'pmc-warehouse', 'warehouse', 'management']
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const requestedFactory = typeof route.query.factory === 'string' ? route.query.factory : 'huaxing'
const factoryId = ref(factoryNames[requestedFactory] ? requestedFactory : 'huaxing')
const search = ref('')
const readiness = ref<'ALL' | 'FACTORY_READY' | 'NOT_FACTORY_READY'>('ALL')
const loading = ref(false)
const loadError = ref('')
const catalog = ref<SharedMoldCatalogPage>({
  items: [], page: 1, pageSize: 30, total: 0,
  summary: { totalDefinitions: 0, factoryReady: 0, notFactoryReady: 0, pendingProposals: 0, canReadPrices: false },
})
const detailOpen = ref(false)
const detailLoading = ref(false)
const detail = ref<SharedMoldDetail | null>(null)
const proposalOpen = ref(false)
const submitting = ref(false)
const feedback = reactive({ message: '', tone: 'success' as 'success' | 'error' })
let searchTimer: ReturnType<typeof setTimeout> | null = null
let feedbackTimer: ReturnType<typeof setTimeout> | null = null

const canScoped = (permission: string) => schedulingDepartments.some((department) => authStore.can(permission, factoryId.value, department))
const canPropose = computed(() => canScoped('shared_mold:propose'))
const canProposePrice = computed(() => canScoped('shared_mold_price:propose'))
const canProposeCapability = computed(() => canScoped('factory_mold_capability:manage'))
const pageCount = computed(() => Math.max(1, Math.ceil(catalog.value.total / catalog.value.pageSize)))
const rangeStart = computed(() => catalog.value.total ? (catalog.value.page - 1) * catalog.value.pageSize + 1 : 0)
const rangeEnd = computed(() => Math.min(catalog.value.total, catalog.value.page * catalog.value.pageSize))

interface ProposalOutputDraft {
  itemNo: string
  variantCode: string
  productName: string
  cavityCount: number | null
  wholeShotNetWeightG: number | null
  wholeShotGrossWeightG: number | null
  defaultMaterial: string
  defaultColor: string
  nominalDailyCapacity: number | null
  unitPriceCny: number | null
}

const newOutput = (): ProposalOutputDraft => ({
  itemNo: '', variantCode: '', productName: '', cavityCount: null,
  wholeShotNetWeightG: null, wholeShotGrossWeightG: null,
  defaultMaterial: '', defaultColor: '', nominalDailyCapacity: null, unitPriceCny: null,
})
const proposal = reactive({
  canonicalMoldNo: '', displayMoldNo: '', standardName: '', aliases: '',
  recommendedMachineClassRaw: '', moldAClass: null as number | null,
  defaultArmType: '', defaultFixtureType: '', includeCapability: false,
  capabilityMachineClass: null as number | null, capabilityMachineClassRaw: '',
  capabilityArmType: '', capabilityFixtureType: '', reason: '',
  outputs: [newOutput()] as ProposalOutputDraft[],
})
const proposalValid = computed(() => Boolean(
  proposal.canonicalMoldNo.trim()
  && proposal.standardName.trim()
  && proposal.reason.trim().length >= 4
  && proposal.outputs.length
  && proposal.outputs.every((item) => item.productName.trim()),
))

function errorMessage(error: unknown) {
  const detailValue = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detailValue === 'string') return detailValue
  if (detailValue && typeof detailValue === 'object') {
    const message = (detailValue as { message?: unknown }).message
    if (typeof message === 'string') return message
  }
  return error instanceof Error ? error.message : '请求失败，请稍后重试'
}

function notify(message: string, tone: 'success' | 'error' = 'success') {
  feedback.message = message
  feedback.tone = tone
  if (feedbackTimer) clearTimeout(feedbackTimer)
  feedbackTimer = setTimeout(() => { feedback.message = '' }, 4200)
}

async function loadCatalog(page = catalog.value.page) {
  loading.value = true
  loadError.value = ''
  try {
    catalog.value = await listSharedMoldCatalog(factoryId.value, {
      q: search.value.trim(), readiness: readiness.value, page, pageSize: catalog.value.pageSize,
    })
  } catch (error) {
    loadError.value = errorMessage(error)
  } finally {
    loading.value = false
  }
}

async function openDetail(item: SharedMoldCatalogItem) {
  detailOpen.value = true
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = await getSharedMoldDetail(factoryId.value, item.id)
  } catch (error) {
    notify(errorMessage(error), 'error')
    detailOpen.value = false
  } finally {
    detailLoading.value = false
  }
}

function resetProposal() {
  Object.assign(proposal, {
    canonicalMoldNo: '', displayMoldNo: '', standardName: '', aliases: '',
    recommendedMachineClassRaw: '', moldAClass: null, defaultArmType: '', defaultFixtureType: '',
    includeCapability: false, capabilityMachineClass: null, capabilityMachineClassRaw: '',
    capabilityArmType: '', capabilityFixtureType: '', reason: '', outputs: [newOutput()],
  })
}

function openProposal() {
  if (!canPropose.value) {
    notify('当前账号没有共享模具提案权限', 'error')
    return
  }
  resetProposal()
  proposalOpen.value = true
}

async function submitProposal() {
  if (!proposalValid.value || submitting.value) return
  submitting.value = true
  try {
    const input: SharedMoldProposalInput = {
      canonicalMoldNo: proposal.canonicalMoldNo.trim(),
      displayMoldNo: proposal.displayMoldNo.trim(),
      standardName: proposal.standardName.trim(),
      rawAliases: proposal.aliases.split(/[，,\n]/).map((item) => item.trim()).filter(Boolean),
      recommendedMachineClassRaw: proposal.recommendedMachineClassRaw.trim(),
      moldAClass: proposal.moldAClass || null,
      defaultArmType: proposal.defaultArmType.trim(),
      defaultFixtureType: proposal.defaultFixtureType.trim(),
      outputs: proposal.outputs.map((item) => ({ ...item })),
      capability: proposal.includeCapability ? {
        machineClass: proposal.capabilityMachineClass || null,
        machineClassRaw: proposal.capabilityMachineClassRaw.trim(),
        requiredArmType: proposal.capabilityArmType.trim(),
        requiredFixtureType: proposal.capabilityFixtureType.trim(),
      } : null,
      reason: proposal.reason.trim(),
    }
    const created = await createSharedMoldProposal(factoryId.value, input)
    proposalOpen.value = false
    notify(`已提交 ${created.length} 个治理提案，需由另一位有权限人员审核后生效`)
    await loadCatalog(1)
  } catch (error) {
    notify(errorMessage(error), 'error')
  } finally {
    submitting.value = false
  }
}

function changeFactory(value: string) {
  factoryId.value = value
  void router.replace({ query: { ...route.query, factory: value } })
  detailOpen.value = false
  void loadCatalog(1)
}

function goScheduling() {
  void router.push({ name: 'injection-scheduling-v2', query: { factory: factoryId.value } })
}

function goMachines() {
  void router.push({ name: 'injection-scheduling-machine-database', query: { factory: factoryId.value } })
}

function goHome() {
  void router.push({ name: 'dashboard' })
}

function readinessLabel(status: string) {
  return status === 'FACTORY_READY' ? '厂区就绪' : '待补实体 / 能力'
}

function armLabel(value: string) {
  return ({ single: '单臂', dual: '双臂', none: '无需机械臂' } as Record<string, string>)[value] || value || '—'
}

function fixtureLabel(value: string) {
  return ({ suction_cup: '吸盘', clamp: '夹具', none: '无需夹具' } as Record<string, string>)[value] || value || '夹具待补充'
}

function dataQualityLabel(value: string) {
  return ({ APPROVED_SOURCE: '已审核来源', APPROVED: '已审核', REVIEW_REQUIRED: '待复核' } as Record<string, string>)[value] || value
}

function formatNumber(value: number | null, digits = 0) {
  return value === null ? '—' : value.toLocaleString('zh-CN', { maximumFractionDigits: digits })
}

watch(search, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { void loadCatalog(1) }, 280)
})
watch(readiness, () => { void loadCatalog(1) })
onMounted(() => { void loadCatalog(1) })
onBeforeUnmount(() => {
  if (searchTimer) clearTimeout(searchTimer)
  if (feedbackTimer) clearTimeout(feedbackTimer)
})
</script>

<template>
  <div class="injection-scheduling-v2 shared-mold-database">
    <header class="scheduling-topbar">
      <div class="brand-mark"><Bot :size="22" /></div>
      <div class="brand-copy"><strong>Royal Regent Nexus</strong><span>ROYAL REGENT · PRODUCTION INTELLIGENCE</span></div>
      <button type="button" class="topbar-home-button" @click="goHome"><House :size="15" /><span>返回主页</span></button>
      <div class="topbar-live"><span class="live-dot"></span><span>共享模具主数据在线</span><b>正式数据</b></div>
      <AccountMenu compact class="scheduling-account-menu" />
    </header>

    <section class="scheduling-commandbar mold-commandbar" aria-label="模具数据库命令栏">
      <div class="page-identity"><span class="eyebrow">生产部 / 注塑排产 / 模具数据库</span><strong>共享模具数据库</strong><span class="readonly-badge editable">受控主数据</span></div>
      <button class="command-button is-secondary" @click="goScheduling"><ArrowLeft :size="15" />返回排产</button>
      <button class="command-button is-secondary" @click="goMachines"><Server :size="15" />厂区机台库</button>
      <label class="command-field factory-field"><span>厂区</span><select :value="factoryId" @change="changeFactory(($event.target as HTMLSelectElement).value)"><option v-for="(name, id) in factoryNames" :key="id" :value="id">{{ name }}</option></select></label>
      <label class="command-search"><Search :size="16" /><input v-model="search" placeholder="搜索模具编号、名称、货号、产品…" /></label>
      <button class="command-button is-secondary" :disabled="loading" @click="loadCatalog()"><RefreshCw :size="15" :class="{ spinning: loading }" />{{ loading ? '加载中' : '刷新数据' }}</button>
      <button class="command-button auto" :disabled="!canPropose" :title="canPropose ? '发起新增模具提案' : '缺少 shared_mold:propose 权限'" @click="openProposal"><Plus :size="15" />新增模具提案</button>
      <span class="sync-time">{{ factoryNames[factoryId] }} · 公司共享 / 厂区能力分层</span>
    </section>

    <main>
      <section class="mold-kpi-strip">
        <article class="mold-kpi teal"><div><span>共享模具定义</span><strong>{{ catalog.summary.totalDefinitions.toLocaleString('zh-CN') }}</strong><p>当前公司范围内已激活</p></div><Database :size="20" /></article>
        <article class="mold-kpi blue"><div><span>{{ factoryNames[factoryId] }}厂区就绪</span><strong>{{ catalog.summary.factoryReady.toLocaleString('zh-CN') }}</strong><p>实体模具与机安能力均齐全</p></div><ShieldCheck :size="20" /></article>
        <article class="mold-kpi amber"><div><span>待补厂区资料</span><strong>{{ catalog.summary.notFactoryReady.toLocaleString('zh-CN') }}</strong><p>不影响下单表导入，排机前补齐</p></div><AlertTriangle :size="20" /></article>
        <article class="mold-kpi violet"><div><span>治理中提案</span><strong>{{ catalog.summary.pendingProposals.toLocaleString('zh-CN') }}</strong><p>待审核、待激活或处理中</p></div><Sparkles :size="20" /></article>
      </section>

      <section class="mold-catalog-workspace">
        <header class="mold-catalog-header">
          <div><span class="catalog-icon"><Boxes :size="18" /></span><div><strong>共享模具目录</strong><p>公司层定义与产品输出；机安、实体模具和价格按厂区叠加显示</p></div></div>
          <label><span>厂区就绪</span><select v-model="readiness"><option value="ALL">全部状态</option><option value="FACTORY_READY">仅厂区就绪</option><option value="NOT_FACTORY_READY">仅待补资料</option></select></label>
          <span class="catalog-count">筛选结果 {{ catalog.total.toLocaleString('zh-CN') }} 条</span>
        </header>

        <div v-if="loadError" class="catalog-error"><AlertTriangle :size="16" /><span>{{ loadError }}</span><button @click="loadCatalog()">重新加载</button></div>
        <div class="mold-table-scroll">
          <table class="mold-catalog-table">
            <thead><tr><th>工模编号 / 名称</th><th>货号 / 产品输出</th><th>安数与机型</th><th>机械臂 / 夹具</th><th>计划目标</th><th>人民币单价</th><th>实体模具</th><th>厂区状态</th><th></th></tr></thead>
            <tbody>
              <tr v-if="loading && !catalog.items.length" v-for="line in 10" :key="`loading-${line}`" class="catalog-skeleton"><td colspan="9"><span></span></td></tr>
              <tr v-for="item in catalog.items" :key="item.id" tabindex="0" @click="openDetail(item)" @keydown.enter="openDetail(item)">
                <td><strong>{{ item.displayMoldNo || item.canonicalMoldNo }}</strong><span>{{ item.standardName || '名称待补充' }}</span><small>r{{ item.revision }} · {{ dataQualityLabel(item.dataQuality) }}</small></td>
                <td><template v-if="item.outputs.length"><strong>{{ item.outputs[0]?.itemNo || '未设货号' }}</strong><span>{{ item.outputs[0]?.productName }}</span><small v-if="item.outputCount > 1">另有 {{ item.outputCount - 1 }} 个产品输出</small></template><span v-else class="muted">暂无产品输出</span></td>
                <td><strong>{{ item.factoryCapability?.machineClass || item.moldAClass || '—' }}<small v-if="item.factoryCapability?.machineClass || item.moldAClass">A</small></strong><span>{{ item.recommendedMachineClassRaw || '机型待补充' }}</span></td>
                <td><strong>{{ armLabel(item.factoryCapability?.requiredArmType || item.defaultArmType) }}</strong><span>{{ fixtureLabel(item.factoryCapability?.requiredFixtureType || item.defaultFixtureType) }}</span></td>
                <td><strong>{{ formatNumber(item.nominalDailyCapacity) }}</strong><span>啤 / 日</span></td>
                <td><strong v-if="item.price">¥ {{ formatNumber(item.price.amount, 4) }}</strong><span v-if="item.price">每啤 · 表内税制</span><span v-else class="muted">{{ catalog.summary.canReadPrices ? '价格待补充' : '无价格权限' }}</span></td>
                <td><strong>{{ item.factoryReadiness.availableAssetCount }}</strong><span>可用实体</span></td>
                <td><span class="readiness-chip" :class="item.factoryReadiness.status.toLowerCase()"><CheckCircle2 v-if="item.factoryReadiness.status === 'FACTORY_READY'" :size="13" /><AlertTriangle v-else :size="13" />{{ readinessLabel(item.factoryReadiness.status) }}</span></td>
                <td><button class="row-detail-button" @click.stop="openDetail(item)">查看详情</button></td>
              </tr>
              <tr v-if="!loading && !catalog.items.length"><td colspan="9" class="catalog-empty"><Database :size="28" /><strong>没有符合条件的共享模具</strong><span>调整搜索词或厂区就绪筛选后重试</span></td></tr>
            </tbody>
          </table>
        </div>
        <footer class="catalog-pagination"><span>显示 {{ rangeStart }}–{{ rangeEnd }} / 共 {{ catalog.total.toLocaleString('zh-CN') }} 条</span><div><button :disabled="catalog.page <= 1 || loading" @click="loadCatalog(catalog.page - 1)"><ChevronLeft :size="15" />上一页</button><strong>第 {{ catalog.page }} / {{ pageCount }} 页</strong><button :disabled="catalog.page >= pageCount || loading" @click="loadCatalog(catalog.page + 1)">下一页<ChevronRight :size="15" /></button></div></footer>
      </section>
    </main>

    <div v-if="detailOpen" class="mold-drawer-layer" @mousedown.self="detailOpen = false">
      <aside class="mold-detail-drawer" aria-label="模具数据详情">
        <header><div><span>共享模具详情</span><strong>{{ detail?.displayMoldNo || detail?.canonicalMoldNo || '读取中' }}</strong><p>{{ detail?.standardName }}</p></div><button @click="detailOpen = false"><X :size="18" /></button></header>
        <div v-if="detailLoading" class="drawer-loading"><RefreshCw :size="22" class="spinning" /><span>正在读取模具完整资料…</span></div>
        <div v-else-if="detail" class="mold-detail-body">
          <section class="detail-status"><span class="readiness-chip" :class="detail.factoryReadiness.status.toLowerCase()"><ShieldCheck :size="14" />{{ readinessLabel(detail.factoryReadiness.status) }}</span><small>公司目录已激活 · {{ dataQualityLabel(detail.dataQuality) }} · r{{ detail.revision }}</small></section>
          <section class="detail-section"><header><Info :size="15" /><strong>基础定义</strong></header><dl class="detail-grid"><div><dt>规范模号</dt><dd>{{ detail.canonicalMoldNo }}</dd></div><div><dt>显示模号</dt><dd>{{ detail.displayMoldNo || '—' }}</dd></div><div><dt>模具名称</dt><dd>{{ detail.standardName || '—' }}</dd></div><div><dt>别名</dt><dd>{{ detail.aliases.map((item) => item.rawAlias).join('、') || '—' }}</dd></div><div><dt>默认安数</dt><dd>{{ detail.moldAClass ? `${detail.moldAClass}A` : '—' }}</dd></div><div><dt>推荐机型</dt><dd>{{ detail.recommendedMachineClassRaw || '—' }}</dd></div></dl></section>
          <section class="detail-section"><header><Boxes :size="15" /><strong>产品输出（{{ detail.outputs.length }}）</strong></header><div class="detail-output-list"><article v-for="output in detail.outputs" :key="output.id"><div><strong>{{ output.itemNo || '未设货号' }}</strong><span>{{ output.productName }}</span></div><dl><div><dt>穴数</dt><dd>{{ output.cavityCount || '—' }}</dd></div><div><dt>净重</dt><dd>{{ formatNumber(output.wholeShotNetWeightG, 4) }} g</dd></div><div><dt>毛重</dt><dd>{{ formatNumber(output.wholeShotGrossWeightG, 4) }} g</dd></div><div><dt>计划目标</dt><dd>{{ formatNumber(output.nominalDailyCapacity) }} / 日</dd></div><div><dt>用料</dt><dd>{{ output.defaultMaterial || '—' }}</dd></div><div><dt>颜色</dt><dd>{{ output.defaultColor || '—' }}</dd></div></dl></article></div></section>
          <section class="detail-section"><header><Gauge :size="15" /><strong>{{ factoryNames[factoryId] }}机安与实体</strong></header><div class="detail-summary-cards"><article><span>机安能力</span><strong>{{ detail.capabilities.length }}</strong><small>{{ detail.capabilities[0]?.machineClass ? `${detail.capabilities[0].machineClass}A` : '安数待补' }} · {{ armLabel(detail.capabilities[0]?.requiredArmType || '') }} · {{ fixtureLabel(detail.capabilities[0]?.requiredFixtureType || '') }}</small></article><article><span>实体模具</span><strong>{{ detail.assets.length }}</strong><small>{{ detail.assets.length ? detail.assets.map((item) => item.assetCode).join('、') : '尚未登记可排机实体' }}</small></article></div></section>
          <section class="detail-section"><header><CircleDollarSign :size="15" /><strong>人民币单价</strong></header><div v-if="detail.priceAccess === 'RESTRICTED'" class="price-restricted"><ShieldCheck :size="15" />当前账号没有共享模具价格查看权限</div><div v-else-if="detail.prices.length" class="price-list"><article v-for="price in detail.prices" :key="price.id"><strong>¥ {{ formatNumber(price.amount, 4) }}</strong><span>{{ price.pricingBasis === 'PER_SHOT' ? '每啤 / 每模次' : price.pricingBasis }} · {{ price.taxMode }}</span></article></div><p v-else class="detail-empty">当前厂区暂无生效单价</p></section>
          <section class="detail-governance"><ShieldCheck :size="16" /><div><strong>受控主数据</strong><p>详情只展示已激活版本。新增或修订必须先提交提案，并由另一位有权限人员审核、激活。</p></div></section>
        </div>
      </aside>
    </div>

    <div v-if="proposalOpen" class="mold-drawer-layer" @mousedown.self="proposalOpen = false">
      <aside class="mold-proposal-drawer" aria-label="新增模具提案">
        <header><div><span>新增模具数据</span><strong>发起共享模具提案</strong><p>提交后不会直接写入正式库</p></div><button @click="proposalOpen = false"><X :size="18" /></button></header>
        <form class="proposal-form" @submit.prevent="submitProposal">
          <div class="proposal-notice"><ShieldCheck :size="16" /><span>公司模具定义、华兴机安能力和人民币单价会拆成独立治理提案；提案人不能审核自己的提案。</span></div>
          <fieldset><legend>1. 模具基础资料</legend><div class="proposal-grid"><label><span>工模编号 *</span><input v-model="proposal.canonicalMoldNo" required placeholder="例如 20 330 2018-001" /></label><label><span>显示编号</span><input v-model="proposal.displayMoldNo" placeholder="留空则沿用工模编号" /></label><label class="wide"><span>工模名称 *</span><input v-model="proposal.standardName" required placeholder="例如 车顶" /></label><label class="wide"><span>模具别名</span><input v-model="proposal.aliases" placeholder="多个别名用逗号分隔" /></label><label><span>默认安数</span><input v-model.number="proposal.moldAClass" type="number" min="1" placeholder="A" /></label><label><span>推荐机型原文</span><input v-model="proposal.recommendedMachineClassRaw" placeholder="例如 14A 模高" /></label><label><span>默认机械臂</span><input v-model="proposal.defaultArmType" placeholder="例如 单臂" /></label><label><span>默认夹具</span><input v-model="proposal.defaultFixtureType" placeholder="例如 吸盘" /></label></div></fieldset>
          <fieldset><legend><span>2. 产品输出</span><button type="button" @click="proposal.outputs.push(newOutput())"><Plus :size="14" />增加产品</button></legend><article v-for="(output, index) in proposal.outputs" :key="index" class="proposal-output"><header><strong>产品 {{ index + 1 }}</strong><button v-if="proposal.outputs.length > 1" type="button" @click="proposal.outputs.splice(index, 1)"><Trash2 :size="14" />移除</button></header><div class="proposal-grid"><label><span>货号</span><input v-model="output.itemNo" placeholder="计划表货号" /></label><label><span>产品名称 *</span><input v-model="output.productName" required placeholder="计划表名称" /></label><label><span>穴数</span><input v-model.number="output.cavityCount" type="number" min="1" /></label><label><span>计划目标（啤/日）</span><input v-model.number="output.nominalDailyCapacity" type="number" min="0" /></label><label><span>整啤净重（g）</span><input v-model.number="output.wholeShotNetWeightG" type="number" min="0" step="0.0001" /></label><label><span>整啤毛重（g）</span><input v-model.number="output.wholeShotGrossWeightG" type="number" min="0" step="0.0001" /></label><label><span>用料名称</span><input v-model="output.defaultMaterial" /></label><label><span>颜色</span><input v-model="output.defaultColor" /></label><label v-if="canProposePrice" class="wide price-input"><span>人民币单价（每啤）</span><input v-model.number="output.unitPriceCny" type="number" min="0" step="0.0001" placeholder="按表格单价，可留空" /><small>币种固定为人民币，口径为每啤 / 每模次，税制按原表。</small></label></div></article></fieldset>
          <fieldset v-if="canProposeCapability"><legend>3. 厂区机安能力</legend><label class="capability-toggle"><input v-model="proposal.includeCapability" type="checkbox" /><span>同时提交 {{ factoryNames[factoryId] }} 机安能力提案</span></label><div v-if="proposal.includeCapability" class="proposal-grid"><label><span>适配安数</span><input v-model.number="proposal.capabilityMachineClass" type="number" min="1" placeholder="A" /></label><label><span>机型原文</span><input v-model="proposal.capabilityMachineClassRaw" /></label><label><span>机械臂</span><input v-model="proposal.capabilityArmType" /></label><label><span>夹具</span><input v-model="proposal.capabilityFixtureType" /></label></div></fieldset>
          <fieldset><legend>{{ canProposeCapability ? '4' : '3' }}. 提案说明</legend><label class="reason-field"><span>新增依据 *</span><textarea v-model="proposal.reason" minlength="4" maxlength="500" required placeholder="说明资料来源和新增原因，至少 4 个字符"></textarea><small>{{ proposal.reason.trim().length }}/500</small></label></fieldset>
          <footer><button type="button" class="secondary" @click="proposalOpen = false">取消</button><button type="submit" class="primary" :disabled="!proposalValid || submitting"><RefreshCw v-if="submitting" :size="15" class="spinning" /><ShieldCheck v-else :size="15" />{{ submitting ? '提交中' : '提交治理提案' }}</button></footer>
        </form>
      </aside>
    </div>

    <div v-if="feedback.message" class="scheduling-feedback-toast" :class="feedback.tone"><CheckCircle2 v-if="feedback.tone === 'success'" :size="17" /><AlertTriangle v-else :size="17" /><span>{{ feedback.message }}</span><button @click="feedback.message = ''"><X :size="15" /></button></div>
  </div>
</template>
