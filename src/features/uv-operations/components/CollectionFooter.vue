<script setup lang="ts">
import { ref, watch } from 'vue'
import { useUvWorkspace } from '../workspace'
import { useUvRequestScope } from '../composables/useUvRequestScope'
const props=defineProps<{name:string}>(), w=useUvWorkspace(),busy=ref(false),error=ref('')
const requests=useUvRequestScope(w.contextVersion)
watch(()=>props.name,()=>{requests.invalidate();busy.value=false;error.value=''})
watch(w.contextVersion,()=>{busy.value=false;error.value=''})
async function more() {if(busy.value)return;const current=requests.start('more');busy.value=true;error.value='';try {await w.load([props.name],true)}catch(cause){if(current())error.value=w.explain(cause)}finally{if(current())busy.value=false}}
</script>
<template><footer v-if="w.pagination[name]" class="uv-collection-footer"><span>已加载 {{w.items(name).length}} / {{w.pagination[name]?.total}} 条</span><button v-if="w.pagination[name]?.has_more" class="uv-button" :disabled="busy" @click="more">{{busy?'加载中…':'加载下一页'}}</button><span v-if="error" role="alert">{{error}}</span></footer></template>
