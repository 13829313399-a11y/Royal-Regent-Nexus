<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { correctYinhuiDraft, selectYinhuiToolCandidate, type YinhuiDraft } from '@/lib/customerPriceConverters/yinhuiDraft'
import YinhuiAiReview from './YinhuiAiReview.vue'

const props = defineProps<{ draft: YinhuiDraft; disabled?: boolean }>()
const emit = defineEmits<{ 'update:draft': [YinhuiDraft]; invalidate: []; save: [] }>()
const edits = ref<Record<string, string>>({})
const message = ref('')
watch(() => props.draft, () => { edits.value = {}; message.value = '' })
const issues = computed(() => props.draft.result.quoteData.importIssues || [])
const cells = computed(() => [...new Map(issues.value.flatMap(i => i.cells).map(c => [`${c.sheet}!${c.cell}`, c])).values()])
const dirty = computed(() => Object.keys(edits.value).length > 0)
function edit(key: string, event: Event) {
  edits.value[key] = (event.target as HTMLInputElement).value
  emit('invalidate')
}
function apply() {
  if (props.disabled) return
  emit('invalidate')
  try {
    const changes = cells.value.filter(c => Object.hasOwn(edits.value, `${c.sheet}!${c.cell}`)).map(c => {
      const value = edits.value[`${c.sheet}!${c.cell}`]!.trim()
      return { sheet: c.sheet, cell: c.cell, value: /^-?\d+(?:\.\d+)?$/.test(value) ? Number(value) : value }
    })
    const next = correctYinhuiDraft(props.draft, changes)
    emit('update:draft', next)
  } catch (e) { message.value = e instanceof Error ? e.message : String(e) }
}
function select(index: number, event: Event) {
  if (props.disabled) return
  selectYinhuiToolCandidate(props.draft, index, (event.target as HTMLSelectElement).value)
  emit('invalidate')
}
</script>

<template>
  <fieldset :disabled="disabled" class="mt-4 rounded-xl border border-slate-300 bg-white p-4" data-testid="yinhui-draft">
    <legend class="px-2 text-sm font-semibold">银辉导入草稿 · 补正与核对</legend>
    <div class="flex flex-wrap items-center justify-between gap-3">
      <p class="text-sm text-slate-700">原文件：{{ draft.sourceFileName }}。草稿保留原表、补正记录和已核对资料，可保存后从银辉导入口重新打开。</p>
      <button type="button" data-testid="yinhui-save-draft" :disabled="disabled || dirty" class="rounded-md border border-slate-300 px-3 py-2 text-sm disabled:opacity-50" @click="emit('save')">保存草稿</button>
    </div>
    <p class="mt-2 text-xs text-slate-500">草稿包含内部报价资料，仅供内部核对，不是可发送客户的报价文件。{{ dirty ? '请先应用补正，再保存草稿。' : '' }}</p>
    <div v-if="issues.length" class="mt-3 rounded-lg border border-red-200 bg-red-50 p-3" role="alert">
      <p class="text-sm font-semibold text-red-900">已保留草稿，{{ issues.length }} 项原表问题待处理；当前只能查看已识别成本小计。</p>
      <ul class="mt-2 list-disc space-y-1 pl-5 text-sm text-red-800"><li v-for="(issue, index) in issues" :key="index">{{ issue.source }}：{{ issue.message }}</li></ul>
      <p v-if="issues.some(i => !i.cells.length)" class="mt-2 text-xs text-red-800">未提供补正输入的问题，请按提示完善下方资料，或修正原表后重新导入；不会自动忽略未识别成本。</p>
    </div>
    <div v-if="cells.length" class="mt-3">
      <p class="text-sm text-slate-700">填写已确认的读取值后，点击“应用补正并重新核对”。补正只用于本次转换，不改动原文件，也不重算原表的其他公式；相关金额须一并核实。重新核对会重置下方手工资料。</p>
      <div class="mt-2 max-h-80 overflow-auto">
        <table class="w-full text-left text-xs"><thead><tr><th class="p-2">来源</th><th class="p-2">字段</th><th class="p-2">当前读取值</th><th class="p-2">确认值</th></tr></thead>
          <tbody><tr v-for="cell in cells" :key="`${cell.sheet}!${cell.cell}`" class="border-t border-slate-200">
            <td class="p-2">{{ cell.sheet }}!{{ cell.cell }}</td><td class="p-2">{{ cell.label }}</td><td class="max-w-64 break-words p-2">{{ cell.value === null || cell.value === '' ? '空白' : cell.value }}</td>
            <td class="p-2"><input :aria-label="`补正 ${cell.sheet}!${cell.cell}`" :value="edits[`${cell.sheet}!${cell.cell}`] ?? cell.value ?? ''" class="w-full min-w-24 rounded border border-slate-300 px-2 py-1" @input="edit(`${cell.sheet}!${cell.cell}`, $event)"></td>
          </tr></tbody>
        </table>
      </div>
      <button type="button" data-testid="yinhui-apply-corrections" :disabled="disabled || !dirty" class="mt-3 rounded bg-teal-700 px-3 py-2 text-sm text-white disabled:opacity-50" @click="apply">应用补正并重新核对</button>
    </div>
    <p v-if="message" class="mt-2 text-sm text-red-700" role="alert">{{ message }}</p>
    <YinhuiAiReview :draft="draft" :disabled="disabled || dirty" @update:draft="emit('update:draft', $event)" @invalidate="emit('invalidate')" />
    <details v-if="draft.candidates.length && draft.result.manualReviewReasons?.length" class="mt-3 rounded border border-slate-200 p-3">
      <summary class="cursor-pointer text-sm font-semibold">选择模具对应资料（{{ draft.candidates.length }} 条原表记录）</summary>
      <p class="mt-2 text-xs text-slate-600">选择只补入模号、零件号；料型、总料重、用量、啤工和费用仍保留当前计算值。请结合原表核实，不能用选择模具消除金额问题。</p>
      <label v-for="(line, index) in draft.result.quoteData.tools" :key="index" class="mt-3 grid gap-1 text-xs">
        {{ index + 1 }} · {{ line.originalDescription || line.description }} · {{ line.weightG }} g · {{ line.moldNo || '未填模号' }}
        <select :aria-label="`模具对应 ${index + 1}`" class="rounded border border-slate-300 px-2 py-1" @change="select(index, $event)">
          <option value="">保留当前资料，请选择原表对应项</option>
          <option v-for="candidate in draft.candidates" :key="candidate.source" :value="candidate.source">{{ candidate.source }} · {{ candidate.moldNo }} · {{ candidate.description }} · {{ candidate.partNo || '未填零件号' }}</option>
        </select>
      </label>
    </details>
    <details v-if="draft.overrides.length" class="mt-3 text-xs text-slate-600"><summary class="cursor-pointer">已应用 {{ draft.overrides.length }} 项补正</summary><ul class="mt-2 list-disc pl-5"><li v-for="item in draft.overrides" :key="`${item.sheet}!${item.cell}`">{{ item.sheet }}!{{ item.cell }} → {{ item.value }}</li></ul></details>
  </fieldset>
</template>
