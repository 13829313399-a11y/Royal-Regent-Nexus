<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { actionLabels, stageLabels, warehouseDay, batchLabel, type Stage, type SubOrder, type SubWorkspace } from '@/api/fabricSubcontract'
import { remaining, sendableSubcontractInputs } from './operations'
import WarehouseLocationPicker from './WarehouseLocationPicker.vue'

const props = defineProps<{ data: SubWorkspace; order: SubOrder; stage: Stage; original?: string; locked: boolean }>()
const emit = defineEmits<{ save: [path: string, body: Record<string, unknown>]; cancel: [] }>()
const target = ref(''), qty = ref(''), date = ref(warehouseDay()), voucher = ref(''), location = ref('')
const lot = ref(''), roll = ref(''), recipient = ref(''), destination = ref(''), reason = ref('')
const countNow = ref(true), differentQuantity = ref(false), countedQty = ref('')
const immediateReceipt = computed(() => props.stage === 'DELIVER' && countNow.value)
const needsWarehouse = computed(() => props.stage === 'RECEIVE' || immediateReceipt.value)
const receivedQuantity = computed(() => differentQuantity.value ? countedQty.value : qty.value)
const quantityPattern = '[0-9]{1,12}(?:[.][0-9]{1,6})?'
const validQuantity = new RegExp('^' + quantityPattern + '$')
const countError = computed(() => {
  if (!immediateReceipt.value || !differentQuantity.value || !validQuantity.test(countedQty.value) || !validQuantity.test(qty.value)) return ''
  if (Number(countedQty.value) === 0) return '实收为零时，请选「先记到货」。'
  if (remaining(qty.value, countedQty.value).startsWith('-')) return '实收数量超过本次送货数量，请核对。'
  return ''
})
const choices = computed(() => {
  const o = props.order
  switch (props.stage) {
    case 'SOURCE': return [{ id:o.id, label:o.id, max:'', unit:'' }]
    case 'SELECT': return props.data.stock.filter(b => !o.inputs.some(i => i.id === b.id)).map(b => ({id:b.id, label:batchLabel(b), max:'', unit:b.unit}))
    case 'SEND': return sendableSubcontractInputs(o.inputs, props.data.stock).map(({batch, max}) => ({id:batch.id, label:batchLabel(batch), max, unit:batch.unit}))
    case 'DELIVER': return o.outputs.filter(r => Number(r.undelivered)>0).map(r => ({id:r.id, label:r.item_code+' · '+r.item_name, max:r.undelivered, unit:r.unit}))
    case 'ISSUE': return o.batches.map(b => ({id:b.id, label:batchLabel(b), max:b.available!, unit:b.unit}))
    case 'RECEIVE': case 'SIGN': return o.events.filter(e => e.kind === (props.stage === 'RECEIVE' ? 'DELIVER' : 'SEND') && !e.voided && Number(e.remaining)>0)
      .map(e => ({id:e.id, label:e.voucher+' · '+e.item_name+' · '+e.business_date, max:e.remaining!, unit:e.unit}))
    case 'VOID': return o.events.filter(e => !e.voided && !['SELECT','VOID','SOURCE'].includes(e.kind)).map(e => ({id:e.id, label:stageLabels[e.kind]+' · '+e.voucher+' · '+e.item_name, max:e.quantity, unit:e.unit}))
  }
})
const chosen = computed(() => choices.value.find(v => v.id === target.value))
const sendError = computed(() => props.stage === 'SEND' && chosen.value?.max && validQuantity.test(qty.value)
  && remaining(chosen.value.max, qty.value).startsWith('-') ? '发料数量超过该批当前可发量。' : '')
const output = computed(() => {
  const outputId = props.stage === 'DELIVER' ? target.value : props.order.events.find(e => e.id === target.value)?.target_id
  return props.order.outputs.find(row => row.id === outputId)
})
const previouslyCounted = computed(() => props.stage === 'RECEIVE' && props.order.events.some(event =>
  event.kind === 'RECEIVE' && event.target_id === target.value && !event.voided))
watch(() => [props.stage,props.original], () => {target.value=props.original || choices.value[0]?.id || ''}, { immediate:true })
watch(target, () => {
  qty.value=''; countedQty.value=''; differentQuantity.value=false; location.value=''; lot.value=''; roll.value=''
  if (props.stage === 'RECEIVE') {
    const delivery = props.order.events.find(event => event.id === target.value)
    voucher.value = previouslyCounted.value ? '' : delivery?.voucher || ''
  }
}, { immediate:true })
const targetLabel: Record<Stage,string> = { SELECT:'库存批次', SEND:'计划原料批次', SIGN:'原料实发凭证', DELIVER:'计划产物', RECEIVE:'送达批次', ISSUE:'可领回仓批次', VOID:'原凭证', SOURCE:'当前委外单' }
function submit() {
  if (!chosen.value || props.locked || countError.value || sendError.value || (needsWarehouse.value && !location.value)) return
  emit('save', '/orders/'+props.order.id+'/actions', {kind:immediateReceipt.value ? 'DELIVER_AND_RECEIVE' : props.stage, target_id:target.value,
    ...(immediateReceipt.value ? {received_quantity:receivedQuantity.value} : {}),
    quantity:['VOID','SOURCE'].includes(props.stage) ? null : qty.value, business_date:date.value, voucher:voucher.value,
    location_id:needsWarehouse.value ? location.value : '', lot:needsWarehouse.value ? lot.value : '', roll_no:needsWarehouse.value ? roll.value : '',
    recipient:recipient.value, destination:destination.value, reason:reason.value})
}
</script>
<template>
  <form class="sub-card sub-action" @submit.prevent="submit">
    <header class="sub-head"><h3>{{ actionLabels[stage] }}</h3><Button type="button" variant="ghost" :disabled="locked" @click="emit('cancel')">收起</Button></header>
    <fieldset :disabled="locked"><div class="sub-grid">
      <label>{{ targetLabel[stage] }}<select v-model="target" required><option value="">请选择</option><option v-for="c in choices" :value="c.id" :key="c.id">{{ c.label }}</option></select></label>
      <label v-if="stage !== 'VOID' && stage !== 'SOURCE'">{{ stage === 'DELIVER' ? '送货数量' : stage === 'RECEIVE' ? '本次实收' : '本次数量' }}{{ chosen ? '（'+chosen.unit+'）' : '' }}<input v-model="qty" type="text" inputmode="decimal" :pattern="quantityPattern" required /><small v-if="chosen?.max">本次最多 {{ chosen.max }} {{ chosen.unit }}</small></label>
      <label>业务日期<input v-model="date" type="date" required :min="order.business_date" :max="warehouseDay()" /></label>
      <label v-if="stage !== 'SELECT'">{{ stage === 'ISSUE' ? '部门来单号' : stage === 'SOURCE' ? '来源单号' : stage === 'DELIVER' ? '送货单号' : stage === 'RECEIVE' ? '本次点收凭证号' : '凭证号' }}<input v-model.trim="voucher" maxlength="128" required /><small v-if="previouslyCounted">此批已点收过，请填写本次点收凭证。</small></label>
      <template v-if="stage === 'ISSUE'"><label>领料部门<input v-model.trim="recipient" required maxlength="128" /></label><label>实际去向<input v-model.trim="destination" required maxlength="128" /></label></template>
      <label v-if="stage === 'VOID'">更正原因<input v-model.trim="reason" required maxlength="255" /></label>
    </div>
    <fieldset v-if="stage === 'DELIVER'" class="sub-receipt-options"><legend>本次怎么收</legend>
      <div class="sub-checks"><label><input v-model="countNow" type="radio" name="count-timing" :value="true" />当场点收</label>
        <label><input v-model="countNow" type="radio" name="count-timing" :value="false" />先记到货</label></div>
    </fieldset>
    <template v-if="needsWarehouse">
      <div class="sub-grid sub-receipt-fields">
        <div><span>回仓仓位</span><WarehouseLocationPicker :key="target" v-model="location" :locations="data.locations" :category="output?.material_category" label="回仓仓位" /></div>
        <label>批次 / 缸号{{ output?.material_category === 'FABRIC' ? '' : '（选填）' }}<input v-model.trim="lot" :required="output?.material_category === 'FABRIC'" maxlength="128" /></label>
        <label>卷号（选填）<input v-model.trim="roll" maxlength="128" /></label>
      </div>
      <div v-if="immediateReceipt" class="sub-checks"><label><input v-model="differentQuantity" type="checkbox" />实收与送货数量不同</label></div>
      <div v-if="immediateReceipt && differentQuantity" class="sub-grid sub-counted-qty">
        <label>实际点收数量{{ chosen ? '（'+chosen.unit+'）' : '' }}<input v-model="countedQty" type="text" inputmode="decimal" :pattern="quantityPattern" required :aria-invalid="!!countError" /></label>
      </div>
      <p v-if="countError" role="alert" class="sub-error">{{ countError }}</p>
    </template>
    <p v-if="!choices.length" role="status" class="sub-note">本单暂时没有可办理这一步的明细。</p>
    <p v-if="sendError" role="alert" class="sub-error">{{ sendError }}</p>
    <footer><Button type="submit" :disabled="!chosen || !!countError || !!sendError || (needsWarehouse && !location)">{{ needsWarehouse ? '确认入库' : stage === 'DELIVER' ? '确认到货，稍后点收' : '确认'+actionLabels[stage] }}</Button>
      <small v-if="immediateReceipt && validQuantity.test(receivedQuantity) && !countError">本次入库 {{ receivedQuantity }} {{ chosen?.unit }}</small>
      <small v-if="stage === 'DELIVER' && !countNow">仅登记送货数量，点收后再入库。</small>
    </footer></fieldset>
  </form>
</template>
