<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Camera, Paperclip, Pencil, X } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import FeedbackImageEditor from './FeedbackImageEditor.vue'

const props = withDefaults(defineProps<{ modelValue: File[]; disabled?: boolean }>(), { disabled: false })
const emit = defineEmits<{ 'update:modelValue': [files: File[]]; capturing: [active: boolean]; editing: [active: boolean] }>()
const input = ref<HTMLInputElement | null>(null)
const editingIndex = ref<number | null>(null)
const error = ref('')
const capturing = ref(false)
const previews = ref<string[]>([])
const editedFile = computed(() => editingIndex.value === null ? null : props.modelValue[editingIndex.value])
let activeStream: MediaStream | null = null
let disposed = false
function cleanPreviews() { previews.value.forEach(url => { if (url) URL.revokeObjectURL(url) }) }
watch(() => props.modelValue, files => {
  cleanPreviews()
  previews.value = files.map(file => /^image\/(png|jpeg|webp)$/.test(file.type) ? URL.createObjectURL(file) : '')
}, { immediate: true })
watch(editedFile, file => emit('editing', !!file))

function addFiles(files: File[]) {
  if (props.disabled) return
  error.value = ''
  const combined = [...props.modelValue, ...files]
  if (combined.length > 5) { error.value = '每次最多添加 5 个附件。'; return }
  if (combined.some(file => !/\.(png|jpe?g|webp|pdf|xlsx?)$/i.test(file.name))) { error.value = '支持 PNG、JPG、WebP、PDF、XLS 和 XLSX。'; return }
  if (combined.some(file => file.size > 10 * 1024 * 1024)) { error.value = '单个附件不能超过 10 MB。'; return }
  if (combined.reduce((sum, file) => sum + file.size, 0) > 25 * 1024 * 1024) { error.value = '附件总大小不能超过 25 MB。'; return }
  emit('update:modelValue', combined)
}
function upload(event: Event) {
  const target = event.target as HTMLInputElement
  addFiles(Array.from(target.files ?? [])); target.value = ''
}
function paste(event: ClipboardEvent) {
  if (props.disabled) return
  const files = Array.from(event.clipboardData?.items ?? []).filter(item => item.kind === 'file').map(item => item.getAsFile()).filter((file): file is File => !!file)
  if (files.length) { event.preventDefault(); event.stopPropagation(); addFiles(files) }
}
async function capture() {
  error.value = ''
  if (!navigator.mediaDevices?.getDisplayMedia) { error.value = '当前浏览器不支持页面截图，请使用系统截图后粘贴或上传。'; return }
  capturing.value = true; emit('capturing', true)
  try {
    const stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false })
    activeStream = stream
    if (disposed) { stream.getTracks().forEach(track => track.stop()); return }
    const video = document.createElement('video')
    video.srcObject = stream; video.muted = true
    await video.play()
    const image = document.createElement('canvas')
    const scale = Math.min(1, 2000 / Math.max(video.videoWidth, video.videoHeight))
    image.width = Math.max(1, Math.round(video.videoWidth * scale)); image.height = Math.max(1, Math.round(video.videoHeight * scale))
    image.getContext('2d')!.drawImage(video, 0, 0, image.width, image.height)
    stream.getTracks().forEach(track => track.stop()); video.srcObject = null
    const blob = await new Promise<Blob | null>(resolve => image.toBlob(resolve, 'image/png'))
    if (blob && !disposed) addFiles([new File([blob], '页面截图.png', { type: 'image/png' })])
  } catch (cause) {
    if (!disposed) error.value = cause instanceof DOMException && cause.name === 'NotAllowedError' ? '已取消截图，可以粘贴或上传图片。' : '截图未完成，请使用系统截图后粘贴或上传。'
  } finally {
    activeStream?.getTracks().forEach(track => track.stop()); activeStream = null
    capturing.value = false; if (!disposed) emit('capturing', false)
  }
}
function saveImage(file: File) {
  const files = [...props.modelValue]
  if (editingIndex.value === null) return
  files[editingIndex.value] = file
  if (file.size > 10 * 1024 * 1024 || files.reduce((sum, item) => sum + item.size, 0) > 25 * 1024 * 1024) {
    error.value = '编辑后图片过大，请裁剪后再保存。'; return
  }
  emit('update:modelValue', files); editingIndex.value = null
}
defineExpose({ paste })
onBeforeUnmount(() => { disposed = true; activeStream?.getTracks().forEach(track => track.stop()); cleanPreviews() })
</script>

<template>
  <div class="feedback-attachments" @paste="paste">
    <div class="feedback-attachments__actions">
      <Button type="button" variant="outline" size="sm" :disabled="disabled || capturing" @click="input?.click()"><Paperclip class="size-4" /> 添加图片 / 文件</Button>
      <Button type="button" variant="outline" size="sm" :disabled="disabled || capturing" @click="capture"><Camera class="size-4" /> {{ capturing ? '正在截图…' : '截取当前页面' }}</Button>
      <input ref="input" type="file" accept=".png,.jpg,.jpeg,.webp,.pdf,.xls,.xlsx" multiple class="sr-only" aria-label="选择反馈附件" :disabled="disabled" @change="upload" />
    </div>
    <p class="feedback-attachments__hint">可直接粘贴截图；每次最多 5 个文件，单个 10 MB，总计 25 MB。截图可批注、裁剪、遮挡。原始业务文件仅在你添加后发送。</p>
    <p v-if="error" class="feedback-attachments__error" role="alert">{{ error }}</p>
    <ul v-if="modelValue.length" class="feedback-attachments__list">
      <li v-for="(file, index) in modelValue" :key="`${index}-${file.name}`">
        <img v-if="previews[index]" :src="previews[index]" :alt="file.name" />
        <Paperclip v-else class="size-6 text-slate-400" />
        <span><b>{{ file.name }}</b><small>{{ Math.ceil(file.size / 1024) }} KB</small></span>
        <button v-if="previews[index]" type="button" :disabled="disabled" :aria-label="`批注 ${file.name}`" @click="editingIndex = index"><Pencil class="size-4" /></button>
        <button type="button" :disabled="disabled" :aria-label="`移除 ${file.name}`" @click="emit('update:modelValue', modelValue.filter((_, i) => i !== index)); editingIndex = null"><X class="size-4" /></button>
      </li>
    </ul>
    <FeedbackImageEditor v-if="editedFile" :key="`${editingIndex}-${editedFile.name}`" :file="editedFile" @save="saveImage" @cancel="editingIndex = null" />
  </div>
</template>

<style scoped>
.feedback-attachments__actions{display:flex;flex-wrap:wrap;gap:8px}.feedback-attachments__hint{font-size:12px;line-height:1.7;color:#64748b;margin:8px 0}.feedback-attachments__error{font-size:13px;color:#b91c1c}.feedback-attachments__list{list-style:none;padding:0;margin:12px 0;display:grid;gap:8px}.feedback-attachments__list li{display:flex;align-items:center;gap:10px;border:1px solid #e2e8f0;border-radius:8px;padding:8px}.feedback-attachments__list img{width:60px;height:45px;object-fit:cover;border-radius:4px}.feedback-attachments__list span{min-width:0;flex:1;display:grid;gap:3px}.feedback-attachments__list b{font-weight:500;font-size:12px;overflow-wrap:anywhere}.feedback-attachments__list small{color:#64748b;font-size:11px}.feedback-attachments__list button{padding:6px;color:#475569;cursor:pointer}
</style>
