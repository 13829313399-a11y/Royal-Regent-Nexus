<script setup lang="ts">
import { computed, ref } from 'vue'
import { Copy, Check, MapPin } from '@lucide/vue'
import { renderMarkdown } from './markdown'
import { stateLabels, type Message } from './types'
import { factoryContexts } from '@/data/enterpriseMock'
const props = defineProps<{ message: Message }>()
const emit = defineEmits<{ citation: [id: string] }>()
const copied = ref(false), copyError = ref('')
const text = computed(() => props.message.content_parts.filter(p => p.type === 'text').map(p => p.text || '').join(''))
const reasoning = computed(() => props.message.content_parts.filter(p => p.type === 'reasoning').map(p => p.text || '').join(''))
const rendered = computed(() => renderMarkdown(text.value))
const contextLabel = computed(() => {
  const context = props.message.context_descriptor
  if (!context) return ''
  const names: Record<string,string> = { portal:'系统门户','work-center':'事项工作台','injection-scheduling':'注塑排产','three-d-printing':'3D 打印','internal-quote':'内部报价','identity-management':'人员与权限','carton-supplier':'供应商协同','molding-sample':'工模手板','customer-orders':'客户订单','carton-procurement':'纸箱采购','carton-mark':'纸箱唛头','qc-inspection':'QC 验货','document-tools':'文档工具','uv-operations':'UV 生产','spray-production':'喷油生产' }
  return `${names[context.module_id] || '页面说明'} · ${factoryContexts.find(f => f.id === context.factory_id)?.name || '通用说明'}`
})
async function copy(value: string) {
  try { await navigator.clipboard.writeText(value); copied.value = true; copyError.value = '' }
  catch { copyError.value = '当前浏览器无法直接复制，请选中文字后复制。' }
}
function codeClick(event: MouseEvent) {
  const button = (event.target as HTMLElement).closest('[data-yl-copy-code]')
  if (button) void copy(button.closest('.yl-code')?.querySelector('code')?.textContent || '')
}
</script>
<template>
  <article class="yl-message" :class="`yl-message-${message.role}`">
    <div class="yl-message-author"><span>{{ message.role === 'user' ? '你' : '曜灵' }}</span><small v-if="message.role === 'assistant'">{{ stateLabels[message.status] }}</small></div>
    <small v-if="message.context_descriptor" class="yl-frozen-context">{{ contextLabel }}</small>
    <details v-if="reasoning" class="yl-reasoning"><summary>思考内容</summary><p>{{ reasoning }}</p></details>
    <div v-if="message.role === 'user'" class="yl-user-text">{{ text }}</div>
    <!-- HTML is produced only by the html:false renderer; remote images are disabled. -->
    <div v-else class="yl-markdown" @click="codeClick" v-html="rendered" />
    <p v-if="!text && message.role === 'assistant'" class="yl-empty-answer">{{ ['cancelled','failed','interrupted'].includes(message.status) ? '尚未生成正文。' : '回答会显示在这里…' }}</p>
    <div v-if="message.content_parts.some(p => p.type === 'image_ref')" class="yl-muted">包含你主动上传的图片</div>
    <div v-if="message.help_citations.length" class="yl-citations"><button v-for="citation in message.help_citations" :key="citation.id" @click="emit('citation', citation.id)"><MapPin :size="13" /> 查看说明 · {{ citation.version }}</button></div>
    <button v-if="text" class="yl-copy" @click="copy(text)" :aria-label="copied ? '已复制回答' : '复制回答'"><Check v-if="copied" :size="14" /><Copy v-else :size="14" />{{ copied ? '已复制' : '复制' }}</button>
    <p v-if="copyError" role="status" class="yl-muted">{{ copyError }}</p>
  </article>
</template>
