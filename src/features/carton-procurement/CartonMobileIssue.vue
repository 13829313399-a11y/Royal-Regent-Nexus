<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, MapPin, Search } from '@lucide/vue'
import CartonIssuePhoto from './CartonIssuePhoto.vue'
import type { IssuePhotoDraft, IssuePhotoStock } from './issuePhoto'

interface StockPosition extends IssuePhotoStock {
  customer: string
  packagingType: string
  paperQuality: string
  specification: string
  location: string
  warehouse?: string
  unit: string
}

const props = defineProps<{ factory: string; positions: StockPosition[]; loading: boolean; error: string; message: string; ready: boolean; selected: string[]; draftDocument: string }>()
const emit = defineEmits<{ select: [id: string]; review: [event: MouseEvent]; clear: []; refresh: []; 'photo-apply': [draft: IssuePhotoDraft]; 'photo-open': [open: boolean] }>()
const search = ref('')
const pageSize = 20
const limit = ref(pageSize)
const quantity = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 4 })
const results = computed(() => {
  const words = search.value.trim().toLowerCase().split(/\s+/).filter(Boolean)
  return props.positions.filter(row => {
    if (row.balance <= 0) return false
    const text = [row.itemNo, row.poNumber, row.customerPo, row.customer, row.packagingType, row.paperQuality, row.specification, row.warehouse, row.location].join(' ').toLowerCase()
    return words.every(word => text.includes(word))
  })
})
watch(search, () => { limit.value = pageSize })
</script>

<template>
  <section aria-label="车间发料库存" class="space-y-3 pb-20">
    <CartonIssuePhoto :factory="factory" :positions="positions" :disabled="!ready || loading" :existing-document="draftDocument"
      @apply="emit('photo-apply', $event)" @open="emit('photo-open', $event)" />
    <label class="relative block">
      <span class="sr-only">搜索发料库存</span>
      <Search aria-hidden="true" class="pointer-events-none absolute left-3.5 top-1/2 size-5 -translate-y-1/2 text-slate-500" />
      <input v-model="search" type="search" placeholder="搜索货号、合同、客户 PO 或仓位" class="h-12 w-full rounded-xl border border-slate-200 bg-white pl-11 pr-3 text-base">
    </label>
    <p v-if="message" role="status" class="rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-900">{{ message }}</p>
    <div v-if="error" role="alert" class="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-amber-50 px-4 py-2 text-sm text-amber-950">
      <span class="min-w-0 [overflow-wrap:anywhere]">{{ error }}</span>
      <button type="button" class="min-h-11 shrink-0 font-semibold underline" @click="emit('refresh')">重试</button>
    </div>
    <p v-else-if="loading" role="status" class="rounded-xl bg-white px-4 py-6 text-center text-sm text-slate-600">正在读取本厂可发库存…</p>
    <p v-else-if="!results.length" role="status" class="rounded-xl bg-white px-4 py-6 text-center text-sm text-slate-600">{{ search.trim() ? '没有匹配的可发库存。' : '本厂暂无可发库存。' }}</p>
    <template v-else>
      <p class="px-1 text-xs font-semibold text-slate-600">可发库存 · {{ results.length }} 项</p>
      <ul class="space-y-2">
        <li v-for="row in results.slice(0, limit)" :key="row.id">
          <button type="button" :disabled="!ready" :aria-pressed="selected.includes(row.id)" class="flex w-full min-w-0 items-start gap-3 rounded-xl border p-3.5 text-left shadow-sm active:border-teal-600 disabled:opacity-60" :class="selected.includes(row.id) ? 'border-teal-600 bg-teal-50' : 'border-slate-200 bg-white'" @click="emit('select', row.id)">
            <span class="mt-1 flex size-6 shrink-0 items-center justify-center rounded-md border" :class="selected.includes(row.id) ? 'border-teal-700 bg-teal-700 text-white' : 'border-slate-300 bg-white'" aria-hidden="true">
              <Check v-if="selected.includes(row.id)" class="size-4" />
            </span>
            <span class="min-w-0 flex-1 [overflow-wrap:anywhere]">
              <strong class="block text-base leading-snug">{{ row.itemNo || row.packagingType }}</strong>
              <span class="mt-1 block text-sm leading-snug text-slate-700">{{ [row.packagingType, row.paperQuality, row.specification].filter(Boolean).join(' · ') }}</span>
              <span v-if="row.customer || row.poNumber || row.customerPo" class="mt-1 block text-xs text-slate-600">{{ [row.customer, row.poNumber, row.customerPo && `客户 PO ${row.customerPo}`].filter(Boolean).join(' · ') }}</span>
              <span class="mt-2 flex items-center gap-1 text-xs text-slate-600"><MapPin class="size-3.5 shrink-0" aria-hidden="true" />{{ [row.warehouse, row.location].filter(Boolean).join(' / ') || '仓位未设置' }}</span>
            </span>
            <span class="max-w-[35%] shrink-0 text-right [overflow-wrap:anywhere]">
              <span class="block text-xs text-slate-500">可发</span>
              <strong class="block text-base tabular-nums text-teal-800">{{ quantity.format(row.balance) }} {{ row.unit }}</strong>
            </span>
          </button>
        </li>
      </ul>
      <button v-if="limit < results.length" type="button" class="min-h-11 w-full rounded-lg border bg-white text-sm font-semibold text-teal-800" @click="limit += pageSize">显示更多库存</button>
    </template>
    <footer class="carton-phone-footer fixed inset-x-0 bottom-0 z-20 border-t border-slate-200 bg-white px-4 pt-3">
      <div class="mx-auto flex max-w-xl gap-2">
        <button v-if="selected.length" type="button" class="min-h-12 shrink-0 rounded-xl border px-4 text-sm font-semibold text-slate-700" @click="emit('clear')">清空</button>
        <button type="button" :disabled="!ready || loading || !selected.length" class="min-h-12 flex-1 rounded-xl bg-teal-800 px-4 text-base font-bold text-white disabled:opacity-50" @click="emit('review', $event)">{{ selected.length ? `已选 ${selected.length} 项 · 去发料` : '请勾选要发料的库存' }}</button>
      </div>
    </footer>
  </section>
</template>
