<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  AlertTriangle,
  CheckCircle2,
  FileCheck2,
  FileSpreadsheet,
  LoaderCircle,
  RotateCcw,
  ShieldCheck,
  Upload,
} from '@lucide/vue'

export interface Phase2ImportIssueView {
  id: string
  severity: 'info' | 'warning' | 'error'
  sourceRow: number | null
  fieldName: string
  rawValue: string
  message: string
}

export interface Phase2ImportPreviewView {
  batchId: string
  sourceFileName: string
  sourceSha256: string
  businessDate: string
  status: string
  revision: number
  detectedSheets: string[]
  machineCount: number
  oldMachineCount: number
  newMachineCount: number
  orderCount: number
  trueUnassignedCount: number
  preassignedCount: number
  scheduledCount: number
  issueCount: number
  blockingIssueCount: number
  issues: Phase2ImportIssueView[]
}

const props = withDefaults(defineProps<{
  preview?: Phase2ImportPreviewView | null
  busy?: boolean
  error?: string
}>(), {
  preview: null,
  busy: false,
  error: '',
})

const emit = defineEmits<{
  previewFile: [file: File]
  confirmImport: [payload: {
    batchId: string
    expectedRevision: number
    businessDate: string
    reason: string
  }]
  reset: []
}>()

const selectedFile = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const businessDate = ref('')
const confirmationReason = ref('')
const showAllIssues = ref(false)

watch(() => props.preview, (preview) => {
  businessDate.value = preview?.businessDate ?? ''
  confirmationReason.value = ''
  showAllIssues.value = false
}, { immediate: true })

const visibleIssues = computed(() => (
  showAllIssues.value
    ? props.preview?.issues ?? []
    : (props.preview?.issues ?? []).slice(0, 12)
))

const canSubmitPreview = computed(() => Boolean(selectedFile.value) && !props.busy)
const canConfirm = computed(() => Boolean(
  props.preview
  && businessDate.value
  && confirmationReason.value.trim().length >= 4
  && props.preview.blockingIssueCount === 0
  && !props.busy,
))

function selectFile(event: Event) {
  selectedFile.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

function submitPreview() {
  if (selectedFile.value) emit('previewFile', selectedFile.value)
}

function confirmImport() {
  const preview = props.preview
  if (!preview || !canConfirm.value) return
  emit('confirmImport', {
    batchId: preview.batchId,
    expectedRevision: preview.revision,
    businessDate: businessDate.value,
    reason: confirmationReason.value.trim(),
  })
}

function resetImport() {
  selectedFile.value = null
  if (fileInput.value) fileInput.value.value = ''
  emit('reset')
}
</script>

<template>
  <section class="phase2-import" aria-labelledby="phase2-import-title">
    <header class="phase2-import__header">
      <div>
        <span class="phase2-import__eyebrow">Phase 2 · 两阶段导入</span>
        <h2 id="phase2-import-title">Excel 导入与确认</h2>
        <p>先生成只读预览和错误清单，确认后才合并厂区主数据并建立草稿版本。</p>
      </div>
      <span class="phase2-import__guard">
        <ShieldCheck aria-hidden="true" />
        不覆盖人工确认字段
      </span>
    </header>

    <div v-if="!preview" class="phase2-import__dropzone">
      <FileSpreadsheet aria-hidden="true" />
      <div>
        <strong>选择华兴日排版 Excel</strong>
        <p>仅接受 .xlsx；系统会校验文件哈希、工作表、公式风险和真实待排分区。</p>
      </div>
      <label>
        <span>选择文件</span>
        <input
          ref="fileInput"
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          @change="selectFile"
        >
      </label>
      <span v-if="selectedFile" class="phase2-import__file">
        <FileCheck2 aria-hidden="true" />
        {{ selectedFile.name }} · {{ (selectedFile.size / 1024 / 1024).toFixed(1) }} MB
      </span>
      <button type="button" :disabled="!canSubmitPreview" @click="submitPreview">
        <LoaderCircle v-if="busy" class="spin" aria-hidden="true" />
        <Upload v-else aria-hidden="true" />
        {{ busy ? '正在解析…' : '生成导入预览' }}
      </button>
    </div>

    <template v-else>
      <div class="phase2-import__summary">
        <article>
          <span>机台</span>
          <strong>{{ preview.machineCount }}</strong>
          <small>旧 {{ preview.oldMachineCount }} / 新 {{ preview.newMachineCount }}</small>
        </article>
        <article>
          <span>订单记录</span>
          <strong>{{ preview.orderCount }}</strong>
          <small>已带机台 {{ preview.scheduledCount + preview.preassignedCount }}</small>
        </article>
        <article class="phase2-import__summary--teal">
          <span>真正未落机</span>
          <strong>{{ preview.trueUnassignedCount }}</strong>
          <small>预分配 {{ preview.preassignedCount }} 条</small>
        </article>
        <article :class="{ 'phase2-import__summary--danger': preview.blockingIssueCount > 0 }">
          <span>资料问题</span>
          <strong>{{ preview.issueCount }}</strong>
          <small>阻断 {{ preview.blockingIssueCount }} 条</small>
        </article>
      </div>

      <section class="phase2-import__source">
        <div>
          <FileCheck2 aria-hidden="true" />
          <span>
            <strong>{{ preview.sourceFileName }}</strong>
            <small>SHA-256 {{ preview.sourceSha256.slice(0, 16) }}…</small>
          </span>
        </div>
        <div>
          <span v-for="sheet in preview.detectedSheets" :key="sheet">{{ sheet }}</span>
        </div>
      </section>

      <section class="phase2-import__issues" aria-labelledby="phase2-import-issues-title">
        <header>
          <div>
            <h3 id="phase2-import-issues-title">导入错误与风险清单</h3>
            <p>1900 相对日期只标记为“未排程”，不会进入正式计划时间。</p>
          </div>
          <button
            v-if="preview.issues.length > 12"
            type="button"
            class="phase2-import__text-button"
            @click="showAllIssues = !showAllIssues"
          >
            {{ showAllIssues ? '收起' : `查看全部 ${preview.issues.length} 条` }}
          </button>
        </header>
        <div class="phase2-import__issue-table" tabindex="0">
          <table>
            <thead>
              <tr>
                <th scope="col">级别</th>
                <th scope="col">来源行</th>
                <th scope="col">字段</th>
                <th scope="col">说明</th>
                <th scope="col">原值</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="issue in visibleIssues" :key="issue.id">
                <td>
                  <span :class="`issue-level issue-level--${issue.severity}`">
                    {{ issue.severity === 'error' ? '阻断' : issue.severity === 'warning' ? '警告' : '提示' }}
                  </span>
                </td>
                <td>{{ issue.sourceRow ?? '—' }}</td>
                <td>{{ issue.fieldName || '—' }}</td>
                <td>{{ issue.message }}</td>
                <td :title="issue.rawValue">{{ issue.rawValue || '—' }}</td>
              </tr>
              <tr v-if="visibleIssues.length === 0">
                <td colspan="5" class="phase2-import__empty">
                  <CheckCircle2 aria-hidden="true" />
                  未发现导入问题
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="phase2-import__confirm">
        <div class="phase2-import__confirm-copy">
          <CheckCircle2 aria-hidden="true" />
          <div>
            <h3>确认业务日期与合并原因</h3>
            <p>确认操作使用 revision 乐观锁；失败时不会影响上一正式批次。</p>
          </div>
        </div>
        <label>
          <span>业务日期</span>
          <input v-model="businessDate" type="date">
        </label>
        <label class="phase2-import__reason">
          <span>确认原因</span>
          <input
            v-model="confirmationReason"
            type="text"
            maxlength="200"
            placeholder="例如：已核对 2026-07-21 华兴日排版"
          >
        </label>
        <div class="phase2-import__actions">
          <button type="button" class="phase2-import__secondary" @click="resetImport">
            <RotateCcw aria-hidden="true" />
            重新选择
          </button>
          <button type="button" :disabled="!canConfirm" @click="confirmImport">
            <LoaderCircle v-if="busy" class="spin" aria-hidden="true" />
            <ShieldCheck v-else aria-hidden="true" />
            {{ busy ? '正在确认…' : '确认导入并建立草稿' }}
          </button>
        </div>
      </section>
    </template>

    <p v-if="error" class="phase2-import__error" role="alert">
      <AlertTriangle aria-hidden="true" />
      {{ error }}
    </p>
  </section>
</template>

<style scoped>
.phase2-import {
  display: grid;
  gap: 16px;
  min-height: 0;
  padding: 18px;
  color: #0f172a;
}

.phase2-import__header,
.phase2-import__source,
.phase2-import__confirm,
.phase2-import__issues > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}

.phase2-import__header h2,
.phase2-import__issues h3,
.phase2-import__confirm h3 {
  margin: 0;
  font-weight: 800;
}

.phase2-import__header h2 { font-size: 18px; }
.phase2-import__issues h3,
.phase2-import__confirm h3 { font-size: 14px; }

.phase2-import__header p,
.phase2-import__issues p,
.phase2-import__confirm p,
.phase2-import__dropzone p {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 12px;
}

.phase2-import__eyebrow {
  color: #0f766e;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.phase2-import__guard,
.phase2-import__file {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border-radius: 999px;
  background: #ecfdf5;
  padding: 7px 10px;
  color: #047857;
  font-size: 11px;
  font-weight: 700;
}

.phase2-import svg { width: 16px; height: 16px; }

.phase2-import__dropzone {
  display: grid;
  grid-template-columns: auto minmax(240px, 1fr) auto;
  align-items: center;
  gap: 14px;
  border: 1px dashed #9fb6bb;
  border-radius: 8px;
  background: #f7fbfb;
  padding: 24px;
}

.phase2-import__dropzone > svg {
  width: 34px;
  height: 34px;
  color: #0f766e;
}

.phase2-import__dropzone label span {
  display: inline-flex;
  min-height: 34px;
  align-items: center;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #fff;
  padding: 0 12px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.phase2-import__dropzone input {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}

.phase2-import button {
  display: inline-flex;
  min-height: 34px;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 1px solid #0f766e;
  border-radius: 6px;
  background: #0f766e;
  padding: 0 12px;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
}

.phase2-import button:disabled { cursor: not-allowed; opacity: 0.48; }
.phase2-import button:focus-visible,
.phase2-import input:focus-visible { outline: 3px solid rgb(20 184 166 / 28%); outline-offset: 2px; }

.phase2-import__file {
  grid-column: 2 / -1;
  justify-self: start;
  background: #eef6ff;
  color: #1d4ed8;
}

.phase2-import__summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.phase2-import__summary article {
  display: grid;
  gap: 3px;
  border: 1px solid #dce5e8;
  border-left: 3px solid #2563eb;
  border-radius: 6px;
  background: #fff;
  padding: 11px 13px;
}

.phase2-import__summary span,
.phase2-import__summary small { color: #64748b; font-size: 11px; }
.phase2-import__summary strong { font-size: 22px; }
.phase2-import__summary--teal { border-left-color: #0f766e !important; }
.phase2-import__summary--danger { border-left-color: #dc2626 !important; background: #fff7f7 !important; }

.phase2-import__source {
  border: 1px solid #dce5e8;
  border-radius: 6px;
  background: #fff;
  padding: 10px 12px;
}

.phase2-import__source > div {
  display: flex;
  align-items: center;
  gap: 9px;
}

.phase2-import__source small { display: block; margin-top: 2px; color: #64748b; font-size: 10px; }
.phase2-import__source > div:last-child span {
  border-radius: 999px;
  background: #eef7f6;
  padding: 4px 8px;
  color: #0f766e;
  font-size: 10px;
  font-weight: 700;
}

.phase2-import__issues {
  min-height: 0;
  border: 1px solid #dce5e8;
  border-radius: 6px;
  background: #fff;
}

.phase2-import__issues > header { padding: 11px 13px; border-bottom: 1px solid #e2e8f0; }
.phase2-import__text-button {
  min-height: 28px !important;
  border-color: transparent !important;
  background: transparent !important;
  color: #0f766e !important;
}

.phase2-import__issue-table { max-height: 270px; overflow: auto; }
.phase2-import table { width: 100%; border-collapse: collapse; font-size: 11px; }
.phase2-import th,
.phase2-import td { border-bottom: 1px solid #edf2f3; padding: 8px 10px; text-align: left; }
.phase2-import th { position: sticky; z-index: 1; top: 0; background: #f7fafa; color: #475569; font-weight: 800; }
.phase2-import td:nth-child(2) { width: 72px; }
.phase2-import td:last-child { max-width: 220px; overflow: hidden; color: #64748b; text-overflow: ellipsis; white-space: nowrap; }

.issue-level {
  display: inline-flex;
  border-radius: 999px;
  background: #eff6ff;
  padding: 3px 7px;
  color: #1d4ed8;
  font-weight: 800;
}
.issue-level--warning { background: #fff7ed; color: #b45309; }
.issue-level--error { background: #fff1f2; color: #be123c; }
.phase2-import__empty { padding: 24px !important; color: #047857; text-align: center !important; }

.phase2-import__confirm {
  align-items: end;
  border: 1px solid #b9d9d5;
  border-radius: 6px;
  background: #f0fdfa;
  padding: 13px;
}

.phase2-import__confirm-copy { display: flex; min-width: 220px; align-items: flex-start; gap: 9px; }
.phase2-import__confirm-copy > svg { flex: none; color: #0f766e; }
.phase2-import__confirm label { display: grid; gap: 4px; color: #475569; font-size: 10px; font-weight: 700; }
.phase2-import__confirm input {
  min-height: 34px;
  border: 1px solid #b7c9cc;
  border-radius: 6px;
  background: #fff;
  padding: 0 9px;
  color: #0f172a;
  font: inherit;
}
.phase2-import__reason { min-width: 260px; flex: 1; }
.phase2-import__actions { display: flex; gap: 8px; }
.phase2-import__secondary { border-color: #b7c9cc !important; background: #fff !important; color: #334155 !important; }

.phase2-import__error {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  border: 1px solid #fecaca;
  border-radius: 6px;
  background: #fff1f2;
  padding: 9px 11px;
  color: #b91c1c;
  font-size: 12px;
}

.spin { animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 1100px) {
  .phase2-import__summary { grid-template-columns: repeat(2, 1fr); }
  .phase2-import__confirm { align-items: stretch; flex-direction: column; }
}

@media (max-width: 720px) {
  .phase2-import__header,
  .phase2-import__source,
  .phase2-import__issues > header { align-items: flex-start; flex-direction: column; }
  .phase2-import__dropzone { grid-template-columns: 1fr; }
  .phase2-import__file { grid-column: auto; }
  .phase2-import__summary { grid-template-columns: 1fr; }
}
</style>
