<script setup lang="ts">
import { ref, onBeforeUnmount } from 'vue'
import { X, Sparkles } from '@lucide/vue'
import { collaborationApi } from '@/api/collaboration'
import type { DirectoryMember } from '@/api/directory'
import { useDialogFocus } from '@/composables/useDialogFocus'
import { acquireBodyScrollLock } from '@/lib/bodyScrollLock'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
const props = defineProps<{ member: DirectoryMember }>(), emit = defineEmits<{ close: [] }>()
const root = ref<HTMLElement | null>(null), text = ref(''), category = ref('timely_help'), error = ref(''), busy = ref(false), sent = ref(false)
const controller = new AbortController(), clientId = createRandomUuid(), release = acquireBodyScrollLock()
let frozen: { client_request_id: string; receiver_id: string; category: string; text: string } | null = null
useDialogFocus(() => true, root, { inertBackground: true, onEscape: () => emit('close') })
onBeforeUnmount(() => { controller.abort(); release() })
async function send() { if (busy.value || !text.value.trim()) return; busy.value = true; error.value = ''; frozen ??= { client_request_id: clientId, receiver_id: props.member.id, category: category.value, text: text.value.trim() }; try { await collaborationApi.post('/appreciations', frozen, controller.signal); if (!controller.signal.aborted) sent.value = true } catch (caught) { if (!controller.signal.aborted) error.value = getApiErrorMessage(caught) } finally { busy.value = false } }
</script>
<template><Teleport to="body"><div class="rr-connect connect-backdrop" data-connect-overlay @click.self="emit('close')"><section ref="root" role="dialog" aria-modal="true" aria-label="表达感谢" class="connect-dialog connect-thanks" tabindex="-1"><header><Sparkles :size="24" /><h2>把感谢，留给真实的帮助</h2><button class="connect-icon-button" aria-label="关闭感谢卡" @click="emit('close')"><X /></button></header><p>给 {{ member.display_name }} · 仅你们双方可见</p><template v-if="!sent"><label>感谢主题<select v-model="category" :disabled="!!frozen"><option value="timely_help">及时协助</option><option value="careful_check">认真核对</option><option value="patient_explanation">耐心讲解</option><option value="problem_solved">解决问题</option></select></label><label>具体帮到了什么<textarea v-model="text" rows="5" maxlength="500" :disabled="!!frozen" placeholder="写下这次让你印象深刻的帮助…" /></label><p v-if="error" class="connect-error" role="alert">{{ error }}</p><button class="connect-button connect-button--primary" :disabled="busy || !text.trim()" @click="send">{{ busy ? '正在送出…' : frozen ? '核对并重试' : '送出感谢' }}</button></template><p v-else role="status">感谢已送达 TA 的私人收藏。</p></section></div></Teleport></template>
