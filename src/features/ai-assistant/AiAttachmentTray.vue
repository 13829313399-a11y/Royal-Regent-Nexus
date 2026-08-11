<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { ImagePlus, Trash2, X } from '@lucide/vue'
import type {
  AIAttachmentMediaType,
  AICloudProcessingConsent,
  AIRequestAttachment,
} from './types'

const MAX_ATTACHMENT_COUNT = 3
const MAX_ATTACHMENT_BYTES = 4 * 1024 * 1024
const MAX_TOTAL_ATTACHMENT_BYTES = 12 * 1024 * 1024
const MAX_IMAGE_PIXELS = 16_000_000
const MAX_TOTAL_IMAGE_PIXELS = 24_000_000
const CLOUD_PROCESSING_NOTICE = '本次图片将发送至阿里云百炼华北2（北京），由qwen3.7-plus处理；store=false不代表供应商零留存，调用数据可能依法存储'
const CLOUD_PROCESSING_NOTICE_VERSION = 'aliyun-cn-beijing-v1' as const

interface LocalAttachment {
  id: string
  file: File
  mediaType: AIAttachmentMediaType
  pixelCount: number
  previewUrl: string
}

interface ValidatedImageInfo {
  mediaType: AIAttachmentMediaType
  pixelCount: number
}

interface ImageDimensions {
  width: number
  height: number
  animated?: boolean
}

interface PreparedAttachmentBatch {
  attachments: AIRequestAttachment[]
  consent: AICloudProcessingConsent | null
}

const props = defineProps<{
  disabled?: boolean
}>()

const fileInput = ref<HTMLInputElement | null>(null)
const attachments = ref<LocalAttachment[]>([])
const cloudProcessingConsent = ref(false)
const errorMessage = ref('')
const isPreparing = ref(false)
const activeReaders = new Set<FileReader>()
let lifecycleGeneration = 0
let consentGeneration = 0
let localSequence = 0
let additionQueue: Promise<void> = Promise.resolve()

const hasAttachments = computed(() => attachments.value.length > 0)

function attachmentId() {
  localSequence += 1
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return `image-${globalThis.crypto.randomUUID()}`
  }
  return `image-${Date.now()}-${localSequence}`
}

function detectedMediaType(bytes: Uint8Array): AIAttachmentMediaType | null {
  if (
    bytes.length >= 8
    && bytes[0] === 0x89
    && bytes[1] === 0x50
    && bytes[2] === 0x4e
    && bytes[3] === 0x47
    && bytes[4] === 0x0d
    && bytes[5] === 0x0a
    && bytes[6] === 0x1a
    && bytes[7] === 0x0a
  ) return 'image/png'
  if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) {
    return 'image/jpeg'
  }
  if (
    bytes.length >= 12
    && bytes[0] === 0x52
    && bytes[1] === 0x49
    && bytes[2] === 0x46
    && bytes[3] === 0x46
    && bytes[8] === 0x57
    && bytes[9] === 0x45
    && bytes[10] === 0x42
    && bytes[11] === 0x50
  ) return 'image/webp'
  return null
}

function uint16BigEndian(bytes: Uint8Array, offset: number) {
  return ((bytes[offset] ?? 0) << 8) | (bytes[offset + 1] ?? 0)
}

function uint16LittleEndian(bytes: Uint8Array, offset: number) {
  return (bytes[offset] ?? 0) | ((bytes[offset + 1] ?? 0) << 8)
}

function uint24LittleEndian(bytes: Uint8Array, offset: number) {
  return (bytes[offset] ?? 0)
    | ((bytes[offset + 1] ?? 0) << 8)
    | ((bytes[offset + 2] ?? 0) << 16)
}

function uint32BigEndian(bytes: Uint8Array, offset: number) {
  return ((bytes[offset] ?? 0) * 0x1000000)
    + ((bytes[offset + 1] ?? 0) << 16)
    + ((bytes[offset + 2] ?? 0) << 8)
    + (bytes[offset + 3] ?? 0)
}

function uint32LittleEndian(bytes: Uint8Array, offset: number) {
  return (bytes[offset] ?? 0)
    + ((bytes[offset + 1] ?? 0) * 0x100)
    + ((bytes[offset + 2] ?? 0) * 0x10000)
    + ((bytes[offset + 3] ?? 0) * 0x1000000)
}

function asciiChunkType(bytes: Uint8Array, offset: number) {
  return String.fromCharCode(
    bytes[offset] ?? 0,
    bytes[offset + 1] ?? 0,
    bytes[offset + 2] ?? 0,
    bytes[offset + 3] ?? 0,
  )
}

function pngDimensions(bytes: Uint8Array): ImageDimensions | null {
  if (
    bytes.length < 24
    || uint32BigEndian(bytes, 8) !== 13
    || bytes[12] !== 0x49
    || bytes[13] !== 0x48
    || bytes[14] !== 0x44
    || bytes[15] !== 0x52
  ) return null
  return {
    width: uint32BigEndian(bytes, 16),
    height: uint32BigEndian(bytes, 20),
  }
}

const JPEG_START_OF_FRAME_MARKERS = new Set([
  0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7,
  0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf,
])

function jpegDimensions(bytes: Uint8Array): ImageDimensions | null {
  if (bytes.length < 4 || bytes[0] !== 0xff || bytes[1] !== 0xd8) return null
  let offset = 2
  let frame: ImageDimensions | null = null
  while (offset < bytes.length) {
    while (offset < bytes.length && bytes[offset] === 0xff) offset += 1
    if (offset >= bytes.length) return null
    const marker = bytes[offset] ?? 0
    offset += 1
    if (marker === 0xd9 || marker === 0xda) return frame
    if (marker === 0x01 || marker === 0xd8 || (marker >= 0xd0 && marker <= 0xd7)) continue
    if (offset + 1 >= bytes.length) return null
    const segmentLength = uint16BigEndian(bytes, offset)
    if (segmentLength < 2 || offset + segmentLength > bytes.length) return null
    if (JPEG_START_OF_FRAME_MARKERS.has(marker)) {
      if (segmentLength < 8 || frame) return null
      frame = {
        width: uint16BigEndian(bytes, offset + 5),
        height: uint16BigEndian(bytes, offset + 3),
      }
    }
    offset += segmentLength
  }
  return null
}

function webpFrameDimensions(
  bytes: Uint8Array,
  chunkType: 'VP8 ' | 'VP8L',
  dataOffset: number,
  chunkSize: number,
): ImageDimensions | null {
  if (chunkType === 'VP8 ') {
    if (
      chunkSize < 10
      || bytes[dataOffset + 3] !== 0x9d
      || bytes[dataOffset + 4] !== 0x01
      || bytes[dataOffset + 5] !== 0x2a
    ) return null
    return {
      width: uint16LittleEndian(bytes, dataOffset + 6) & 0x3fff,
      height: uint16LittleEndian(bytes, dataOffset + 8) & 0x3fff,
    }
  }
  if (chunkSize < 5 || bytes[dataOffset] !== 0x2f) return null
  const first = bytes[dataOffset + 1] ?? 0
  const second = bytes[dataOffset + 2] ?? 0
  const third = bytes[dataOffset + 3] ?? 0
  const fourth = bytes[dataOffset + 4] ?? 0
  return {
    width: 1 + first + ((second & 0x3f) << 8),
    height: 1 + (second >> 6) + (third << 2) + ((fourth & 0x0f) << 10),
  }
}

function webpDimensions(bytes: Uint8Array): ImageDimensions | null {
  if (bytes.length < 25) return null
  const declaredEnd = uint32LittleEndian(bytes, 4) + 8
  if (declaredEnd < 25 || declaredEnd > bytes.length) return null
  let offset = 12
  let canvas: ImageDimensions | null = null
  let frame: ImageDimensions | null = null
  let animated = false
  while (offset + 8 <= declaredEnd) {
    const chunkType = asciiChunkType(bytes, offset)
    const chunkSize = uint32LittleEndian(bytes, offset + 4)
    const dataOffset = offset + 8
    const dataEnd = dataOffset + chunkSize
    if (dataEnd > declaredEnd) return null
    if (chunkType === 'VP8X') {
      if (offset !== 12 || chunkSize !== 10) return null
      canvas = {
        width: uint24LittleEndian(bytes, dataOffset + 4) + 1,
        height: uint24LittleEndian(bytes, dataOffset + 7) + 1,
      }
      animated = Boolean((bytes[dataOffset] ?? 0) & 0x02)
    } else if (chunkType === 'ANIM' || chunkType === 'ANMF') {
      animated = true
    } else if (chunkType === 'VP8 ' || chunkType === 'VP8L') {
      if (frame) return null
      frame = webpFrameDimensions(bytes, chunkType, dataOffset, chunkSize)
      if (!frame) return null
    }
    offset = dataEnd + (chunkSize % 2)
  }
  if (offset !== declaredEnd || !frame) return null
  if (!canvas) return { ...frame, animated }
  if (frame.width > canvas.width || frame.height > canvas.height) return null
  return { ...canvas, animated }
}

function imageDimensions(bytes: Uint8Array, mediaType: AIAttachmentMediaType) {
  if (mediaType === 'image/png') return pngDimensions(bytes)
  if (mediaType === 'image/jpeg') return jpegDimensions(bytes)
  return webpDimensions(bytes)
}

async function validateFile(file: File): Promise<ValidatedImageInfo | null> {
  if (!file.size) {
    errorMessage.value = '不能添加空图片。'
    return null
  }
  if (file.size > MAX_ATTACHMENT_BYTES) {
    errorMessage.value = '单张图片不能超过 4 MiB。'
    return null
  }
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
    errorMessage.value = '仅支持 PNG、JPEG 或 WebP 图片。'
    return null
  }
  let bytes: Uint8Array
  try {
    bytes = new Uint8Array(await file.arrayBuffer())
  } catch {
    errorMessage.value = '无法读取该图片，请重新选择。'
    return null
  }
  const detected = detectedMediaType(bytes)
  if (!detected || detected !== file.type) {
    errorMessage.value = '图片类型与文件内容不一致，已拒绝添加。'
    return null
  }
  const dimensions = imageDimensions(bytes, detected)
  if (!dimensions || dimensions.width < 1 || dimensions.height < 1) {
    errorMessage.value = '无法安全读取图片尺寸，已拒绝添加。'
    return null
  }
  if (dimensions.animated) {
    errorMessage.value = '不支持动画 WebP 图片。'
    return null
  }
  const pixelCount = dimensions.width * dimensions.height
  if (
    dimensions.width > MAX_IMAGE_PIXELS
    || dimensions.height > MAX_IMAGE_PIXELS
    || pixelCount > MAX_IMAGE_PIXELS
  ) {
    errorMessage.value = '单张图片不能超过 1600 万像素。'
    return null
  }
  return { mediaType: detected, pixelCount }
}

async function addFilesBatch(files: File[], generation: number) {
  if (props.disabled || generation !== lifecycleGeneration || !files.length) return
  resetConsent()
  errorMessage.value = ''
  if (attachments.value.length + files.length > MAX_ATTACHMENT_COUNT) {
    errorMessage.value = '每次最多添加 3 张图片。'
    return
  }
  const existingBytes = attachments.value.reduce((total, item) => total + item.file.size, 0)
  const incomingBytes = files.reduce((total, file) => total + file.size, 0)
  if (existingBytes + incomingBytes > MAX_TOTAL_ATTACHMENT_BYTES) {
    errorMessage.value = '每次图片原始大小合计不能超过 12 MiB。'
    return
  }
  const validated: Array<{
    file: File
    mediaType: AIAttachmentMediaType
    pixelCount: number
  }> = []
  for (const file of files) {
    const info = await validateFile(file)
    if (!info || generation !== lifecycleGeneration) return
    validated.push({ file, ...info })
  }
  const existingPixels = attachments.value.reduce((total, item) => total + item.pixelCount, 0)
  const incomingPixels = validated.reduce((total, item) => total + item.pixelCount, 0)
  if (existingPixels + incomingPixels > MAX_TOTAL_IMAGE_PIXELS) {
    errorMessage.value = '每次图片合计不能超过 2400 万像素。'
    return
  }
  const pending: LocalAttachment[] = []
  for (const { file, mediaType, pixelCount } of validated) {
    try {
      pending.push({
        id: attachmentId(),
        file,
        mediaType,
        pixelCount,
        previewUrl: URL.createObjectURL(file),
      })
    } catch {
      pending.forEach((item) => revokePreview(item.previewUrl))
      errorMessage.value = '当前浏览器无法安全预览该图片。'
      return
    }
  }
  if (generation !== lifecycleGeneration) {
    pending.forEach((item) => revokePreview(item.previewUrl))
    return
  }
  attachments.value.push(...pending)
  resetConsent()
}

function addFiles(input: FileList | readonly File[]) {
  const files = Array.from(input)
  const generation = lifecycleGeneration
  additionQueue = additionQueue
    .catch(() => undefined)
    .then(() => addFilesBatch(files, generation))
  return additionQueue
}

function chooseFiles() {
  if (!props.disabled) fileInput.value?.click()
}

function handleFileSelection(event: Event) {
  const input = event.target as HTMLInputElement
  if (input.files) void addFiles(input.files)
  input.value = ''
}

function removeAttachment(id: string) {
  const index = attachments.value.findIndex((item) => item.id === id)
  if (index < 0) return
  const [removed] = attachments.value.splice(index, 1)
  if (removed) revokePreview(removed.previewUrl)
  resetConsent()
  errorMessage.value = ''
}

function revokePreview(previewUrl: string) {
  if (typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(previewUrl)
}

function revokeAllPreviews() {
  attachments.value.forEach((item) => revokePreview(item.previewUrl))
}

function resetConsent() {
  consentGeneration += 1
  cloudProcessingConsent.value = false
  abortActiveReaders()
}

function handleConsentChange(event: Event) {
  const accepted = (event.target as HTMLInputElement).checked
  if (accepted) {
    cloudProcessingConsent.value = true
    errorMessage.value = ''
    return
  }
  resetConsent()
}

function abortActiveReaders() {
  const readers = [...activeReaders]
  activeReaders.clear()
  readers.forEach((reader) => {
    if (reader.readyState === FileReader.LOADING) reader.abort()
  })
}

function clear() {
  lifecycleGeneration += 1
  abortActiveReaders()
  revokeAllPreviews()
  attachments.value = []
  resetConsent()
  errorMessage.value = ''
  isPreparing.value = false
  if (fileInput.value) fileInput.value.value = ''
}

function readAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    const releaseReader = () => {
      activeReaders.delete(reader)
      reader.onload = null
      reader.onerror = null
      reader.onabort = null
    }
    activeReaders.add(reader)
    reader.onload = () => {
      const result = reader.result
      releaseReader()
      if (typeof result === 'string') resolve(result)
      else reject(new Error('invalid image data'))
    }
    reader.onerror = () => {
      releaseReader()
      reject(new Error('image read failed'))
    }
    reader.onabort = () => {
      releaseReader()
      reject(new DOMException('Image read aborted', 'AbortError'))
    }
    reader.readAsDataURL(file)
  })
}

async function prepareForSend(): Promise<PreparedAttachmentBatch | null> {
  if (!attachments.value.length) return { attachments: [], consent: null }
  if (isPreparing.value) {
    errorMessage.value = '图片正在准备中，请稍候。'
    return null
  }
  if (!cloudProcessingConsent.value) {
    errorMessage.value = `请先确认：${CLOUD_PROCESSING_NOTICE}。`
    return null
  }
  const generation = lifecycleGeneration
  const acceptedConsentGeneration = consentGeneration
  const current = [...attachments.value]
  const prepared: AIRequestAttachment[] = []
  isPreparing.value = true
  errorMessage.value = ''
  try {
    for (const item of current) {
      prepared.push({
        id: item.id,
        media_type: item.mediaType,
        data_url: await readAsDataUrl(item.file),
      })
      if (
        generation !== lifecycleGeneration
        || acceptedConsentGeneration !== consentGeneration
        || !cloudProcessingConsent.value
      ) throw new DOMException('Attachment consent changed', 'AbortError')
    }
    return {
      attachments: prepared,
      consent: {
        accepted: true,
        notice_version: CLOUD_PROCESSING_NOTICE_VERSION,
        attachment_ids: prepared.map((item) => item.id),
      },
    }
  } catch {
    prepared.forEach((attachment) => {
      attachment.data_url = ''
    })
    abortActiveReaders()
    if (generation === lifecycleGeneration) {
      if (acceptedConsentGeneration !== consentGeneration) {
        errorMessage.value = '页面、厂区或图片已变化，请重新确认云端处理。'
      } else {
        errorMessage.value = '图片读取失败，未发送任何内容。'
        resetConsent()
      }
    }
    return null
  } finally {
    if (generation === lifecycleGeneration) isPreparing.value = false
  }
}

onBeforeUnmount(clear)

defineExpose({ addFiles, clear, hasAttachments, prepareForSend, resetConsent })
</script>

<template>
  <section
    data-ai-attachment-tray
    class="shrink-0 border-t border-slate-200 bg-white px-4 pt-3 sm:px-5"
    aria-label="图片附件"
  >
    <input
      ref="fileInput"
      hidden
      type="file"
      accept="image/png,image/jpeg,image/webp"
      multiple
      :disabled="disabled"
      @change="handleFileSelection"
    />
    <div class="flex items-center justify-between gap-3">
      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs font-semibold text-slate-700 transition hover:border-sky-400 hover:text-sky-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="disabled || isPreparing || attachments.length >= MAX_ATTACHMENT_COUNT"
        aria-label="添加图片"
        @click="chooseFiles"
      >
        <ImagePlus class="size-3.5" aria-hidden="true" />
        添加图片
      </button>
      <button
        v-if="hasAttachments"
        type="button"
        class="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-rose-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
        :disabled="disabled || isPreparing"
        aria-label="清空全部图片"
        @click="clear"
      >
        <Trash2 class="size-3.5" aria-hidden="true" />
        清空
      </button>
    </div>

    <ul v-if="hasAttachments" class="mt-2 grid grid-cols-3 gap-2" aria-label="待发送图片">
      <li
        v-for="item in attachments"
        :key="item.id"
        class="group relative overflow-hidden rounded-xl border border-slate-200 bg-slate-100"
      >
        <img
          :src="item.previewUrl"
          :alt="`${item.file.name} 预览`"
          class="aspect-square w-full object-cover"
        />
        <button
          type="button"
          class="absolute right-1 top-1 flex size-6 items-center justify-center rounded-full bg-slate-950/75 text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white disabled:opacity-50"
          :aria-label="`删除图片 ${item.file.name}`"
          :disabled="disabled || isPreparing"
          @click="removeAttachment(item.id)"
        >
          <X class="size-3.5" aria-hidden="true" />
        </button>
      </li>
    </ul>

    <label
      v-if="hasAttachments"
      class="mt-2 flex cursor-pointer items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] leading-4 text-amber-900"
    >
      <input
        :checked="cloudProcessingConsent"
        type="checkbox"
        class="mt-0.5 size-3.5 shrink-0 accent-sky-700"
        :disabled="disabled"
        @change="handleConsentChange"
      />
      <span>我已知悉并同意：{{ CLOUD_PROCESSING_NOTICE }}。本次发送完成或取消后需重新确认。</span>
    </label>
    <p
      v-if="errorMessage"
      class="mt-2 text-xs leading-4 text-rose-700"
      role="alert"
    >
      {{ errorMessage }}
    </p>
    <p v-else class="mt-2 text-[11px] leading-4 text-slate-500">
      可选择、粘贴或拖入 PNG/JPEG/WebP；单张不超过 4 MiB/1600 万像素，最多 3 张，合计不超过 12 MiB/2400 万像素。服务端将再次安全校验。
    </p>
  </section>
</template>
