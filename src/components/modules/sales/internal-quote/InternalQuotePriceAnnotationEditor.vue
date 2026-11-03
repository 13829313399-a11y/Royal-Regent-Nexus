<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { internalQuoteApi } from '@/api/internalQuote'
import type { OutputEdits, OutputField } from '@/api/internalQuoteOutput'
import { getApiErrorMessage } from '@/lib/http'
const props = defineProps<{ quoteId: string; field: OutputField; value?: NonNullable<OutputEdits['edits'][number]['annotation']>; disabled?: boolean }>()
const emit = defineEmits<{ change: [value: NonNullable<OutputEdits['edits'][number]['annotation']>]; busy: [value: boolean] }>()
const error = ref('')
const reading = ref(false)
const images = ref<Record<string, string>>({})
let active = true
onBeforeUnmount(() => { active = false; if (reading.value) emit('busy', false) })
function current() { return props.value ?? { text: props.field.annotation?.text ?? '', image_attachment_ids: [...(props.field.annotation?.image_attachment_ids ?? [])], new_images: [] } }
function text(event: Event) { emit('change', { ...current(), text: (event.target as HTMLTextAreaElement).value }) }
function read(file: Blob): Promise<string> { return new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = reject; reader.readAsDataURL(file) }) }
async function add(files: File[]) {
  if (props.disabled || reading.value) return
  const quoteId = props.quoteId, fieldId = props.field.id
  reading.value = true; error.value = ''; emit('busy', true)
  try {
    const note = current()
    if (note.image_attachment_ids.length + note.new_images.length + files.length > 4) throw new Error('每条调价说明最多 4 张截图。')
    const encoded: string[] = []
    for (const file of files) {
      if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 3 * 1024 * 1024) throw new Error('请使用不超过 3 MB 的 PNG、JPG 或 WebP 截图。')
      encoded.push((await read(file)).split(',')[1]!)
    }
    if (active && props.quoteId === quoteId && props.field.id === fieldId && !props.disabled) emit('change', { ...current(), new_images: [...current().new_images, ...encoded] })
  } catch (cause) { error.value = getApiErrorMessage(cause) }
  finally { reading.value = false; if (active) emit('busy', false) }
}
function choose(event: Event) { const input = event.target as HTMLInputElement; const files = Array.from(input.files ?? []); input.value = ''; void add(files) }
function paste(event: ClipboardEvent) { const files = Array.from(event.clipboardData?.files ?? []); if (files.length) { event.preventDefault(); void add(files) } }
async function view(id: string) {
  try { images.value[id] = await read(await internalQuoteApi.downloadAttachment(props.quoteId, id)) }
  catch (cause) { error.value = getApiErrorMessage(cause) }
}
</script>
<template>
  <div class="price-note" @paste="paste">
    <label>调价批注<textarea :value="current().text" :disabled="disabled" maxlength="3000" rows="3" placeholder="例如：供应商电话确认降价，新报价单待补。可粘贴截图。" :aria-label="`${field.label} 调价批注`" @input="text" /></label>
    <label class="price-note-upload">{{ reading ? '正在读取截图…' : '添加截图 / 粘贴截图（最多 4 张）' }}<input type="file" multiple accept="image/png,image/jpeg,image/webp" :disabled="disabled || reading" @change="choose"></label>
    <div v-for="(id, index) in current().image_attachment_ids" :key="id" class="price-note-image"><button type="button" @click="view(id)">查看已保存截图 {{ index + 1 }}</button><img v-if="images[id]" :src="images[id]" alt="已保存调价截图"><button :disabled="disabled" @click="emit('change', { ...current(), image_attachment_ids: current().image_attachment_ids.filter(item => item !== id) })">移除</button></div>
    <div v-for="(data, index) in current().new_images" :key="index" class="price-note-image"><img :src="`data:image/png;base64,${data}`" alt="待保存调价截图"><button :disabled="disabled" @click="emit('change', { ...current(), new_images: current().new_images.filter((_, i) => i !== index) })">移除</button></div>
    <small>保存后，批注保留在报价单元格；截图随 Excel 的“调价说明”页导出。</small><p v-if="error" role="alert">{{ error }}</p>
  </div>
</template>
<style scoped>
.price-note{border-top:1px dashed #ccdcd4;margin-top:12px;padding-top:12px;font-size:12px}.price-note label{display:grid;gap:7px;color:#42675b}.price-note textarea{width:100%;box-sizing:border-box;border:1px solid #cdded4;border-radius:5px;padding:8px;font:inherit;resize:vertical}.price-note-upload{margin:10px 0}.price-note-upload input{width:100%;font-size:11px}.price-note small{display:block;color:#72877c;line-height:1.6;margin-top:10px}.price-note-image{display:flex;flex-wrap:wrap;align-items:flex-start;gap:8px;margin:10px 0}.price-note-image img{max-width:100%;max-height:180px;object-fit:contain}.price-note button{border:1px solid #c7dcd1;border-radius:5px;padding:5px 8px;background:#fff;color:#266858;font-size:12px;cursor:pointer}.price-note p{color:#a13620}
</style>
