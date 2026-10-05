<script setup lang="ts">
import { ref } from 'vue'
import { Button } from '@/components/ui/button'
import { useSprayWorkspace } from '../workspace'
import WorkspaceDialog from './WorkspaceDialog.vue'
const w=useSprayWorkspace(),open=ref(false),mode=ref('opening'),cutoff=ref(''),evidence=ref(''),error=ref(''),busy=ref(false)
async function show(){await w.load(['history-policy']);open.value=true}
async function close(){if(w.dirty.value&&!(await w.confirmDiscard('放弃尚未确认的历史衔接口径？')))return;open.value=false;w.dirty.value=false}
async function save(){busy.value=true;try{await w.command('history-policy',{mode:mode.value,cutoff:cutoff.value,evidence:evidence.value});await w.load(['history-policy'])}catch(cause){error.value=w.explain(cause)}finally{busy.value=false}}
</script>
<template><Button v-if="w.can('import')&&w.can('stock_write')" variant="outline" @click="show">历史衔接口径</Button><WorkspaceDialog :open="open" title="确认历史与新系统的衔接" @close="close"><template v-if="w.items('history-policy').length"><p>已确认{{w.items('history-policy')[0]?.mode==='opening'?'期初结余':'逐笔重放'}}口径，截止日期 {{w.items('history-policy')[0]?.cutoff}}。</p><p class="spray-muted">{{w.items('history-policy')[0]?.evidence}}</p></template><form v-else class="spray-form" @input="w.dirty.value=true" @submit.prevent="save"><p class="wide spray-alert">两种口径互斥。期初结余不会生成历史产量；确认期初后，截止日及以前不能重放实物与金额交易。</p><label>衔接方式<select v-model="mode"><option value="opening">核对期初结余</option><option value="replay">按原单逐笔重放</option></select></label><label>历史截止日<input v-model="cutoff" type="date" required/></label><label class="wide">盘点、核对人及依据<textarea v-model="evidence" required/></label><p v-if="error" role="alert" class="spray-alert wide">{{error}}</p><Button type="submit" :disabled="busy">确认此工厂衔接口径</Button></form></WorkspaceDialog></template>
