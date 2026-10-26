<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { X } from '@lucide/vue'

export interface AdjustmentPaper { id: string; label: string; unit: string; current: number; protected: number; minimum?: number }
const props = withDefaults(defineProps<{
  action: 'append' | 'reduce' | 'date'; orderNo: string; lines?: AdjustmentPaper[]; busy?: boolean
  productEnabled?: boolean; productCurrent?: number; productMaximum?: number
  customerDateEnabled?: boolean; customerDateRequired?: boolean; manualPlan?: boolean; plannedDate?: string
  dateLabel?: string; minDate?: string; dateHelp?: string; guidance?: string; notice?: string; error?: string
  title?: string; submitLabel?: string; reasonMax?: number
}>(), { lines: () => [], manualPlan: true, dateLabel: '计划交期', reasonMax: 500 })
const byPaper = defineModel<boolean>('byPaper', { default: true })
const quantity = defineModel<number>('quantity', { default: 0 })
const targets = defineModel<Record<string, number | string>>('targets', { default: () => ({}) })
const customerDate = defineModel<string>('customerDate', { default: '' })
const dueDate = defineModel<string>('dueDate', { default: '' })
const reason = defineModel<string>('reason', { default: '' })
const emit = defineEmits<{ submit: []; close: [] }>()
const formElement = ref<HTMLFormElement>()
onMounted(() => { formElement.value?.querySelector<HTMLInputElement>(props.action === 'date' ? 'input[type=date]' : 'input[type=number]')?.focus() })
const titles = { append: '追加订单', reduce: '减少未入库量', date: '调整交期' }
const title = computed(() => props.title || titles[props.action])
const format = (value: number) => value.toLocaleString('zh-CN', { maximumFractionDigits: 4 })
const productAfter = computed(() => (props.productCurrent || 0) + (props.action === 'reduce' ? -quantity.value : quantity.value))
const targetLabel = (id: string) => `${props.action === 'append' ? '追加后' : '减少后'}纸品需求 ${id}`
function setTarget(id: string, event: Event) { targets.value = { ...targets.value, [id]: (event.target as HTMLInputElement).value } }
</script>

<template>
  <form ref="formElement" :data-testid="`${action}-order-form`" :aria-label="title" class="carton-adjustment-form flex max-h-[88dvh] w-full flex-col overflow-hidden rounded-2xl bg-white shadow-2xl" :class="action === 'append' ? 'max-w-2xl' : 'max-w-lg'" @submit.prevent="!busy && emit('submit')">
    <div class="flex shrink-0 items-start justify-between border-b border-slate-200 px-5 py-4">
      <div><h2 class="text-[16px] font-bold text-slate-950">{{ title }} · {{ orderNo }}</h2><p v-if="notice" class="mt-1 text-xs text-amber-800">{{ notice }}</p><p v-if="guidance" class="mt-1 text-xs text-slate-500">{{ guidance }}</p></div>
      <button type="button" :aria-label="`关闭${title}`" :disabled="busy" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100 disabled:opacity-40" @click="emit('close')"><X class="size-4" /></button>
    </div>
    <fieldset :disabled="busy" class="min-h-0 space-y-4 overflow-y-auto p-5">
      <p v-if="error" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">{{ error }}</p>
      <label v-if="productEnabled && action !== 'date'" class="block text-sm"><input v-model="byPaper" type="checkbox" :aria-label="action === 'append' ? '追加只调整纸品数量' : '减少只调整纸品数量'"> 只调整纸品数量（产品数量不变）</label>
      <template v-if="action !== 'date' && !byPaper && productEnabled">
        <div class="grid grid-cols-3 gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs"><div>当前产品数量<b class="mt-1 block">{{ format(productCurrent || 0) }}</b></div><div v-if="action === 'reduce'">最大可减<b class="mt-1 block text-amber-700">{{ format(productMaximum || 0) }}</b></div><div>调整后数量<b class="mt-1 block text-teal-700">{{ format(productAfter) }}</b></div></div>
        <label class="block text-xs font-bold text-slate-600">{{ action === 'append' ? '追加产品数量' : '减少产品数量' }} *<input v-model.number="quantity" :aria-label="action === 'append' ? '追加订单数量' : '减单数量'" type="number" min="1" :max="action === 'reduce' ? productMaximum : undefined" required class="mt-2 h-10 w-full rounded-lg border px-3 text-right"></label>
      </template>
      <div v-if="action !== 'reduce'" class="grid gap-4" :class="customerDateEnabled ? 'sm:grid-cols-2' : 'grid-cols-1'">
        <label v-if="customerDateEnabled" class="text-xs font-bold text-slate-600">{{ action === 'append' ? '新客户交期' : '客户交期' }}<input v-model="customerDate" :aria-label="action === 'append' ? '追加订单客户交期' : '调整客户交期'" type="date" :min="minDate" :required="customerDateRequired" class="mt-2 h-10 w-full rounded-lg border px-3"></label>
        <label class="text-xs font-bold text-slate-600">{{ dateLabel }}<input v-if="manualPlan" v-model="dueDate" :aria-label="customerDateEnabled ? action === 'append' ? '追加订单计划交期' : '调整计划交期' : '需求日期'" type="date" :min="minDate" required class="mt-2 h-10 w-full rounded-lg border px-3"><input v-else :value="plannedDate" :aria-label="action === 'append' ? '追加订单计划交期' : '调整计划交期'" type="date" readonly class="mt-2 h-10 w-full rounded-lg border border-teal-200 bg-teal-50 px-3 text-teal-800"><span v-if="dateHelp" class="mt-1 block font-normal text-slate-500">{{ dateHelp }}</span></label>
      </div>
      <div v-if="action !== 'date' && byPaper" class="min-w-0">
        <p class="mb-2 text-xs text-teal-700">逐纸品填写{{ action === 'append' ? '追加' : '减少' }}后的总需求，未调整的行保持原值。</p>
        <table class="w-full text-left text-xs"><thead class="bg-slate-50 text-slate-600"><tr><th>纸品 / 纸质 / 规格</th><th>当前需求</th><th v-if="action === 'reduce'">已收及受保护数量</th><th>{{ action === 'append' ? '追加后' : '减少后' }}总需求</th></tr></thead><tbody><tr v-for="line in lines" :key="line.id" class="border-t border-slate-200"><td data-label="纸品 / 纸质 / 规格">{{ line.label }}</td><td data-label="当前需求">{{ format(line.current) }} {{ line.unit }}</td><td v-if="action === 'reduce'" data-label="已收及受保护数量">{{ format(line.protected) }} {{ line.unit }}</td><td :data-label="action === 'append' ? '追加后总需求' : '减少后总需求'"><input :value="targets[line.id]" :aria-label="targetLabel(line.id)" type="number" :min="action === 'append' ? line.current : Math.max(line.protected, line.minimum || 0)" :max="action === 'reduce' ? line.current : undefined" step="0.0001" required class="h-9 w-full min-w-20 rounded border bg-white px-2 text-right" @input="setTarget(line.id, $event)"><span>{{ line.unit }}</span></td></tr></tbody></table>
      </div>
      <slot />
      <label class="block text-xs font-bold text-slate-600">{{ action === 'append' ? '追加原因' : action === 'reduce' ? '减单 / 退单原因' : '调整原因' }} *<textarea v-model="reason" :aria-label="action === 'append' ? '追加订单原因' : action === 'reduce' ? '减单原因' : '交期调整原因'" rows="3" minlength="4" :maxlength="reasonMax" required class="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2" /></label>
    </fieldset>
    <div class="flex shrink-0 justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-4"><button type="button" :disabled="busy" class="h-9 rounded-lg border bg-white px-4 text-xs font-bold text-slate-600 disabled:opacity-40" @click="emit('close')">返回</button><button type="submit" :disabled="busy" class="h-9 rounded-lg px-4 text-xs font-bold text-white disabled:opacity-40" :class="action === 'reduce' ? 'bg-red-600' : action === 'append' ? 'bg-amber-600' : 'bg-teal-700'">{{ busy ? '正在保存…' : submitLabel || (action === 'date' ? '保存并同步供应商' : action === 'append' ? '确认追加并同步供应商' : '确认减单并同步供应商') }}</button></div>
  </form>
</template>

<style scoped>
th,td { padding:8px; overflow-wrap:anywhere; } td { font-variant-numeric:tabular-nums; }
@media(max-width:639px) { table,tbody,tr,td { display:block; } thead { display:none; } tr { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); padding:8px 0; } td::before { display:block; content:attr(data-label); color:var(--muted-foreground); margin-bottom:4px; } }
</style>
