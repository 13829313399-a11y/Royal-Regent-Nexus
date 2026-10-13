<script setup lang="ts">
import { ref, onBeforeUnmount } from 'vue'
import { cartonSupplierPortalApi as api, type SupplierMarkUploadOrder, type SupplierMarkLayout, type MarkLayoutConfig, type MarkLayoutPreview, type MarkLayoutRegion } from '@/api/cartonSupplierPortal'
import { getApiErrorMessage } from '@/lib/http'
const props = defineProps<{ factory: string; order: SupplierMarkUploadOrder; current: SupplierMarkLayout | null }>()
const emit = defineEmits<{ saved: [layout: SupplierMarkLayout]; close: [] }>()
const name = ref(props.current?.name ?? props.order.customer_name + '箱唛')
const config = ref<MarkLayoutConfig>(props.current ? { frame_style: 'plain', ...JSON.parse(JSON.stringify(props.current.config)) } : {
  mode: 'front_side', paper: 'A4', font: 'Helvetica', font_size: 11, front_percent: 55, front_copies: 2, side_copies: 2,
  frame_style: 'original_red',
  barcode: 'Code128', side_address: '', instructions: '', reference_page: 0, logo_region: null, stamp_region: null, field_cells: {},
})
const file = ref<File | null>(null), preview = ref<MarkLayoutPreview | null>(null), error = ref(''), busy = ref(false)
const image = ref<HTMLImageElement | null>(null), selecting = ref<'logo_region' | 'stamp_region' | null>(null)
const controller = new AbortController(); let active = true, revision = 0
const start = ref<{ x: number; y: number } | null>(null), pending = ref<MarkLayoutRegion | null>(null)
const fields: { key: keyof MarkLayoutConfig['field_cells']; title: string }[] = [
  { key: 'item', title: '货号' }, { key: 'vendor', title: '厂商' }, { key: 'product', title: '品名' }, { key: 'content', title: '装箱数' },
  { key: 'gtin', title: 'GTIN' }, { key: 'vendor_item', title: '厂家货号' }, { key: 'dimensions', title: '尺寸' }, { key: 'gross_weight', title: '毛重' },
]
async function loadPreview() {
  const token = ++revision
  busy.value = true; error.value = ''; preview.value = null
  try {
    const result = file.value ? await api.previewLayoutReference(props.factory, props.order, file.value, config.value.reference_page, controller.signal)
      : props.current ? await api.previewSavedLayout(props.factory, props.order, props.current, controller.signal) : null
    if (!active || token !== revision) return
    preview.value = result
    if (!props.current && !config.value.side_address && result?.suggested_side_address) config.value.side_address = result.suggested_side_address
  } catch (cause) { if (active && token === revision) error.value = getApiErrorMessage(cause) }
  finally { if (active && token === revision) busy.value = false }
}
function pick(event: Event) {
  const chosen = (event.target as HTMLInputElement).files?.[0]
  if (!chosen) return
  if (!/\.pdf$/i.test(chosen.name) || !chosen.size || chosen.size > 20 * 1024 * 1024) { error.value = '请选择客户历史 PDF，最多 20 MB。'; return }
  file.value = chosen; config.value.reference_page = 0; config.value.logo_region = null; config.value.stamp_region = null
  void loadPreview()
}
function point(event: PointerEvent) {
  const box = image.value!.getBoundingClientRect(), p = preview.value!
  return { x: Math.max(0, Math.min(p.page_width_mm, (event.clientX - box.left) / box.width * p.page_width_mm)),
    y: Math.max(0, Math.min(p.page_height_mm, (event.clientY - box.top) / box.height * p.page_height_mm)) }
}
function begin(event: PointerEvent) {
  if (!selecting.value || !preview.value || !image.value || busy.value) return
  start.value = point(event); pending.value = null; (event.currentTarget as Element).setPointerCapture(event.pointerId)
}
function move(event: PointerEvent) {
  if (!start.value) return
  const end = point(event)
  pending.value = { x: Math.min(end.x, start.value.x), y: Math.min(end.y, start.value.y), width: Math.abs(end.x - start.value.x), height: Math.abs(end.y - start.value.y) }
}
function finish(event: PointerEvent) {
  move(event)
  if (selecting.value && pending.value && pending.value.width >= 1 && pending.value.height >= 1) config.value[selecting.value] = pending.value
  start.value = null; pending.value = null; selecting.value = null
}
async function save() {
  if (busy.value || !preview.value || !name.value.trim()) return
  busy.value = true; error.value = ''
  try {
    const result = await api.saveMarkLayout(props.factory, props.order, name.value, config.value, props.current, file.value, controller.signal)
    if (active) emit('saved', result)
  } catch (cause) { if (active) error.value = getApiErrorMessage(cause) }
  finally { if (active) busy.value = false }
}
if (props.current) void loadPreview()
onBeforeUnmount(() => { active = false; revision++; controller.abort() })
</script>

<template>
  <section class="mt-4 rounded-xl border border-teal-200 bg-teal-50/40 p-4" aria-label="客户排版模板">
    <div class="flex items-center justify-between gap-3"><h3 class="font-bold">{{ order.customer_name }} · {{ current ? '调整客户模板' : '建立客户模板' }}</h3><button type="button" :disabled="busy" class="rounded border px-3 py-1" @click="emit('close')">收起</button></div>
    <p class="mt-2 text-sm text-slate-600">上传客户历史稿，确认版式、固定地址和素材，保存后同客户订单自动套用。正侧唛分别重排文字和条码；历史稿仅保留你选取的 LOGO、图章。</p>
    <div class="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <label class="text-sm">模板名称<input v-model="name" maxlength="128" :disabled="busy" class="mt-1 w-full rounded border bg-white p-2"></label>
      <label class="text-sm">客户历史 PDF<input type="file" accept=".pdf" aria-label="客户历史 PDF" :disabled="busy" class="mt-1 block w-full text-xs" @change="pick"><span class="mt-1 block text-xs">{{ file?.name || current?.reference_name || '第一次须选择历史稿' }}</span></label>
      <label class="text-sm">排版模式<select v-model="config.mode" :disabled="busy" class="mt-1 w-full rounded border bg-white p-2"><option value="front_side">正侧唛并排</option><option value="front_only">仅正唛</option><option value="separate_pages">正侧唛分别一页</option></select></label>
      <label class="text-sm">纸张<select v-model="config.paper" :disabled="busy" class="mt-1 w-full rounded border bg-white p-2"><option>A4</option><option>A3</option></select></label>
      <label class="text-sm">框线样式<select v-model="config.frame_style" :disabled="busy" class="mt-1 w-full rounded border bg-white p-2"><option value="original_red">原版红框（带折边线）</option><option value="plain">普通黑框</option></select></label>
      <label class="text-sm">字体<select v-model="config.font" :disabled="busy" class="mt-1 w-full rounded border bg-white p-2"><option value="Helvetica">Arial 风格</option><option value="Courier">等宽字体</option></select></label>
      <label class="text-sm">字号<input v-model.number="config.font_size" type="number" min="7" max="16" :disabled="busy" class="mt-1 w-full rounded border bg-white p-2"></label>
      <label class="text-sm">条码<select v-model="config.barcode" :disabled="busy" class="mt-1 w-full rounded border bg-white p-2"><option>Code128</option><option>ITF14</option><option value="none">无需条码</option></select></label>
      <label v-if="config.mode === 'front_side'" class="text-sm">正唛宽度占比 %<input v-model.number="config.front_percent" type="number" min="40" max="60" :disabled="busy" class="mt-1 w-full rounded border bg-white p-2"></label>
      <label class="text-sm">正唛面数<input v-model.number="config.front_copies" type="number" min="1" max="4" :disabled="busy" class="mt-1 w-full rounded border bg-white p-2"></label>
      <label v-if="config.mode !== 'front_only'" class="text-sm">侧唛面数<input v-model.number="config.side_copies" type="number" min="1" max="4" :disabled="busy" class="mt-1 w-full rounded border bg-white p-2"></label>
    </div>
    <div class="mt-3 grid gap-3 sm:grid-cols-2"><label class="text-sm">客户固定侧唛地址<textarea v-model="config.side_address" rows="3" maxlength="500" :disabled="busy" class="mt-1 w-full rounded border bg-white p-2" placeholder="从历史稿确认后保存"></textarea></label><label class="text-sm">固定制作说明<textarea v-model="config.instructions" rows="3" maxlength="500" :disabled="busy" class="mt-1 w-full rounded border bg-white p-2"></textarea></label></div>
    <details class="mt-3 text-sm"><summary class="cursor-pointer">Excel 字段位置（自动识别不适用时设置）</summary><p class="my-2 text-xs text-slate-500">填写单元格，如 C15。留空按字段名称识别，每张可见工作表使用相同位置。</p><div class="grid grid-cols-2 gap-2 sm:grid-cols-4"><label v-for="field in fields" :key="field.key">{{ field.title }}<input v-model="config.field_cells[field.key]" :disabled="busy" placeholder="自动识别" class="mt-1 w-full rounded border bg-white p-2"></label></div></details>
    <div v-if="preview" class="mt-4">
      <label v-if="file && preview.page_count > 1" class="mb-2 block text-sm">取素材页<select v-model.number="config.reference_page" :disabled="busy" class="ml-2 rounded border bg-white p-1" @change="config.logo_region = null; config.stamp_region = null; loadPreview()"><option v-for="page in preview.page_count" :key="page" :value="page - 1">第 {{ page }} 页</option></select></label>
      <div class="mb-2 flex flex-wrap items-center gap-2 text-sm"><button type="button" :disabled="busy" class="rounded border bg-white px-3 py-1" @click="selecting = 'logo_region'">选取 LOGO</button><button type="button" :disabled="busy" class="rounded border bg-white px-3 py-1" @click="selecting = 'stamp_region'">选取图章</button><button type="button" :disabled="busy" class="rounded border bg-white px-3 py-1" @click="config.logo_region = null; config.stamp_region = null">清除选区</button><span>{{ selecting ? '在历史稿上拖出矩形，框住需要保留的素材。' : '蓝框 LOGO · 橙框图章；未选 LOGO 时尝试读取 Excel 内唯一 LOGO。' }}</span></div>
      <div class="relative mx-auto max-w-4xl border bg-white" :class="selecting ? 'cursor-crosshair' : ''" style="touch-action: none" @pointerdown.prevent="begin" @pointermove="move" @pointerup="finish" @pointercancel="start = null; pending = null">
        <img ref="image" :src="preview.preview_data_url" alt="客户历史 PDF，框选固定素材" class="block w-full select-none" draggable="false">
        <svg class="pointer-events-none absolute inset-0 h-full w-full" :viewBox="`0 0 ${preview.page_width_mm} ${preview.page_height_mm}`"><rect v-if="config.logo_region" v-bind="config.logo_region" fill="#38bdf822" stroke="#0284c7" stroke-width="0.6"/><rect v-if="config.stamp_region" v-bind="config.stamp_region" fill="#fb923c22" stroke="#ea580c" stroke-width="0.6"/><rect v-if="pending" v-bind="pending" fill="#38bdf822" stroke="#0284c7" stroke-width="0.6"/></svg>
      </div>
      <p class="mt-2 text-xs text-slate-500">当前取历史稿第 {{ config.reference_page + 1 }} 页素材。此模板生成排版审阅稿，实际箱面尺寸需另行确认。</p>
    </div>
    <p v-if="error" role="alert" class="mt-3 rounded bg-red-50 p-3 text-sm text-red-800">{{ error }}</p>
    <div class="mt-4 flex items-center gap-3"><button type="button" :disabled="busy || !preview || !name.trim()" class="rounded-lg bg-teal-700 px-4 py-2 text-white disabled:opacity-50" @click="save">{{ busy ? '处理中…' : `确认并保存为 V${(current?.version ?? 0) + 1}` }}</button><span class="text-xs text-slate-500">保存后应用于同厂区、同供应商、同客户的后续订单。</span></div>
  </section>
</template>
