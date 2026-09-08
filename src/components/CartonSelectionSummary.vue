<script setup lang="ts">
import { computed, ref, watch } from 'vue'
const props = defineProps<{ rows: { id: string; label: string }[]; visibleIds: string[]; unit?: string }>()
const emit = defineEmits<{ clear: []; remove: [id: string] }>()
const details = ref<HTMLDetailsElement>()
watch(() => props.rows.length, count => { if (!count && details.value) details.value.open = false })
const hidden = computed(() => props.rows.filter(row => !props.visibleIds.includes(row.id)).length)
</script>

<template>
  <div class="relative flex min-h-9 w-full items-center gap-3 text-xs" aria-label="批量已选范围">
    <div class="flex min-w-0 flex-1 items-center gap-3">
      <span class="truncate">已选 <b>{{ rows.length }}</b> {{ unit || '条' }}<span v-if="hidden" class="ml-2 font-semibold text-amber-700">其中 {{ hidden }} {{ unit || '条' }}不在当前筛选内</span></span>
      <button type="button" :disabled="!rows.length" class="shrink-0 text-teal-700 disabled:text-slate-400" @click="emit('clear')">清空选择</button>
    </div>
    <details ref="details" class="shrink-0"><summary class="cursor-pointer text-teal-700" :aria-disabled="!rows.length" @click="!rows.length && $event.preventDefault()">查看已选</summary>
      <ul class="absolute right-0 top-full z-30 mt-1 max-h-64 w-full max-w-xl overflow-auto rounded-lg border border-teal-100 bg-white px-3 shadow-lg">
        <li v-for="row in rows" :key="row.id" class="flex items-center justify-between gap-3 border-b border-slate-100 py-2 last:border-0">
          <span>{{ row.label }}<span v-if="!visibleIds.includes(row.id)" class="ml-2 text-amber-700">当前筛选外</span></span>
          <button type="button" :aria-label="`取消选择 ${row.label}`" class="shrink-0 text-slate-500 underline" @click="emit('remove', row.id)">取消选择</button>
        </li>
      </ul>
    </details>
  </div>
</template>
