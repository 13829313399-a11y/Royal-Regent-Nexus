<script setup lang="ts">
import { ref } from 'vue'
import ShippingLoadingSheetPanel from './ShippingLoadingSheetPanel.vue'
import ShippingZuruSheetPanel from './ShippingZuruSheetPanel.vue'

defineProps<{ factoryId: string }>()
const emit = defineEmits<{ notify: [message: string]; back: [] }>()

const mode = ref<'dk' | 'zuru'>('dk')
</script>

<template>
  <section class="space-y-4" aria-label="SO出货表">
    <div class="rounded-xl border border-emerald-100/80 bg-gradient-to-b from-white to-emerald-50/50 p-4">
      <div class="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 class="text-[16px] font-bold text-emerald-950">SO 出货表</h2>
          <p class="mt-0.5 text-[11px] text-slate-500">
            两种表格同属 SO 出货表，只是模板不同；生成后的表格按出货港口命名。
          </p>
        </div>
        <button type="button" class="text-[11px] font-semibold text-emerald-800 hover:underline" @click="emit('back')">← 返回工厂排期单</button>
      </div>
      <div class="mt-3 inline-flex rounded-lg border border-emerald-200 bg-white p-0.5">
        <button
          type="button"
          class="h-8 rounded-md px-3 text-[12px] font-semibold transition"
          :class="mode === 'dk' ? 'bg-emerald-700 text-white' : 'text-emerald-900 hover:bg-emerald-50'"
          @click="mode = 'dk'"
        >
          装柜单模板
        </button>
        <button
          type="button"
          class="h-8 rounded-md px-3 text-[12px] font-semibold transition"
          :class="mode === 'zuru' ? 'bg-emerald-700 text-white' : 'text-emerald-900 hover:bg-emerald-50'"
          @click="mode = 'zuru'"
        >
          ZURU 柜货单模板
        </button>
      </div>
    </div>

    <ShippingLoadingSheetPanel v-if="mode === 'dk'" :factory-id="factoryId" @notify="emit('notify', $event)" />
    <ShippingZuruSheetPanel v-else :factory-id="factoryId" @notify="emit('notify', $event)" />
  </section>
</template>
