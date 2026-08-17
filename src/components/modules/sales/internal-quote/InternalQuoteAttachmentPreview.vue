<script setup lang="ts">
import { AlertCircle, Download, FileSpreadsheet, X } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { internalQuoteApi } from '@/api/internalQuote'
import { parseXlsxWorkbook, type XlsxCellValue } from '@/lib/customerPriceConverters/xlsxLite'
import type { InternalQuoteAttachmentRecord } from '@/types/internalQuoteDesk'

const props = defineProps<{
  quoteId: string
  attachment?: InternalQuoteAttachmentRecord
}>()
const emit = defineEmits<{
  close: []
  download: [attachment: InternalQuoteAttachmentRecord]
}>()

const MAX_ROWS = 200
const MAX_COLUMNS = 40

type PreviewSheet = {
  name: string
  rows: XlsxCellValue[][]
  totalRows: number
  totalColumns: number
}

const loading = ref(false)
const errorMessage = ref('')
const sheets = ref<PreviewSheet[]>([])
const activeSheetIndex = ref(0)
let loadVersion = 0

function cellHasValue(value: XlsxCellValue) {
  return value !== null && value !== undefined && String(value).trim() !== ''
}

function prepareSheet(name: string, sourceRows: XlsxCellValue[][]): PreviewSheet {
  let lastRow = -1
  let totalColumns = 0
  sourceRows.forEach((row, rowIndex) => {
    let lastColumn = -1
    row.forEach((cell, columnIndex) => {
      if (cellHasValue(cell)) lastColumn = columnIndex
    })
    if (lastColumn >= 0) {
      lastRow = rowIndex
      totalColumns = Math.max(totalColumns, lastColumn + 1)
    }
  })
  const totalRows = lastRow + 1
  return {
    name,
    totalRows,
    totalColumns,
    rows: sourceRows
      .slice(0, Math.min(totalRows, MAX_ROWS))
      .map((row) => row.slice(0, MAX_COLUMNS)),
  }
}

function errorText(error: unknown) {
  if (error instanceof Error && error.message) return error.message
  return '附件预览加载失败，请下载原文件查看。'
}

watch(() => props.attachment?.id, async (attachmentId) => {
  const version = ++loadVersion
  sheets.value = []
  activeSheetIndex.value = 0
  errorMessage.value = ''
  if (!attachmentId) return
  loading.value = true
  try {
    const blob = await internalQuoteApi.previewAttachment(props.quoteId, attachmentId)
    const workbook = parseXlsxWorkbook(await blob.arrayBuffer())
    if (version !== loadVersion) return
    sheets.value = workbook.sheets.map((sheet) => prepareSheet(sheet.name, sheet.rows))
    if (!sheets.value.length) errorMessage.value = '该 Excel 没有可显示的工作表。'
  } catch (error) {
    if (version === loadVersion) errorMessage.value = errorText(error)
  } finally {
    if (version === loadVersion) loading.value = false
  }
}, { immediate: true })

const activeSheet = computed(() => sheets.value[activeSheetIndex.value])
const visibleColumnCount = computed(() => Math.min(activeSheet.value?.totalColumns ?? 0, MAX_COLUMNS))
const columnIndexes = computed(() => Array.from({ length: visibleColumnCount.value }, (_, index) => index))
const isTruncated = computed(() => (
  Boolean(activeSheet.value)
  && ((activeSheet.value?.totalRows ?? 0) > MAX_ROWS || (activeSheet.value?.totalColumns ?? 0) > MAX_COLUMNS)
))

function columnLabel(index: number) {
  let value = index + 1
  let label = ''
  while (value > 0) {
    value -= 1
    label = String.fromCharCode(65 + (value % 26)) + label
    value = Math.floor(value / 26)
  }
  return label
}

function displayCell(value: XlsxCellValue) {
  if (value === null || value === undefined) return ''
  if (typeof value === 'boolean') return value ? 'TRUE' : 'FALSE'
  return String(value)
}
</script>

<template>
  <Teleport to="body">
    <div v-if="attachment" class="workbook-preview-backdrop" @click.self="emit('close')">
      <section class="workbook-preview-dialog" role="dialog" aria-modal="true" aria-labelledby="workbook-preview-title">
        <header>
          <div class="workbook-preview-heading">
            <span class="workbook-preview-icon"><FileSpreadsheet /></span>
            <div>
              <h3 id="workbook-preview-title">预览附件</h3>
              <p>{{ attachment.fileName }} · {{ Math.max(1, Math.ceil(attachment.sizeBytes / 1024)) }} KB</p>
            </div>
          </div>
          <button type="button" class="workbook-preview-close" aria-label="关闭附件预览" @click="emit('close')"><X /></button>
        </header>

        <div v-if="loading" class="workbook-preview-state"><FileSpreadsheet /><strong>正在读取 Excel 工作表…</strong><span>原文件保持不变，预览仅用于核对导入来源。</span></div>
        <div v-else-if="errorMessage" class="workbook-preview-state error"><AlertCircle /><strong>无法显示附件</strong><span>{{ errorMessage }}</span></div>
        <template v-else-if="activeSheet">
          <nav class="workbook-sheet-tabs" aria-label="Excel 工作表">
            <button v-for="(sheet,index) in sheets" :key="`${sheet.name}-${index}`" type="button" :class="{ active: activeSheetIndex === index }" @click="activeSheetIndex = index">{{ sheet.name }}</button>
          </nav>
          <div class="workbook-preview-meta">
            <span>{{ activeSheet.totalRows }} 行 × {{ activeSheet.totalColumns }} 列</span>
            <strong v-if="isTruncated">当前仅显示前 {{ MAX_ROWS }} 行、{{ MAX_COLUMNS }} 列，完整内容请下载原文件。</strong>
            <span v-else>已显示该工作表全部有效区域</span>
          </div>
          <div v-if="activeSheet.totalRows && activeSheet.totalColumns" class="workbook-preview-table-wrap">
            <table>
              <thead><tr><th class="row-number-corner" /><th v-for="columnIndex in columnIndexes" :key="columnIndex">{{ columnLabel(columnIndex) }}</th></tr></thead>
              <tbody>
                <tr v-for="(row,rowIndex) in activeSheet.rows" :key="rowIndex">
                  <th>{{ rowIndex + 1 }}</th>
                  <td v-for="columnIndex in columnIndexes" :key="columnIndex" :title="displayCell(row[columnIndex])">{{ displayCell(row[columnIndex]) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="workbook-preview-state compact"><strong>该工作表为空</strong><span>可切换其他工作表，或下载原文件核对格式。</span></div>
        </template>

        <footer>
          <span>只读预览，不会改动当前报价或附件内容。</span>
          <button type="button" class="secondary" @click="emit('download', attachment)"><Download />下载原文件</button>
          <button type="button" class="primary" @click="emit('close')">关闭</button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.workbook-preview-backdrop{position:fixed;inset:0;z-index:1100;display:grid;place-items:center;background:rgb(15 23 42/.52);padding:20px;backdrop-filter:blur(4px)}
.workbook-preview-dialog{display:grid;width:min(1180px,100%);max-height:min(820px,calc(100vh - 40px));overflow:hidden;border:1px solid #cbd5e1;border-radius:16px;background:#fff;box-shadow:0 30px 80px rgb(15 23 42/.34);grid-template-rows:auto auto auto minmax(0,1fr) auto}
.workbook-preview-dialog>header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;border-bottom:1px solid #e2e8f0;padding:16px 18px;background:#f8fafc}.workbook-preview-heading{display:flex;align-items:center;gap:11px}.workbook-preview-icon{display:grid;width:40px;height:40px;place-items:center;border-radius:10px;background:#ccfbf1;color:#0f766e}.workbook-preview-icon svg{width:21px}.workbook-preview-heading h3{margin:0;color:#0f172a;font-size:18px;font-weight:950}.workbook-preview-heading p{margin:4px 0 0;color:#64748b;font-size:12px}.workbook-preview-close{display:grid;width:34px;height:34px;place-items:center;border:1px solid #cbd5e1;border-radius:8px;background:#fff;color:#64748b}.workbook-preview-close svg{width:16px}
.workbook-sheet-tabs{display:flex;overflow-x:auto;gap:5px;border-bottom:1px solid #e2e8f0;background:#fff;padding:8px 12px}.workbook-sheet-tabs button{height:31px;flex:0 0 auto;border:1px solid #cbd5e1;border-radius:7px;background:#fff;padding:0 10px;color:#475569;font-size:11px;font-weight:800}.workbook-sheet-tabs button.active{border-color:#0f766e;background:#0f766e;color:#fff}.workbook-preview-meta{display:flex;flex-wrap:wrap;align-items:center;gap:9px;border-bottom:1px solid #e2e8f0;background:#f0fdfa;padding:8px 12px;color:#0f766e;font-size:11px}.workbook-preview-meta strong{color:#b45309}
.workbook-preview-table-wrap{overflow:auto;background:#fff}.workbook-preview-table-wrap table{border-collapse:separate;border-spacing:0;min-width:100%;font-size:11px}.workbook-preview-table-wrap th,.workbook-preview-table-wrap td{height:27px;max-width:260px;border-right:1px solid #e2e8f0;border-bottom:1px solid #e2e8f0;padding:4px 7px;overflow:hidden;color:#334155;text-overflow:ellipsis;white-space:nowrap}.workbook-preview-table-wrap thead th{position:sticky;z-index:2;top:0;min-width:90px;background:#e2e8f0;color:#475569;text-align:center}.workbook-preview-table-wrap tbody th{position:sticky;z-index:1;left:0;width:44px;min-width:44px;background:#f1f5f9;color:#64748b;text-align:right}.workbook-preview-table-wrap .row-number-corner{left:0;z-index:3;width:44px;min-width:44px}
.workbook-preview-state{display:grid;min-height:260px;place-content:center;justify-items:center;gap:7px;padding:30px;color:#64748b;text-align:center}.workbook-preview-state svg{width:34px;color:#0f766e}.workbook-preview-state strong{color:#334155;font-size:14px}.workbook-preview-state span{font-size:12px}.workbook-preview-state.error svg,.workbook-preview-state.error strong{color:#b91c1c}.workbook-preview-state.compact{min-height:180px}
.workbook-preview-dialog>footer{display:flex;align-items:center;justify-content:flex-end;gap:8px;border-top:1px solid #e2e8f0;background:#f8fafc;padding:12px 16px}.workbook-preview-dialog>footer>span{margin-right:auto;color:#64748b;font-size:11px}.workbook-preview-dialog>footer button{display:inline-flex;height:35px;align-items:center;gap:5px;border-radius:8px;padding:0 12px;font-size:12px;font-weight:900}.workbook-preview-dialog>footer button svg{width:14px}.workbook-preview-dialog>footer .secondary{border:1px solid #99f6e4;background:#fff;color:#0f766e}.workbook-preview-dialog>footer .primary{border:1px solid #0f766e;background:#0f766e;color:#fff}
@media(max-width:640px){.workbook-preview-backdrop{padding:8px}.workbook-preview-dialog{max-height:calc(100vh - 16px)}.workbook-preview-dialog>footer{align-items:stretch;flex-direction:column}.workbook-preview-dialog>footer>span{margin-right:0}.workbook-preview-dialog>footer button{justify-content:center}}
</style>
