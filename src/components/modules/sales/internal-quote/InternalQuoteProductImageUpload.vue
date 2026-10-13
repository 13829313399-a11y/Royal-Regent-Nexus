<script setup lang="ts">
import { computed, ref } from 'vue'
import { internalQuoteApi } from '@/api/internalQuote'
import { getApiErrorMessage } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import type { InternalQuote } from '@/types/internalQuoteDesk'

const props = defineProps<{ quote: InternalQuote; hasImage: boolean; hasUnsavedChanges: () => boolean }>()
const emit = defineEmits<{ open: [id: string] }>()
const auth = useAuthStore()
const store = useInternalQuoteDeskStore()
const input = ref<HTMLInputElement>()
const busy = ref(false)
const error = ref('')
const message = ref('')
const canUpload = computed(() => ['sales-business', 'engineering'].some(dept => auth.can('internal_quote:create', props.quote.factoryId, dept)))
const frozen = computed(() => ['released', 'exported'].includes(props.quote.status))
const canCopy = computed(() => ['sales-business', 'engineering'].some(dept => auth.can('internal_quote:create', props.quote.factoryId, dept) && auth.can('internal_quote:clone', props.quote.factoryId, dept)))
const editable = computed(() => !['final_pending', 'released', 'exported', 'archived'].includes(props.quote.status))
function choose() {
  error.value = ''; message.value = ''
  if (props.hasUnsavedChanges()) { error.value = '请先保存当前款，再上传主图。'; return }
  input.value?.click()
}
async function upload(event: Event) {
  const field = event.target as HTMLInputElement
  const file = field.files?.[0]
  field.value = ''
  if (!file || busy.value || !canUpload.value || (!editable.value && !(frozen.value && canCopy.value))) return
  if (props.hasUnsavedChanges()) { error.value = '请先保存当前款，再上传主图。'; return }
  if (!/\.(jpe?g|png|webp)$/i.test(file.name) || file.size > 10 * 1024 * 1024) {
    error.value = '请选择不超过 10 MB 的 JPG、PNG 或 WEBP 图片。'; return
  }
  busy.value = true; error.value = ''; message.value = ''
  const sourceId = props.quote.id
  let targetId = sourceId
  let revision = props.quote.headerRevision
  try {
    if (frozen.value) {
      const family = await internalQuoteApi.listAlternatives(sourceId)
      const current = family.items.find(item => item.quote_id === sourceId)
      const created = await internalQuoteApi.createAlternative(sourceId, {
        revision, family_revision: family.revision, kind: 'version', name: current?.scenario_name ?? '', change_note: '补充或更新产品主图',
      })
      targetId = created.id; revision = created.header_revision
    }
    await store.uploadProductImage(targetId, file, revision)
    if (props.quote.id === sourceId) {
      message.value = '产品主图已上传。'
      if (targetId !== sourceId) emit('open', targetId)
    }
  } catch (cause) {
    if (props.quote.id === sourceId) error.value = getApiErrorMessage(cause)
  } finally {
    busy.value = false
    // A successfully created draft is kept even if its separate upload fails.
    if (targetId !== sourceId && props.quote.id === sourceId && error.value) {
      message.value = '新版本已创建，主图尚未上传成功。'
      createdDraftId.value = targetId
    }
  }
}
const createdDraftId = ref('')
</script>

<template>
  <div v-if="canUpload" class="product-image-upload">
    <input ref="input" hidden type="file" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" aria-label="选择产品主图" :disabled="busy || store.fileBusy" @change="upload">
    <button v-if="editable || (frozen && canCopy)" type="button" :disabled="busy || store.fileBusy || !!createdDraftId" @click="choose">{{ busy ? '主图上传中…' : frozen ? '复制新版本并上传主图' : hasImage ? '更换主图' : '上传主图' }}</button>
    <small v-if="frozen">已输出版本保留原图和原文件。</small>
    <small v-else-if="!editable">当前状态不可修改主图。</small>
    <p v-if="message" role="status">{{ message }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <button v-if="createdDraftId" type="button" @click="emit('open', createdDraftId)">打开新版本重试上传</button>
  </div>
</template>

<style scoped>
.product-image-upload{display:grid;gap:6px;margin-top:8px;max-width:190px}.product-image-upload button{border:1px solid #99f6e4;border-radius:8px;background:#f0fdfa;color:#0f766e;padding:8px;cursor:pointer;font-size:12px}.product-image-upload button:disabled{opacity:.5;cursor:not-allowed}.product-image-upload small,.product-image-upload p{margin:0;font-size:11px;color:#64748b}.product-image-upload [role=alert]{color:#b91c1c}
</style>
