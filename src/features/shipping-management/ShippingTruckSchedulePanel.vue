<script setup lang="ts">
import { ref } from 'vue'
import ShippingTruckSheetPanel from './ShippingTruckSheetPanel.vue'
import ShippingBulkTruckSheetPanel from './ShippingBulkTruckSheetPanel.vue'
import ShippingGeneratedDocs from './ShippingGeneratedDocs.vue'

defineProps<{ factoryId: string }>()
const emit = defineEmits<{ notify: [message: string]; back: [] }>()

const mode = ref<'buzzbee' | 'bulk'>('buzzbee')
</script>

<template>
  <section class="space-y-4" aria-label="车的排出货表">
    <ShippingGeneratedDocs :factory-id="factoryId" module="truck" label="车的排出货表" />
    <div class="rounded-xl border border-emerald-100/80 bg-gradient-to-b from-white to-emerald-50/50 p-4">
      <div class="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 class="text-[16px] font-bold text-emerald-950">车的排出货表</h2>
          <p class="mt-0.5 text-[11px] text-slate-500">两种车货表同属车的排出货，按发车港口 / CFS 与车次命名。</p>
        </div>
        <button type="button" class="text-[13px] font-semibold text-emerald-800 hover:underline" @click="emit('back')">← 返回工厂排期单</button>
      </div>
      <div class="mt-3 inline-flex rounded-lg border border-emerald-200 bg-white p-0.5">
        <button
          type="button"
          class="h-8 rounded-md px-3 text-[12px] font-semibold transition"
          :class="mode === 'buzzbee' ? 'bg-emerald-700 text-white' : 'text-emerald-900 hover:bg-emerald-50'"
          @click="mode = 'buzzbee'"
        >
          Buzzbee 客上车
        </button>
        <button
          type="button"
          class="h-8 rounded-md px-3 text-[12px] font-semibold transition"
          :class="mode === 'bulk' ? 'bg-emerald-700 text-white' : 'text-emerald-900 hover:bg-emerald-50'"
          @click="mode = 'bulk'"
        >
          盐田散货 W 车
        </button>
      </div>
    </div>

    <ShippingTruckSheetPanel v-if="mode === 'buzzbee'" :factory-id="factoryId" @notify="emit('notify', $event)" @back="emit('back')" />
    <ShippingBulkTruckSheetPanel v-else :factory-id="factoryId" @notify="emit('notify', $event)" @back="emit('back')" />
  </section>
</template>
