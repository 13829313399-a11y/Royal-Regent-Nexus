<script setup lang="ts">
import { AlertTriangle, CheckCircle2, FileSpreadsheet, LoaderCircle, Upload, X } from '@lucide/vue'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'

import { injectionSchedulingApi } from '../api'
import type { ImportBatch, ImportPreviewRow } from '../types'

const props = defineProps<{
  open: boolean
  factoryId: string
  factoryName: string
}>()

const emit = defineEmits<{
  close: []
  imported: [batch: ImportBatch]
}>()

const fileInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const businessDate = ref(new Date().toISOString().slice(0, 10))
const batch = ref<ImportBatch | null>(null)
const error = ref('')
const isValidating = ref(false)
const isConfirming = ref(false)

const previewRows = computed<ImportPreviewRow[]>(() => batch.value
  ? [...batch.value.backlog_orders, ...batch.value.scheduled_baseline_tasks, ...batch.value.invalid_rows]
  : [])
const blockingIssues = computed(() => batch.value?.issues.filter(issue => issue.blocking) ?? [])
const warningIssues = computed(() => batch.value?.issues.filter(issue => !issue.blocking) ?? [])
const canConfirm = computed(() => Boolean(
  batch.value
  && batch.value.status === 'PREVIEW'
  && batch.value.summary.can_confirm
  && previewRows.value.length > 0
  && blockingIssues.value.length === 0,
))

watch(() => props.open, async (open) => {
  if (!open) return
  selectedFile.value = null
  batch.value = null
  error.value = ''
  await nextTick()
  fileInput.value?.focus()
})

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && props.open && !isValidating.value && !isConfirming.value) {
    emit('close')
  }
}

watch(() => props.open, (open) => {
  if (open) document.addEventListener('keydown', onKeydown)
  else document.removeEventListener('keydown', onKeydown)
}, { immediate: true })
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown))

function chooseFile(event: Event) {
  const input = event.target as HTMLInputElement
  selectedFile.value = input.files?.[0] ?? null
  batch.value = null
  error.value = ''
}

async function validateFile() {
  if (!selectedFile.value) {
    error.value = '请选择集团统一注塑排产模板。'
    return
  }
  isValidating.value = true
  error.value = ''
  try {
    batch.value = await injectionSchedulingApi.previewImport(
      props.factoryId,
      selectedFile.value,
      businessDate.value,
    )
  }
  catch (cause) {
    error.value = getApiErrorMessage(cause)
  }
  finally {
    isValidating.value = false
  }
}

async function confirmImport() {
  if (!batch.value || !canConfirm.value) return
  isConfirming.value = true
  error.value = ''
  try {
    const confirmed = await injectionSchedulingApi.confirmImport(batch.value, businessDate.value)
    emit('imported', confirmed)
    emit('close')
  }
  catch (cause) {
    error.value = getApiErrorMessage(cause)
  }
  finally {
    isConfirming.value = false
  }
}

function resultLabel(row: ImportPreviewRow) {
  if (row.classification === 'BACKLOG') return '进入待排池'
  if (row.classification === 'SCHEDULED_BASELINE') return '接管现有队列'
  return '阻断'
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="wb-modal-layer" role="presentation">
      <button class="wb-modal-backdrop" aria-label="关闭导入对话框" @click="emit('close')" />
      <section
        class="wb-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="standard-import-title"
      >
        <header class="wb-modal__header">
          <div>
            <p class="wb-eyebrow">RR-ISP-1.0 · {{ factoryName }}</p>
            <h2 id="standard-import-title">导入集团统一计划表</h2>
            <p>固定 Sheet、版本和 30 列表头；系统按严格字段契约校验。</p>
          </div>
          <Button variant="ghost" size="icon-sm" aria-label="关闭" :disabled="isValidating || isConfirming" @click="emit('close')">
            <X class="size-4" aria-hidden="true" />
          </Button>
        </header>

        <div class="wb-modal__body">
          <div v-if="error" class="wb-alert wb-alert--error" role="alert">
            <AlertTriangle class="size-4" aria-hidden="true" />
            <span>{{ error }}</span>
          </div>

          <div class="wb-import-controls">
            <label class="wb-file-picker">
              <FileSpreadsheet class="size-5" aria-hidden="true" />
              <span>
                <strong>{{ selectedFile?.name || '选择 .xlsx 文件' }}</strong>
                <small>只接受系统提供的集团统一模板</small>
              </span>
              <input ref="fileInput" type="file" accept=".xlsx" @change="chooseFile">
            </label>
            <label class="wb-field">
              <span>业务日期</span>
              <input v-model="businessDate" type="date">
            </label>
            <Button :disabled="!selectedFile || isValidating" @click="validateFile">
              <LoaderCircle v-if="isValidating" class="size-4 animate-spin" aria-hidden="true" />
              <Upload v-else class="size-4" aria-hidden="true" />
              {{ isValidating ? '正在校验' : '上传并校验' }}
            </Button>
          </div>

          <template v-if="batch">
            <div class="wb-import-summary" aria-label="导入预览摘要">
              <div><span>模板版本</span><strong>RR-ISP-1.0</strong></div>
              <div><span>有效行</span><strong>{{ Number(batch.summary.backlog_count || 0) + Number(batch.summary.scheduled_baseline_count || 0) }}</strong></div>
              <div><span>进入待排池</span><strong>{{ batch.summary.backlog_count || 0 }}</strong></div>
              <div><span>接管队列</span><strong>{{ batch.summary.scheduled_baseline_count || 0 }}</strong></div>
              <div><span>生产中</span><strong>{{ previewRows.filter(row => row.execution_status === 'RUNNING').length }}</strong></div>
              <div><span>阻断 / 提醒</span><strong>{{ blockingIssues.length }} / {{ warningIssues.length }}</strong></div>
            </div>

            <div v-if="blockingIssues.length" class="wb-issue-list" role="alert">
              <h3>必须先修正的内容</h3>
              <p v-for="issue in blockingIssues" :key="issue.id">
                Excel 第 {{ issue.source_row || '—' }} 行 · {{ issue.field_name || issue.cell_ref || '模板' }}：{{ issue.message }}
                <span v-if="issue.raw_value">（原值：{{ issue.raw_value }}）</span>
              </p>
            </div>

            <div class="wb-preview-table-wrap">
              <table class="wb-preview-table">
                <thead>
                  <tr>
                    <th>行号</th><th>单号</th><th>工模</th><th>产品</th><th>订单数</th><th>完成数</th><th>欠数</th><th>交期</th><th>优先级</th><th>当前机台</th><th>执行状态</th><th>结果</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in previewRows" :key="`${row.source.source_row}-${row.order_no}`">
                    <td>{{ row.source.source_row }}</td>
                    <td>{{ row.order_no || '—' }}</td>
                    <td>{{ row.mold_no || '—' }}</td>
                    <td>{{ row.product_name || '—' }}</td>
                    <td class="wb-number">{{ row.order_quantity ?? '—' }}</td>
                    <td class="wb-number">{{ row.completed_quantity ?? 0 }}</td>
                    <td class="wb-number">{{ Math.max((row.order_quantity || 0) - (row.completed_quantity || 0), 0) }}</td>
                    <td>{{ row.delivery_due_date || '—' }}</td>
                    <td>{{ row.priority_code || 'NORMAL' }}</td>
                    <td>{{ row.machine_code || '待排' }}</td>
                    <td>{{ row.execution_status || '—' }}</td>
                    <td><span class="wb-result" :data-result="row.classification">{{ resultLabel(row) }}</span></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>
        </div>

        <footer class="wb-modal__footer">
          <p v-if="batch && canConfirm" class="wb-ready"><CheckCircle2 class="size-4" aria-hidden="true" /> 校验通过，可直接确认导入。</p>
          <span v-else />
          <div class="flex gap-2">
            <Button variant="outline" :disabled="isConfirming" @click="emit('close')">取消</Button>
            <Button :disabled="!canConfirm || isConfirming" @click="confirmImport">
              <LoaderCircle v-if="isConfirming" class="size-4 animate-spin" aria-hidden="true" />
              {{ isConfirming ? '正在导入' : '确认导入' }}
            </Button>
          </div>
        </footer>
      </section>
    </div>
  </Teleport>
</template>
