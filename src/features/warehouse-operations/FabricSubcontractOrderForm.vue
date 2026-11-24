<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { processes, warehouseDay, batchLabel, type Process, type SubWorkspace } from '@/api/fabricSubcontract'

const props = defineProps<{ data: SubWorkspace; locked: boolean }>()
const emit = defineEmits<{ save: [path: string, body: Record<string, unknown>]; cancel: [] }>()
const process = ref<Process>('捆条'), processorId = ref('')
const businessDate = ref(warehouseDay()), due = ref(''), source = ref(''), previous = ref('')
const engineering = computed(() => process.value === '电绣' || process.value === '丝印')
const factories = computed(() => props.data.processors.filter(p => p.active && p.processes.includes(process.value)))
const inputs = reactive<{ id: string; quantity: string }[]>([])
const outputs = reactive([{ id: '', quantity: '' }])
watch(process, () => { processorId.value = '' })
function submit() {
  if (engineering.value || props.locked) return
  emit('save', '/orders', { process: process.value, processor_id: processorId.value, business_date: businessDate.value,
    due_date: due.value, source_no: source.value, previous_order_id: previous.value || null, inputs, outputs })
}
</script>
<template>
  <form class="sub-card" aria-label="新建委外单" @submit.prevent="submit">
    <header class="sub-head"><h2>新建委外单</h2><Button type="button" variant="outline" :disabled="locked" @click="emit('cancel')">返回台账</Button></header>
    <fieldset :disabled="locked"><div class="sub-grid">
      <label>委外工艺<select v-model="process"><option v-for="p in processes" :key="p">{{ p }}</option></select></label>
      <label v-if="!engineering">加工厂<select v-model="processorId" required><option value="">请选择加工厂</option><option v-for="p in factories" :key="p.id" :value="p.id">{{ p.code }} · {{ p.name }}</option></select></label>
      <label v-else>工程指定加工厂<input value="待工程系统带出" readonly /></label>
      <label>开单日期<input v-model="businessDate" type="date" :max="warehouseDay()" required /></label>
      <label>要求交期<input v-model="due" type="date" :min="businessDate" required /></label>
      <label>来源单号（选填）<input v-model.trim="source" maxlength="128" placeholder="工程或纸质单号" /></label>
      <label v-if="data.orders.length">前序委外单（选填）<select v-model="previous"><option value="">无前序单</option><option v-for="o in data.orders" :value="o.id" :key="o.id">{{ o.id }} · {{ o.process }} · {{ o.processor.name }}</option></select></label>
      <label>首个收货仓<input value="华康 C 布料仓" readonly /></label>
    </div>
    <p v-if="engineering" class="sub-note" role="status">该工艺由工程指定加工厂。待工程资料接入后方可开单。</p>
    <p v-else-if="!factories.length" class="sub-note">请先在「基础资料 → 加工厂」启用适用该工艺的加工厂。</p>
    <h3>应回产物</h3>
    <div v-for="(line, i) in outputs" :key="i" class="sub-line">
      <label>产物<select v-model="line.id" required><option value="">请选择已启用物料</option><option v-for="m in data.materials" :key="m.id" :value="m.id" :disabled="outputs.some(r => r !== line && r.id === m.id)">{{ m.item_code }} · {{ m.item_name }}（{{ m.unit }}）</option></select></label>
      <label>应回数量<input v-model="line.quantity" type="text" inputmode="decimal" pattern="(?:[0-9]{1,12})(?:[.][0-9]{1,6})?" required /></label>
      <Button v-if="outputs.length > 1" type="button" variant="ghost" @click="outputs.splice(i,1)">移除</Button>
    </div>
    <Button type="button" variant="outline" @click="outputs.push({id:'',quantity:''})">添加产物</Button>
    <h3>计划投入原料</h3><p class="sub-note">可以在开单后选料。仓管确认实发时扣减相应批次。</p>
    <div v-for="(line, i) in inputs" :key="i" class="sub-line">
      <label>原料批次<select v-model="line.id" required><option value="">请选择库存批次</option><option v-for="b in data.stock" :key="b.id" :value="b.id" :disabled="inputs.some(r => r !== line && r.id === b.id)">{{ batchLabel(b) }}</option></select></label>
      <label>计划投入数量<input v-model="line.quantity" type="text" inputmode="decimal" pattern="(?:[0-9]{1,12})(?:[.][0-9]{1,6})?" required /></label>
      <Button type="button" variant="ghost" @click="inputs.splice(i,1)">移除</Button>
    </div>
    <Button type="button" variant="outline" @click="inputs.push({id:'',quantity:''})">从库存选料</Button>
    <footer><Button type="submit" :disabled="engineering || !factories.length || !data.materials.length">确认开单</Button></footer>
    </fieldset>
  </form>
</template>
