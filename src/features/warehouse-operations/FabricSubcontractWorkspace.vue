<script setup lang="ts">
import { computed, inject, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { actionLabels, processes, stageLabels, subcontractApi, type Processor, type Stage, type SubWorkspace } from '@/api/fabricSubcontract'
import { inventorySearchKey } from './inventorySearch'
import { purchaseSearchKey } from './purchaseSearch'
import { warehouseRequestId } from './requestIdentity'
import { remaining, sendableSubcontractInputs } from './operations'
import FabricSubcontractOrderForm from './FabricSubcontractOrderForm.vue'
import FabricSubcontractActionForm from './FabricSubcontractActionForm.vue'
import FabricSubcontractProgress from './FabricSubcontractProgress.vue'
import './fabric-subcontract.css'

const props = defineProps<{ mode: 'orders' | 'processors' }>()
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const search = inject(inventorySearchKey, undefined), masterSearch = inject(purchaseSearchKey, undefined)
const data = ref<SubWorkspace>(), selected = ref(''), create = ref(false), editor = ref<Processor>(), stage = ref<Stage>(), original = ref('')
const busy = ref(false), loading = ref(false), error = ref(''), notice = ref('')
const actionBar = ref<HTMLElement>()
const order = computed(() => data.value?.orders.find(o => o.id === selected.value))
const term = computed(() => (props.mode === 'orders' ? search : masterSearch)?.search.value.trim().toLowerCase() || '')
const orders = computed(() => (data.value?.orders ?? []).filter(o => [o.id,o.processor.name,o.process,o.source_no,
  ...o.outputs.map(p => p.item_code+' '+p.item_name)].join(' ').toLowerCase().includes(term.value)))
const processors = computed(() => (data.value?.processors ?? []).filter(p => [p.code,p.name,...p.processes].join(' ').toLowerCase().includes(term.value)))
const moreOpen = ref(false)
const sendableInputs = computed(() => sendableSubcontractInputs(order.value?.inputs ?? [], data.value?.stock ?? []))
const hasNewInput = computed(() => data.value?.stock.some(batch => !order.value?.inputs.some(input => input.id === batch.id)))
const dailyActions = computed<Stage[]>(() => {
  const current = order.value
  if (!current) return []
  const actions: Stage[] = []
  if (current.outputs.some(line => Number(line.uncounted) > 0)) actions.push('RECEIVE')
  if (sendableInputs.value.length) actions.push('SEND')
  else if (hasNewInput.value && ((!current.inputs.length && current.outputs.every(line => Number(line.delivered) === 0))
    || current.inputs.some(line => Number(remaining(line.planned, line.sent)) > 0))) actions.push('SELECT')
  if (current.batches.some(batch => Number(batch.available) > 0)) actions.push('ISSUE')
  if (current.outputs.some(line => Number(line.undelivered) > 0)) actions.push('DELIVER')
  return actions
})
const otherActions = computed<Stage[]>(() => {
  const current = order.value
  if (!current) return []
  const actions: Stage[] = []
  if (!dailyActions.value.includes('SELECT') && hasNewInput.value) actions.push('SELECT')
  if (current.events.some(event => event.kind === 'SEND' && !event.voided && Number(event.remaining) > 0)) actions.push('SIGN')
  if (!current.source_no) actions.push('SOURCE')
  return actions
})
const movementLabels = { ISSUE:'出库领用', TRANSFER:'调仓', RETURN:'退料', CORRECTION:'冲销' }
type Pending = { path: string; body: Record<string,unknown> }
const pending = ref<Pending>()
const storageKey = () => 'fabric-subcontract:huakang-c:'+auth.currentUser?.id+':'+props.mode
const locked = computed(() => busy.value || !!pending.value)
let generation = 0, loadId = 0
async function load() {
  const seq = ++loadId
  loading.value = true
  try {
    const result = props.mode === 'processors' ? await subcontractApi.processors() : await subcontractApi.workspace()
    if (seq === loadId) data.value = result
  } catch(e) { if (seq === loadId) { data.value=undefined; error.value=getApiErrorMessage(e) } }
  finally { if(seq === loadId) loading.value=false }
}
function close() { selected.value=''; create.value=false; editor.value=undefined; stage.value=undefined; original.value=''; moreOpen.value=false }
function selectOrder(id: string) {
  close()
  selected.value = id
  if (route.query.subcontract_id !== (id || undefined)) {
    void router.replace({ path:route.path, query:{...route.query, subcontract_id:id || undefined} })
  }
}
watch(() => route.query.subcontract_id, id => {
  if (props.mode === 'orders' && selected.value !== (id || '')) {
    close()
    selected.value = typeof id === 'string' ? id : ''
  }
})
watch([() => props.mode, () => auth.currentUser?.id, () => auth.authorizationVersion], () => {
  generation++; close(); if(props.mode === 'orders' && typeof route.query.subcontract_id === 'string') selected.value=route.query.subcontract_id; data.value=undefined; busy.value=false; notice.value=''; error.value=''; pending.value=undefined
  try { const saved = sessionStorage.getItem(storageKey()); if(saved) pending.value=JSON.parse(saved) } catch { /* storage may be disabled */ }
  void load()
}, {immediate:true, flush:'sync'})
onBeforeUnmount(() => { generation++; loadId++ })
function remember(value?: Pending) {
  pending.value=value
  try { if(value) sessionStorage.setItem(storageKey(),JSON.stringify(value)); else sessionStorage.removeItem(storageKey()) } catch { /* keep the request in memory */ }
}
async function submit(path: string, body: Record<string,unknown>) {
  if (!data.value || locked.value) return
  remember({path, body:JSON.parse(JSON.stringify({...body, factory_id:'huakang-c',request_id:warehouseRequestId(),expected_revision:data.value.revision}))})
  await retry()
}
async function retry() {
  const command = pending.value
  if (busy.value || !command) return
  const epoch=generation
  busy.value=true; error.value=''; notice.value=''
  try {
    const result = await subcontractApi.save(command.path,command.body)
    if(epoch !== generation) return
    remember(); create.value=false; editor.value=undefined; stage.value=undefined
    if (command.path === '/orders' && result.id) selectOrder(result.id)
    else if (result.order_id) selectOrder(result.order_id)
    await load()
    if(epoch !== generation || !data.value) return
    notice.value = command.body.kind === 'DELIVER_AND_RECEIVE' ? '已登记送货，实收数量已入库。'
      : command.body.kind === 'DELIVER' ? '已登记到货，可在「点收已到货」办理入库。' : '已保存。'
    await nextTick()
    const bar = actionBar.value
    if (bar && (bar.getBoundingClientRect().top < 130 || bar.getBoundingClientRect().bottom > window.innerHeight)) {
      bar.scrollIntoView?.({ block:'center', behavior:'instant' })
    }
  } catch(e) {
    if(epoch !== generation) return
    const status=(e as { response?: {status:number} }).response?.status
    error.value=getApiErrorMessage(e)
    if(status && [400,401,403,404,409,422].includes(status)) { remember(); await load() }
  } finally { if(epoch === generation) busy.value=false }
}
function startStage(kind: Stage, target='') { original.value=target; stage.value=kind; error.value=''; notice.value='' }
function editProcessor(p?: Processor) {
  if(locked.value) return
  editor.value=p ? {...p, processes:[...p.processes]} : {id:'',code:'',name:'',phone:'',contact:'',active:true,processes:[]}
}
function saveProcessor() {
  if(!editor.value) return
  void submit('/processors', {...editor.value, id:editor.value.id || null})
}
function orderState(outputs: {received:string;outstanding:string}[]) {
  return outputs.every(p => Number(p.outstanding) === 0) ? '已收齐' : outputs.some(p => Number(p.received)>0) ? '部分回仓' : '待回仓'
}
</script>
<template>
  <section class="fabric-subcontract" :aria-label="mode === 'orders' ? '布料仓委外加工' : '加工厂资料'">
    <p v-if="error" class="sub-error" role="alert">{{ error }}</p><p v-if="notice" role="status" class="sub-success">{{ notice }}</p>
    <div v-if="pending && !busy" class="sub-card" role="status">上次提交结果待核对。<Button variant="outline" @click="retry">按原请求核对</Button></div>
    <p v-if="loading && !data" role="status">正在读取布料仓资料…</p>
    <Button v-if="!data && !loading" variant="outline" @click="error=''; load()">重新读取</Button>
    <template v-if="data">
      <template v-if="mode === 'processors'">
        <header class="sub-head"><h2>加工厂资料</h2><Button v-if="data.can_manage && !editor" :disabled="locked" @click="editProcessor()">新增加工厂</Button></header>
        <form v-if="editor" class="sub-card" @submit.prevent="saveProcessor"><fieldset :disabled="locked">
          <header class="sub-head"><h3>{{ editor.id ? '编辑加工厂' : '新增加工厂' }}</h3><Button type="button" variant="ghost" @click="editor=undefined">取消</Button></header>
          <div class="sub-grid"><label>加工厂编号<input v-model.trim="editor.code" :readonly="!!editor.id" maxlength="128" required /></label>
            <label>加工厂名称<input v-model.trim="editor.name" maxlength="128" required /></label><label>联系人<input v-model.trim="editor.contact" maxlength="128" /></label>
            <label>电话<input v-model.trim="editor.phone" maxlength="64" /></label>
            <label>状态<select v-model="editor.active"><option :value="true">启用</option><option :value="false">停用</option></select></label></div>
          <h3>适用工艺</h3><div class="sub-checks"><label v-for="p in processes" :key="p"><input type="checkbox" v-model="editor.processes" :value="p" />{{ p }}</label></div>
          <footer><Button type="submit" :disabled="!editor.processes.length">保存加工厂</Button></footer>
        </fieldset></form>
        <div v-if="processors.length" class="sub-table"><table><thead><tr><th>编号 / 加工厂</th><th>适用工艺</th><th>联系人 / 电话</th><th>状态</th><th v-if="data.can_manage">操作</th></tr></thead>
          <tbody><tr v-for="p in processors" :key="p.id"><td><strong>{{ p.name }}</strong><small>{{ p.code }}</small></td><td>{{ p.processes.join('、') }}</td><td>{{ p.contact || '—' }} {{ p.phone }}</td><td>{{ p.active ? '启用':'停用' }}</td><td v-if="data.can_manage"><Button variant="outline" :disabled="locked" @click="editProcessor(p)">编辑</Button></td></tr></tbody></table></div>
        <p v-else class="sub-empty">{{ term ? '没有匹配的加工厂。' : '暂无加工厂资料。' }}</p>
      </template>
      <FabricSubcontractOrderForm v-else-if="create" :data="data" :locked="locked" @save="submit" @cancel="close" />
      <template v-else-if="order">
        <header class="sub-head"><div><small>委外单 · {{ orderState(order.outputs) }}</small><h2>{{ order.process }} · {{ order.processor.name }}</h2><p>{{ order.id }}　交期 {{ order.due_date }}　来源 {{ order.source_no || '手工开单' }}</p><small v-if="order.previous_order_id">前序单 {{ order.previous_order_id }}</small></div><Button variant="outline" :disabled="locked" @click="selectOrder('')">返回台账</Button></header>
        <section class="sub-card"><h3>加工产物</h3><div v-for="p in order.outputs" :key="p.id" class="sub-product"><strong>{{ p.item_code }} · {{ p.item_name }}</strong>
          <div class="sub-quantities"><div><small>计划应回</small><b>{{ p.planned }} {{ p.unit }}</b></div><div><small>加工厂尚未交</small><b>{{ p.undelivered }} {{ p.unit }}</b></div>
            <div><small>到货待点收</small><b>{{ p.uncounted }} {{ p.unit }}</b></div><div><small>累计实收</small><b>{{ p.received }} {{ p.unit }}</b></div><div><small>待实收</small><b>{{ p.outstanding }} {{ p.unit }}</b></div><div><small>仓内可领</small><b>{{ p.available }} {{ p.unit }}</b></div></div></div></section>
        <div v-if="data.can_operate" ref="actionBar" class="sub-actions" role="group" aria-label="单内操作">
          <Button v-for="(action, index) in dailyActions" :key="action" :variant="index === 0 ? 'default' : 'outline'" :disabled="locked" @click="startStage(action)">{{ actionLabels[action] }}</Button>
          <Button v-if="otherActions.length" variant="ghost" :aria-expanded="moreOpen" :disabled="locked" @click="moreOpen = !moreOpen">其他操作</Button>
          <div v-if="moreOpen && otherActions.length" class="sub-extra-actions">
            <Button v-for="action in otherActions" :key="action" variant="outline" :disabled="locked" @click="startStage(action)">{{ actionLabels[action] }}</Button>
          </div>
        </div>
        <FabricSubcontractActionForm v-if="stage" :key="order.id+stage+original" :data="data" :order="order" :stage="stage" :original="original" :locked="locked" @cancel="stage=undefined" @save="submit" />
        <section class="sub-card"><h3>投入原料</h3><p v-if="!order.inputs.length">尚未选入本仓原料。</p><ul v-else><li v-for="b in order.inputs" :key="b.id">{{ b.item_code }} · {{ b.item_name }} · {{ b.location }} {{ b.lot }} {{ b.roll_no }}　计划 {{ b.planned }} {{ b.unit }}，已发 {{ b.sent }} {{ b.unit }}<template v-if="Number(remaining(b.planned, b.sent)) > 0">，当前可发 {{ sendableInputs.find(line => line.batch.id === b.id)?.max ?? '0' }} {{ b.unit }}</template></li></ul></section>
        <section class="sub-card"><h3>单内流水</h3><p v-if="!order.events.length">尚无收发凭证。</p>
          <ol v-else class="sub-history"><li v-for="e in [...order.events].reverse()" :key="e.id"><div><strong>{{ stageLabels[e.kind] }}<template v-if="e.quantity"> · {{ e.quantity }} {{ e.unit }}</template></strong><small>{{ e.business_date }}　{{ e.actor }}　{{ e.voided ? '已更正' : '' }}</small></div>
            <p>{{ e.item_name }}　凭证 {{ e.voucher }}　{{ e.recipient }} {{ e.destination }} {{ e.location || e.batch?.location }} {{ e.lot || e.batch?.lot }} {{ e.roll_no || e.batch?.roll_no }}</p>
            <small v-if="e.stock_id">库存凭证 {{ e.stock_id }}</small><small v-if="e.kind==='VOID'">原凭证 {{ order.events.find(r=>r.id===e.target_id)?.voucher }} · {{ e.reason }}</small>
            <Button v-if="data.can_correct && !e.voided && !['SELECT','VOID','SOURCE'].includes(e.kind)" variant="outline" :disabled="locked" @click="startStage('VOID', e.id)">更正</Button></li></ol>
        </section>
        <section v-if="order.other_movements.length" class="sub-card"><h3>回仓批次的其他库存流水</h3>
          <ol class="sub-history"><li v-for="m in [...order.other_movements].reverse()" :key="m.id"><strong>{{ movementLabels[m.kind] }} · {{ m.quantity }} {{ m.unit }}</strong>
            <small>{{ m.business_date }}　{{ m.actor }}　{{ m.reversed ? '已冲销' : '' }}</small><p>{{ m.item_name }}　{{ m.voucher }}　{{ m.recipient }} {{ m.destination }}</p><small>库存凭证 {{ m.id }}</small></li></ol>
        </section>
      </template>
      <template v-else><header class="sub-head"><div><h2>委外加工</h2><p>布料仓委外单</p></div><Button v-if="data.can_operate" :disabled="locked" @click="create=true; notice=''">新建委外单</Button></header>
        <div v-if="orders.length" class="sub-table sub-orders-table"><table><thead><tr><th>委外单 / 工艺</th><th>加工厂</th><th>应回产物</th><th>交期</th><th>委外进度</th><th>操作</th></tr></thead><tbody>
          <tr v-for="o in orders" :key="o.id"><td><strong>{{ o.process }}</strong><small>{{ o.id }}</small></td><td>{{ o.processor.name }}</td><td><div v-for="p in o.outputs" :key="p.id">{{ p.item_name }} · {{ p.planned }} {{ p.unit }}</div></td>
          <td class="sub-due"><span>交期 </span>{{ o.due_date }}</td><td class="sub-progress-cell"><FabricSubcontractProgress v-for="line in o.outputs" :key="line.id" :order="o" :output="line" /></td><td><Button variant="outline" :disabled="locked" @click="selectOrder(o.id);notice=''">查看委外单</Button></td></tr></tbody></table></div>
        <p v-else class="sub-empty">{{ term ? '没有匹配的委外单。' : '暂无委外单。' }}</p>
      </template>
    </template>
  </section>
</template>
