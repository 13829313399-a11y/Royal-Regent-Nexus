<script setup lang="ts">
import {
  ArrowLeft,
  Building2,
  CheckCircle2,
  ClipboardCheck,
  FileSpreadsheet,
  Layers3,
  LineChart,
  Search,
  ShieldCheck,
} from '@lucide/vue'
import { computed } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import SectionPanel from '@/components/common/SectionPanel.vue'
import QuoteCenterPanel from '@/components/modules/sales/QuoteCenterPanel.vue'
import { useAppStore } from '@/stores/app'

type QuoteDeskId = 'customer-price-conversion' | 'quote-pool' | 'cost-review' | 'profit-analysis'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()

appStore.setActiveDepartment('sales-business')

const quoteDeskTabs = [
  {
    id: 'customer-price-conversion',
    label: '客价转换台',
    summary: '选择客户、导入内部报价、输出报客价 Excel',
    icon: FileSpreadsheet,
  },
  {
    id: 'quote-pool',
    label: '报价池',
    summary: '集中跟踪报价单、客户、状态和版本',
    icon: ClipboardCheck,
  },
  {
    id: 'cost-review',
    label: '核价复核',
    summary: '工程、采购、财务一起复核成本口径',
    icon: ShieldCheck,
  },
  {
    id: 'profit-analysis',
    label: '利润分析',
    summary: '按客户、项目和版本观察利润带变化',
    icon: LineChart,
  },
] satisfies Array<{
  id: QuoteDeskId
  label: string
  summary: string
  icon: typeof FileSpreadsheet
}>

const quoteDeskIds = quoteDeskTabs.map((tab) => tab.id)

const activeDeskId = computed<QuoteDeskId>(() => {
  const rawSection = route.query.section ?? route.query.desk ?? quoteDeskTabs[0].id
  const section = Array.isArray(rawSection) ? rawSection[0] : rawSection
  return quoteDeskIds.includes(section as QuoteDeskId) ? section as QuoteDeskId : quoteDeskTabs[0].id
})

const activeDesk = computed(() => quoteDeskTabs.find((tab) => tab.id === activeDeskId.value) ?? quoteDeskTabs[0])
const activeDeskIndex = computed(() => quoteDeskTabs.findIndex((tab) => tab.id === activeDeskId.value) + 1)

const pageHeadCopy = computed(() => {
  if (activeDeskId.value === 'quote-pool') {
    return {
      title: '报价池',
      subtitle: '集中跟踪客户报价单、导入来源、输出版本和处理状态。',
      pill: '报价状态',
    }
  }

  if (activeDeskId.value === 'cost-review') {
    return {
      title: '核价复核',
      subtitle: '把工程成本、采购补价、财务口径和主管复核集中在同一条线上。',
      pill: '复核流转',
    }
  }

  if (activeDeskId.value === 'profit-analysis') {
    return {
      title: '利润分析',
      subtitle: '按客户、项目、版本和利润带观察报价变化，提前发现低利润风险。',
      pill: '利润看板',
    }
  }

  return {
    title: '报价与成本中枢',
    subtitle: '业务部 · 客户报价 · 内部成本 · 报客价输出，先从客价转换台落地。',
    pill: '客价转换台',
  }
})

const overviewMetrics = [
  { label: '待转换', value: '2', detail: 'BuzzBee / Target' },
  { label: '待复核', value: '1', detail: '主管核价口径' },
  { label: '权限范围', value: '车间', detail: '本人客户可见' },
]

function selectDesk(deskId: QuoteDeskId) {
  void router.replace({
    path: '/modules/sales-business/quote-center',
    query: deskId === quoteDeskTabs[0].id ? {} : { section: deskId },
  })
}
</script>

<template>
  <div class="quote-workbench min-h-screen bg-[radial-gradient(circle_at_top_left,rgba(13,148,136,0.12),transparent_34%),linear-gradient(180deg,#f8fafc_0%,#eef4f8_100%)] text-slate-950">
    <header class="quote-topbar">
      <div class="quote-topbar-inner">
        <div class="quote-brand">
          <span class="quote-brand-mark">
            <Layers3 class="size-[18px]" aria-hidden="true" />
          </span>
          报价与成本中枢
        </div>

        <nav class="quote-step-nav" aria-label="报价与成本中心步骤">
          <button
            v-for="(desk, index) in quoteDeskTabs"
            :key="desk.id"
            type="button"
            class="quote-step-tab"
            :class="{ active: desk.id === activeDeskId }"
            @click="selectDesk(desk.id)"
          >
            <span class="step-no">{{ index + 1 }}</span>
            {{ desk.label }}
          </button>
        </nav>

        <label class="quote-global-search">
          <Search class="size-4" aria-hidden="true" />
          <input type="search" placeholder="搜索客户、报价单、版本" aria-label="搜索客户、报价单、版本">
        </label>

        <div class="quote-topbar-right">
          <span class="quote-scope">
            <Building2 class="size-4" aria-hidden="true" />
            业务部
          </span>
        </div>
      </div>
    </header>

    <main class="quote-page">
      <header class="quote-page-head">
        <div>
          <RouterLink
            to="/modules/sales-business"
            class="quote-back-link"
          >
            <ArrowLeft class="size-[15px]" aria-hidden="true" />
            业务部模块中心
          </RouterLink>
          <div class="quote-title-row">
            <h1 class="quote-page-title">{{ pageHeadCopy.title }}</h1>
            <span class="quote-pill">
              <span class="dot"></span>
              {{ activeDeskId === 'customer-price-conversion' ? pageHeadCopy.pill : `步骤 ${activeDeskIndex} / 4` }}
            </span>
            <span class="quote-pill blue">{{ activeDesk.summary }}</span>
          </div>
          <p class="quote-page-sub">{{ pageHeadCopy.subtitle }}</p>
        </div>

        <div class="quote-metrics">
          <article
            v-for="metric in overviewMetrics"
            :key="metric.label"
            class="quote-metric"
          >
            <p>{{ metric.label }}</p>
            <strong>{{ metric.value }}</strong>
            <span>{{ metric.detail }}</span>
          </article>
        </div>
      </header>

      <QuoteCenterPanel v-if="activeDeskId === 'customer-price-conversion'" />

      <SectionPanel
        v-else
        :title="activeDesk.label"
        :subtitle="activeDesk.summary"
      >
        <div class="quote-empty">
          <component :is="activeDesk.icon" class="mx-auto size-10 text-slate-400" aria-hidden="true" />
          <h2>{{ activeDesk.label }}规划中</h2>
          <p>
            这里会作为{{ activeDesk.label }}的独立工作区，后续直接补表格、筛选、审批动作和状态数据，不再经过中转页面。
          </p>
          <div class="quote-empty-flow">
            <span>
              <CheckCircle2 class="size-4" aria-hidden="true" />
              保留顶部切换
            </span>
            <span>
              <CheckCircle2 class="size-4" aria-hidden="true" />
              返回业务部模块中心
            </span>
            <span>
              <CheckCircle2 class="size-4" aria-hidden="true" />
              后续接真实数据
            </span>
          </div>
        </div>
      </SectionPanel>
    </main>
  </div>
</template>

<style scoped>
.quote-topbar {
  position: sticky;
  top: 0;
  z-index: 40;
  border-bottom: 1px solid #e2e8f0;
  background: rgba(248, 250, 252, 0.88);
  backdrop-filter: saturate(1.4) blur(8px);
}

.quote-topbar-inner {
  display: flex;
  max-width: 1680px;
  min-height: 58px;
  margin: 0 auto;
  align-items: center;
  gap: 18px;
  padding: 10px 24px;
}

.quote-brand {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 10px;
  color: #020617;
  font-weight: 800;
  white-space: nowrap;
}

.quote-brand-mark {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 10px;
  background: #0f766e;
  color: #fff;
  box-shadow: 0 6px 16px rgba(13, 118, 110, 0.35);
}

.quote-step-nav {
  display: flex;
  min-width: 0;
  flex: 1 1 auto;
  gap: 4px;
  overflow-x: auto;
  padding-bottom: 2px;
}

.quote-step-nav::-webkit-scrollbar {
  height: 4px;
}

.quote-step-nav::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: #cbd5e1;
}

.quote-step-tab {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  border-radius: 999px;
  padding: 7px 14px;
  color: #64748b;
  font-size: 13px;
  font-weight: 800;
  white-space: nowrap;
  transition: background 0.15s ease, color 0.15s ease;
}

.quote-step-tab:hover {
  background: #f1f5f9;
  color: #020617;
}

.quote-step-tab.active {
  background: #0f766e;
  color: #fff;
}

.step-no {
  display: inline-grid;
  width: 18px;
  height: 18px;
  margin-right: 6px;
  place-items: center;
  border-radius: 999px;
  background: #f1f5f9;
  color: #64748b;
  font-size: 11px;
  font-weight: 900;
}

.quote-step-tab.active .step-no {
  background: rgba(255, 255, 255, 0.22);
  color: #fff;
}

.quote-global-search {
  display: flex;
  width: min(312px, 24vw);
  min-width: 230px;
  flex: 0 1 auto;
  align-items: center;
  gap: 8px;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  background: #fff;
  padding: 6px 12px;
  color: #94a3b8;
}

.quote-global-search:focus-within {
  border-color: #0f766e;
  box-shadow: 0 0 0 3px rgba(20, 184, 166, 0.12);
}

.quote-global-search input {
  min-width: 0;
  flex: 1;
  border: 0;
  background: transparent;
  color: #0f172a;
  font-size: 13px;
  outline: none;
}

.quote-global-search input::placeholder {
  color: #94a3b8;
}

.quote-topbar-right {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
}

.quote-scope {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border: 1px solid #ccfbf1;
  border-radius: 999px;
  background: #f0fdfa;
  color: #0f766e;
  padding: 7px 12px;
  font-size: 12px;
  font-weight: 800;
}

.quote-page {
  max-width: 1680px;
  margin: 0 auto;
  padding: 24px 40px 56px;
}

.quote-page-head {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 20px;
}

.quote-back-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #475569;
  font-size: 13px;
  font-weight: 700;
}

.quote-back-link:hover {
  color: #020617;
}

.quote-title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 16px;
}

.quote-page-title {
  margin: 0;
  color: #020617;
  font-size: clamp(30px, 3.2vw, 46px);
  font-weight: 900;
  line-height: 1.06;
  letter-spacing: 0;
}

.quote-page-sub {
  max-width: 850px;
  margin: 10px 0 0;
  color: #475569;
  font-size: 14px;
  line-height: 1.8;
}

.quote-pill {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border: 1px solid #99f6e4;
  border-radius: 999px;
  background: #f0fdfa;
  color: #0f766e;
  padding: 6px 10px;
  font-size: 12px;
  font-weight: 800;
}

.quote-pill.blue {
  border-color: #bfdbfe;
  background: #eff6ff;
  color: #1d4ed8;
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: currentColor;
}

.quote-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(132px, 1fr));
  gap: 10px;
}

.quote-metric {
  min-width: 0;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.82);
  padding: 12px 14px;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
}

.quote-metric p {
  margin: 0;
  color: #64748b;
  font-size: 11px;
  font-weight: 700;
}

.quote-metric strong {
  display: block;
  margin-top: 6px;
  color: #020617;
  font-size: 24px;
  line-height: 1;
}

.quote-metric span {
  display: block;
  margin-top: 6px;
  color: #64748b;
  font-size: 11px;
  white-space: nowrap;
}

.quote-empty {
  border: 1px dashed #cbd5e1;
  border-radius: 12px;
  background: #f8fafc;
  padding: 44px 20px;
  text-align: center;
}

.quote-empty h2 {
  margin: 14px 0 0;
  color: #020617;
  font-size: 18px;
  font-weight: 800;
}

.quote-empty p {
  max-width: 620px;
  margin: 10px auto 0;
  color: #64748b;
  font-size: 14px;
  line-height: 1.7;
}

.quote-empty-flow {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
  margin-top: 22px;
}

.quote-empty-flow span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid #ccfbf1;
  border-radius: 999px;
  background: #fff;
  color: #0f766e;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 800;
}

@media (min-width: 1280px) {
  .quote-page-head {
    flex-direction: row;
    align-items: flex-end;
    justify-content: space-between;
  }
}

@media (max-width: 1180px) {
  .quote-topbar-inner {
    flex-wrap: wrap;
    align-items: flex-start;
  }

  .quote-step-nav {
    order: 3;
    flex-basis: 100%;
  }

  .quote-global-search {
    margin-left: auto;
    width: min(360px, 44vw);
  }
}

@media (max-width: 720px) {
  .quote-topbar-inner {
    gap: 10px;
    padding: 10px 16px;
  }

  .quote-global-search {
    order: 4;
    width: 100%;
    min-width: 0;
  }

  .quote-topbar-right {
    margin-left: auto;
  }

  .quote-page {
    padding: 18px 16px 40px;
  }

  .quote-metrics {
    grid-template-columns: 1fr;
  }
}
</style>
