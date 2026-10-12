<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { getDocument, GlobalWorkerOptions, type RenderTask } from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
GlobalWorkerOptions.workerSrc = workerUrl
const props = defineProps<{ file: Blob; token: string }>()
const emit = defineEmits<{ ready: [token: string]; failed: [token: string, message: string] }>()
const root = ref<HTMLElement>(), pages = ref<{ image: string; width: number; height: number; name: string }[]>([])
const progress = ref('正在绘制加码原单…')
let epoch = 0, task: ReturnType<typeof getDocument> | undefined, rendering: RenderTask | undefined, sheet: HTMLStyleElement | undefined
function release() { rendering?.cancel(); rendering = undefined; void task?.destroy().catch(() => {}); task = undefined; sheet?.remove(); sheet = undefined; pages.value = [] }
watch(() => [props.file, props.token], async () => {
  const current = ++epoch, token = props.token
  release(); progress.value = '正在绘制加码原单…'
  try {
    const bytes = new Uint8Array(await props.file.arrayBuffer())
    if (current !== epoch) return
    const loading = getDocument({ data: bytes }); task = loading
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
      if (pixels > 140_000_000) throw new Error('原单预览过大，请下载加码 PDF 后打印')
      const canvas = document.createElement('canvas'), context = canvas.getContext('2d')
      if (!context) throw new Error('当前浏览器不能绘制原单，请下载加码 PDF 打印')
      canvas.width = Math.ceil(viewport.width); canvas.height = Math.ceil(viewport.height)
      rendering = page.render({ canvas, canvasContext: context, viewport })
      await rendering.promise
      if (current !== epoch) return
      prepared.push({ image: canvas.toDataURL('image/png'), width: base.width, height: base.height, name: `handoverOriginal${index}` })
      canvas.width = canvas.height = 0; page.cleanup()
      progress.value = `正在绘制加码原单 ${index+1} / ${doc.numPages} 页…`
    }
    if (current !== epoch) return
    pages.value = prepared
    sheet = document.createElement('style'); sheet.dataset.handoverOriginalPrint = ''
    sheet.textContent = prepared.map(page => `@page ${page.name}{size:${page.width}pt ${page.height}pt;margin:0}`).join('\n')
    document.head.append(sheet)
    await nextTick()
    await Promise.all(Array.from(root.value?.querySelectorAll('img') || []).map(img => img.decode?.() || Promise.resolve()))
    if (current !== epoch) return
    progress.value = ''; emit('ready', token)
  } catch (error) {
    if (current === epoch) { progress.value = ''; pages.value = []; emit('failed', token, error instanceof Error ? error.message : '原单预览失败') }
  }
}, { immediate: true })
onBeforeUnmount(() => { epoch++; release() })
</script>
<template>
  <section ref="root" class="original-print-preview">
    <div class="original-preview-heading"><h2>原单加码打印预览</h2><p>保留原单内容，顶部预留二维码位置。请核对文字、分页与缸号；识别明细有修改时附系统确认明细。</p><p v-if="progress" role="status">{{ progress }}</p></div>
    <div class="original-print-pages"><div v-for="page in pages" :key="page.name" class="original-print-page" :style="{ page: page.name, '--original-width': `${page.width}pt`, '--original-height': `${page.height}pt` }"><img :src="page.image" alt="带交接二维码的原单打印页" /></div></div>
  </section>
</template>
<style scoped>
.original-print-preview{margin:20px 0;background:white;border:1px solid #dce5e1;border-radius:10px;padding:20px}.original-preview-heading h2{font-size:18px;font-weight:650}.original-preview-heading p{color:#667a73;margin:8px 0;font-size:13px}.original-print-pages{max-height:650px;overflow:auto;padding:12px;background:#e8eee9}.original-print-page{width:var(--original-width);max-width:100%;margin:0 auto 16px;box-shadow:0 1px 6px #243b3020;background:white}.original-print-page img{display:block;width:100%;height:auto}@media print{.original-print-preview{margin:0!important;padding:0!important;border:0!important;border-radius:0!important}.original-preview-heading{display:none!important}.original-print-pages{max-height:none;overflow:visible;padding:0;background:white}.original-print-page{max-width:none;width:var(--original-width);height:var(--original-height);margin:0;box-shadow:none;break-after:page}.original-print-page:last-child{break-after:auto}.original-print-page img{width:100%;height:100%}}
</style>
