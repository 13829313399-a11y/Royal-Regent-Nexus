<script setup lang="ts">
import axios from 'axios'
import {
  AlertTriangle,
  ArrowLeft,
  CalendarDays,
  ClipboardCheck,
  FileBarChart,
  ListChecks,
  RefreshCw,
} from '@lucide/vue'
import { computed, defineAsyncComponent, provide, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import PageHeader from '@/components/common/PageHeader.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { Button } from '@/components/ui/button'
import { qcInspectionApi, type QcWorkspace } from '@/api/qcInspection'
import { factoryContexts, productionFactoryContextIds } from '@/data/enterpriseMock'
import {
  qcInspectionWorkspaceKey,
  type QcWorkspaceState,
} from '@/features/qc-inspection/context'
import { qcInspectionPermissions } from '@/features/qc-inspection/permissions'
import { getApiErrorMessage } from '@/lib/http'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import '@/features/qc-inspection/workspace.css'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const authStore = useAuthStore()

const sectionComponents = {
  'qc-inspection-schedule': defineAsyncComponent(() => import('@/features/qc-inspection/QcScheduleWorkspace.vue')),
  'qc-inspection-schedule-details': defineAsyncComponent(() => import('@/features/qc-inspection/QcScheduleDetailsView.vue')),
  'qc-inspection-order-records': defineAsyncComponent(() => import('@/features/qc-inspection/QcScheduleDetailsView.vue')),
  'qc-inspection-order-detail': defineAsyncComponent(() => import('@/features/qc-inspection/QcInspectionOrderDetailView.vue')),
  'qc-inspection-problems': defineAsyncComponent(() => import('@/features/qc-inspection/QcProblemStatisticsView.vue')),
  'qc-inspection-reports': defineAsyncComponent(() => import('@/features/qc-inspection/QcReportCenterView.vue')),
} as const

const activeSectionComponent = computed(() => {
  const routeName = String(route.name ?? '') as keyof typeof sectionComponents
  return sectionComponents[routeName] ?? sectionComponents['qc-inspection-schedule']
})

const workspace = ref<QcWorkspace | null>(null)
const state = ref<QcWorkspaceState>('loading')
const errorMessage = ref('')

function currentIsoWeek() {
  const date = new Date()
  const utcDate = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()))
  const day = utcDate.getUTCDay() || 7
  utcDate.setUTCDate(utcDate.getUTCDate() + 4 - day)
  const yearStart = new Date(Date.UTC(utcDate.getUTCFullYear(), 0, 1))
  const week = Math.ceil((((utcDate.getTime() - yearStart.getTime()) / 86_400_000) + 1) / 7)
  return `${utcDate.getUTCFullYear()}-W${String(week).padStart(2, '0')}`
}

const factoryId = computed(() => {
  const requested = Array.isArray(route.query.factory) ? route.query.factory[0] : route.query.factory
  return typeof requested === 'string' && productionFactoryContextIds.includes(requested as never)
    ? requested
    : appStore.activeProductionFactory.id
})
const factoryName = computed(() => (
  factoryContexts.find((factory) => factory.id === factoryId.value)?.shortName
  ?? factoryId.value
))
const weekKey = computed(() => {
  const requested = Array.isArray(route.query.week) ? route.query.week[0] : route.query.week
  return typeof requested === 'string' && /^\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])$/.test(requested)
    ? requested
    : currentIsoWeek()
})

const can = (permission: string) => computed(() => authStore.can(permission, factoryId.value, 'qc'))
const canScheduleWrite = can(qcInspectionPermissions.scheduleWrite)
const canOrderWrite = can(qcInspectionPermissions.orderWrite)
const canResultWrite = can(qcInspectionPermissions.resultWrite)
const canProblemWrite = can(qcInspectionPermissions.problemWrite)
const canReportExport = can(qcInspectionPermissions.reportExport)
const canGroupSummary = can(qcInspectionPermissions.groupSummary)
const canFactorySummary = can(qcInspectionPermissions.factorySummary)
const hasAnyWriteAccess = computed(() => [
  canScheduleWrite.value,
  canOrderWrite.value,
  canResultWrite.value,
  canProblemWrite.value,
  canReportExport.value,
].some(Boolean))

let requestSequence = 0
async function refresh() {
  const sequence = ++requestSequence
  if (!workspace.value) state.value = 'loading'
  errorMessage.value = ''
  try {
    const result = await qcInspectionApi.getWorkspace(factoryId.value, weekKey.value)
    if (sequence !== requestSequence) return
    workspace.value = result
    state.value = 'ready'
  } catch (error) {
    if (sequence !== requestSequence) return
    workspace.value = null
    state.value = axios.isAxiosError(error) && error.response?.status === 403 ? 'forbidden' : 'error'
    errorMessage.value = getApiErrorMessage(error)
  }
}

async function setWeek(week: string) {
  if (!/^\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])$/.test(week)) return
  await router.replace({
    query: { ...route.query, factory: factoryId.value, week },
  })
}

provide(qcInspectionWorkspaceKey, {
  factoryId,
  factoryName,
  weekKey,
  workspace,
  state,
  errorMessage,
  canScheduleWrite,
  canOrderWrite,
  canResultWrite,
  canProblemWrite,
  canReportExport,
  canGroupSummary,
  canFactorySummary,
  refresh,
  setWeek,
})

const navigation = [
  { name: 'qc-inspection-schedule', label: '验货总排期', icon: CalendarDays },
  { name: 'qc-inspection-schedule-details', label: '排期明细', icon: ClipboardCheck },
  { name: 'qc-inspection-problems', label: '问题处理', icon: ListChecks },
  { name: 'qc-inspection-reports', label: '报表中心', icon: FileBarChart },
] as const

function navigationTarget(name: string) {
  return {
    name,
    query: { ...route.query, factory: factoryId.value, week: weekKey.value },
  }
}

watch([factoryId, weekKey], () => {
  workspace.value = null
  void refresh()
}, { immediate: true })
</script>

<template>
  <div class="min-h-screen bg-[radial-gradient(circle_at_top_left,rgba(13,148,136,0.10),transparent_34%),linear-gradient(180deg,#f8fbfc_0%,#eef5f7_100%)] px-4 py-5 text-slate-950 sm:px-6 lg:px-8">
    <main class="mx-auto w-full max-w-[1920px] space-y-6" data-yl-help="qc-inspection.overview">
      <PageHeader
        eyebrow="QC Inspection Operations"
        :title="`${factoryName} · QC 验货工作台`"
        description="从总排期安排验货，记录检验与复验结果，跟进问题并输出报表。"
      >
        <template #actions>
          <Button as-child variant="outline">
            <RouterLink :to="{ path: '/modules/qc', query: { factory: factoryId } }">
              <ArrowLeft class="size-4" aria-hidden="true" />
              返回 QC 模块中心
            </RouterLink>
          </Button>
          <label class="flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 shadow-sm">
            <CalendarDays class="size-4 text-teal-700" aria-hidden="true" />
            <span class="sr-only">业务周</span>
            <input
              :value="weekKey"
              type="week"
              class="min-w-0 border-0 bg-transparent font-semibold outline-none"
              @change="setWeek(($event.target as HTMLInputElement).value)"
            >
          </label>
          <Button type="button" variant="outline" :disabled="state === 'loading'" @click="refresh">
            <RefreshCw class="size-4" :class="{ 'animate-spin': state === 'loading' }" aria-hidden="true" />
            刷新
          </Button>
        </template>
      </PageHeader>

      <nav aria-label="QC 验货运营导航" class="flex max-w-full gap-1 overflow-x-auto rounded-xl border border-slate-200 bg-white p-1.5 shadow-sm">
        <RouterLink
          v-for="item in navigation"
          :key="item.name"
          :to="navigationTarget(item.name)"
          class="inline-flex h-10 shrink-0 items-center gap-2 rounded-lg px-4 text-sm font-semibold text-slate-600 transition hover:bg-slate-50 hover:text-slate-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
          active-class="bg-teal-700 text-white shadow-sm hover:bg-teal-700 hover:text-white"
        >
          <component :is="item.icon" class="size-4" aria-hidden="true" />
          {{ item.label }}
        </RouterLink>
      </nav>

      <div
        v-if="state === 'ready' && !hasAnyWriteAccess"
        class="flex items-start gap-3 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800"
      >
        <ClipboardCheck class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span><b>只读访问。</b> 可以查看当前厂区正式数据，但不能导入排期、维护订单、填写结果、修改问题、生成报表。</span>
      </div>

      <SectionPanel v-if="state === 'loading'" title="正在读取正式数据" subtitle="正在按厂区和业务周加载验货主单、问题、导入批次和报表。">
        <div class="grid gap-4 md:grid-cols-3" aria-label="正在加载 QC 工作区">
          <div v-for="index in 6" :key="index" class="h-24 animate-pulse rounded-xl bg-slate-100" />
        </div>
      </SectionPanel>

      <SectionPanel v-else-if="state === 'forbidden'" title="无权读取当前厂区 QC 数据" subtitle="公共入口不会扩大厂区或部门权限。">
        <div class="flex flex-col items-start gap-4 rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">
          <AlertTriangle class="size-5" aria-hidden="true" />
          <p>{{ errorMessage || '请联系管理员授予当前厂区的 QC 验货读取权限。' }}</p>
          <Button as-child variant="outline"><RouterLink :to="{ path: '/modules/qc', query: { factory: factoryId } }">返回 QC 模块中心</RouterLink></Button>
        </div>
      </SectionPanel>

      <SectionPanel v-else-if="state === 'error'" title="QC 正式数据读取失败" subtitle="页面不会用演示数据替代正式记录。">
        <div role="alert" class="flex flex-col items-start gap-4 rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-800">
          <p>{{ errorMessage }}</p>
          <Button type="button" variant="outline" @click="refresh">重新加载</Button>
        </div>
      </SectionPanel>

      <component :is="activeSectionComponent" v-else :key="`${factoryId}:${weekKey}:${String(route.name)}`" />

      <footer class="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-4 text-xs text-slate-500">
        <span>当前范围：{{ factoryName }} · {{ weekKey }}</span>
        <StatusPill label="厂区隔离" tone="teal" compact />
      </footer>
    </main>
  </div>
</template>
