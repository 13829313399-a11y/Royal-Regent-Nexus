<script setup lang="ts">
import { ShieldCheck } from '@lucide/vue'

defineProps<{ mode: 'each_page' | 'ranges'; pageRanges: string; disabled?: boolean }>()
const emit = defineEmits<{
  'update:mode': [value: 'each_page' | 'ranges']
  'update:pageRanges': [value: string]
}>()
</script>

<template>
  <div class="rounded-xl border border-slate-200 bg-slate-50 p-3">
    <div class="flex items-center gap-2 text-sm font-semibold text-slate-800"><ShieldCheck class="size-4 text-teal-700" aria-hidden="true" />本地确定性处理</div>
    <p class="mt-1.5 text-xs leading-5 text-slate-600">使用 pypdf 拆分，不调用 AI。</p>
  </div>
  <div>
    <p class="text-xs font-semibold text-slate-700">拆分方式</p>
    <div class="mt-2 grid grid-cols-2 gap-2">
      <button type="button" class="rounded-lg border px-3 py-2 text-xs font-semibold" :class="mode === 'each_page' ? 'border-teal-400 bg-teal-50 text-teal-800' : 'border-slate-200 text-slate-600'" :disabled="disabled" @click="emit('update:mode', 'each_page')">每页一个文件</button>
      <button type="button" class="rounded-lg border px-3 py-2 text-xs font-semibold" :class="mode === 'ranges' ? 'border-teal-400 bg-teal-50 text-teal-800' : 'border-slate-200 text-slate-600'" :disabled="disabled" @click="emit('update:mode', 'ranges')">指定页段</button>
    </div>
    <label v-if="mode === 'ranges'" class="mt-3 block text-xs font-medium text-slate-600">页段<input :value="pageRanges" type="text" class="mt-1.5 h-9 w-full rounded-lg border border-slate-300 px-3 text-sm" placeholder="例如 1-3,5,8-10" :disabled="disabled" @input="emit('update:pageRanges', ($event.target as HTMLInputElement).value)"></label>
  </div>
</template>
