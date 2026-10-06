<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { DialogRoot, DialogOverlay, DialogContent, DialogPortal, DialogTitle, DialogDescription } from 'reka-ui'
import { screenshotRectangle, type ScreenshotMark } from '@/lib/feedbackScreenshot'
const props = defineProps<{ file: File }>()
const emit = defineEmits<{ save: [file: File, notes: string[]]; cancel: [] }>()
const canvas = ref<HTMLCanvasElement | null>(null), marks = ref<ScreenshotMark[]>([])
const ready = ref(false), error = ref(''), saving = ref(false)
let source: HTMLImageElement | null = null, url = '', generation = 0
let start: { x: number; y: number } | null = null
let pending: ScreenshotMark | null = null
function draw() {
  const target = canvas.value, context = target?.getContext('2d')
  if (!target || !context || !source) return
  context.clearRect(0, 0, target.width, target.height); context.drawImage(source, 0, 0, target.width, target.height)
  const scale = Math.max(1, target.width / 1000)
  ;[...marks.value, ...(pending ? [pending] : [])].forEach((mark, index) => {
    context.strokeStyle = '#0284c7'; context.lineWidth = 3 * scale
    context.strokeRect(mark.x, mark.y, mark.width, mark.height)
    const radius = 14 * scale, x = Math.max(radius, Math.min(target.width - radius, mark.x + radius)), y = Math.max(radius, Math.min(target.height - radius, mark.y + radius))
    context.beginPath(); context.arc(x, y, radius, 0, Math.PI * 2); context.fillStyle = '#0284c7'; context.fill()
    context.fillStyle = '#fff'; context.font = `bold ${14 * scale}px sans-serif`; context.textAlign = 'center'; context.textBaseline = 'middle'
    context.fillText(String(index + 1), x, y)
  })
}
function point(event: PointerEvent) {
  const rect = canvas.value!.getBoundingClientRect()
  return { x: (event.clientX - rect.left) * canvas.value!.width / rect.width, y: (event.clientY - rect.top) * canvas.value!.height / rect.height }
}
function begin(event: PointerEvent) {
  if (!ready.value || saving.value || marks.value.length >= 5) return
  start = point(event); canvas.value?.setPointerCapture(event.pointerId)
}
function move(event: PointerEvent) { if (start && canvas.value) { pending = screenshotRectangle(start, point(event), canvas.value.width, canvas.value.height); draw() } }
function finish(event: PointerEvent) {
  move(event)
  if (pending && pending.width > 5 && pending.height > 5) marks.value.push(pending)
  start = null; pending = null; draw()
}
async function save() {
  if (!ready.value || saving.value || !canvas.value) return
  const current = generation
  saving.value = true
  const blob = await new Promise<Blob | null>(resolve => canvas.value!.toBlob(resolve, 'image/png'))
  if (current !== generation) return
  saving.value = false
  if (!blob || blob.size > 5 * 1024 * 1024) { error.value = '标注截图超过 5 MB，请换用更小的图片。'; return }
  emit('save', new File([blob], props.file.name.replace(/\.[^.]+$/, '') + '-批注.png', { type: 'image/png' }), marks.value.map((mark, index) => `${index + 1}. ${mark.note.trim() || '请查看标记区域'}`))
}
watch(() => props.file, async file => {
  const current = ++generation
  if (url) URL.revokeObjectURL(url)
  url = URL.createObjectURL(file); ready.value = false; error.value = ''; marks.value = []; start = null; pending = null
  await nextTick()
  source = new Image()
  source.onload = () => {
    if (current !== generation || !canvas.value || !source) return
    if (source.naturalWidth * source.naturalHeight > 16_000_000) { error.value = '图片像素超过 1600 万，请缩小后重新选择。'; return }
    canvas.value.width = source.naturalWidth; canvas.value.height = source.naturalHeight; ready.value = true; draw()
  }
  source.onerror = () => { if (current === generation) error.value = '无法读取图片，请选择 PNG、JPG 或 WebP 截图。' }
  source.src = url
}, { immediate: true })
onBeforeUnmount(() => { generation++; if (url) URL.revokeObjectURL(url); source = null })
</script>

<template>
  <DialogRoot :open="true" @update:open="emit('cancel')">
    <DialogPortal>
    <DialogOverlay class="fixed inset-0 z-[80] bg-slate-950/60" />
    <DialogContent class="fixed left-1/2 top-1/2 z-[81] max-h-[92dvh] w-[calc(100%_-_2rem)] max-w-5xl -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl bg-white p-4 sm:p-6">
      <DialogTitle class="text-lg font-bold">截图批注</DialogTitle>
      <DialogDescription class="mt-1 text-sm text-slate-500">拖动框选问题位置，自动加编号。每张最多 5 个标记，可在下方补充说明。</DialogDescription>
      <p v-if="error" role="alert" class="mt-3 text-sm text-red-700">{{ error }}</p>
      <canvas ref="canvas" aria-label="框选截图问题区域" class="mt-4 w-full touch-none rounded-lg border border-slate-200" @pointerdown="begin" @pointermove="move" @pointerup="finish" @pointercancel="start = null; pending = null; draw()" />
      <label v-for="(mark, index) in marks" :key="index" class="mt-3 flex items-center gap-2 text-sm"><span class="font-bold text-sky-700">{{ index + 1 }}</span><input v-model="mark.note" :aria-label="`截图标记 ${index + 1} 说明`" maxlength="120" placeholder="说明这个位置的问题" class="min-w-0 flex-1 rounded-lg border p-2"></label>
      <div class="mt-4 flex flex-wrap justify-end gap-2">
        <button type="button" :disabled="saving || !marks.length" class="rounded-lg border px-3 py-2 text-sm disabled:opacity-50" @click="marks.pop(); draw()">撤销上一个标记</button>
        <button type="button" :disabled="saving" class="rounded-lg border px-3 py-2 text-sm" @click="emit('cancel')">取消</button>
        <button type="button" :disabled="!ready || saving" class="rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" @click="save">使用这张截图</button>
      </div>
    </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
