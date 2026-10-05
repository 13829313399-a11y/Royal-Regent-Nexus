<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { Button } from '@/components/ui/button'

const props = defineProps<{ file: File }>()
const emit = defineEmits<{ save: [file: File]; cancel: [] }>()
type Tool = 'box' | 'arrow' | 'pen' | 'text' | 'redact' | 'crop'
type Snapshot = { width: number; height: number; data: ImageData }
const tools: { id: Tool; label: string }[] = [
  { id: 'box', label: '画框' }, { id: 'arrow', label: '箭头' }, { id: 'pen', label: '画笔' },
  { id: 'text', label: '文字' }, { id: 'redact', label: '遮挡' }, { id: 'crop', label: '裁剪' },
]
const canvas = ref<HTMLCanvasElement | null>(null)
const tool = ref<Tool>('box')
const label = ref('')
const error = ref('')
const loaded = ref(false)
const saving = ref(false)
const history = ref<Snapshot[]>([])
let base: Snapshot | null = null
let origin: { x: number; y: number } | null = null
let previous: { x: number; y: number } | null = null
let disposed = false
const objectUrl = URL.createObjectURL(props.file)

function snapshot(): Snapshot | null {
  const element = canvas.value
  const ctx = element?.getContext('2d')
  return element && ctx ? { width: element.width, height: element.height, data: ctx.getImageData(0, 0, element.width, element.height) } : null
}
function restore(state: Snapshot) {
  if (!canvas.value) return
  canvas.value.width = state.width
  canvas.value.height = state.height
  canvas.value.getContext('2d')?.putImageData(state.data, 0, 0)
}
function point(event: PointerEvent) {
  const element = canvas.value!
  const rect = element.getBoundingClientRect()
  return { x: Math.max(0, Math.min(element.width, (event.clientX - rect.left) * element.width / rect.width)),
    y: Math.max(0, Math.min(element.height, (event.clientY - rect.top) * element.height / rect.height)) }
}
function remember() {
  if (base) history.value = [...history.value.slice(-7), base]
}
function start(event: PointerEvent) {
  if (!loaded.value || saving.value || !canvas.value) return
  error.value = ''
  if (tool.value === 'text' && !label.value.trim()) { error.value = '先填写批注文字，再点图片上的位置。'; return }
  origin = previous = point(event)
  base = snapshot()
  canvas.value.setPointerCapture(event.pointerId)
  if (tool.value === 'text') {
    const ctx = canvas.value.getContext('2d')!
    ctx.font = `bold ${Math.max(20, canvas.value.width / 45)}px "Microsoft YaHei", sans-serif`
    ctx.fillStyle = '#dc2626'
    ctx.strokeStyle = '#ffffff'
    ctx.lineWidth = 4
    ctx.strokeText(label.value.trim(), origin.x, origin.y)
    ctx.fillText(label.value.trim(), origin.x, origin.y)
    remember(); origin = null; base = null
  }
}
function move(event: PointerEvent) {
  if (!origin || !base || !canvas.value) return
  const current = point(event)
  const ctx = canvas.value.getContext('2d')!
  if (tool.value !== 'pen') ctx.putImageData(base.data, 0, 0)
  ctx.strokeStyle = '#dc2626'; ctx.fillStyle = '#dc2626'
  ctx.lineWidth = Math.max(3, canvas.value.width / 400)
  ctx.lineCap = 'round'
  if (tool.value === 'box' || tool.value === 'crop') {
    if (tool.value === 'crop') ctx.setLineDash([8, 5])
    ctx.strokeRect(origin.x, origin.y, current.x - origin.x, current.y - origin.y)
    ctx.setLineDash([])
  } else if (tool.value === 'redact') {
    ctx.fillStyle = '#0f172a'
    ctx.fillRect(origin.x, origin.y, current.x - origin.x, current.y - origin.y)
  } else {
    const from = tool.value === 'pen' ? previous! : origin
    ctx.beginPath(); ctx.moveTo(from.x, from.y); ctx.lineTo(current.x, current.y); ctx.stroke()
    if (tool.value === 'arrow') {
      const angle = Math.atan2(current.y - origin.y, current.x - origin.x)
      const size = Math.max(16, canvas.value.width / 70)
      ctx.beginPath(); ctx.moveTo(current.x, current.y)
      ctx.lineTo(current.x - size * Math.cos(angle - .45), current.y - size * Math.sin(angle - .45))
      ctx.lineTo(current.x - size * Math.cos(angle + .45), current.y - size * Math.sin(angle + .45))
      ctx.closePath(); ctx.fill()
    }
  }
  previous = current
}
function end(event: PointerEvent) {
  if (!origin || !base || !canvas.value) return
  move(event)
  if (tool.value === 'crop') {
    const current = point(event)
    const x = Math.floor(Math.min(origin.x, current.x)), y = Math.floor(Math.min(origin.y, current.y))
    const width = Math.floor(Math.abs(current.x - origin.x)), height = Math.floor(Math.abs(current.y - origin.y))
    canvas.value.getContext('2d')!.putImageData(base.data, 0, 0)
    if (width >= 10 && height >= 10) {
      const cropped = canvas.value.getContext('2d')!.getImageData(x, y, width, height)
      remember(); restore({ width, height, data: cropped })
    }
  } else remember()
  origin = null; base = null; previous = null
}
function cancelStroke() {
  if (base) restore(base)
  origin = null; base = null; previous = null
}
function undo() {
  const state = history.value.at(-1)
  if (state) { restore(state); history.value = history.value.slice(0, -1) }
}
function save() {
  if (!loaded.value || !canvas.value) return
  saving.value = true
  canvas.value.toBlob((blob) => {
    saving.value = false
    if (disposed) return
    if (!blob) { error.value = '图片保存失败，请重试。'; return }
    emit('save', new File([blob], `批注-${props.file.name.replace(/\.[^.]+$/, '').slice(0, 80)}.png`, { type: 'image/png' }))
  }, 'image/png')
}
onMounted(() => {
  const image = new Image()
  image.onload = () => {
    if (disposed || !canvas.value) return
    const scale = Math.min(1, 1600 / Math.max(image.naturalWidth, image.naturalHeight))
    canvas.value.width = Math.max(1, Math.round(image.naturalWidth * scale))
    canvas.value.height = Math.max(1, Math.round(image.naturalHeight * scale))
    canvas.value.getContext('2d')!.drawImage(image, 0, 0, canvas.value.width, canvas.value.height)
    loaded.value = true
  }
  image.onerror = () => { error.value = '无法读取图片，请换一张 PNG、JPG 或 WebP 图片。' }
  image.src = objectUrl
})
onBeforeUnmount(() => { disposed = true; URL.revokeObjectURL(objectUrl) })
</script>

<template>
  <section class="feedback-image-editor" aria-label="截图批注编辑器">
    <div class="feedback-image-editor__tools">
      <Button v-for="item in tools" :key="item.id" type="button" :variant="tool === item.id ? 'default' : 'outline'" size="sm" :aria-pressed="tool === item.id" @click="tool = item.id">{{ item.label }}</Button>
      <Button type="button" variant="outline" size="sm" :disabled="!history.length || saving" @click="undo">撤销</Button>
    </div>
    <label v-if="tool === 'text'" class="feedback-image-editor__label">批注文字<input v-model="label" maxlength="120" placeholder="例如：此处装箱数应为 24" /></label>
    <p class="feedback-image-editor__hint">{{ tool === 'text' ? '输入文字后，点击图片放置。' : '在图片上拖动画出范围；遮挡会覆盖所选内容，保存后只提交编辑后的图片。' }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <div class="feedback-image-editor__canvas"><canvas ref="canvas" aria-label="待批注截图" @pointerdown="start" @pointermove="move" @pointerup="end" @pointercancel="cancelStroke" /></div>
    <div class="feedback-image-editor__tools feedback-image-editor__footer">
      <Button type="button" variant="outline" :disabled="saving" @click="emit('cancel')">取消编辑</Button>
      <Button type="button" :disabled="!loaded || saving" @click="save">{{ saving ? '正在保存…' : '保存批注' }}</Button>
    </div>
  </section>
</template>

<style scoped>
.feedback-image-editor{border:1px solid #cbd5e1;border-radius:12px;padding:14px;background:#fff}.feedback-image-editor__tools{display:flex;gap:6px;flex-wrap:wrap}.feedback-image-editor__hint{font-size:12px;color:#64748b;margin:10px 0;line-height:1.6}.feedback-image-editor__label{display:grid;gap:6px;font-size:13px;margin-top:12px}.feedback-image-editor input{padding:8px;border:1px solid #cbd5e1;border-radius:6px}.feedback-image-editor__canvas{max-height:50vh;overflow:auto;background:#e2e8f0}.feedback-image-editor canvas{display:block;max-width:100%;height:auto;touch-action:none;cursor:crosshair}.feedback-image-editor__footer{justify-content:flex-end;margin-top:12px}
</style>
