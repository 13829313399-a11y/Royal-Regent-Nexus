<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Link2, X } from '@lucide/vue'
import { useMessagingStore } from '@/stores/messaging'
import { directoryApi, type DirectoryMember } from '@/api/directory'
import { collaborationApi, type Reference } from '@/api/collaboration'
import { useDialogFocus } from '@/composables/useDialogFocus'
import { acquireBodyScrollLock, type BodyScrollLockRelease } from '@/lib/bodyScrollLock'
import { getApiErrorMessage } from '@/lib/http'
const props = defineProps<{ reference: Reference }>()
const messaging = useMessagingStore(), open = ref(false), q = ref(''), members = ref<DirectoryMember[]>([]), error = ref(''), busy = ref(false), root = ref<HTMLElement | null>(null)
let request = new AbortController(), timer: ReturnType<typeof setTimeout> | undefined, release: BodyScrollLockRelease | undefined
useDialogFocus(() => open.value, root, { inertBackground: true, onEscape: () => open.value = false })
async function search() { request.abort(); const active = request = new AbortController(); try { const result = await directoryApi.getMembers({ q: q.value, page_size: 10 }, active.signal); if (!active.signal.aborted) members.value = result.items.filter(m => m.id !== messaging.capabilities?.owner.user_id && m.actions?.can_message) } catch (caught) { if (!active.signal.aborted) error.value = getApiErrorMessage(caught) } }
watch(open, value => { if (value) { release ??= acquireBodyScrollLock(); void search() } else { release?.(); release = undefined; request.abort() } })
watch(q, () => { clearTimeout(timer); timer = setTimeout(search, 250) })
watch(() => messaging.identityKey, () => { open.value = false; members.value = []; q.value = '' })
async function choose(member: DirectoryMember) {
  if (busy.value) return
  busy.value = true; error.value = ''; const owner = messaging.identityKey, reference = { ...props.reference }
  try {
    const preview = await collaborationApi.post<{ reference: { available: boolean }; peer_can_view: boolean }>(`/references/preview?peer_user_id=${encodeURIComponent(member.id)}`, reference, request.signal)
    if (!preview.reference.available) { error.value = '该业务记录当前不可分享'; return }
    if (owner !== messaging.identityKey) return
    open.value = false; await nextTick()
    const cid = await messaging.openPeer(member.id)
    if (cid && owner === messaging.identityKey) { if (messaging.drafts[cid]?.attachment_ids.length) { messaging.error = '当前草稿还有附件，请先发送或移除后再分享业务记录。'; return }; messaging.edit(cid, { reference }); if (!preview.peer_can_view) messaging.error = '对方当前无权查看该记录，发送后仅显示不可查看提示。' }
  } catch (caught) { if (owner === messaging.identityKey) error.value = getApiErrorMessage(caught) }
  finally { busy.value = false }
}
onBeforeUnmount(() => { request.abort(); clearTimeout(timer); release?.() })
</script>
<template><span v-if="messaging.ready" class="rr-connect"><button type="button" class="connect-button" @click="open = true"><Link2 :size="15" />分享至私信</button></span><Teleport to="body"><div v-if="open" class="rr-connect connect-backdrop" @click.self="open = false"><section ref="root" class="connect-dialog" role="dialog" aria-modal="true" aria-label="将业务记录带入私信" tabindex="-1"><header><h2>把业务记录带入私信</h2><button class="connect-icon-button" aria-label="关闭分享" @click="open = false"><X /></button></header><p>选择同事，确认内容后亲自发送。</p><label>查找同事<input v-model="q" type="search" maxlength="64" /></label><p v-if="error" class="connect-error" role="alert">{{ error }}</p><button v-for="member in members" :key="member.id" class="connect-contact-link" :disabled="busy" @click="choose(member)"><strong>{{ member.display_name }}</strong><small>{{ member.org_name }} · {{ member.position }}</small></button></section></div></Teleport></template>
