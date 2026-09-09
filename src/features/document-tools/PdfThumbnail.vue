<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import type { PDFPageProxy, RenderTask } from 'pdfjs-dist'
const props = defineProps<{
  index: number
  selected: boolean
  loadPage: (index: number) => Promise<PDFPageProxy>
}>()
const emit = defineEmits<{ select: [index: number] }>()
const root = ref<HTMLButtonElement>(),
  canvas = ref<HTMLCanvasElement>(),
  failed = ref(false)
let observer: IntersectionObserver | undefined,
  task: RenderTask | undefined,
  disposed = false
async function render() {
  try {
    const page = await props.loadPage(props.index)
    if (disposed || !canvas.value) return
    const base = page.getViewport({ scale: 1 })
    const viewport = page.getViewport({
      scale: Math.min(72 / base.width, 92 / base.height),
    })
    const context = canvas.value.getContext('2d')
    if (!context) return
    canvas.value.width = viewport.width
    canvas.value.height = viewport.height
    task = page.render({
      canvas: canvas.value,
      canvasContext: context,
      viewport,
    })
    await task.promise
  } catch {
    if (!disposed) failed.value = true
  }
}
onMounted(() => {
  if (typeof IntersectionObserver !== 'undefined') {
    observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          observer?.disconnect()
          void render()
        }
      },
      { rootMargin: '80px' },
    )
    if (root.value) observer.observe(root.value)
  } else void render()
})
onBeforeUnmount(() => {
  disposed = true
  observer?.disconnect()
  task?.cancel()
})
</script>

<template>
  <button
    ref="root"
    type="button"
    class="dt-thumbnail"
    :class="{ selected }"
    :aria-label="`转到第 ${index + 1} 页`"
    :aria-pressed="selected"
    @click="emit('select', index)"
  >
    <canvas ref="canvas" aria-hidden="true" /><span
      >{{ index + 1 }}{{ failed ? ' · 预览不可用' : '' }}</span
    >
  </button>
</template>

<style scoped>
.dt-thumbnail {
  min-width: 88px;
  width: 88px;
  height: 120px;
  padding: 8px 5px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  gap: 5px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--muted-foreground);
  font-size: 11px;
}
.dt-thumbnail canvas {
  max-width: 72px;
  max-height: 92px;
  object-fit: contain;
}
.dt-thumbnail.selected {
  border: 2px solid var(--primary);
  color: var(--primary);
}
.dt-thumbnail:focus-visible {
  outline: 2px solid var(--ring);
  outline-offset: 2px;
}
</style>
