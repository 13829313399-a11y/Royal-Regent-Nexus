<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { internalQuoteApi } from '@/api/internalQuote'
import { getApiErrorMessage } from '@/lib/http'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
const props = defineProps<{ quoteId: string; fileName: string }>()
const emit = defineEmits<{ close: []; downloaded: [] }>()
const store = useInternalQuoteDeskStore()
const options = ref<Awaited<ReturnType<typeof internalQuoteApi.getEngineeringExportOptions>>>()
const selected = ref<string[]>([])
const busy = ref(false)
const loading = ref(true)
const error = ref('')
let active = true
onBeforeUnmount(() => { active = false })
const allSelected = computed(() => Boolean(options.value?.items.length) && selected.value.length === options.value?.items.length)
async function load() {
  loading.value = true; error.value = ''; options.value = undefined
  try {
    const result = await internalQuoteApi.getEngineeringExportOptions(props.quoteId)
    if (!active) return
    options.value = result; selected.value = result.items.map(item => item.id)
  } catch (cause) { if (active) error.value = getApiErrorMessage(cause) }
  finally { if (active) loading.value = false }
}
async function download() {
  if (!options.value || busy.value) return
  busy.value = true; error.value = ''
  try {
    await store.downloadEngineeringWorkbook(props.quoteId, props.fileName, {
      header_revision: options.value.header_revision, electronic_revision: options.value.electronic_revision,
      electronic_selection: [...selected.value],
    })
    if (active) emit('downloaded')
  } catch (cause) { if (active) error.value = getApiErrorMessage(cause) }
  finally { if (active) busy.value = false }
}
onMounted(load)
</script>
<template>
  <DialogRoot :open="true" @update:open="value => { if (!value && !busy) emit('close') }">
    <DialogPortal><DialogOverlay class="engineering-export-overlay" />
      <DialogContent class="engineering-export-dialog" @escape-key-down="event => { if (busy) event.preventDefault() }" @pointer-down-outside="event => { if (busy) event.preventDefault() }">
        <header><DialogTitle>选择导出的电子明细</DialogTitle><DialogDescription>只影响本次工程资料的外购清单，报价金额及原始资料保持不变。</DialogDescription></header>
        <p v-if="loading" role="status">正在读取电子明细…</p>
        <template v-else-if="options">
          <label class="engineering-export-all"><input type="checkbox" :checked="allSelected" :disabled="busy || !options.items.length" @change="selected = allSelected ? [] : options.items.map(item => item.id)">全选 / 取消全选 <span>已选 {{ selected.length }} / {{ options.items.length }}</span></label>
          <div class="engineering-export-items"><label v-for="item in options.items" :key="item.id"><input v-model="selected" type="checkbox" :value="item.id" :disabled="busy"><span><strong>{{ item.name || '未命名电子明细' }}</strong><small>{{ item.specification }} · 用量 {{ item.quantity }}{{ item.supplier ? ` · ${item.supplier}` : '' }}</small></span></label><p v-if="!options.items.length">当前没有电子明细，可继续导出其他工程资料。</p></div>
        </template>
        <p v-if="error" class="engineering-export-error" role="alert">{{ error }} <button :disabled="busy || loading" @click="load">重新读取明细</button></p>
        <footer><button :disabled="busy" @click="emit('close')">取消</button><button class="primary" :disabled="busy || loading || !options" @click="download">{{ busy ? '正在生成…' : `生成工程资料（电子 ${selected.length} 条）` }}</button></footer>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
<style scoped>
.engineering-export-overlay{position:fixed;inset:0;z-index:120;background:#173e3559}.engineering-export-dialog{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);z-index:121;display:flex;flex-direction:column;gap:18px;width:min(680px,calc(100vw - 32px));max-height:85vh;padding:24px;border-radius:14px;background:#fff;color:#234b45;box-shadow:0 20px 70px #15382b38}.engineering-export-dialog header{display:grid;gap:8px}.engineering-export-dialog h2{margin:0;font-size:20px}.engineering-export-dialog p{margin:0;line-height:1.6}.engineering-export-dialog header p{font-size:13px;color:#658178}.engineering-export-all{display:flex;gap:10px;align-items:center;font-size:14px}.engineering-export-all span{margin-left:auto}.engineering-export-items{overflow:auto;min-height:70px}.engineering-export-items label{display:flex;gap:12px;padding:13px 4px;border-bottom:1px solid #e3ece8}.engineering-export-items span{display:grid;gap:5px}.engineering-export-items small{color:#6c837b}.engineering-export-dialog footer{display:flex;justify-content:flex-end;gap:12px}.engineering-export-dialog button{padding:9px 14px;border:1px solid #bfd8cf;border-radius:7px;background:#fff;color:#23695b;cursor:pointer}.engineering-export-dialog button.primary{background:#14796b;color:#fff}.engineering-export-dialog button:disabled{opacity:.5;cursor:not-allowed}.engineering-export-error{color:#a13620}
</style>
