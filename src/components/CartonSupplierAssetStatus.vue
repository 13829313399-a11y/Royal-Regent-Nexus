<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { DialogRoot, DialogTrigger, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { Button } from '@/components/ui/button'
import { cartonSupplierPortalApi } from '@/api/cartonSupplierPortal'
import { useAuthStore } from '@/stores/auth'
import { viewerKey, responseStatus } from '@/features/carton-procurement/quickAssets'
import { createRandomUuid } from '@/lib/randomUuid'
import { getApiErrorMessage } from '@/lib/http'

const props = defineProps<{ factoryId: string; asset: { id: string; revision: number; file_name: string; can_classify?: boolean; workflow?: { status: string } } }>()
const emit = defineEmits<{ changed: [] }>()
const auth = useAuthStore(), open = ref(false), busy = ref(false), status = ref<'DRAFT' | 'PENDING'>('PENDING'), error = ref('')
const allowed = computed(() => props.asset.can_classify === true && !['READY', 'HISTORY'].includes(props.asset.workflow?.status || '') && auth.can('carton_supplier:edit', props.factoryId, '*'))
const context = computed(() => JSON.stringify([props.factoryId, props.asset.id, props.asset.revision, allowed.value, viewerKey(auth)]))
const frozen = shallowRef<{ factory: string; asset: { id: string; revision: number }; status: 'DRAFT' | 'PENDING'; requestId: string } | null>(null)
let generation = 0, controller = new AbortController()
function changeOpen(value: boolean) {
  if (busy.value && !value) return
  if (value && !frozen.value) { status.value = props.asset.workflow?.status === 'DRAFT' ? 'DRAFT' : 'PENDING'; error.value = '' }
  open.value = value
}
async function save() {
  if (!allowed.value || busy.value) return
  const original = context.value, token = ++generation
  const request = frozen.value || { factory: props.factoryId, asset: { id: props.asset.id, revision: props.asset.revision }, status: status.value, requestId: createRandomUuid() }
  busy.value = true; error.value = ''; controller = new AbortController()
  try {
    await cartonSupplierPortalApi.classifyMarkAsset(request.factory, request.asset, request.status, request.requestId, controller.signal)
    if (token !== generation || original !== context.value) return
    frozen.value = null; open.value = false; emit('changed')
  } catch (cause) {
    if (token !== generation || original !== context.value) return
    const code = responseStatus(cause)
    if (code === undefined || code >= 500) { frozen.value = request; error.value = '保存结果尚未确认，请保持原状态并原样重试。' }
    else { frozen.value = null; error.value = code === 409 ? '文件已更新，请关闭窗口并刷新资料后核对。' : getApiErrorMessage(cause) }
  } finally { if (token === generation) busy.value = false }
}
watch(context, () => { generation++; controller.abort(); open.value = false; busy.value = false; frozen.value = null; error.value = '' }, { flush: 'sync' })
onBeforeUnmount(() => { generation++; controller.abort() })
</script>

<template>
  <DialogRoot v-if="allowed" :open="open" @update:open="changeOpen">
    <DialogTrigger as-child><Button type="button" variant="outline" size="sm" :aria-label="`修改 ${asset.file_name} 状态`">修改状态</Button></DialogTrigger>
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 z-[70] bg-slate-950/45" />
      <DialogContent as="form" class="fixed left-1/2 top-1/2 z-[71] max-h-[calc(100dvh-1.5rem)] w-[calc(100%_-_1.5rem)] max-w-md -translate-x-1/2 -translate-y-1/2 space-y-4 overflow-y-auto rounded-xl border border-border bg-card p-4 text-foreground shadow-xl" @submit.prevent="save" @escape-key-down="event => { if (busy) event.preventDefault() }" @interact-outside="event => event.preventDefault()">
        <DialogTitle class="font-bold">修改资料状态</DialogTitle>
        <DialogDescription class="break-all text-sm text-muted-foreground">{{ asset.file_name }}。仅设置本供应商自有稿件；已确认由内部人员处理。</DialogDescription>
        <label class="block text-sm font-semibold">资料状态<select v-model="status" aria-label="供应商文件状态" :disabled="busy || !!frozen" class="mt-2 h-10 w-full rounded-lg border border-input bg-card px-3"><option value="DRAFT">待处理</option><option value="PENDING">待确认</option></select></label>
        <p v-if="error" role="alert" class="text-sm text-destructive">{{ error }}</p>
        <div class="flex flex-wrap justify-end gap-2"><Button type="button" variant="outline" :disabled="busy" @click="changeOpen(false)">取消</Button><Button type="submit" :disabled="busy">{{ busy ? '保存中…' : frozen ? '原样重试保存' : '保存状态' }}</Button></div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
