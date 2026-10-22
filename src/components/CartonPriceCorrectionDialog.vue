<script setup lang="ts">
import { computed, ref } from 'vue'
import { DialogRoot, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { Button } from '@/components/ui/button'
import CartonPriceCorrections from './CartonPriceCorrections.vue'
import type { PriceCorrectionBlocker } from '@/api/cartonPriceCorrections'
defineProps<{ open: boolean; factoryId?: string; factories?: { factory_id: string }[]; internal?: boolean; receiptLineId?: string; viewerKey?: string }>()
const emit = defineEmits<{ 'update:open': [open: boolean]; changed: []; navigate: [blocker: PriceCorrectionBlocker, currency: string] }>()
const workspace = ref<InstanceType<typeof CartonPriceCorrections> | null>(null)
const busy = computed(() => workspace.value?.busy === true)
function update(open: boolean) { if (!busy.value) emit('update:open', open) }
</script>
<template>
  <DialogRoot :open="open" @update:open="update">
    <DialogOverlay class="fixed inset-0 z-[70] bg-slate-950/45" />
    <DialogContent v-if="open" class="fixed left-1/2 top-1/2 z-[71] flex max-h-[90dvh] w-[calc(100%-2rem)] max-w-6xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl border bg-card shadow-2xl" @escape-key-down="busy && $event.preventDefault()" @interact-outside="busy && $event.preventDefault()">
      <div class="flex shrink-0 items-start justify-between gap-3 border-b p-4"><div><DialogTitle class="text-lg font-semibold">收料单价更正</DialogTitle><DialogDescription class="mt-1 text-xs text-muted-foreground">按实收批次核对，供方确认后由主管预览并同步生效。</DialogDescription></div><Button type="button" variant="outline" size="sm" :disabled="busy" @click="update(false)">关闭价格更正</Button></div>
      <div class="min-h-0 overflow-y-auto p-4"><CartonPriceCorrections ref="workspace" :factory-id="factoryId" :factories="factories" :internal="internal" :receipt-line-id="receiptLineId" :viewer-key="viewerKey" @changed="emit('changed')" @navigate="(blocker, currency) => emit('navigate', blocker, currency)" /></div>
    </DialogContent>
  </DialogRoot>
</template>
