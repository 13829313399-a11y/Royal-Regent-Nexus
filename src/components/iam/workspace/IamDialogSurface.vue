<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import {
  DialogRoot,
  DialogPortal,
  DialogOverlay,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from 'reka-ui'
import { X } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import './iam-studio.css'
import './iam-motion.css'
const props = withDefaults(
  defineProps<{
    open: boolean
    title: string
    description?: string
    drawer?: boolean
    busy?: boolean
    dirty?: boolean
    savedDescription?: string
  }>(),
  { description: '请核对当前内容后操作。' },
)
const emit = defineEmits<{ 'update:open': [boolean]; closed: []; discarded: [] }>()
const askDiscard = ref(false)
const busyNotice = ref(false)
const titleElement = ref<{ $el: HTMLElement }>()
const discardPanel = ref<HTMLElement>()
let editingFocus: HTMLElement | undefined
let opener: HTMLElement | undefined
let resolveLeave: ((allow: boolean) => void) | undefined
watch(
  () => props.open,
  (value) => {
    if (value) {
      opener = document.activeElement instanceof HTMLElement ? document.activeElement : undefined
      askDiscard.value = false
      busyNotice.value = false
    }
  },
  { immediate: true },
)
async function permitLeave() {
  if (props.busy) {
    busyNotice.value = true
    return false
  }
  if (!props.dirty) return true
  editingFocus = document.activeElement instanceof HTMLElement ? document.activeElement : undefined
  askDiscard.value = true
  await nextTick()
  discardPanel.value?.querySelector<HTMLElement>('button')?.focus()
  return new Promise<boolean>((resolve) => {
    resolveLeave?.(false)
    resolveLeave = resolve
  })
}
async function requestClose() {
  if (await permitLeave()) emit('update:open', false)
}
function answer(allow: boolean) {
  askDiscard.value = false
  if (allow) emit('discarded')
  else void nextTick(() => editingFocus?.focus())
  resolveLeave?.(allow)
  resolveLeave = undefined
}
function closed(event: Event) {
  event.preventDefault()
  if (props.open) return
  if (opener?.isConnected && !['BODY', 'HTML'].includes(opener.tagName)) opener.focus()
  else document.querySelector<HTMLElement>('[data-iam-focus-fallback]')?.focus()
  emit('closed')
}
function escape(event: Event) {
  event.preventDefault()
  if (askDiscard.value) answer(false)
  else void requestClose()
}
onBeforeUnmount(() => resolveLeave?.(false))
defineExpose({ permitLeave, requestClose })
</script>
<template>
  <DialogRoot
    :open="open"
    @update:open="
      (value) => {
        if (!value) requestClose()
      }
    "
  >
    <DialogPortal>
      <DialogOverlay class="rrn-iam-studio iamx-overlay" />
      <DialogContent
        class="rrn-iam-studio iamx-dialog notranslate"
        translate="no"
        :class="{ 'iamx-drawer': drawer }"
        @escape-key-down="escape"
        @pointer-down-outside="
          (event) => {
            event.preventDefault()
            requestClose()
          }
        "
        @open-auto-focus="
          (event) => {
            event.preventDefault()
            nextTick(() => titleElement?.$el?.focus())
          }
        "
        @close-auto-focus="closed"
      >
        <header class="iamx-dialog-header">
          <div>
            <DialogTitle ref="titleElement" tabindex="-1">{{ title }}</DialogTitle
            ><DialogDescription>{{ description }}</DialogDescription>
          </div>
          <Button variant="ghost" :aria-label="`关闭${title}`" @click="requestClose"
            ><X :size="21"
          /></Button>
        </header>
        <p v-if="busyNotice" role="status" class="iamx-notice">
          请求正在处理中，请等待结果。关闭页面不会取消服务器办理。
        </p>
        <div
          v-if="askDiscard"
          ref="discardPanel"
          class="iamx-discard"
          role="alertdialog"
          aria-label="离开当前编辑"
        >
          <h3>放弃当前未保存内容？</h3>
          <p>{{ savedDescription || '当前修改只在本页，离开后不会保留。' }}</p>
          <div class="iamx-actions">
            <Button @click="answer(false)">继续编辑</Button
            ><Button variant="outline" @click="answer(true)">放弃未保存内容</Button>
          </div>
        </div>
        <div v-show="!askDiscard" class="iamx-dialog-slots">
          <slot name="navigation" />
          <div class="iamx-dialog-body"><slot /></div>
          <footer v-if="$slots.footer" class="iamx-dialog-footer"><slot name="footer" /></footer>
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
