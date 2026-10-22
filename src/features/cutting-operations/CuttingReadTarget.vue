<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
const props=defineProps<{target:{month:string;id?:string;eventId?:string};label:string;retryLabel:string;disabled?:boolean;readable:boolean}>()
const emit=defineEmits<{retry:[]}>()
const copying=ref(false),message=ref('')
const identity=computed(()=>JSON.stringify([props.target.month,props.target.id,props.target.eventId,props.readable,!!props.disabled]))
let generation=0,alive=true
let copyTimer:ReturnType<typeof setTimeout>|undefined
function clearCopyTimer(){if(copyTimer!==undefined){clearTimeout(copyTimer);copyTimer=undefined}}
function resetCopy(){generation++;clearCopyTimer();copying.value=false;message.value=''}
watch(identity,resetCopy,{flush:'sync'})
onBeforeUnmount(()=>{alive=false;resetCopy()})
async function copy(kind:'id'|'eventId'){
  const value=props.target[kind]
  if(!value||!props.readable||props.disabled||copying.value)return
  const ticket=++generation;copying.value=true
  const name=kind==='id'?'单据编号':'历史版本编号'
  message.value=`正在复制${name}，请稍候…`
  copyTimer=setTimeout(()=>{
    if(!alive||ticket!==generation)return
    copyTimer=undefined;generation++;copying.value=false
    message.value=`复制等待超时，请选中上方${name}手动复制。若浏览器仍显示复制授权提示，请关闭后再试。`
  },10000)
  try{
    if(!navigator.clipboard?.writeText)throw new Error('clipboard unavailable')
    await navigator.clipboard.writeText(value)
    if(alive&&ticket===generation)message.value=`${name}已复制。`
  }catch{if(alive&&ticket===generation)message.value=`无法自动复制，请选中上方${name}手动复制。`}
  finally{if(alive&&ticket===generation){clearCopyTimer();copying.value=false}}
}
</script>
<template>
  <div class="cutting-notice cutting-read-target" role="group" :aria-label="`${label}读取目标`">
    <span>读取未完成：{{target.month}} · {{label}}</span>
    <span v-if="target.id">单据编号：{{target.id}}</span>
    <Button v-if="target.id" type="button" size="sm" variant="outline" :disabled="disabled||!readable||copying" @click="copy('id')">复制单据编号</Button>
    <span>{{target.eventId?`历史版本：${target.eventId}`:target.id?'原当前版本':'原月份记录'}}</span>
    <Button v-if="target.eventId" type="button" size="sm" variant="outline" :disabled="disabled||!readable||copying" @click="copy('eventId')">复制历史版本编号</Button>
    <Button type="button" variant="outline" :disabled="disabled||!readable" @click="emit('retry')">{{retryLabel}}</Button>
    <p v-if="message" role="status">{{message}}</p>
  </div>
</template>
<style scoped>
span{user-select:text;overflow-wrap:anywhere}p{flex-basis:100%;margin:0}
</style>
