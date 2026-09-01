<script setup lang="ts">
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  Loader2,
  Upload,
  XCircle,
} from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { injectionSchedulingApi } from '@/api/injectionScheduling'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
import type {
  InjectionScheduleImportCommitResult,
  InjectionScheduleImportPreview,
} from '@/types/injectionScheduling'

const props = defineProps<{
  factoryId: string
  profiles: string[]
  canEdit: boolean
}>()
const emit = defineEmits<{ committed: [] }>()

const file = ref<File | null>(null)
const profileOverride = ref('')
const preview = ref<InjectionScheduleImportPreview | null>(null)
const commitResult = ref<InjectionScheduleImportCommitResult | null>(null)
const busyAction = ref<'template' | 'preview' | 'commit' | 'reject' | ''>('')
const errorMessage = ref('')

const profileNames: Record<string, string> = {
  UNIFIED_PLAN_V2: '统一计划表 V2.0',
  WAREHOUSE_ORDER_FLAT_V1: '仓库扁平下单表',
  PRODUCTION_ORDER_FORM_V1: '啤机部生产啤货表',
  HK_B_PLAN_V1: '河源华康 B 计划表',
  HUA_XING_PLAN_V1: '河源华兴计划表',
}
const canCommit = computed(() => (
  props.canEdit
  && preview.value?.status === 'READY'
  && preview.value.summary.blocking_issue_count === 0
  && !busyAction.value
))
const visibleRows = computed(() => preview.value?.rows.slice(0, 30) ?? [])
const visibleIssues = computed(() => preview.value?.issues.slice(0, 50) ?? [])

function resetResult() {
  preview.value = null
  commitResult.value = null
  errorMessage.value = ''
}

function selectFile(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
  resetResult()
}

async function downloadTemplate() {
  busyAction.value = 'template'
  errorMessage.value = ''
  try {
    const blob = await injectionSchedulingApi.downloadUnifiedTemplate(props.factoryId)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = '统一注塑排产计划表模板_V2.0.xlsx'
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    busyAction.value = ''
  }
}

async function createPreview() {
  if (!file.value) {
    errorMessage.value = '请先选择 .xlsx 或 .xlsm 文件。'
    return
  }
  busyAction.value = 'preview'
  resetResult()
  try {
    preview.value = await injectionSchedulingApi.previewImport(
      props.factoryId,
      file.value,
      createRandomUuid(),
      profileOverride.value,
    )
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    busyAction.value = ''
  }
}

async function commitPreview() {
  if (!preview.value || !canCommit.value) return
  busyAction.value = 'commit'
  errorMessage.value = ''
  try {
    commitResult.value = await injectionSchedulingApi.commitImport(
      props.factoryId,
      preview.value.batch_id,
      createRandomUuid(),
    )
    preview.value.status = 'CONFIRMED'
    emit('committed')
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    busyAction.value = ''
  }
}

async function rejectPreview() {
  if (!preview.value || preview.value.status === 'CONFIRMED') return
  busyAction.value = 'reject'
  errorMessage.value = ''
  try {
    preview.value = await injectionSchedulingApi.rejectImport(
      props.factoryId,
      preview.value.batch_id,
      '用户在导入预览中取消',
    )
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    busyAction.value = ''
  }
}

function formatBytes(value: number) {
  return value >= 1024 * 1024
    ? `${(value / 1024 / 1024).toFixed(1)} MB`
    : `${Math.ceil(value / 1024)} KB`
}

watch(() => props.factoryId, () => {
  file.value = null
  profileOverride.value = ''
  resetResult()
})
</script>

<template>
  <section class="rounded-xl border border-slate-200/80 bg-white/90 p-4 shadow-sm">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 class="flex items-center gap-2 font-bold text-slate-900">
          <FileSpreadsheet class="size-5 text-teal-700" aria-hidden="true" />
          Excel 确定性导入
        </h2>
        <p class="mt-1 text-xs text-slate-500">先生成只读预览并校验；存在阻塞错误时不能写入订单。</p>
      </div>
      <div class="flex flex-wrap items-center justify-end gap-2">
        <Button variant="outline" :disabled="Boolean(busyAction)" @click="downloadTemplate">
          <Loader2 v-if="busyAction === 'template'" class="animate-spin" aria-hidden="true" />
          <Download v-else aria-hidden="true" />
          下载统一计划表模板
        </Button>
        <span class="rounded-full px-2.5 py-1 text-xs font-semibold" :class="canEdit ? 'bg-teal-50 text-teal-700' : 'bg-slate-100 text-slate-500'">
          {{ canEdit ? '可导入' : '只读权限' }}
        </span>
      </div>
    </div>

    <p class="mt-3 rounded-lg border border-teal-100 bg-teal-50/70 px-3 py-2 text-xs text-teal-800">
      华兴、华登、华康A、华康B共用同一份计划表格式；机台与模具主数据由系统数据库提供，上传数据按当前厂区隔离。
    </p>

    <div class="mt-4 grid gap-2 lg:grid-cols-[minmax(260px,1fr)_240px_auto]">
      <label class="flex h-10 cursor-pointer items-center gap-2 rounded-lg border border-dashed border-slate-300 bg-slate-50 px-3 text-sm hover:border-teal-500">
        <Upload class="size-4 text-slate-500" aria-hidden="true" />
        <span class="min-w-0 truncate">{{ file?.name ?? '选择 .xlsx / .xlsm 文件' }}</span>
        <input class="sr-only" type="file" accept=".xlsx,.xlsm" :disabled="!canEdit || Boolean(busyAction)" @change="selectFile">
      </label>
      <select v-model="profileOverride" class="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm" :disabled="!canEdit || Boolean(busyAction)">
        <option value="">自动识别模板</option>
        <option v-for="profile in profiles" :key="profile" :value="profile">{{ profileNames[profile] ?? profile }}</option>
      </select>
      <Button :disabled="!canEdit || !file || Boolean(busyAction)" @click="createPreview">
        <Loader2 v-if="busyAction === 'preview'" class="animate-spin" aria-hidden="true" />
        <Upload v-else aria-hidden="true" />
        生成预览
      </Button>
    </div>

    <p v-if="errorMessage" class="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{{ errorMessage }}</p>
    <p v-if="commitResult" class="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
      已确认导入：新增 {{ commitResult.created_count }}，更新 {{ commitResult.updated_count }}，未变化 {{ commitResult.skipped_count }}。
    </p>

    <div v-if="preview" class="mt-4 space-y-4">
      <div class="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
        <div class="rounded-lg bg-slate-50 p-3"><p class="text-xs text-slate-500">文件</p><p class="mt-1 truncate text-sm font-semibold">{{ preview.source_file_name }}</p><p class="text-xs text-slate-400">{{ formatBytes(preview.source_size_bytes) }}</p></div>
        <div class="rounded-lg bg-slate-50 p-3"><p class="text-xs text-slate-500">识别模板</p><p class="mt-1 text-sm font-semibold">{{ profileNames[preview.profile_code] ?? preview.profile_code }}</p></div>
        <div class="rounded-lg bg-slate-50 p-3"><p class="text-xs text-slate-500">新增 / 更新 / 重复</p><p class="mt-1 text-sm font-semibold">{{ preview.summary.create_count ?? preview.summary.row_count }} / {{ preview.summary.update_count ?? 0 }} / {{ preview.summary.unchanged_count ?? 0 }}</p><p class="text-xs text-slate-400">机台 {{ preview.summary.machine_count }} · 白夜班记录 {{ preview.summary.history_output_count }}</p></div>
        <div class="rounded-lg bg-amber-50 p-3"><p class="text-xs text-amber-700">警告</p><p class="mt-1 text-sm font-bold text-amber-800">{{ preview.summary.warning_count }}</p></div>
        <div class="rounded-lg p-3" :class="preview.summary.blocking_issue_count ? 'bg-red-50' : 'bg-emerald-50'"><p class="text-xs" :class="preview.summary.blocking_issue_count ? 'text-red-700' : 'text-emerald-700'">阻塞错误</p><p class="mt-1 text-sm font-bold" :class="preview.summary.blocking_issue_count ? 'text-red-800' : 'text-emerald-800'">{{ preview.summary.blocking_issue_count }}</p></div>
      </div>

      <div v-if="visibleIssues.length" class="overflow-hidden rounded-lg border border-slate-200">
        <div class="flex items-center gap-2 border-b border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold"><AlertTriangle class="size-4 text-amber-600" aria-hidden="true" />校验问题（显示前 {{ visibleIssues.length }} 条）</div>
        <div class="max-h-48 overflow-auto divide-y divide-slate-100">
          <div v-for="(issue, index) in visibleIssues" :key="`${issue.source_row}-${issue.field_name}-${index}`" class="grid gap-1 px-3 py-2 text-xs sm:grid-cols-[80px_130px_80px_1fr]">
            <span>第 {{ issue.source_row ?? '-' }} 行</span><span class="font-mono text-slate-500">{{ issue.field_name }}</span><span :class="issue.blocking ? 'font-semibold text-red-700' : 'text-amber-700'">{{ issue.blocking ? '阻塞' : '警告' }}</span><span>{{ issue.message }}</span>
          </div>
        </div>
      </div>

      <div class="overflow-auto rounded-lg border border-slate-200">
        <table class="min-w-[1000px] w-full text-left text-xs">
          <thead class="bg-slate-50 text-slate-600"><tr><th class="px-3 py-2">来源行</th><th class="px-3 py-2">机号</th><th class="px-3 py-2">单号</th><th class="px-3 py-2">货号</th><th class="px-3 py-2">工模</th><th class="px-3 py-2">名称</th><th class="px-3 py-2">啤数</th><th class="px-3 py-2">交货期</th><th class="px-3 py-2">完整性</th></tr></thead>
          <tbody class="divide-y divide-slate-100"><tr v-for="row in visibleRows" :key="`${row.business_key}-${row.source_row}`"><td class="px-3 py-2">{{ row.source_row }}</td><td class="px-3 py-2">{{ row.machine_code || '-' }}</td><td class="px-3 py-2 font-medium">{{ row.order_no }}</td><td class="px-3 py-2">{{ row.product_code }}</td><td class="px-3 py-2">{{ row.mold_code }}</td><td class="max-w-60 truncate px-3 py-2">{{ row.product_name }}</td><td class="px-3 py-2">{{ row.order_shots }}</td><td class="px-3 py-2">{{ row.delivery_due_date || '-' }}</td><td class="px-3 py-2"><span :class="row.data_completeness_status === 'COMPLETE' ? 'text-emerald-700' : 'font-semibold text-red-700'">{{ row.data_completeness_status === 'COMPLETE' ? '完整' : '待修正' }}</span></td></tr></tbody>
        </table>
        <p v-if="preview.rows.length > visibleRows.length" class="border-t border-slate-200 bg-slate-50 px-3 py-2 text-center text-xs text-slate-500">预览仅显示前 {{ visibleRows.length }} 条，共 {{ preview.rows.length }} 条。</p>
      </div>

      <div class="flex flex-wrap items-center justify-end gap-2">
        <p v-if="preview.summary.blocking_issue_count" class="mr-auto text-xs font-medium text-red-700">请先修正 {{ preview.summary.blocking_issue_count }} 个阻塞错误并重新上传。</p>
        <Button variant="outline" :disabled="Boolean(busyAction) || preview.status === 'CONFIRMED' || preview.status === 'REJECTED'" @click="rejectPreview"><XCircle aria-hidden="true" />取消本批次</Button>
        <Button :disabled="!canCommit" @click="commitPreview"><Loader2 v-if="busyAction === 'commit'" class="animate-spin" aria-hidden="true" /><CheckCircle2 v-else aria-hidden="true" />确认写入订单</Button>
      </div>
    </div>
  </section>
</template>
