<script setup lang="ts">
import { Download, FileBarChart2, LoaderCircle, RefreshCw } from '@lucide/vue'
import { computed, reactive, ref, watch } from 'vue'
import { qcInspectionApi, type QcGeneratedReport, type QcReportType } from '@/api/qcInspection'
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
]

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
  void loadGroupReports()
}, { immediate: true })
</script>

<template>
  <div class="space-y-6">
    <SectionPanel title="QC 报表中心" subtitle="第一版输出 XLSX；用户可手动生成，每周结束后由后端保留正式快照。">
      <div class="rounded-xl border border-teal-200 bg-teal-50 p-4 text-sm leading-6 text-teal-900">
        字段和版式以现有五份 Excel 为准；归档口径为“年份 / 周次 / 厂区 / 报表类型”。PDF、CSV 和定时生成不在第一版范围内。
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
            <template v-else>当前周尚未生成该报表。</template>
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
              生成正式周快照
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

    <SectionPanel title="生成历史" subtitle="只展示当前厂区和当前业务周返回的正式制品。">
      <div v-if="!reports.length" class="grid min-h-40 place-items-center rounded-xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center text-sm text-slate-500">当前周暂无报表生成记录。</div>
      <div v-else class="overflow-x-auto rounded-xl border border-slate-200">
        <table class="min-w-full text-left text-sm"><thead class="bg-slate-50 text-xs uppercase tracking-wide text-slate-500"><tr><th class="px-4 py-3">报表</th><th class="px-4 py-3">周次</th><th class="px-4 py-3">状态</th><th class="px-4 py-3">快照</th><th class="px-4 py-3 text-right">操作</th></tr></thead><tbody class="divide-y divide-slate-100 bg-white"><tr v-for="report in reports" :key="report.id"><td class="px-4 py-3 font-semibold text-slate-900">{{ report.artifact_file_name || report.report_type }}</td><td class="px-4 py-3">{{ report.week_key }}</td><td class="px-4 py-3"><StatusPill :label="report.status" :tone="report.status === 'GENERATED' ? 'green' : 'red'" compact /></td><td class="px-4 py-3">{{ report.is_formal_snapshot ? '正式周快照' : '手动生成' }}</td><td class="px-4 py-3 text-right"><button v-if="report.status === 'GENERATED'" type="button" class="font-semibold text-teal-700 hover:text-teal-900" @click="download(report)">下载</button><span v-else class="text-xs text-red-600">{{ report.error_message || '生成失败，可重新生成' }}</span></td></tr></tbody></table>
      </div>
    </SectionPanel>
  </div>
</template>
