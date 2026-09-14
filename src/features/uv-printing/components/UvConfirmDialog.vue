<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { AlertTriangle } from '@lucide/vue'
import { Button } from '@/components/ui/button'

/**
 * 影响预览确认框。只用于会影响结果的动作：冲销、工资确认、日月关闭、批量应用导入。
 * 新增普通主数据、普通筛选、切换 Tab 不需要确认。
 */

const props = withDefaults(defineProps<{
  open: boolean
  title: string
  /** 影响说明：对象、后果、是否保留审计。 */
  impacts: string[]
  confirmLabel?: string
  cancelLabel?: string
  destructive?: boolean
  /** 需要原因时不允许空原因提交。 */
  requireReason?: boolean
  reasonLabel?: string
  reasonPlaceholder?: string
  busy?: boolean
  hint?: string
}>(), {
  confirmLabel: '确认',
  cancelLabel: '取消',
  destructive: false,
  requireReason: false,
  reasonLabel: '原因',
  reasonPlaceholder: '说明这次操作的业务原因，会写入审计',
  busy: false,
  hint: '',
})

const emit = defineEmits<{ confirm: [reason: string]; cancel: [] }>()

const reason = ref('')
const dialog = ref<HTMLElement | null>(null)
const canConfirm = computed(() => !props.busy && (!props.requireReason || reason.value.trim().length > 0))

watch(() => props.open, async (open) => {
  if (open) {
    reason.value = ''
    await nextTick()
    dialog.value?.querySelector<HTMLElement>('[data-autofocus]')?.focus()
  }
})

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && !props.busy) emit('cancel')
}
</script>

<template>
  <Transition name="uv-dialog">
    <div v-if="open" class="uv-dialog-layer" role="presentation" @click.self="!busy && emit('cancel')">
      <section
        ref="dialog"
        class="uv-dialog"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
        @keydown="onKeydown"
      >
        <header class="uv-dialog__head">
          <span class="uv-dialog__mark" :class="destructive ? 'uv-dialog__mark--danger' : ''" aria-hidden="true">
            <AlertTriangle class="size-4" />
          </span>
          <div>
            <h2 class="uv-dialog__title">{{ title }}</h2>
            <p v-if="hint" class="uv-dialog__hint">{{ hint }}</p>
          </div>
        </header>

        <div class="uv-dialog__body">
          <p class="uv-dialog__lead">这次操作会影响：</p>
          <ul class="uv-dialog__impacts">
            <li v-for="impact in impacts" :key="impact">{{ impact }}</li>
          </ul>

          <label v-if="requireReason" class="uv-form-field">
            <span class="uv-form-label">{{ reasonLabel }}<span class="uv-form-required">必填</span></span>
            <textarea
              v-model="reason"
              class="uv-input uv-textarea"
              rows="3"
              :placeholder="reasonPlaceholder"
              data-autofocus
            />
            <span class="uv-form-help">留空无法提交；原因会与原单关联保存。</span>
          </label>
        </div>

        <footer class="uv-dialog__foot">
          <Button variant="outline" type="button" :disabled="busy" @click="emit('cancel')">
            {{ cancelLabel }}
          </Button>
          <Button
            :variant="destructive ? 'destructive' : 'default'"
            type="button"
            :disabled="!canConfirm"
            @click="emit('confirm', reason.trim())"
          >
            {{ busy ? '正在提交…' : confirmLabel }}
          </Button>
        </footer>
      </section>
    </div>
  </Transition>
</template>
