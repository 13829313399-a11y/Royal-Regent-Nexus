<script setup lang="ts">
import type { PdfRenameFieldCompletion } from './pdfRenameUtils'

withDefaults(defineProps<{
  sourceFileName: string
  status: 'READY' | 'REVIEW' | 'ERROR'
  completion?: PdfRenameFieldCompletion
  manualName: string
  confirmed: boolean
  allowed?: boolean
  busy: boolean
  expanded?: boolean
}>(), { allowed: true, expanded: false })

const emit = defineEmits<{
  field: [key: string, value: string]
  name: [value: string]
  confirm: [value: boolean]
}>()
</script>

<template>
  <div v-if="completion" class="mt-3 rounded-lg border border-amber-200 bg-amber-50/70 p-3 text-xs leading-5">
    <p class="font-semibold text-amber-950">补充未识别字段</p>
    <p class="mt-1 text-slate-600">其余识别内容已保留，补齐后自动组成完整文件名。</p>
    <label v-for="field in completion.fields.filter(field => field.validation_error)" :key="field.key" class="mt-2 block text-slate-700">
      {{ field.label }}
      <input :value="completion.values[field.key] ?? ''" :disabled="busy" :aria-label="`补充 ${field.label} ${sourceFileName}`" class="mt-1 w-full min-w-44 rounded-md border border-amber-300 bg-white px-2 py-1.5 text-sm text-slate-900" :placeholder="field.key === 'report_date' ? '年.月.日，例如 2026.11.5' : '请对照原 PDF 补充此项'" @input="emit('field', field.key, ($event.target as HTMLInputElement).value)">
    </label>
    <label v-if="manualName.trim()" class="mt-3 flex items-start gap-2 text-amber-950">
      <input type="checkbox" :checked="confirmed" :disabled="busy" :aria-label="`确认人工改名 ${sourceFileName}`" class="mt-1 size-4 shrink-0" @change="emit('confirm', ($event.target as HTMLInputElement).checked)">
      <span>确认补充内容及完整文件名并放行</span>
    </label>
  </div>
  <details v-else-if="allowed" :open="expanded || status === 'ERROR'" class="mt-3 text-xs leading-5">
    <summary class="cursor-pointer font-semibold">{{ status === 'ERROR' ? '人工改名并放行' : '修改文件名（可选）' }}</summary>
    <label class="mt-2 block text-slate-700">正确文件名
      <input :value="manualName" :disabled="busy" :aria-label="`人工文件名 ${sourceFileName}`" class="mt-1 w-full min-w-44 rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-900" placeholder="请输入核对后的完整文件名.pdf" @input="emit('name', ($event.target as HTMLInputElement).value)">
    </label>
    <p class="mt-1 text-slate-500">可省略 .pdf；清空可撤销人工改名。原识别依据保留。</p>
    <label v-if="manualName.trim()" class="mt-2 flex items-start gap-2 text-amber-950">
      <input type="checkbox" :checked="confirmed" :disabled="busy" :aria-label="`确认人工改名 ${sourceFileName}`" class="mt-1 size-4 shrink-0" @change="emit('confirm', ($event.target as HTMLInputElement).checked)">
      <span>确认此人工文件名并放行</span>
    </label>
  </details>
  <p v-else class="mt-2 text-xs text-rose-700">此异常不能人工放行，请按错误提示处理文件或联系管理员。</p>
</template>
