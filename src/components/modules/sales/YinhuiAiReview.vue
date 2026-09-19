<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { getQuoteRecognitionStatus, recognizeQuoteFields } from '@/api/quoteRecognition'
import type { YinhuiDraft } from '@/lib/customerPriceConverters/yinhuiDraft'
import { applyYinhuiRecognition, buildYinhuiRecognitionTasks, validateYinhuiRecognition, type RecognitionItem, type RecognitionTask } from '@/lib/customerPriceConverters/yinhuiRecognition'

const props = defineProps<{ draft: YinhuiDraft; disabled?: boolean }>()
const emit = defineEmits<{ 'update:draft': [YinhuiDraft]; invalidate: [] }>()
const busy = ref(false)
const message = ref('')
const suggestions = ref<Array<{ task: RecognitionTask; item: RecognitionItem }>>([])
const applied = ref<string[]>([])
const plan = computed(() => buildYinhuiRecognitionTasks(props.draft))
let generation = 0
let controller: AbortController | undefined
let applying = false
function cancel() { generation++; controller?.abort(); controller = undefined; busy.value = false; suggestions.value = []; applied.value = [] }
watch(() => [props.draft, props.disabled], () => { if (!applying) { cancel(); message.value = '' } }, { deep: true, flush: 'sync' })
onBeforeUnmount(cancel)
async function recognize() {
  if (props.disabled || busy.value || !plan.value.tasks.length) return
  cancel()
  const ticket = generation
  controller = new AbortController()
  const signal = controller.signal
  const tasks = plan.value.tasks
  busy.value = true
  message.value = '正在连接 AI…'
  try {
    const status = await getQuoteRecognitionStatus(signal)
    if (ticket !== generation) return
    if (!status.available) { message.value = status.message; return }
    message.value = '正在识别表头、部件对应和成本类别，请稍候…'
    const response = await recognizeQuoteFields(tasks, signal)
    if (ticket !== generation) return
    suggestions.value = validateYinhuiRecognition(response, tasks).map((item, i) => ({ item, task: tasks[i]! }))
    message.value = '识别完成。请核对来源，再逐项确认应用；不确定的项目请手工处理。'
  } catch {
    if (ticket === generation) message.value = 'AI 识别暂不可用或返回结果不完整，草稿未修改。请重试，或继续手工核对。'
  } finally { if (ticket === generation) busy.value = false }
}
function apply(task: RecognitionTask, item: RecognitionItem) {
  if (props.disabled || busy.value || applied.value.includes(task.id)) return
  try {
    applying = true
    const next = applyYinhuiRecognition(props.draft, task, item)
    emit('invalidate')
    if (task.kind === 'tool_match') applied.value.push(task.id)
    else { cancel(); message.value = task.kind === 'header' ? '已应用表头对应，可再次识别部件。' : '已应用类别并重新核对金额，下方手工资料已重置。' }
    emit('update:draft', next)
  } catch (error) { message.value = error instanceof Error ? error.message : '建议未应用，请重新识别' }
  finally { applying = false }
}
</script>

<template>
  <section class="mt-4 rounded-lg border border-teal-200 bg-teal-50/50 p-3" data-testid="yinhui-ai">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h4 class="text-sm font-semibold">AI 辅助识别</h4>
      <button type="button" data-testid="yinhui-ai-recognize" :disabled="disabled || busy || !plan.tasks.length" class="rounded bg-teal-700 px-3 py-2 text-sm text-white disabled:opacity-50" @click="recognize">{{ busy ? '识别中…' : '获取 AI 建议' }}</button>
    </div>
    <p class="mt-2 text-xs text-slate-600">点击后会将相关表头、部件名称及候选编号发送至已配置的千问服务。AI 建议只用于模具表头、模具对应和未知成本分类；单价、用量、金额仍按原表及现有规则核对。</p>
    <p class="mt-1 text-xs text-slate-600">确认模具对应只补入模号和零件号；确认成本类别会重新读取原表并重置下方手工资料。已确认的表头对应随草稿保存。</p>
    <p v-if="!plan.tasks.length" class="mt-2 text-sm">当前没有可供 AI 判断的候选，请继续处理草稿提示。</p>
    <p v-if="plan.notice" class="mt-2 text-sm">{{ plan.notice }}</p>
    <p v-if="message" role="status" class="mt-2 text-sm">{{ message }}</p>
    <ol v-if="suggestions.length" class="mt-3 max-h-96 space-y-3 overflow-auto">
      <li v-for="entry in suggestions" :key="entry.task.id" class="rounded border border-slate-200 bg-white p-3 text-sm">
        <p class="font-semibold">{{ entry.task.target }} · {{ entry.task.source.sheet }}!{{ entry.task.source.cell }} · {{ entry.task.source.text }}</p>
        <p v-for="context in entry.task.context" :key="context.cell" class="mt-1 text-xs text-slate-600">{{ context.sheet }}!{{ context.cell }}：{{ context.text }}</p>
        <p class="mt-2">建议：{{ entry.task.choices.find(c => c.id === entry.item.choice_id)?.label || '无法确定，请手工核对' }}</p>
        <p v-for="source in entry.task.choices.find(c => c.id === entry.item.choice_id)?.evidence || []" :key="source.cell" class="text-xs text-slate-600">来源：{{ source.sheet }}!{{ source.cell }} · {{ source.text }}</p>
        <p class="mt-1 text-xs text-slate-700">理由：{{ entry.item.reason }}</p>
        <button v-if="entry.item.choice_id" type="button" data-testid="yinhui-ai-apply" :disabled="disabled || busy || applied.includes(entry.task.id)" class="mt-2 rounded border border-teal-600 px-3 py-1 text-teal-800 disabled:opacity-50" @click="apply(entry.task, entry.item)">{{ applied.includes(entry.task.id) ? '已应用' : '确认并应用此项' }}</button>
      </li>
    </ol>
  </section>
</template>
