<script setup lang="ts">
import { ref } from 'vue'
import { ThumbsDown, ThumbsUp } from '@lucide/vue'
import { createRandomUuid } from '@/lib/randomUuid'
import {
  submitAIFeedback,
  type AIFeedbackIssueCategory,
  type AIFeedbackRating,
} from '@/api/aiFeedback'

const props = defineProps<{
  factoryId: string
  targetType: 'RESPONSE' | 'MESSAGE' | 'TASK' | 'ACTION'
  targetId: string
}>()

const selected = ref<AIFeedbackRating | null>(null)
const category = ref<AIFeedbackIssueCategory>('INCORRECT')
const comment = ref('')
const submitting = ref(false)
const submitted = ref(false)
const error = ref('')
const requestIds = new Map<AIFeedbackRating, string>()

const categories: Array<{ value: AIFeedbackIssueCategory; label: string }> = [
  { value: 'INCORRECT', label: '事实不正确' },
  { value: 'MISSING_CONTEXT', label: '遗漏上下文' },
  { value: 'WRONG_TOOL', label: '选错业务能力' },
  { value: 'WRONG_ARGUMENTS', label: '厂区、日期或参数不对' },
  { value: 'UNSUPPORTED_CLAIM', label: '结论缺少证据' },
  { value: 'PERMISSION', label: '权限说明不正确' },
  { value: 'PREVIEW_MISLABEL', label: '把预览误称为已执行' },
  { value: 'UNSAFE', label: '存在安全问题' },
  { value: 'OTHER', label: '其他问题' },
]

function requestId(rating: AIFeedbackRating) {
  const existing = requestIds.get(rating)
  if (existing) return existing
  const value = `feedback-${createRandomUuid()}`
  requestIds.set(rating, value)
  return value
}

async function submit(rating: AIFeedbackRating) {
  if (submitting.value || submitted.value) return
  selected.value = rating
  if (rating === 'NOT_HELPFUL' && !category.value) return
  submitting.value = true
  error.value = ''
  try {
    const result = await submitAIFeedback({
      factoryId: props.factoryId,
      targetType: props.targetType,
      targetId: props.targetId,
      rating,
      issueCategory: rating === 'HELPFUL' ? 'NONE' : category.value,
      comment: rating === 'HELPFUL' ? '' : comment.value.trim(),
      idempotencyKey: requestId(rating),
    })
    if (result.auto_applied_to_prompt_or_knowledge !== false) {
      throw new Error('反馈合同无效')
    }
    submitted.value = true
  } catch {
    error.value = '反馈暂未保存，请稍后重试。'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="mt-2 border-t border-slate-100 pt-2 text-[11px]" data-ai-feedback>
    <p v-if="submitted" class="font-medium text-emerald-700">感谢反馈。反馈只进入人工审核，不会自动修改 Prompt 或知识。</p>
    <template v-else>
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-slate-500">这个回答有帮助吗？</span>
        <button type="button" class="inline-flex items-center gap-1 rounded-md px-2 py-1 text-slate-600 ring-1 ring-inset ring-slate-200 hover:bg-slate-50" :disabled="submitting" aria-label="回答有帮助" @click="submit('HELPFUL')">
          <ThumbsUp class="size-3" aria-hidden="true" />有帮助
        </button>
        <button type="button" class="inline-flex items-center gap-1 rounded-md px-2 py-1 text-slate-600 ring-1 ring-inset ring-slate-200 hover:bg-slate-50" :disabled="submitting" aria-label="回答没有帮助" @click="selected = 'NOT_HELPFUL'">
          <ThumbsDown class="size-3" aria-hidden="true" />需要改进
        </button>
      </div>
      <div v-if="selected === 'NOT_HELPFUL'" class="mt-2 space-y-2 rounded-lg bg-slate-50 p-2">
        <label class="block">
          <span class="font-medium text-slate-600">问题类型</span>
          <select v-model="category" class="mt-1 w-full rounded-md border border-slate-200 bg-white px-2 py-1.5">
            <option v-for="item in categories" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </label>
        <label class="block">
          <span class="font-medium text-slate-600">补充说明（可选）</span>
          <textarea v-model="comment" maxlength="1000" rows="2" class="mt-1 w-full rounded-md border border-slate-200 bg-white px-2 py-1.5" placeholder="请说明希望如何改进" />
        </label>
        <button type="button" class="rounded-md bg-slate-900 px-2.5 py-1.5 font-semibold text-white disabled:opacity-50" :disabled="submitting" @click="submit('NOT_HELPFUL')">{{ submitting ? '保存中…' : '提交反馈' }}</button>
      </div>
      <p v-if="error" class="mt-1 font-medium text-rose-600">{{ error }}</p>
    </template>
  </div>
</template>
