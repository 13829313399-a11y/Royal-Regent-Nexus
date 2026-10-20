<script setup lang="ts">
import { computed } from 'vue'
import { FileSpreadsheet, Upload } from '@lucide/vue'
import type { SpreadsheetInspection } from '@/api/spreadsheetMerge'
import { Button } from '@/components/ui/button'
import { extractMergeTable } from './mergeHelpers'
import SpreadsheetGrid from './SpreadsheetGrid.vue'
const props = defineProps<{
  label: string; inspection: SpreadsheetInspection | null; sheet: string; headerRow: number
  loading: boolean; error: string; secondary?: boolean; preset?: string; disabled?: boolean
}>()
const emit = defineEmits<{
  file: [file: File]; sheet: [name: string]; headerRow: [row: number]; preset: [value: string]
}>()
const current = computed(() => props.inspection?.sheets.find(sheet => sheet.name === props.sheet))
const table = computed(() => extractMergeTable(props.inspection?.filename ?? '', current.value?.rows ?? [], props.headerRow))
function picked(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) emit('file', file)
  input.value = ''
}
</script>

<template>
  <div class="sm-source">
    <div class="sm-source-heading"><h3><FileSpreadsheet :size="18" aria-hidden="true" />{{ label }}</h3><span v-if="table">{{ table.rows.length }} 行 · {{ table.headers.length }} 列</span></div>
    <label v-if="secondary" class="sm-field">副表格式
      <select :value="preset ?? ''" :disabled="disabled" @change="emit('preset', ($event.target as HTMLSelectElement).value)"><option value="">普通表格</option><option value="carton-packaging-source">纸箱尺码表整理</option></select>
    </label>
    <p v-if="secondary && preset" class="sm-help">按客户、货号和纸品整理尺码；原表中的缺项与待核问题会保留。产品名称缺失时留空。</p>
    <label class="sm-upload" :class="{ 'sm-upload-busy': loading }">
      <Upload :size="22" aria-hidden="true" /><strong>{{ loading ? '正在读取表格…' : inspection ? '更换表格文件' : '选择表格文件' }}</strong>
      <span>{{ inspection?.filename || 'XLSX / CSV · 单份最多 64 MiB' }}</span>
      <input type="file" accept=".xlsx,.csv" :aria-label="`上传${label}`" :disabled="disabled" @change="picked" />
    </label>
    <p v-if="error" role="alert" class="sm-error">{{ error }}</p>
    <div v-if="inspection" class="sm-source-controls">
      <label class="sm-field">工作表<select :value="sheet" :disabled="loading || disabled" :aria-label="`${label}工作表`" @change="emit('sheet', ($event.target as HTMLSelectElement).value)"><option v-for="item in inspection.sheets" :key="item.name" :value="item.name">{{ item.name }}</option></select></label>
      <label class="sm-field">表头所在行<input type="number" min="1" :max="current?.rows.length || 1" :value="headerRow" :aria-label="`${label}表头行`" :disabled="loading || disabled" @input="emit('headerRow', Number(($event.target as HTMLInputElement).value))" /></label>
    </div>
    <p v-if="inspection && !table" class="sm-error" role="alert">请选择包含字段名的有效表头行。</p>
    <details v-if="inspection?.warnings.length" class="sm-warnings"><summary>读取提示 · {{ inspection.warnings.length }} 项</summary><ul class="sm-warning-list"><li v-for="warning in inspection.warnings" :key="warning">{{ warning }}</li></ul></details>
    <details v-if="table" class="sm-source-preview"><summary>查看源表前 5 行</summary><SpreadsheetGrid :headers="table.headers" :rows="table.rows.slice(0, 5)" :start-row="headerRow + 1" :caption="`${label}源表预览`" /></details>
  </div>
</template>

<style scoped>
.sm-source { min-width: 0; display: flex; flex-direction: column; gap: 14px; }
.sm-source-heading { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; justify-content: space-between; }
h3 { display: flex; align-items: center; gap: 8px; font-size: 15px; font-weight: 600; }
.sm-source-heading > span, .sm-help { font-size: 12px; color: var(--muted-foreground); line-height: 1.7; }
.sm-field { display: flex; flex-direction: column; gap: 6px; font-size: 13px; font-weight: 500; min-width: 0; }
select, input[type=number] { width: 100%; min-width: 0; border: 1px solid var(--input); border-radius: var(--radius); background: var(--card); padding: 8px 10px; height: 38px; font-size: 13px; }
.sm-source-controls { display: grid; grid-template-columns: minmax(0, 1fr) 130px; gap: 12px; }
.sm-upload { position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; min-height: 128px; padding: 20px 12px; border: 1px dashed var(--input); border-radius: var(--radius); background: var(--muted); cursor: pointer; text-align: center; overflow-wrap: anywhere; }
.sm-upload strong { font-size: 14px; }.sm-upload span { font-size: 12px; color: var(--muted-foreground); word-break: break-all; }
.sm-upload input { position: absolute; inset: 0; opacity: 0; width: 100%; cursor: pointer; }
.sm-upload:focus-within { outline: 3px solid var(--ring); outline-offset: 2px; }
.sm-upload-busy { opacity: .7; }
.sm-error { font-size: 13px; color: var(--destructive); line-height: 1.6; }
.sm-warning-list { font-size: 12px; line-height: 1.7; padding-left: 18px; color: var(--muted-foreground); }
.sm-warning-list { max-height: 200px; overflow: auto; overflow-wrap: anywhere; }
summary { cursor: pointer; font-size: 13px; font-weight: 500; padding: 4px 0 12px; }
@media(max-width: 420px) { .sm-source-controls { grid-template-columns: 1fr; } }
</style>
