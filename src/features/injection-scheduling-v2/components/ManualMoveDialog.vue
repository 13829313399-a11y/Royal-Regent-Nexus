<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowRightLeft, ShieldAlert, X } from '@lucide/vue'
import { useDialogFocus } from '../composables/useDialogFocus'
import type { MachineRecord, MovePreview } from '../types'

const props = defineProps<{ preview: MovePreview | null; machines: MachineRecord[]; loading: boolean; canOverride: boolean }>()
const emit = defineEmits<{ close: []; update: [changes: Partial<MovePreview>]; confirm: [] }>()
const machine = computed(() => props.preview ? props.machines.find((item) => item.id === props.preview!.targetMachineId) : null)
const dialogRoot = ref<HTMLElement | null>(null)
const { announcement: dialogAnnouncement } = useDialogFocus(() => Boolean(props.preview), dialogRoot, {
  onEscape: () => emit('close'),
  openAnnouncement: '人工移动资格预览已打开，按 Escape 关闭。',
})
</script>

<template>
  <Teleport to="body">
  <Transition name="modal">
  <div v-if="preview" ref="dialogRoot" class="modal-backdrop" tabindex="-1" @mousedown.self="emit('close')">
    <section class="phase2-dialog move-dialog" role="dialog" aria-modal="true" aria-label="人工移动资格预览">
      <p class="scheduling-sr-only dialog-live-announcement" role="status" aria-live="polite">{{ dialogAnnouncement }}</p>
      <header><div><span class="eyebrow">人工调度</span><strong>人工移动资格预览</strong></div><button aria-label="关闭人工移动弹窗" @click="emit('close')"><X :size="17" /></button></header>
      <div class="move-decision" :class="preview.decision.toLowerCase()"><ShieldAlert :size="18" /><div><strong>{{ preview.decision === 'PASS' ? '资格通过，可保存' : preview.decision === 'FAIL' ? '硬约束失败，禁止移动' : '需要授权覆盖' }}</strong><p>{{ preview.explanation }}</p></div></div>
      <dl class="move-summary"><div><dt>目标机台</dt><dd>{{ machine?.code ?? preview.targetMachineId }}</dd></div><div><dt>目标队列</dt><dd>#{{ preview.targetSequence }}</dd></div><div><dt>换模/转色影响</dt><dd>{{ preview.setupReview }}</dd></div></dl>
      <div class="move-window"><label><span>计划开始</span><input type="datetime-local" :value="preview.plannedStart.replace(' ', 'T').slice(0, 16)" @input="emit('update', { plannedStart: ($event.target as HTMLInputElement).value })" /></label><ArrowRightLeft :size="16" /><label><span>计划完成</span><input type="datetime-local" :value="preview.plannedFinish.replace(' ', 'T').slice(0, 16)" @input="emit('update', { plannedFinish: ($event.target as HTMLInputElement).value })" /></label></div>
      <div v-if="preview.hardFailures.length || preview.warnings.length" class="move-reasons"><article v-for="reason in [...preview.hardFailures, ...preview.warnings]" :key="`${reason.label}-${reason.detail}`"><strong>{{ reason.label }}</strong><span>{{ reason.detail }}</span></article></div>
      <label v-if="preview.decision === 'REVIEW_REQUIRED'" class="override-reason"><span>人工覆盖原因</span><textarea :value="preview.overrideReason" :disabled="!canOverride" placeholder="必须说明现场判断依据" @input="emit('update', { overrideReason: ($event.target as HTMLTextAreaElement).value })"></textarea><small v-if="!canOverride">当前账号没有发布/覆盖权限。</small></label>
      <footer><button @click="emit('close')">取消</button><button class="primary" :disabled="loading || preview.decision === 'FAIL' || (preview.decision === 'REVIEW_REQUIRED' && (!canOverride || !preview.overrideReason.trim()))" @click="emit('confirm')">{{ loading ? '保存中…' : '确认移动' }}</button></footer>
    </section>
  </div>
  </Transition>
  </Teleport>
</template>
