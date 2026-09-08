<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import {
  getDocument,
  GlobalWorkerOptions,
  TextLayer,
  type PDFDocumentProxy,
  type PDFPageProxy,
  type RenderTask,
} from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { Button } from '@/components/ui/button'
import { normalizeCuts, pointerToVisiblePoint, ptToMm } from './coordinates'
import PdfThumbnail from './PdfThumbnail.vue'
GlobalWorkerOptions.workerSrc = workerUrl
const props = withDefaults(
  defineProps<{
    url: string
    pageIndex?: number
    cuts?: number[]
    snapPoints?: number[]
    axis?: 'x' | 'y'
    editing?: boolean
    highlight?: number[] | null
    selectRegion?: boolean
  }>(),
  {
    pageIndex: 0,
    cuts: () => [],
    snapPoints: () => [],
    axis: 'y',
    editing: false,
    highlight: null,
    selectRegion: false,
  },
)
const emit = defineEmits<{
  page: [index: number]
  cuts: [values: number[]]
  region: [bbox: number[]]
  dimensions: [size: { width: number; height: number }]
}>()
const canvas = ref<HTMLCanvasElement>(),
  textContainer = ref<HTMLElement>(),
  paper = ref<HTMLElement>(),
  container = ref<HTMLElement>()
const loading = ref(false),
  showThumbnails = ref(false),
  snapping = ref(true),
  error = ref(''),
  pageCount = ref(0),
  zoom = ref(1),
  width = ref(0),
  height = ref(0),
  selection = ref<number[] | null>(null)
let doc: PDFDocumentProxy | undefined,
  page: PDFPageProxy | undefined,
  renderTask: RenderTask | undefined,
  generation = 0
let loadingTask: ReturnType<typeof getDocument> | undefined
let textLayer: TextLayer | undefined
let renderGeneration = 0
let viewport: ReturnType<PDFPageProxy['getViewport']> | undefined,
  visible: ReturnType<PDFPageProxy['getViewport']> | undefined
let drag:
  | { index?: number; start: [number, number]; current?: number }
  | undefined
const activeBox = computed(() => selection.value ?? props.highlight)
const boxStyle = computed(() => {
  const b = activeBox.value
  return b
    ? {
        left: `${(b[0]! / width.value) * 100}%`,
        top: `${(b[1]! / height.value) * 100}%`,
        width: `${((b[2]! - b[0]!) / width.value) * 100}%`,
        height: `${((b[3]! - b[1]!) / height.value) * 100}%`,
      }
    : {}
})
async function load() {
  const ticket = ++generation
  error.value = ''
  loading.value = true
  renderTask?.cancel()
  await loadingTask?.destroy()
  doc = undefined
  try {
    loadingTask = getDocument({ url: props.url, withCredentials: true })
    const loaded = await loadingTask.promise
    if (ticket !== generation) {
      return
    }
    doc = loaded
    pageCount.value = doc.numPages
    await render()
  } catch (reason) {
    if (ticket === generation)
      error.value =
        reason instanceof Error ? reason.message : 'PDF 预览加载失败'
  } finally {
    if (ticket === generation) loading.value = false
  }
}
async function render() {
  if (!doc) return
  const ticket = ++renderGeneration
  const previousTask = renderTask
  renderTask?.cancel()
  textLayer?.cancel()
  loading.value = true
  try {
    await previousTask?.promise.catch(() => undefined)
    const loadedPage = await doc.getPage(
      Math.min(doc.numPages, props.pageIndex + 1),
    )
    if (ticket !== renderGeneration) return
    page?.cleanup()
    page = loadedPage
    visible = page.getViewport({ scale: 1 })
    width.value = visible.width
    height.value = visible.height
    emit('dimensions', { width: width.value, height: height.value })
    viewport = page.getViewport({ scale: zoom.value })
    await nextTick()
    if (ticket !== renderGeneration) return
    if (!canvas.value) return
    const dpr = Math.min(window.devicePixelRatio || 1, 2),
      context = canvas.value.getContext('2d')
    if (!context) return
    canvas.value.width = Math.ceil(viewport.width * dpr)
    canvas.value.height = Math.ceil(viewport.height * dpr)
    renderTask = page.render({
      canvas: canvas.value,
      canvasContext: context,
      viewport,
      transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : undefined,
    })
    await renderTask.promise
    if (ticket !== renderGeneration) return
    if (textContainer.value) {
      textContainer.value.replaceChildren()
      textContainer.value.style.setProperty(
        '--total-scale-factor',
        String(zoom.value * page.userUnit),
      )
      textLayer = new TextLayer({
        textContentSource: page.streamTextContent(),
        container: textContainer.value,
        viewport,
      })
      await textLayer.render()
    }
    error.value = ''
  } catch (reason) {
    if (
      ticket === renderGeneration &&
      !(
        reason instanceof Error && reason.name === 'RenderingCancelledException'
      )
    )
      error.value = reason instanceof Error ? reason.message : '页面渲染失败'
  } finally {
    if (ticket === renderGeneration) loading.value = false
  }
}
function point(event: PointerEvent): [number, number] {
  return pointerToVisiblePoint(
    event.clientX,
    event.clientY,
    paper.value!.getBoundingClientRect(),
    viewport!,
    visible!,
  )
}
function start(event: PointerEvent, index?: number) {
  if (
    (!props.selectRegion && index === undefined) ||
    !paper.value ||
    !viewport ||
    !visible
  )
    return
  event.preventDefault()
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  drag = { index, start: point(event) }
}
function move(event: PointerEvent) {
  if (!drag) return
  const p = point(event)
  if (drag.index !== undefined) {
    drag.current = p[props.axis === 'x' ? 0 : 1]
    if (snapping.value) {
      const nearby = props.snapPoints
        .filter((value) => Math.abs(value - drag!.current!) <= 6 / zoom.value)
        .sort(
          (a, b) => Math.abs(a - drag!.current!) - Math.abs(b - drag!.current!),
        )
      if (nearby.length) drag.current = nearby[0]
    }
    const line = paper.value?.querySelector<HTMLElement>(
      `[data-cut="${drag.index}"]`,
    )
    if (line)
      line.style[props.axis === 'x' ? 'left' : 'top'] =
        `${(drag.current / (props.axis === 'x' ? width.value : height.value)) * 100}%`
  } else
    selection.value = [
      Math.min(p[0], drag.start[0]),
      Math.min(p[1], drag.start[1]),
      Math.max(p[0], drag.start[0]),
      Math.max(p[1], drag.start[1]),
    ]
}
function finish() {
  if (!drag) return
  if (drag.index !== undefined && drag.current !== undefined) {
    const values = [...props.cuts]
    values[drag.index] = drag.current
    emit(
      'cuts',
      normalizeCuts(values, props.axis === 'x' ? width.value : height.value),
    )
  } else if (
    selection.value &&
    selection.value[2]! - selection.value[0]! > 2 &&
    selection.value[3]! - selection.value[1]! > 2
  )
    emit('region', selection.value)
  drag = undefined
}
function nudge(event: KeyboardEvent, index: number) {
  if (
    !['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Delete'].includes(
      event.key,
    )
  )
    return
  event.preventDefault()
  const values = [...props.cuts]
  if (event.key === 'Delete') values.splice(index, 1)
  else
    values[index] =
      values[index]! +
      (['ArrowUp', 'ArrowLeft'].includes(event.key) ? -1 : 1) *
        (event.shiftKey ? 10 : 0.5)
  emit(
    'cuts',
    normalizeCuts(values, props.axis === 'x' ? width.value : height.value),
  )
}
function fit() {
  zoom.value = Math.max(
    0.1,
    Math.min(
      2,
      ((container.value?.clientWidth ?? 600) - 48) / (width.value || 600),
    ),
  )
}
async function loadThumbnailPage(index: number) {
  if (!doc) throw new Error('尚未加载文档')
  return doc.getPage(index + 1)
}
watch(() => props.url, load, { immediate: true })
watch(
  () => props.pageIndex,
  () => {
    selection.value = null
    void render()
  },
)
watch(zoom, () => {
  void render()
})
watch(
  () => props.highlight,
  async () => {
    selection.value = null
    await nextTick()
    paper.value?.querySelector('.dt-source-highlight')?.scrollIntoView({
      block: 'center',
      inline: 'center',
      behavior: 'instant',
    })
  },
)
onBeforeUnmount(() => {
  generation++
  renderGeneration++
  textLayer?.cancel()
  renderTask?.cancel()
  void loadingTask?.destroy()
  page?.cleanup()
})
</script>

<template>
  <section class="dt-pdf" aria-label="PDF 文档预览">
    <div class="dt-pdf-toolbar">
      <Button
        variant="ghost"
        size="sm"
        :disabled="pageIndex <= 0"
        @click="emit('page', pageIndex - 1)"
        >上一页</Button
      >
      <label
        >页
        <input
          aria-label="预览页码"
          type="number"
          :value="pageIndex + 1"
          min="1"
          :max="pageCount"
          @change="
            emit(
              'page',
              Math.max(
                0,
                Math.min(
                  pageCount - 1,
                  Number(($event.target as HTMLInputElement).value) - 1,
                ),
              ),
            )
          "
        />
        / {{ pageCount }}</label
      >
      <Button
        variant="ghost"
        size="sm"
        :disabled="pageIndex >= pageCount - 1"
        @click="emit('page', pageIndex + 1)"
        >下一页</Button
      >
      <select v-model.number="zoom" aria-label="预览缩放">
        <option :value="0.5">50%</option>
        <option :value="0.75">75%</option>
        <option :value="1">100%</option>
        <option :value="1.5">150%</option>
        <option :value="2">200%</option>
        <option v-if="![0.5, 0.75, 1, 1.5, 2].includes(zoom)" :value="zoom">
          {{ Math.round(zoom * 100) }}%
        </option>
      </select>
      <Button variant="ghost" size="sm" @click="fit">适合宽度</Button>
      <Button
        variant="ghost"
        size="sm"
        :aria-pressed="showThumbnails"
        @click="showThumbnails = !showThumbnails"
        >缩略图</Button
      >
      <label v-if="editing" class="dt-snap"
        ><input v-model="snapping" type="checkbox" />吸附到建议 / 行边界</label
      >
    </div>
    <div
      v-if="showThumbnails && pageCount"
      class="dt-thumbnail-strip"
      aria-label="页面缩略图"
    >
      <PdfThumbnail
        v-for="index in pageCount"
        :key="index"
        :index="index - 1"
        :selected="index - 1 === pageIndex"
        :load-page="loadThumbnailPage"
        @select="emit('page', $event)"
      />
    </div>
    <p v-if="error" role="alert" class="dt-pdf-error">
      {{ error }}
      <Button variant="outline" size="sm" @click="load">重试预览</Button>
    </p>
    <div ref="container" class="dt-pdf-scroll" :aria-busy="loading">
      <p v-if="loading" class="dt-loading" role="status">正在加载页面…</p>
      <div
        v-if="!error"
        ref="paper"
        class="dt-paper"
        :class="{ selecting: selectRegion }"
        :style="{ width: `${width * zoom}px`, height: `${height * zoom}px` }"
        @pointerdown="start($event)"
        @pointermove="move"
        @pointerup="finish"
        @pointercancel="finish"
      >
        <canvas
          ref="canvas"
          :style="{ width: `${width * zoom}px`, height: `${height * zoom}px` }"
          aria-label="当前 PDF 页面；可用结果来源定位或下载原文查看文字"
        />
        <div
          ref="textContainer"
          class="dt-text-layer"
          :class="{ 'dt-text-inactive': selectRegion }"
        />
        <div v-if="activeBox" class="dt-source-highlight" :style="boxStyle" />
        <div v-if="editing" class="dt-ruler" aria-hidden="true">
          <span
            v-for="tick in 11"
            :key="tick"
            :style="{ top: `${(tick - 1) * 10}%` }"
            >{{ Math.round(ptToMm((height * (tick - 1)) / 10)) }}</span
          >
        </div>
        <button
          v-for="(cut, index) in editing ? cuts : []"
          :key="index"
          :data-cut="index"
          type="button"
          class="dt-cut"
          :class="axis"
          :style="
            axis === 'y'
              ? { top: `${(cut / height) * 100}%` }
              : { left: `${(cut / width) * 100}%` }
          "
          :aria-label="`切线 ${index + 1}，${ptToMm(cut).toFixed(1)} 毫米；方向键微调，Delete 删除`"
          @pointerdown.stop="start($event, index)"
          @pointermove.stop="move"
          @pointerup.stop="finish"
          @keydown="nudge($event, index)"
        >
          <span>{{ index + 1 }} · {{ ptToMm(cut).toFixed(1) }} mm</span>
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.dt-snap{display:flex;align-items:center;gap:5px}.dt-pdf-toolbar .dt-snap input{width:auto;accent-color:var(--primary)}
.dt-thumbnail-strip {
  display: flex;
  overflow-x: auto;
  gap: 8px;
  padding: 10px;
  background: var(--muted);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.dt-text-layer {
  position: absolute;
  inset: 0;
  text-align: initial;
  overflow: clip;
  line-height: 1;
  letter-spacing: normal;
  word-spacing: normal;
  text-size-adjust: none;
  transform-origin: 0 0;
  --min-font-size: 1;
  --text-scale-factor: calc(var(--total-scale-factor) * var(--min-font-size));
  --min-font-size-inv: calc(1 / var(--min-font-size));
}
.dt-text-layer :deep(span),
.dt-text-layer :deep(br) {
  color: transparent;
  position: absolute;
  white-space: pre;
  cursor: text;
  transform-origin: 0% 0%;
  user-select: text;
}
.dt-text-layer :deep(span:not(.markedContent)) {
  --font-height: 0;
  font-size: calc(var(--text-scale-factor) * var(--font-height));
  --scale-x: 1;
  --rotate: 0deg;
  transform: rotate(var(--rotate)) scaleX(var(--scale-x))
    scale(var(--min-font-size-inv));
}
.dt-text-layer :deep(.markedContent) {
  display: contents;
}
.dt-text-layer :deep(::selection) {
  background: color-mix(in srgb, var(--primary) 30%, transparent);
  color: transparent;
}
.dt-text-inactive {
  pointer-events: none;
}
.dt-pdf {
  min-width: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 350px;
}
.dt-pdf-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 3px;
  padding: 6px;
  background: var(--card);
  border-bottom: 1px solid var(--border);
  font-size: 12px;
}
.dt-pdf-toolbar input {
  width: 48px;
  padding: 4px;
}
.dt-pdf-toolbar select {
  max-width: 76px;
}
.dt-pdf-scroll {
  position: relative;
  overflow: auto;
  min-height: 260px;
  flex: 1;
  padding: 24px;
  background: var(--muted);
}
.dt-paper {
  position: relative;
  margin: 0 auto;
  background: white;
  box-shadow: 0 1px 6px #152e2c22;
  touch-action: pan-x pan-y;
}
.dt-paper.selecting {
  touch-action: none;
  cursor: crosshair;
}
.dt-paper canvas {
  display: block;
}
.dt-source-highlight {
  position: absolute;
  pointer-events: none;
  border: 2px solid var(--primary);
  background: color-mix(in oklch, var(--primary) 15%, transparent);
}
.dt-cut {
  position: absolute;
  border: 0;
  background: transparent;
  padding: 0;
  z-index: 2;
  touch-action: none;
}
.dt-cut.y {
  height: 16px;
  left: 0;
  width: 100%;
  transform: translateY(-50%);
  cursor: ns-resize;
  border-top: 1px dashed var(--primary);
}
.dt-cut.x {
  width: 16px;
  top: 0;
  height: 100%;
  transform: translateX(-50%);
  cursor: ew-resize;
  border-left: 1px dashed var(--primary);
}
.dt-cut span {
  position: absolute;
  left: 0;
  top: 0;
  background: var(--primary);
  color: white;
  font-size: 11px;
  padding: 2px 5px;
  white-space: nowrap;
}
.dt-cut:focus-visible {
  outline: 3px solid var(--ring);
}
.dt-ruler {
  position: absolute;
  left: -23px;
  top: 0;
  bottom: 0;
  width: 22px;
  font-size: 9px;
  color: var(--muted-foreground);
  pointer-events: none;
}
.dt-ruler span {
  position: absolute;
}
.dt-loading {
  position: absolute;
  top: 3px;
  left: 12px;
  background: var(--card);
  z-index: 3;
  font-size: 12px;
}
.dt-pdf-error {
  padding: 16px;
  color: var(--destructive);
}
</style>
