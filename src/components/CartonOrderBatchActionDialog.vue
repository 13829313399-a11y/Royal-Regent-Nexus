<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { Button } from '@/components/ui/button'
import { cartonSpecialRequestsApi, type UnifiedOrderEntry } from '@/api/cartonSpecialRequests'
import { getApiErrorMessage } from '@/lib/http'

const props = defineProps<{ open: boolean; factoryId: string; viewerKey: string; action: 'CONFIRM' | 'CANCEL' | 'DELETE'; entries: UnifiedOrderEntry[] }>()
const emit = defineEmits<{ 'update:open': [value: boolean]; saved: [] }>()
const busy = ref(false), error = ref(''), reason = ref('')
const title = computed(() => ({ CONFIRM: '确认订单并锁定', CANCEL: '取消订单', DELETE: '删除订单' })[props.action])
const labels: Record<string, string> = { PURCHASE: '正单', SAMPLE: '样板', WORKSHOP_MISC: '杂单', SUPPLIER_GIFT: '历史赠送' }
let generation = 0, controller = new AbortController()
const attempts = new Map<string, string>()
watch(() => [props.factoryId, props.viewerKey, props.open, props.action], () => {
  generation++; controller.abort(); controller = new AbortController(); busy.value = false; error.value = ''; reason.value = ''; attempts.clear()
}, { flush: 'sync' })
onBeforeUnmount(() => { generation++; controller.abort() })
async function submit() {
  if (busy.value || !props.entries.length || (props.action !== 'CONFIRM' && reason.value.trim().length < 4)) return
  const payload = { factory_id: props.factoryId, action: props.action, reason: reason.value.trim(), items: props.entries.map(entry => ({
    kind: entry.kind, id: entry.order?.order_no || entry.special!.id, expected_revision: entry.order?.revision ?? entry.special!.revision,
  })) }
  const signature = JSON.stringify(payload)
  if (!attempts.has(signature)) attempts.set(signature, crypto.randomUUID())
  const token = generation; busy.value = true; error.value = ''
  try {
    await cartonSpecialRequestsApi.batchAction({ ...payload, request_id: attempts.get(signature)! }, controller.signal)
    if (token === generation) { attempts.delete(signature); emit('saved'); emit('update:open', false) }
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) busy.value = false }
}
</script>

<template>
  <DialogRoot :open="open" @update:open="value => { if (!busy) emit('update:open', value) }"><DialogPortal>
    <DialogOverlay class="fixed inset-0 z-[80] bg-slate-950/40" />
    <DialogContent class="fixed left-1/2 top-1/2 z-[81] max-h-[88vh] w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 -translate-y-1/2 space-y-4 overflow-y-auto rounded-2xl border bg-white p-5 shadow-xl" @interact-outside.prevent @escape-key-down="event => { if (busy) event.preventDefault() }">
      <DialogTitle class="text-base font-bold text-slate-950">{{ title }} · {{ entries.length }} 张</DialogTitle>
      <DialogDescription class="text-sm leading-6 text-slate-600">{{ action === 'CONFIRM' ? '核对所选订单后统一确认。正单生成采购单，样板和杂单锁定当前需求；箱唛在资料库维护。' : action === 'DELETE' ? '从订单台账移除符合条件的订单，历史资料和已确认订单原记录保留。' : '取消后不能继续送货，原订单及操作历史保留。' }}全部订单校验通过后一次生效。</DialogDescription>
      <ul class="max-h-52 space-y-2 overflow-y-auto rounded-xl border bg-slate-50 p-3 text-xs"><li v-for="entry in entries" :key="`${entry.kind}:${entry.order?.order_no || entry.special?.id}`" class="break-words"><b class="mr-2 text-teal-700">{{ labels[entry.kind] }}</b>{{ entry.order?.order_no || entry.special?.request_no }} · {{ entry.order?.customer_name || entry.special?.customer_name || '未关联客户' }}</li></ul>
      <form class="space-y-4" @submit.prevent="submit">
        <label v-if="action !== 'CONFIRM'" class="block text-sm font-semibold">操作原因 *<textarea v-model="reason" aria-label="批量订单操作原因" :disabled="busy" maxlength="500" rows="2" class="mt-2 w-full rounded-lg border p-3 text-sm" placeholder="请填写至少四字的原因" /></label>
        <p v-if="error" role="alert" class="text-sm text-red-700">{{ error }}</p>
        <div class="flex justify-end gap-2"><Button type="button" variant="outline" :disabled="busy" @click="emit('update:open', false)">返回</Button><Button type="submit" :variant="action === 'CONFIRM' ? 'default' : 'destructive'" :disabled="busy || !entries.length || (action !== 'CONFIRM' && reason.trim().length < 4)">{{ busy ? '正在处理…' : title }}</Button></div>
      </form>
    </DialogContent>
  </DialogPortal></DialogRoot>
</template>
