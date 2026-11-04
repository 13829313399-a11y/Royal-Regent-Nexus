<script setup lang="ts">
import { computed } from 'vue'
import type { OutputField } from '@/api/internalQuoteOutput'
type Mode = 'formula' | 'per_piece' | 'per_carton'
const props = defineProps<{ field: OutputField; mode: Mode; value: string | number | null; disabled?: boolean }>()
const emit = defineEmits<{ change: [mode: Mode, value: string | number | null] }>()
const basis = computed(() => props.field.adjustment!)
const adopted = computed(() => {
  if (props.mode === 'formula') return Number(basis.value.original_per_piece_hkd)
  if (props.value === null || props.value === '' || !Number.isFinite(Number(props.value)) || Number(props.value) < 0) return null
  return Number(props.value) / (props.mode === 'per_carton' ? Number(basis.value.qty_per_carton) : 1)
})
function selectMode(event: Event) {
  const mode = (event.target as HTMLSelectElement).value as Mode
  const current = adopted.value ?? Number(basis.value.original_per_piece_hkd)
  emit('change', mode, mode === 'formula' ? null : String(current * (mode === 'per_carton' ? Number(basis.value.qty_per_carton) : 1)))
}
</script>

<template>
  <section class="amount-adjustment" aria-label="报价采用金额">
    <p v-if="basis.status === 'pending'" class="pending" role="status">原资料已变化，旧调价待确认。请核对以下依据，重新确认或恢复公式核算。</p>
    <dl><div><dt>原核算金额</dt><dd>HKD {{ Number(basis.original_per_piece_hkd).toFixed(4) }} / 件</dd></div>
      <div v-if="basis.qty_per_carton"><dt>原每箱金额 / 装箱数量</dt><dd>HKD {{ Number(basis.original_per_carton_hkd).toFixed(4) }} / {{ basis.qty_per_carton }} 件</dd></div></dl>
    <p class="hint">倍率前成本，整单报价仍按原有倍率和杂费计算。<template v-if="basis.qty_per_carton">纸箱金额不含平卡；平卡按各自用量单独计算。</template></p>
    <label><span>计价方式</span><select :value="mode" :disabled="disabled" aria-label="计价方式" @change="selectMode"><option value="formula">公式核算</option><option value="per_piece">直接采用每件金额</option><option v-if="basis.allowed_modes.includes('per_carton')" value="per_carton">供应商每箱金额</option></select></label>
    <label v-if="mode !== 'formula'"><span>{{ mode === 'per_carton' ? '每箱金额 HKD' : '采用金额 HKD/件' }}</span><input :value="value" :disabled="disabled" type="number" min="0" step="any" aria-label="报价采用金额" @input="emit('change', mode, ($event.target as HTMLInputElement).value)"></label>
    <p v-if="mode === 'per_carton' && field.id.includes('flat_cards')" class="hint">填写每箱该项平卡的合计金额，已包含平卡用量。</p>
    <dl><div><dt>采用金额</dt><dd>{{ adopted === null ? '待填写' : `HKD ${adopted.toFixed(4)} / 件` }}</dd></div><div><dt>与原核算差额</dt><dd>{{ adopted === null ? '—' : `HKD ${(adopted - Number(basis.original_per_piece_hkd)).toFixed(4)} / 件` }}</dd></div></dl>
    <div class="actions"><button v-if="basis.status === 'pending' && mode !== 'formula'" :disabled="disabled" @click="emit('change', mode, value)">确认按当前资料采用此金额</button><button v-if="mode !== 'formula'" :disabled="disabled" @click="emit('change', 'formula', null)">恢复公式核算</button></div>
    <p v-if="mode !== 'formula'" class="hint">请在下方填写调价原因（必填），可附截图。保存后生效。</p>
    <details v-if="field.adjustment_history?.length"><summary>调价记录（{{ field.adjustment_history.length }}）</summary><p v-for="(entry,index) in [...field.adjustment_history].reverse()" :key="index">{{ entry.updated_at }} · {{ entry.action === 'formula' ? '恢复公式' : `${entry.amount_hkd} HKD/${entry.action === 'per_carton' ? '箱' : '件'}` }}</p></details>
  </section>
</template>

<style scoped>
.amount-adjustment{margin-top:12px;border-top:1px solid #dce8e1;padding-top:12px;color:#234b45;font-size:12px}.amount-adjustment dl{margin:0;background:#f0faf6;border-radius:6px;padding:10px;display:grid;gap:9px}.amount-adjustment dl>div{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}.amount-adjustment dd{margin:0;font-weight:700;font-variant-numeric:tabular-nums}.hint{color:#607d77;font-size:11px;line-height:1.6}.pending{background:#fff7df;color:#895d14;padding:10px;line-height:1.6}.amount-adjustment label{display:grid;gap:7px;margin:12px 0}.amount-adjustment select,.amount-adjustment input{width:100%;min-width:0;box-sizing:border-box;border:1px solid #c7dbd1;border-radius:6px;padding:9px;background:#fff;color:#234b45}.actions{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}.actions button{border:1px solid #bddbd4;border-radius:6px;padding:8px;background:#fff;color:#19685b;cursor:pointer}.amount-adjustment :disabled{opacity:.5;cursor:not-allowed}details{margin:12px 0;color:#607d77}summary{cursor:pointer}details p{padding:5px 0;border-bottom:1px solid #e4efeb}
</style>
