<script setup lang="ts">
import { Download, FileBarChart2, Layers3, LoaderCircle, RefreshCw } from '@lucide/vue'
import { computed, reactive, ref, watch } from 'vue'
import { qcInspectionApi, type QcGeneratedReport, type QcReportPeriodMode, type QcReportType } from '@/api/qcInspection'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { useQcInspectionWorkspace } from './context'

const context = useQcInspectionWorkspace()
const actionError = ref('')
const actionMessage = ref('')
const generating = reactive<Record<string, boolean>>({})
const downloading = reactive<Record<string, boolean>>({})
const groupReports = ref<QcGeneratedReport[]>([])
const periodMode = ref<QcReportPeriodMode>('WEEK')
const periodKey = ref(context.weekKey.value)
const batchGenerating = ref(false)

const reportDefinitions: Array<{
  type: QcReportType
  title: string
  description: string
  scope: string
}> = [
  { type: 'CUSTOMER_SUMMARY', title: '文件1：客户验货汇总', description: '按客户分 Sheet，字段和版式沿用现有 Excel。', scope: '本厂' },
  { type: 'WEEKLY_STATISTICS', title: '文件2：每周统计', description: '按业务周汇总验货次数、结果和问题。', scope: '本厂' },
  { type: 'HUAXING_CUSTOMER_WEEKLY_DETAIL', title: '文件3：华兴客户每周明细', description: '保留华兴各客户的交易级验货明细。', scope: '华兴' },
  { type: 'HUAXING_WEEKLY_AGGREGATE', title: '文件4：华兴每周聚合', description: '按客户或企业维度聚合华兴验货数据。', scope: '华兴' },
  { type: 'GROUP_SUMMARY', title: '文件5：集团验货汇总', description: '跨厂汇总验货次数、退货率等集团指标。', scope: '集团授权' },
  { type: 'WEEKLY_INSPECTION_SCHEDULE', title: '验货排期表', description: '按周期输出计划验货日期、客户、合同、PO、货号、数量和当前进度。', scope: '本厂' },
  { type: 'DAILY_INSPECTION_LEDGER', title: '验货台账', description: '按每次实际验货输出抽样、AQL 缺陷数、结果与报告号。', scope: '本厂' },
  { type: 'WEEKLY_PROBLEM_DETAIL', title: '验货问题明细', description: '输出问题、退货原因、纠正措施、责任人和闭环状态。', scope: '本厂' },
  { type: 'WEEKLY_RETURN_SUMMARY', title: '退货汇总', description: '只统计明确登记 RETURN 处置的订单，不把普通 FAIL 误算为退货。', scope: '本厂' },
  { type: 'INSPECTION_PASS_RATE', title: '验货合格率', description: '按客户统计已结论次数、通过次数、退货次数和合格率。', scope: '本厂' },
  { type: 'ANNUAL_INSPECTION_STATISTICS', title: '年度验货统计', description: '按月输出全年验货次数、通过率、退货次数和缺陷数量。', scope: '本厂' },
  { type: 'PRODUCT_QUALITY_LEDGER', title: '产品质量验货台账', description: '按 PO、Release、货号、批次和 Date Code 输出产品质量履历。', scope: '本厂' },
  { type: 'INSPECTION_DOCUMENT_INDEX', title: '验货报告文件索引', description: '输出报告包、外部报告号、文档版本、文件类型和 SHA256。', scope: '本厂' },
]

const commonReportTypes: QcReportType[] = [
  'WEEKLY_INSPECTION_SCHEDULE', 'DAILY_INSPECTION_LEDGER', 'WEEKLY_PROBLEM_DETAIL',
  'WEEKLY_RETURN_SUMMARY', 'INSPECTION_PASS_RATE', 'PRODUCT_QUALITY_LEDGER',
  'INSPECTION_DOCUMENT_INDEX', 'ANNUAL_INSPECTION_STATISTICS',
]

function monthForWeek(weekKey: string) {
  const [yearText, weekText] = weekKey.split('-W')
  const year = Number(yearText)
  const week = Number(weekText)
  const januaryFourth = new Date(Date.UTC(year, 0, 4))
  const monday = new Date(januaryFourth)
  monday.setUTCDate(januaryFourth.getUTCDate() - ((januaryFourth.getUTCDay() + 6) % 7) + (week - 1) * 7)
  return `${monday.getUTCFullYear()}-${String(monday.getUTCMonth() + 1).padStart(2, '0')}`
}

const reports = computed(() => {
  const merged = [...(context.workspace.value?.reports ?? []), ...groupReports.value]
  return [...new Map(merged.map((report) => [report.id, report])).values()]
})
const reportByType = computed(() => Object.fromEntries(
  reportDefinitions.map(({ type }) => [type, reports.value.find((report) => report.report_type === type)]),
) as Partial<Record<QcReportType, QcGeneratedReport>>)

function disabledReason(type: QcReportType) {
  if (type === 'GROUP_SUMMARY') return context.canGroupSummary.value ? '' : '集团汇总需要单独的跨厂授权'
  if (!context.canReportExport.value) return '当前账号没有本厂报表生成权限'
  if (type.startsWith('HUAXING_') && context.factoryId.value !== 'huaxing') return '该报表只适用于华兴厂区'
  return ''
}

function canCreateFormalSnapshot(type: QcReportType) {
  return type === 'GROUP_SUMMARY' ? context.canGroupSummary.value : context.canFactorySummary.value
}

async function loadGroupReports() {
  if (!context.canGroupSummary.value) return
  try {
    groupReports.value = await qcInspectionApi.listReports('*', context.weekKey.value)
  } catch {
    groupReports.value = []
  }
}

async function generate(type: QcReportType, isFormalSnapshot = false) {
  if (disabledReason(type)) return
  generating[type] = true
  actionError.value = ''
  actionMessage.value = ''
  try {
    const report = await qcInspectionApi.generateReport({
      factory_id: type === 'GROUP_SUMMARY' ? '*' : context.factoryId.value,
      week_key: context.weekKey.value,
      report_type: type,
      is_formal_snapshot: isFormalSnapshot,
      period_mode: type === 'ANNUAL_INSPECTION_STATISTICS' ? 'YEAR' : periodMode.value,
      period_key: type === 'ANNUAL_INSPECTION_STATISTICS' ? context.weekKey.value.slice(0, 4) : periodKey.value,
    })
    actionMessage.value = `${report.artifact_file_name || report.report_type} 已生成。`
    if (type === 'GROUP_SUMMARY') {
      groupReports.value = [report, ...groupReports.value.filter((current) => current.id !== report.id)]
    } else {
      await context.refresh()
    }
  } catch (error) {
    actionError.value = getApiErrorMessage(error)
  } finally {
    generating[type] = false
  }
}

async function generateCommonReports() {
  if (!context.canReportExport.value || batchGenerating.value) return
  batchGenerating.value = true
  actionError.value = ''
  actionMessage.value = ''
  try {
    for (const type of commonReportTypes) {
      generating[type] = true
      await qcInspectionApi.generateReport({
        factory_id: context.factoryId.value,
        week_key: context.weekKey.value,
        report_type: type,
        period_mode: type === 'ANNUAL_INSPECTION_STATISTICS' ? 'YEAR' : periodMode.value,
        period_key: type === 'ANNUAL_INSPECTION_STATISTICS' ? context.weekKey.value.slice(0, 4) : periodKey.value,
      })
      generating[type] = false
    }
    await context.refresh()
    actionMessage.value = `已生成 ${commonReportTypes.length} 份常用业务报表。`
  } catch (error) {
    actionError.value = getApiErrorMessage(error)
  } finally {
    commonReportTypes.forEach((type) => { generating[type] = false })
    batchGenerating.value = false
  }
}

function saveBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  anchor.click()
  URL.revokeObjectURL(url)
}

async function download(report: QcGeneratedReport) {
  downloading[report.id] = true
  actionError.value = ''
  try {
    const result = await qcInspectionApi.downloadReport(
      report.id,
      report.artifact_file_name || `${report.report_type}-${report.week_key}.xlsx`,
      report.report_type === 'GROUP_SUMMARY' ? '*' : report.factory_id,
    )
    saveBlob(result.blob, result.fileName)
  } catch (error) {
    actionError.value = getApiErrorMessage(error)
  } finally {
    downloading[report.id] = false
  }
}

watch([context.weekKey, context.canGroupSummary], () => {
  if (periodMode.value === 'WEEK') periodKey.value = context.weekKey.value
  void loadGroupReports()
}, { immediate: true })

watch(periodMode, (mode) => {
  if (mode === 'WEEK') periodKey.value = context.weekKey.value
  else if (mode === 'MONTH') periodKey.value = monthForWeek(context.weekKey.value)
  else if (mode === 'YEAR') periodKey.value = context.weekKey.value.slice(0, 4)
})
</script>

<template>
  <div class="space-y-6">
    <SectionPanel title="QC 报表中心" subtitle="从同一套验货主单、验货记录、问题、处置和报告包数据，一键输出业务所需 XLSX。">
      <div class="rounded-xl border border-teal-200 bg-teal-50 p-4 text-sm leading-6 text-teal-900">
        保留原有五份 Excel，并新增排期、验货台账、问题、退货、合格率、年度、产品质量及文件索引。退货统计只认明确的 RETURN 处置。
      </div>
      <div class="mt-4 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4">
        <label class="space-y-1"><span class="block text-xs font-semibold text-slate-600">统计周期</span><select v-model="periodMode" class="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm"><option value="WEEK">周</option><option value="MONTH">月</option><option value="YEAR">年</option></select></label>
        <label class="min-w-44 flex-1 space-y-1"><span class="block text-xs font-semibold text-slate-600">周期值</span><input v-model="periodKey" class="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm" :placeholder="periodMode === 'WEEK' ? '2026-W34' : periodMode === 'MONTH' ? '2026-08' : '2026'"></label>
        <Button type="button" :disabled="!context.canReportExport.value || batchGenerating" @click="generateCommonReports"><LoaderCircle v-if="batchGenerating" class="size-4 animate-spin" /><Layers3 v-else class="size-4" />一键生成 8 份常用报表</Button>
      </div>
      <p v-if="actionError" role="alert" class="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{{ actionError }}</p>
      <p v-if="actionMessage" class="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{{ actionMessage }}</p>

      <div class="mt-5 grid gap-4 lg:grid-cols-2">
        <article v-for="definition in reportDefinitions" :key="definition.type" class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div class="flex items-start justify-between gap-3">
            <span class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-teal-50 text-teal-700"><FileBarChart2 class="size-5" aria-hidden="true" /></span>
            <StatusPill :label="definition.scope" :tone="definition.scope === '集团授权' ? 'amber' : 'teal'" compact />
          </div>
          <h3 class="mt-4 font-semibold text-slate-950">{{ definition.title }}</h3>
          <p class="mt-2 min-h-10 text-sm leading-6 text-slate-600">{{ definition.description }}</p>

          <div class="mt-4 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
            <template v-if="reportByType[definition.type]">
              <b>{{ reportByType[definition.type]?.artifact_file_name || '文件已生成' }}</b>
              <span class="mt-1 block">状态：{{ reportByType[definition.type]?.status }} · {{ reportByType[definition.type]?.created_at }}</span>
            </template>
            <template v-else>当前筛选下尚未生成该报表。</template>
          </div>

          <p v-if="disabledReason(definition.type)" class="mt-3 text-xs leading-5 text-amber-700">{{ disabledReason(definition.type) }}</p>
          <div class="mt-4 flex flex-wrap gap-2">
            <Button type="button" :disabled="Boolean(disabledReason(definition.type)) || generating[definition.type]" @click="generate(definition.type, false)">
              <LoaderCircle v-if="generating[definition.type]" class="size-4 animate-spin" aria-hidden="true" />
              <RefreshCw v-else class="size-4" aria-hidden="true" />
              {{ reportByType[definition.type] ? '重新生成' : '生成 XLSX' }}
            </Button>
            <Button
              v-if="canCreateFormalSnapshot(definition.type)"
              type="button"
              variant="outline"
              :disabled="Boolean(disabledReason(definition.type)) || generating[definition.type]"
              @click="generate(definition.type, true)"
            >
              生成正式快照
            </Button>
            <Button
              v-if="reportByType[definition.type]?.status === 'GENERATED'"
              type="button"
              variant="outline"
              :disabled="downloading[reportByType[definition.type]!.id]"
              @click="download(reportByType[definition.type]!)"
            >
              <Download class="size-4" aria-hidden="true" />下载
            </Button>
          </div>
        </article>
      </div>
    </SectionPanel>

    <SectionPanel title="生成历史" subtitle="展示当前厂区及页面业务周关联的生成制品。">
      <div v-if="!reports.length" class="grid min-h-40 place-items-center rounded-xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center text-sm text-slate-500">当前周暂无报表生成记录。</div>
      <div v-else class="overflow-x-auto rounded-xl border border-slate-200">
        <table class="min-w-full text-left text-sm"><thead class="bg-slate-50 text-xs uppercase tracking-wide text-slate-500"><tr><th class="px-4 py-3">报表</th><th class="px-4 py-3">周期</th><th class="px-4 py-3">状态</th><th class="px-4 py-3">快照</th><th class="px-4 py-3 text-right">操作</th></tr></thead><tbody class="divide-y divide-slate-100 bg-white"><tr v-for="report in reports" :key="report.id"><td class="px-4 py-3 font-semibold text-slate-900">{{ report.artifact_file_name || report.report_type }}</td><td class="px-4 py-3">{{ report.period_mode || 'WEEK' }} · {{ report.period_key || report.week_key }}</td><td class="px-4 py-3"><StatusPill :label="report.status" :tone="report.status === 'GENERATED' ? 'green' : 'red'" compact /></td><td class="px-4 py-3">{{ report.is_formal_snapshot ? '正式快照' : '手动生成' }}</td><td class="px-4 py-3 text-right"><button v-if="report.status === 'GENERATED'" type="button" class="font-semibold text-teal-700 hover:text-teal-900" @click="download(report)">下载</button><span v-else class="text-xs text-red-600">{{ report.error_message || '生成失败，可重新生成' }}</span></td></tr></tbody></table>
      </div>
    </SectionPanel>
  </div>
</template>
