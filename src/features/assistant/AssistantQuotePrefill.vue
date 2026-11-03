<script setup lang="ts">
import { computed, ref } from 'vue'
import { isNavigationFailure, NavigationFailureType, useRouter } from 'vue-router'
import type { Message } from './types'
import { useAuthStore } from '@/stores/auth'
import { quoteDepartments } from '@/features/internal-quote/assistantContext'
import { prepareQuotePrefill, quotePrefillTargets, clearQuotePrefill } from './quotePrefill'
const props=defineProps<{message:Message}>()
const emit=defineEmits<{prepared:[]}>()
const router=useRouter(), open=ref(false), text=ref(''), selected=ref(''), busy=ref(false), error=ref('')
const auth=useAuthStore()
const targets=computed(()=>quotePrefillTargets(props.message).filter(target=>auth.can('internal_quote:header_edit',target.factoryId,'sales-business') && quoteDepartments.some(department=>auth.can('internal_quote:summary_read',target.factoryId,department))))
async function prepare() {
  const target=targets.value.find(t=>t.quoteId===selected.value)
  if(!target || busy.value) return
  busy.value=true;error.value=''
  try {
    const action=await prepareQuotePrefill(props.message.run_id,target,text.value)
    if(action.type!=='open_record') return
    const failure=await router.push({name:action.route_name,params:action.params,query:action.query})
    if(failure && !isNavigationFailure(failure,NavigationFailureType.duplicated)) {clearQuotePrefill();throw new Error('原页面保留了未保存内容，请处理后重新带入。')}
    open.value=false;emit('prepared')
  } catch(e) {error.value=e instanceof Error?e.message:'带入失败，请重新核对来源。'}
  finally {busy.value=false}
}
</script>
<template>
  <div v-if="targets.length" class="yl-quote-prefill">
    <button :disabled="busy" @click="open=!open; selected ||= targets[0]!.quoteId">准备报价备注</button>
    <div v-if="open" class="yl-excerpt-editor">
      <p>核对要带入的文字和原报价。建议只在本机暂存5分钟；在原表单明确追加到备注后仍未保存。</p>
      <label>原报价<select v-model="selected" aria-label="备注建议对应的原报价"><option v-for="target in targets" :key="target.quoteId" :value="target.quoteId">{{ target.label }}</option></select></label>
      <label>备注建议<textarea v-model="text" aria-label="报价备注建议" maxlength="2000" rows="3" placeholder="填写或粘贴本回答中经你核对、适合原报价备注的文字。"/></label>
      <button :disabled="busy || !text.trim()" @click="prepare">{{ busy?'正在核对原来源…':'打开原报价核对' }}</button><button :disabled="busy" @click="open=false">取消</button>
      <p v-if="error" role="status">{{ error }}</p>
    </div>
  </div>
</template>
