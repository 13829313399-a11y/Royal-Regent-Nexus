<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { SendHorizontal, Square } from '@lucide/vue'

const props = defineProps<{
  disabled?: boolean
  streaming?: boolean
  attachmentsEnabled?: boolean
}>()

const emit = defineEmits<{
  send: [prompt: string]
  cancel: []
}>()

const text = ref('')
const textarea = ref<HTMLTextAreaElement | null>(null)

function submit() {
  const prompt = text.value.trim()
  if (!prompt || props.disabled || props.streaming) return
  emit('send', prompt)
  void nextTick(() => textarea.value?.focus())
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  submit()
}

function focus() {
  textarea.value?.focus()
}

function clear() {
  text.value = ''
}

defineExpose({ clear, focus })
</script>

<template>
  <form
    data-ai-composer
    class="shrink-0 border-t border-slate-200 bg-white px-4 pb-4 pt-3 sm:px-5"
    @submit.prevent="submit"
  >
    <label for="ai-assistant-message" class="sr-only">输入给 AI 的消息</label>
    <div class="flex items-end gap-2 rounded-2xl border border-slate-300 bg-white p-2 shadow-sm focus-within:border-sky-500 focus-within:ring-2 focus-within:ring-sky-100">
      <textarea
        id="ai-assistant-message"
        ref="textarea"
        v-model="text"
        rows="2"
        maxlength="8000"
        :disabled="disabled || streaming"
        class="max-h-36 min-h-12 flex-1 resize-none border-0 bg-transparent px-1 py-1 text-sm leading-5 text-slate-800 outline-none placeholder:text-slate-400 disabled:cursor-not-allowed"
        placeholder="询问这个页面的操作或已授权业务信息…"
        aria-describedby="ai-assistant-composer-help"
        @keydown="handleKeydown"
      />
      <button
        v-if="streaming"
        type="button"
        class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-amber-600 text-white transition hover:bg-amber-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-600"
        aria-label="停止 AI 生成"
        @click="emit('cancel')"
      >
        <Square class="size-3.5 fill-current" aria-hidden="true" />
      </button>
      <button
        v-else
        type="submit"
        class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-slate-950 text-white transition hover:bg-sky-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 disabled:cursor-not-allowed disabled:bg-slate-300"
        :disabled="disabled || !text.trim()"
        aria-label="发送消息"
      >
        <SendHorizontal class="size-4" aria-hidden="true" />
      </button>
    </div>
    <p id="ai-assistant-composer-help" class="mt-2 text-[11px] leading-4 text-slate-500">
      <template v-if="streaming">AI 正在生成；可点击停止，本次取消不会影响业务页面。</template>
      <template v-else>
        Enter 发送，Shift+Enter 换行。{{ attachmentsEnabled ? '可添加已授权的截图或图片。' : '当前仅支持文字，不上传附件。' }}
      </template>
    </p>
  </form>
</template>
