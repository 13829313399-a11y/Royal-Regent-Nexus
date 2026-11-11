<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { getDocument, RenderTask } from 'pdfjs-dist/legacy/build/pdf.mjs'
import workerUrl from 'pdfjs-dist/legacy/build/pdf.worker.min.mjs?url'
const props = defineProps<{ file: Blob; token: string }>()
const emit = defineEmits<{ ready: [token: string]; failed: [token: string, message: string] }>()
const root = ref<HTMLElement>(), pages = ref<{ image: string; width: number; height: number; name: string }[]>([])
let epoch = 0, task: ReturnType<typeof getDocument> | undefined, rendering: RenderTask | undefined, sheet: HTMLStyleElement | undefined
function release() { rendering?.cancel(); rendering = undefined; void task?.destroy().catch(() => {}); task = undefined; sheet?.remove(); sheet = undefined; pages.value = [] }
watch(() => [props.file, props.token], async () => {
  const current = ++epoch, token = props.token
  release()
  try {
    const pdf = await import('pdfjs-dist/legacy/build/pdf.mjs')
    const bytes = new Uint8Array(await props.file.arrayBuffer())
    if (current !== epoch) return
    pdf.GlobalWorkerOptions.workerSrc = workerUrl
    const loading = pdf.getDocument({ data: bytes }); task = loading
    const doc = await loading.promise
    if (current !== epoch) return
    if (doc.numPages > 40) throw new Error('打印页数过多，请下载加码 PDF 后分批打印')
    const prepared: typeof pages.value = []
    let pixels = 0
    for (let index = 0; index < doc.numPages; index++) {
      const page = await doc.getPage(index+1)
      if (current !== epoch) return
      const base = page.getViewport({ scale: 1 }), viewport = page.getViewport({ scale: 2 })
      pixels += viewport.width*viewport.height
      if (pixels > 140_000_000) throw new Error('原单打印页过大，请下载加码 PDF 后打印')
      const canvas = document.createElement('canvas'), context = canvas.getContext('2d')
      if (!context) throw new Error('当前浏览器不能绘制原单，请下载加码 PDF 打印')
      canvas.width = Math.ceil(viewport.width); canvas.height = Math.ceil(viewport.height)
      rendering = page.render({ canvas, canvasContext: context, viewport })
      await rendering.promise
      if (current !== epoch) return
      prepared.push({ image: canvas.toDataURL('image/png'), width: base.width, height: base.height, name: `handoverOriginal${index}` })
      canvas.width = canvas.height = 0; page.cleanup()
    }
    if (current !== epoch) return
    pages.value = prepared
    sheet = document.createElement('style'); sheet.dataset.handoverOriginalPrint = ''
    sheet.textContent = prepared.map(page => `@page ${page.name}{size:${page.width}pt ${page.height}pt;margin:0}`).join('\n')
    document.head.append(sheet)
    await nextTick()
    await Promise.all(Array.from(root.value?.querySelectorAll('img') || []).map(img => img.decode?.() || Promise.resolve()))
    if (current !== epoch) return
    emit('ready', token)
  } catch (error) {
    if (current === epoch) {
      release()
      emit('failed', token, error instanceof Error ? error.message : '无法准备加码原单打印页')
    }
  }
}, { immediate: true })
onBeforeUnmount(() => { epoch++; release() })
</script>
<template>
  <div ref="root" class="handover-original-print" aria-hidden="true">
    <div v-for="page in pages" :key="page.name" class="original-print-page" :style="{ page: page.name, '--original-width': `${page.width}pt`, '--original-height': `${page.height}pt` }">
      <img :src="page.image" alt="带交接二维码的原单打印页" />
    </div>
  </div>
</template>
<style scoped>
.handover-original-print { display: none; }
@media print {
  .original-print-page { width: var(--original-width); height: var(--original-height); break-after: page; }
  .original-print-page:last-child { break-after: auto; }
  .original-print-page img { display: block; width: 100%; height: 100%; }
}
</style>
