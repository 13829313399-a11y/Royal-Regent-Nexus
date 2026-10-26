<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import type { MarkReadResult, MarkReviewEdits, MarkReviewAddition, MarkGraphicSelection } from '@/api/cartonSupplierPortal'
const props = defineProps<{ review: MarkReadResult; busy: boolean; applied?: MarkReviewEdits | null }>()
const emit = defineEmits<{ render: [value: MarkReviewEdits] }>()
const values = reactive<Record<string, string>>({})
const fields = props.review.records.flatMap(r => r.panels.flatMap(p => p.fields))
for (const field of fields) values[field.id] = field.value
const checked = ref<string[]>([]), paper = ref(props.review.paper), orientation = ref(props.review.orientation)
const omissions = ref<string[]>([]), additions = ref<MarkReviewAddition[]>([])
const target = ref('0:front'), newLabel = ref(''), newValue = ref(''), sourceChoice = ref(''), sourceSearch = ref('')
const sourceAsBarcode = ref(false)
const graphics = reactive<MarkGraphicSelection[]>(props.review.records.flatMap((r, index) => (['front', 'side'] as const).map(face => {
  const panel = r.panels.find(p => p.face === face)
  return { record: index, face, logo: panel?.logo ?? false, symbols: [...(panel?.symbols ?? [])] }
})))
const originalGraphics = graphics.map(g => JSON.stringify(g))
const changedGraphics = computed(() => graphics.filter((g, i) => JSON.stringify(g) !== originalGraphics[i]))
const sourceOptions = computed(() => props.review.unselected_cells.filter(c => c.printable && `${c.location} ${c.text}`.toLowerCase().includes(sourceSearch.value.trim().toLowerCase())).slice(0, 100))
const changed = computed(() => Object.fromEntries(fields.filter(f => values[f.id]?.trim() !== f.value).map(f => [f.id, values[f.id]!.trim()])))
const invalid = computed(() => fields.some(f => !omissions.value.includes(f.id) && !values[f.id]?.trim()))
const advancedOpen = ref(false), showAllIssues = ref(false)
const issues = computed(() => props.review.issues ?? fields.filter(f => f.placeholder).map(f => ({ kind: 'missing_value', message: `请补充或核实 ${f.label}`, field_ids: [f.id], sources: f.sources })))
const pendingIssues = computed(() => issues.value.filter(i => !i.field_ids.length || !i.field_ids.every(id => props.applied?.edits[id]?.trim())))
const visibleIssues = computed(() => showAllIssues.value ? pendingIssues.value : pendingIssues.value.slice(0, 6))
const issueFields = (ids: string[]) => fields.filter(f => ids.includes(f.id) && !omissions.value.includes(f.id))
const changeSet = computed<MarkReviewEdits>(() => ({ edits: changed.value, reviewed_notes: checked.value, paper: paper.value, orientation: orientation.value, additions: additions.value, omissions: omissions.value, graphics: changedGraphics.value, include_sources: false }))
const dirty = computed(() => JSON.stringify(changeSet.value) !== JSON.stringify({ edits: props.applied?.edits ?? {}, reviewed_notes: props.applied?.reviewed_notes ?? [], paper: props.applied?.paper ?? props.review.paper, orientation: props.applied?.orientation ?? props.review.orientation, additions: props.applied?.additions ?? [], omissions: props.applied?.omissions ?? [], graphics: props.applied?.graphics ?? [], include_sources: false }))
function add(source = false) {
  const [record, face] = target.value.split(':')
  if (source ? !sourceChoice.value : !newValue.value.trim()) return
  additions.value.push({ record: Number(record), face: face as 'front' | 'side', ...(source ? { source_id: sourceChoice.value, ...(sourceAsBarcode.value ? { as_barcode: true } : {}) } : { label: newLabel.value.trim(), value: newValue.value.trim() }) })
  newLabel.value = ''; newValue.value = ''; sourceChoice.value = ''
}
</script>

<template>
  <section aria-label="原稿识别与核对" class="mt-5 space-y-4 border-t pt-5">
    <div>
      <h3 class="font-bold text-slate-900">{{ pendingIssues.length ? `需要确认的内容 · ${pendingIssues.length} 项` : '原稿已整理' }}</h3>
      <p class="mt-1 text-sm leading-6 text-slate-500">已整理 {{ review.records.length }} 组箱唛。{{ pendingIssues.length ? '只列出需补填或有歧义的项目，不用逐条勾选全部备注。' : '暂无需补填的字段，请查看下方预览；特殊制版要求仍需对照原稿。' }}修改后更新预览，不重新调用 API。</p>
    </div>
    <p v-if="review.mode === 'needs_mapping'" role="status" class="rounded-lg bg-amber-50 p-3 text-sm leading-6 text-amber-900">原稿已读取，但 AI 排版建议未通过核验。下面是按原生单元格整理的待核对内容，可以选择字段、补充内容及调整正侧唛；这不算 AI 自动排版成功。</p>
    <p v-if="review.confirmed_template" role="status" class="rounded-lg bg-teal-50 p-3 text-sm leading-6 text-teal-900">采用 {{ review.confirmed_template.name }} V{{ review.confirmed_template.version }}。正侧唛左右排版；尺寸按宽×长×高（CM）填写，毛重带 KG，补充一次自动同步两面。认证章需按本单纸箱确认。</p>
    <div v-if="pendingIssues.length" class="space-y-3" aria-label="需要确认的项目">
      <article v-for="(issue, i) in visibleIssues" :key="`${issue.kind}:${i}`" class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm">
        <p class="font-medium leading-6 text-amber-900">{{ issue.message }}</p>
        <label v-for="field in issueFields(issue.field_ids)" :key="field.id" class="mt-2 block">
          <span class="text-xs text-slate-600">{{ field.label }} · 原文 {{ field.value }}</span>
          <input v-model="values[field.id]" :aria-label="`补充 ${field.id} ${field.label}`" :disabled="busy || field.locked" maxlength="2000" class="mt-1 block w-full rounded-lg border bg-white p-2" placeholder="填写本次确定的完整内容及单位">
        </label>
        <button v-if="!issue.field_ids.length" type="button" :disabled="busy" class="mt-2 text-teal-800 underline disabled:opacity-50" @click="advancedOpen = true">打开高级调整核实</button>
      </article>
      <button v-if="pendingIssues.length > 6" type="button" :disabled="busy" class="text-sm text-teal-800 underline disabled:opacity-50" @click="showAllIssues = !showAllIssues">{{ showAllIssues ? '收起' : `查看其余 ${pendingIssues.length - 6} 项` }}</button>
    </div>
    <details :open="advancedOpen" aria-label="高级调整与完整原稿记录" class="rounded-lg border p-3 sm:p-4" @toggle="advancedOpen = ($event.target as HTMLDetailsElement).open">
      <summary class="cursor-pointer font-semibold">高级调整与完整原稿记录</summary>
      <p class="mt-3 text-xs leading-5 text-slate-500">完整字段、图示、{{ review.notes.length }} 条备注及未选入文字都在这里。日常只需查看预览和上方待确认项。</p>
      <details v-if="review.warnings.length" class="my-3 rounded-lg bg-slate-50 p-3 text-sm"><summary class="cursor-pointer">完整读稿提示 · {{ review.warnings.length }} 条</summary><ul class="mt-2 list-inside list-disc leading-6 text-slate-600"><li v-for="item in review.warnings" :key="item">{{ item }}</li></ul></details>
    <details v-for="(record, index) in review.records" :key="index" :open="index === 0" class="rounded-lg border p-3 sm:p-4">
      <summary class="cursor-pointer break-words font-semibold">第 {{ index + 1 }} 组箱唛{{ record.title ? ` · ${record.title}` : '' }}</summary>
      <div class="mt-4 grid gap-5 lg:grid-cols-2">
        <section v-for="panel in record.panels" :key="panel.face" class="min-w-0 space-y-3">
          <h4 class="border-b pb-2 text-sm font-bold text-teal-800">{{ panel.face === 'front' ? '正唛' : '侧唛' }} · {{ panel.copies }} 面</h4>
          <label v-for="field in panel.fields" v-show="!omissions.includes(field.id)" :key="field.id" class="block text-sm">
            <span class="font-medium">{{ field.label }}</span><span v-if="field.placeholder" class="ml-2 text-amber-700">需要补充</span>
            <textarea v-model="values[field.id]" :aria-label="`第${index + 1}组${panel.face === 'front' ? '正唛' : '侧唛'} ${field.label}`" :disabled="busy || field.locked" :rows="field.value.length > 80 ? 3 : 1" maxlength="2000" class="mt-1 block w-full rounded-lg border bg-white p-2 leading-6 disabled:bg-slate-50 disabled:text-slate-600" />
            <span class="mt-1 block break-all text-xs leading-5 text-slate-500">来源：{{ field.sources.join('、') }}<template v-if="values[field.id]?.trim() !== field.value"> · 原文：{{ field.value }} · 本次人工补充</template><template v-if="field.locked"> · PO 身份取原稿</template></span>
            <button v-if="!field.locked && !review.confirmed_template" type="button" :disabled="busy" class="mt-1 text-xs text-slate-500 underline" @click.prevent="omissions.push(field.id)">从箱面移除，保留原文</button>
          </label>
          <div v-for="(bar, b) in panel.barcodes" :key="b" class="rounded-lg bg-slate-50 p-3 text-sm leading-6">
            <p class="break-all font-medium">条码 {{ bar.value }}</p><p class="text-slate-500">{{ bar.kind }} · 条形区域 {{ bar.width_mm }} × {{ bar.height_mm }} mm<template v-if="bar.frame === 'box'"> · 黑框</template></p>
          </div>
        </section>
      </div>
    </details>
    <details v-if="!review.confirmed_template" class="rounded-lg border p-3 sm:p-4">
      <summary class="cursor-pointer font-semibold">核对品牌标志和搬运图案</summary>
      <p class="mt-2 text-xs leading-5 text-slate-500">请对照原图明确选择。ZURU 使用已确认素材，其他三个图案使用标准示意；这里的明确选择会另列为本次补充，不表示图片已被完整理解。</p>
      <div class="mt-3 grid gap-4 sm:grid-cols-2">
        <fieldset v-for="setting in graphics" :key="`${setting.record}:${setting.face}`" class="rounded-lg bg-slate-50 p-3 text-sm">
          <legend class="px-1 font-medium">第 {{ setting.record + 1 }} 组{{ setting.face === 'front' ? '正唛' : '侧唛' }}</legend>
          <label class="flex items-center gap-2"><input v-model="setting.logo" type="checkbox" :disabled="busy || !review.logo_available" :aria-label="`第${setting.record + 1}组${setting.face} ZURU标志`">已确认的 ZURU 标志</label>
          <label v-for="symbol in [{ kind: 'fragile', title: '易碎' }, { kind: 'this_side_up', title: '向上' }, { kind: 'keep_dry', title: '防潮' }]" :key="symbol.kind" class="mt-2 flex items-center gap-2"><input v-model="setting.symbols" type="checkbox" :value="symbol.kind" :disabled="busy" :aria-label="`第${setting.record + 1}组${setting.face} ${symbol.title}`">{{ symbol.title }}</label>
        </fieldset>
      </div>
      <p v-if="!review.logo_available" class="mt-2 text-xs text-slate-500">原稿未提供可核实的 ZURU 品牌依据，未开放自动采用品牌素材；其他标志请对照原稿处理。</p>
    </details>
    <details v-if="!review.confirmed_template" class="rounded-lg border p-3 sm:p-4">
      <summary class="cursor-pointer font-semibold">添加原稿字段或本次补充</summary>
      <div class="mt-3 space-y-3 text-sm">
        <label class="block">添加到<select v-model="target" :disabled="busy" aria-label="补充字段的箱面" class="mt-1 block w-full rounded-lg border bg-white p-2"><template v-for="(_, index) in review.records" :key="index"><option :value="`${index}:front`">第 {{ index + 1 }} 组正唛</option><option :value="`${index}:side`">第 {{ index + 1 }} 组侧唛</option></template></select></label>
        <label class="block">从未选入原文中查找<input v-model="sourceSearch" :disabled="busy" aria-label="查找原稿字段" class="mt-1 block w-full rounded-lg border p-2" placeholder="输入字段文字或单元格位置"></label>
        <div class="flex flex-col gap-2 sm:flex-row"><select v-model="sourceChoice" :disabled="busy" aria-label="待添加的原稿字段" class="min-w-0 flex-1 rounded-lg border bg-white p-2"><option value="">选择原稿文字（最多显示100项，可搜索）</option><option v-for="cell in sourceOptions" :key="cell.id" :value="cell.id">{{ cell.location }} · {{ cell.text.slice(0, 100) }}</option></select><button type="button" :disabled="busy || !sourceChoice" class="shrink-0 rounded-lg border px-3 py-2 disabled:opacity-50" @click="add(true)">添加原文字段</button></div>
        <label class="flex items-start gap-2 text-xs leading-5 text-slate-500"><input v-model="sourceAsBarcode" type="checkbox" :disabled="busy" class="mt-1 shrink-0" aria-label="将所选原稿号码生成为条码">将所选原稿的12/13/14位号码生成为条码图，程序校验原号码并遵守明确的最低尺寸。</label>
        <div class="grid gap-3 sm:grid-cols-2"><label>补充字段名称<input v-model="newLabel" :disabled="busy" maxlength="100" aria-label="新增字段名称" class="mt-1 block w-full rounded-lg border p-2" placeholder="如：实际毛重"></label><label>本次明确填写的内容<input v-model="newValue" :disabled="busy" maxlength="2000" aria-label="新增字段内容" class="mt-1 block w-full rounded-lg border p-2" placeholder="如：5.5 KGS"></label></div>
        <button type="button" :disabled="busy || !newValue.trim()" class="rounded-lg border px-3 py-2 disabled:opacity-50" @click="add(false)">添加本次补充</button>
        <ul v-if="additions.length" class="space-y-2"><li v-for="(item, i) in additions" :key="i" class="flex items-start justify-between gap-2 rounded-lg bg-slate-50 p-2"><span class="min-w-0 break-words">第 {{ item.record + 1 }} 组{{ item.face === 'front' ? '正唛' : '侧唛' }} · {{ item.source_id ? review.unselected_cells.find(c => c.id === item.source_id)?.text : `${item.label} ${item.value}` }}</span><button type="button" :disabled="busy" class="shrink-0 text-slate-500 underline" @click="additions.splice(i, 1)">移除</button></li></ul>
        <button v-if="omissions.length" type="button" :disabled="busy" class="text-slate-500 underline" @click="omissions = []">恢复本次移除的 {{ omissions.length }} 项原稿字段</button>
      </div>
    </details>
    <details v-if="review.notes.length" class="rounded-lg border p-3 sm:p-4">
      <summary class="cursor-pointer font-semibold">制版备注与待确认项 · {{ checked.length }} / {{ review.notes.length }} 已对照核对</summary>
      <p class="mt-2 text-xs leading-5 text-slate-500">每条原文都会保留。勾选表示你已对照原稿核实，不代表审核或 QC 放行；未勾选项目仍会在审阅稿中标为待核对。</p>
      <label v-for="note in review.notes" :key="note.id" class="mt-3 flex items-start gap-3 border-t pt-3 text-sm">
        <input v-model="checked" type="checkbox" :value="note.id" :disabled="busy" :aria-label="`已核对 ${note.location}`" class="mt-1 shrink-0">
        <span class="min-w-0"><span class="block break-all text-xs text-slate-500">{{ note.location }}</span><span class="mt-1 block whitespace-pre-wrap break-words leading-6">{{ note.text }}</span></span>
      </label>
    </details>
    <details v-if="review.images.length" class="rounded-lg border p-3 sm:p-4">
      <summary class="cursor-pointer font-semibold">原稿图片与本地文字候选 · {{ review.images.length }} 张</summary>
      <p class="mt-2 text-xs leading-5 text-slate-500">图片像素不发送给 DeepSeek。图片文字由本机识别后作为参考，旧示例里的 PO、数量和条码不作为本单业务数据。没有文字的图示仍需对照确认。</p>
      <div class="mt-3 grid gap-4 sm:grid-cols-2">
        <figure v-for="image in review.images" :key="image.id" class="min-w-0 rounded-lg border p-3">
          <img :src="image.preview" :alt="`${image.location} 原稿图片`" class="max-h-64 w-full object-contain">
          <figcaption class="mt-2 break-all text-xs text-slate-500">{{ image.location }}</figcaption>
          <p class="mt-2 whitespace-pre-wrap break-words text-sm leading-6">{{ image.text || '未识别出文字，请对照图片核实图案和要求。' }}</p>
        </figure>
      </div>
    </details>
    <details v-if="review.unselected_cells.length" class="rounded-lg border p-3 sm:p-4">
      <summary class="cursor-pointer font-semibold">未进入箱面的原稿文字 · {{ review.unselected_cells.length }} 项</summary>
      <p class="mt-2 text-xs text-slate-500">包含标题、重复、示例及未选入内容，请核对是否有遗漏。</p>
      <div class="mt-3 max-h-80 space-y-2 overflow-auto text-sm"><p v-for="(cell, i) in review.unselected_cells" :key="i" class="break-words border-t pt-2"><span class="text-xs text-slate-500">{{ cell.location }}</span><br>{{ cell.text }}</p></div>
    </details>
    <div class="mt-3 flex flex-wrap items-end gap-3 rounded-lg bg-slate-50 p-3">
      <label class="text-sm">纸张<select v-model="paper" :disabled="busy" aria-label="审阅稿纸张" class="mt-1 block rounded-lg border bg-white p-2"><option>A3</option><option>A4</option></select></label>
      <label class="text-sm">方向<select v-model="orientation" :disabled="busy" aria-label="审阅稿方向" class="mt-1 block rounded-lg border bg-white p-2"><option value="landscape">横向</option><option value="portrait">竖向</option></select></label>
      <p v-if="invalid" class="text-sm text-amber-800">印刷字段不能为空，请补充后生成。</p>
    </div>
    </details>
    <div v-if="dirty || busy" class="flex flex-wrap items-center gap-3">
      <button type="button" :disabled="busy || invalid" class="rounded-lg bg-teal-700 px-4 py-2 font-semibold text-white disabled:opacity-50" @click="emit('render', changeSet)">{{ busy ? '正在排版…' : '更新预览（不重新读稿）' }}</button>
      <p class="text-xs text-slate-500">补充只用于本次预览，原 Excel 保留原样。</p>
    </div>
  </section>
</template>
