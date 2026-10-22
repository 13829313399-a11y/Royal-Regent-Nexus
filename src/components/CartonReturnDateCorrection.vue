<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { formatBusinessDate } from '@/lib/dateTime'

export interface ReturnDateCorrectionSource {
  movementId: string
  documentNo: string
  returnDate: string
  postingDate: string
  revision: number
  fingerprint: string
}
const props = defineProps<{ source: ReturnDateCorrectionSource; busy?: boolean; disabled?: boolean; error?: string }>()
const emit = defineEmits<{ save: [{ return_date: string; reason: string }]; cancel: [] }>()
const nextDate = ref(''), reason = ref(''), localError = ref('')
const today = () => formatBusinessDate(new Date().toISOString())
const oldMonth = computed(() => props.source.returnDate.slice(0, 7))
watch([() => props.source.movementId, () => props.source.revision, () => props.source.fingerprint], () => {
  nextDate.value = ''; reason.value = ''; localError.value = ''
}, { immediate: true })
function save() {
  if (props.busy || props.disabled) return
  localError.value = ''
  if (!/^\d{4}-\d{2}-\d{2}$/.test(nextDate.value) || nextDate.value > today() || nextDate.value === props.source.returnDate || reason.value.trim().length < 4) {
    localError.value = '请填写不晚于今天、与原记录不同的实际退货日期，以及至少四字更正原因。'
    return
  }
  emit('save', { return_date: nextDate.value, reason: reason.value.trim() })
}
</script>

<template>
  <form aria-label="更正已录实际退货日期" class="space-y-3 rounded-xl border border-amber-200 bg-white p-4 text-xs" @submit.prevent="save">
    <div><h3 class="font-semibold text-slate-900">更正实际退货日期 · {{ source.documentNo }}</h3><p class="mt-2 text-slate-600">只更正供应商退货归属月份，库存原记账时间和真实回款记录保留。涉及已确认月份须先说明原因重核，相关签收与贷项按最新版本重新核对。</p></div>
    <div class="grid gap-3 sm:grid-cols-2">
      <p class="rounded-lg bg-slate-50 p-3">原实际退货日期 <b class="tabular-nums">{{ source.returnDate }}</b><span class="mt-1 block text-slate-500">旧归属月份 {{ oldMonth }}</span></p>
      <p class="rounded-lg bg-slate-50 p-3">库存原记账日期 <b class="tabular-nums">{{ source.postingDate }}</b><span class="mt-1 block text-slate-500">更正日期不会重做库存出库</span></p>
      <label class="block font-semibold">更正后的实际退货日期<input v-model="nextDate" :disabled="busy || disabled" required type="date" :max="today()" aria-label="更正后的实际退货日期" class="mt-1 block h-10 w-full rounded-lg border border-input bg-card px-3 font-normal"><span class="mt-1 block font-normal text-slate-500">新归属月份 {{ nextDate ? nextDate.slice(0, 7) : '待填写' }}</span></label>
      <label class="block font-semibold">更正原因<textarea v-model="reason" :disabled="busy || disabled" required minlength="4" maxlength="2000" rows="2" aria-label="实际退货日期更正原因" class="mt-1 block w-full rounded-lg border border-input bg-card px-3 py-2 font-normal" placeholder="说明原日期错误及核实依据" /></label>
    </div>
    <p v-if="error || localError" role="alert" class="text-red-700">{{ error || localError }}</p>
    <div class="flex flex-wrap gap-2"><Button :disabled="busy || disabled" size="sm">{{ busy ? '正在保存更正…' : '保存更正日期' }}</Button><Button type="button" variant="outline" size="sm" :disabled="busy" @click="emit('cancel')">返回</Button></div>
  </form>
</template>
