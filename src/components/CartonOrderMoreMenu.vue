<script setup lang="ts">
import { watch } from 'vue'
import { DropdownMenuRoot, DropdownMenuTrigger, DropdownMenuPortal, DropdownMenuContent } from 'reka-ui'
import { ChevronDown } from '@lucide/vue'

const props = defineProps<{ orderNo: string; disabled?: boolean }>()
const open = defineModel<boolean>('open', { default: false })
watch(() => props.disabled, disabled => { if (disabled) open.value = false })
watch(() => props.orderNo, () => { open.value = false })
</script>

<template>
  <div class="relative w-full">
    <DropdownMenuRoot v-model:open="open">
      <DropdownMenuTrigger :disabled="disabled" :aria-label="`更多 ${orderNo} 订单操作`" class="inline-flex h-8 w-full items-center justify-center gap-1 whitespace-nowrap rounded-md border border-slate-200 bg-white px-1 text-[10px] font-bold text-slate-600 transition hover:border-slate-300 hover:bg-slate-100 disabled:opacity-40">更多<ChevronDown aria-hidden="true" class="size-2.5" /></DropdownMenuTrigger>
      <DropdownMenuPortal>
        <DropdownMenuContent align="end" :side-offset="4" :collision-padding="8" :aria-label="`${orderNo} 订单操作`" class="z-[75] max-h-[var(--reka-dropdown-menu-content-available-height)] w-44 max-w-[calc(100vw-1rem)] overflow-y-auto rounded-lg border border-slate-200 bg-white py-1 shadow-xl">
          <slot />
        </DropdownMenuContent>
      </DropdownMenuPortal>
    </DropdownMenuRoot>
  </div>
</template>
