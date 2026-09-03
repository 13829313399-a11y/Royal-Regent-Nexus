<script setup lang="ts">
import { ref, watch } from 'vue'
import { internalQuoteApi, internalQuoteAttachmentPreviewUrl, type ApiInternalQuoteAttachment } from '@/api/internalQuote'
const props = defineProps<{ quoteId: string; componentId: string; componentName: string; revision: number; editable: boolean }>()
const emit = defineEmits<{ changed: [] }>()
const current = ref<ApiInternalQuoteAttachment>()
const busy = ref(false)
const error = ref('')
let requestId = 0
watch(() => [props.quoteId, props.componentId, props.revision], async () => {
  const request = ++requestId
  current.value = undefined
  error.value = ''
  try {
    const attachments = await internalQuoteApi.listAttachments(props.quoteId)
    if (request === requestId) current.value = attachments.find(a => a.pricing_component_id === props.componentId)
  } catch { if (request === requestId) error.value = '分项图片读取失败，请重新读取报价。' }
}, { immediate: true })
async function upload(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file || !props.editable || busy.value) return
  busy.value = true; error.value = ''
  try {
    current.value = await internalQuoteApi.uploadComponentImage(props.quoteId, props.componentId, file, props.revision)
    emit('changed')
  } catch (e) { error.value = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail || '图片上传失败，请检查权限和版本后重试。' }
  finally { busy.value = false; input.value = '' }
}
async function remove() {
  if (!props.editable || busy.value || !window.confirm(`删除“${props.componentName}”的分项图片？`)) return
  busy.value = true; error.value = ''
  try { await internalQuoteApi.deleteComponentImage(props.quoteId, props.componentId, props.revision); current.value = undefined; emit('changed') }
  catch (e) { error.value = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail || '删除失败，请重新读取报价后重试。' }
  finally { busy.value = false }
}
</script>
<template>
  <section class="quote-component-image" aria-label="当前分项图片">
    <a v-if="current" :href="internalQuoteAttachmentPreviewUrl(quoteId,current.id)" target="_blank" rel="noopener"><img :src="internalQuoteAttachmentPreviewUrl(quoteId,current.id)" :alt="`${componentName} 分项图片`"></a>
    <div><strong>{{ componentName }} · 分项图片</strong><p>导出放在本分项明细右侧，不使用产品主图替代。{{ current ? '点击图片可放大。' : '尚未上传图片。' }}</p>
      <label v-if="editable"><span>{{ busy ? '处理中…' : current ? '替换图片' : '上传图片' }}</span><input type="file" accept=".jpg,.jpeg,.png,.webp" :disabled="busy" :aria-label="`${componentName} 上传图片`" @change="upload"></label>
      <button v-if="editable && current" type="button" :disabled="busy" @click="remove">删除图片</button>
      <p v-if="error" role="alert">{{ error }}</p>
    </div>
  </section>
</template>
<style scoped>
.quote-component-image{display:flex;gap:16px;align-items:center;padding:14px;border:1px solid #cbd5e1;border-radius:10px;background:#fff}.quote-component-image img{width:140px;height:110px;object-fit:contain}.quote-component-image strong{color:#134e4a}.quote-component-image p{font-size:12px;color:#64748b}.quote-component-image label,.quote-component-image button{display:inline-flex;border:1px solid #99f6e4;background:#f0fdfa;color:#0f766e;border-radius:6px;padding:7px 10px;cursor:pointer;font-size:12px;margin-right:8px}.quote-component-image input{position:absolute;width:1px;height:1px;opacity:0}.quote-component-image [role=alert]{color:#b91c1c}
</style>
