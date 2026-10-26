<script setup lang="ts">
export interface AcceptancePaper { id: string; label: string; description: string; required: number; accepted: boolean; promised?: string; dateLabel: string; date: string; difference?: string }
defineProps<{ lines: AcceptancePaper[]; plannedDate: string; wholeOrder?: boolean; busy?: boolean; disabled?: boolean; dateLocked?: boolean; date?: string; dateLabel?: string; difference?: string; accepted?: boolean }>()
const emit = defineEmits<{ date: [id: string, value: string]; accept: [id: string] }>()
</script>
<template>
  <div class="space-y-3">
    <p class="text-xs text-slate-500">我方计划交期 {{ plannedDate || '未填写' }}。{{ wholeOrder ? '本次确认当前版本的全部纸品，共用一个承诺交期。' : '逐条确认纸品及承诺交期；全部确认后，订单进入可发货状态。' }}</p>
    <div v-for="line in lines" :key="line.id" class="flex flex-wrap items-center gap-3 border-b border-slate-100 py-3 text-xs">
      <div class="min-w-0 flex-1 basis-64"><b>{{ line.label }}</b><p class="mt-1 text-slate-500">{{ line.description }}</p><p v-if="line.promised && !line.accepted" class="mt-1 text-amber-700">旧交期 {{ line.promised }}，需重新确认</p></div>
      <span v-if="line.required <= 0" class="font-semibold text-slate-500">需求已归零 · 无需接单</span>
      <template v-else-if="!wholeOrder"><span v-if="line.accepted" class="font-semibold text-emerald-700">已确认 · {{ line.promised }}</span><label class="font-semibold text-slate-600">承诺交期 <input :value="line.date" type="date" :aria-label="line.dateLabel" :disabled="busy || disabled || dateLocked" class="ml-1 h-9 max-w-full rounded-lg border border-slate-200 px-2" @input="emit('date', line.id, ($event.target as HTMLInputElement).value)"></label><p v-if="line.difference" role="status" class="w-full font-semibold text-amber-700">{{ line.difference }}</p><button type="button" :disabled="busy || disabled" class="h-9 rounded-lg bg-teal-700 px-3 font-semibold text-white disabled:opacity-40" @click="emit('accept', line.id)">{{ line.accepted ? '保存承诺交期' : '确认接单' }}</button></template>
    </div>
    <template v-if="wholeOrder"><span v-if="accepted" class="text-xs font-semibold text-emerald-700">当前版本已确认</span><label class="block text-xs font-semibold text-slate-600">承诺交期 <input :value="date" type="date" :aria-label="dateLabel" :disabled="busy || disabled || dateLocked" class="ml-1 h-9 max-w-full rounded-lg border border-slate-200 px-2" @input="emit('date', '', ($event.target as HTMLInputElement).value)"></label><p v-if="difference" role="status" class="text-xs font-semibold text-amber-700">{{ difference }}</p></template>
  </div>
</template>
