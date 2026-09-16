<script setup lang="ts">
import { computed, ref } from 'vue'
import { ShieldCheck, TriangleAlert } from '@lucide/vue'
import EntryForm from '../components/EntryForm.vue'
import SprayButton from '../components/ui/SprayButton.vue'
import SprayStatusPill from '../components/ui/SprayStatusPill.vue'
import { useSprayWorkspace, str, amount } from '../workspace'
const s=useSprayWorkspace(),selected=ref(''),formKey=ref(0)
const balances = (id:string) => Object.entries(s.balances[id]??{}).filter(([,quantity])=>Number(quantity)!==0)
/* 状态键形如 held:step-1 / route:...；色调只取互斥状态前缀，工序名继续随文字展示。 */
const stateKey = (key:string) => key.startsWith('route:') ? 'route' : key.split(':')[0] ?? key

const held=computed(()=>Object.keys(s.balances[selected.value]??{}).filter(k=>(k.startsWith('held:')||k==='receipt-held'||k==='return-held')&&Number(s.balances[selected.value]?.[k])>0).map(value=>({value,label:s.stateName(value)+' · '+amount(s.balances[selected.value]?.[value])})))
async function disposition(v:Record<string,string>){const result=await s.command('quality',{...v,batch_id:selected.value});if(result)formKey.value++}
</script>
<template><div class="spray-toolbar"><div><h2>在制与质量</h2><p>每个部件在哪里、等待谁处理；返工沿用同一批次，不增加来料。</p></div><div class="spray-toolbar-actions"><span class="spray-badge"><ShieldCheck :size="14" aria-hidden="true" /><b>{{ s.items('batches').length }}</b> 个实体批次</span></div></div>
  <div class="spray-table-wrap"><p class="spray-table-caption">数量按状态互斥划分；待判与返工量以文字标明，选择批次后查看流转与可用处置</p><table class="spray-table"><thead><tr><th>实体批次</th><th>状态与数量</th><th>处置</th></tr></thead><tbody><tr v-for="b in s.items('batches')" :key="b.id" :class="{selected:b.id===selected}"><td><strong>{{ s.lineLabel(s.find('lines',b.line_id)) }}</strong>{{ b.document_no }} / {{ b.source_line }}</td><td><div class="spray-actions"><SprayStatusPill v-for="([key,qty]) in balances(b.id)" :key="key" :status="stateKey(key)" :label="s.stateName(key) + ' ' + amount(qty)" /><span v-if="!balances(b.id).length" class="spray-muted">该批次已无实体数量</span></div></td><td><SprayButton variant="outline" size="sm" :aria-pressed="b.id===selected" @click="selected=b.id;s.selection=b.id">{{ b.id===selected ? '已选择 · 在下方处置' : '检查与处置' }}</SprayButton></td></tr></tbody></table></div><p v-if="!s.items('batches').length" class="spray-empty">尚无已登记来料批次；不会推算历史期初余额。</p>
  <section v-if="selected && s.can('quality')" class="spray-panel mt-5 spray-enter"><div class="spray-section-title"><h3><TriangleAlert :size="15" aria-hidden="true" />质量处置 · {{ s.batchLabel(s.find('batches',selected)) }}</h3><SprayButton variant="outline" size="sm" @click="selected='';s.selection=''">收起处置</SprayButton></div><p class="spray-help">先确认待判来源状态，再选择处置结果。转返工沿用同一批次；拒收与报废分别计量，不互相抵扣。</p><EntryForm :key="selected+formKey" :fields="[{key:'source_state',label:'待判状态',options:held},{key:'disposition',label:'处置结果',options:[{value:'release',label:'合格放行'},{value:'rework',label:'转返工'},{value:'scrap',label:'报废'},{value:'reject',label:'拒收'}]},{key:'quantity',label:'本次处置数量',type:'decimal'},{key:'step_id',label:'退货返工工序',optional:true,options:s.items('steps').filter(t=>t.line_id===s.find('batches',selected)?.line_id).map(t=>({value:t.id,label:str(t,'name')}))},{key:'reason',label:'问题、责任与处置依据',type:'textarea'}]" :busy="s.busy" submit-label="确认本次处置" @submit="disposition" /></section>
  <p v-else-if="selected" class="spray-help">当前账号没有质量处置权限；可继续在选择行查看批次流转。</p>
</template>
