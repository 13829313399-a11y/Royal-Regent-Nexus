<script setup lang="ts">
import { computed, ref, watch, nextTick, onBeforeUnmount } from 'vue'
import { sprayProductionApi } from '@/api/sprayProduction'
import { useSprayWorkspace, str, amount, errorText, type Entity } from '../workspace'
import { Button } from '@/components/ui/button'
const store = useSprayWorkspace()
const batch = computed(() => store.find('batches', store.selection))
const movements = ref<Entity[]>([])
const error = ref('')
const balances = computed(() => Object.entries(store.balances[batch.value?.id ?? ''] ?? {}).filter(([,quantity])=>Number(quantity)!==0))
const viewport = window.matchMedia('(max-width: 1279px)')
const narrow = ref(viewport.matches), panel = ref<HTMLElement | null>(null)
function resize(event: MediaQueryListEvent) { narrow.value = event.matches }
viewport.addEventListener('change', resize)
onBeforeUnmount(() => viewport.removeEventListener('change', resize))
let opener: HTMLElement | null = null
watch([batch,narrow], async () => { const trigger = document.activeElement; await nextTick(); if(panel.value instanceof HTMLDialogElement && !panel.value.open) { opener=trigger instanceof HTMLElement ? trigger : null; panel.value.showModal() } }, {immediate:true})
async function close() { if(panel.value instanceof HTMLDialogElement) panel.value.close(); store.selection=''; await nextTick(); if(opener?.isConnected) opener.focus() }
let generation = 0
watch(() => [store.selection, store.summary?.revision], async () => {
  const request = ++generation; movements.value = []; error.value = ''
  if (!store.selection) return
  try { const data = await sprayProductionApi.trace(store.factory, store.selection); if (request === generation) movements.value = data.movements } catch (e) { if(request === generation) error.value = errorText(e) }
}, { immediate: true })
</script>
<template>
  <component :is="narrow ? 'dialog' : 'aside'" v-if="batch" ref="panel" class="spray-inspector" aria-label="批次检查器" @cancel.prevent="close">
    <div class="spray-section-title"><h2>批次检查器</h2><Button variant="ghost" size="sm" @click="close">关闭</Button></div>
    <h3>{{ store.lineLabel(store.find('lines', batch.line_id)) }}</h3>
    <p class="spray-muted">来料 {{ str(batch, 'document_no') }} · 第 {{ str(batch, 'source_line') }} 行</p>
    <div class="spray-balance" v-for="[state,qty] in balances" :key="state"><span>{{ store.stateName(state) }}</span><strong>{{ amount(qty) }}</strong></div>
    <p class="spray-help">实体数量按状态互斥划分。返工尝试不增加来料。</p>
    <h3>流转履历</h3>
    <p v-if="error" role="alert">{{ error }}</p>
    <ol class="spray-timeline"><li v-for="event in movements" :key="event.id"><strong>{{ store.stateName(str(event, 'to_state')) }} · {{ amount(event.quantity) }}</strong><small>{{ new Date(str(event, 'created_at')).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai'}) }}</small><span>{{ str(event, 'reason') }}</span></li></ol>
  </component>
</template>
<style scoped>
dialog.spray-inspector{position:fixed;inset:0 0 0 auto;margin:0;width:min(400px,100%);height:100dvh;max-height:100dvh;max-width:100%;border:0;border-left:1px solid var(--border);color:var(--foreground)}
dialog.spray-inspector::backdrop{background:rgb(15 23 42 / 35%)}
</style>
