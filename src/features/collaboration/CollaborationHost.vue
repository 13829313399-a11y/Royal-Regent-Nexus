<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { X } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import { useMessagingStore } from '@/stores/messaging'
import { useNotificationSound } from '@/composables/useNotificationSound'
import { useDialogFocus } from '@/composables/useDialogFocus'
import { acquireBodyScrollLock, type BodyScrollLockRelease } from '@/lib/bodyScrollLock'
import { registerSurface, preemptSurface, businessPreempted, foregroundSurface } from './panelCoordinator'
import ChatPanel from './ChatPanel.vue'
import './connect.css'
const messaging = useMessagingStore(), auth = useAuthStore(), route = useRoute(), sound = useNotificationSound()
const root = ref<HTMLElement | null>(null), small = ref(innerWidth < 640), width = ref(480)
const sideVisible = computed(() => messaging.ready && messaging.opened && route.name !== 'messages')
const modal = computed(() => sideVisible.value && small.value), notice = ref<{ type: string; id: string; conversation_id?: string } | null>(null)
let release: BodyScrollLockRelease | undefined, observer: MutationObserver | undefined, noticeTimer: ReturnType<typeof setTimeout> | undefined
let foregroundOpener: HTMLElement | null = null
const unregister = registerSurface('messages', messaging.closePanel)
useDialogFocus(() => modal.value, root, { inertBackground: true, shouldRestoreFocus: () => !businessPreempted.value && (!foregroundSurface.value || foregroundSurface.value === 'messages'), onEscape: messaging.closePanel })
watch(modal, value => { if (value) release ??= acquireBodyScrollLock(); else { release?.(); release = undefined } })
watch(sideVisible, value => { if (value) foregroundOpener = document.activeElement instanceof HTMLElement ? document.activeElement : null })
watch(() => messaging.identityKey, async key => { notice.value = null; messaging.bind(key); if (key && !auth.currentUser?.force_password_change) { await messaging.refreshCapabilities(); messaging.resume() } }, { immediate: true })
watch([() => auth.authorizationVersion, () => auth.currentUser?.identity?.effective_context_key], async () => { if (messaging.bound) { for (const rows of Object.values(messaging.history)) for (const message of rows) if (message.reference) message.reference = { available: false, label: '正在重新核验业务权限' }; await messaging.refreshCapabilities(); messaging.resume() } })
function resume() { if (document.hidden || navigator.onLine === false) messaging.stopNetwork(); else void messaging.refreshCapabilities().then(messaging.resume) }
function resize() { small.value = innerWidth < 640 }
function close() { messaging.closePanel(); if (foregroundOpener?.isConnected) foregroundOpener.focus({ preventScroll: true }) }
async function notification(event: Event) {
  const item = (event as CustomEvent<{ type: string; id: string; conversation_id?: string }>).detail
  if (!messaging.ready || document.hidden || (messaging.preferences?.dnd_until && Date.parse(messaging.preferences.dnd_until) > Date.now())) return
  const conversation = messaging.conversations.find(c => c.id === item.conversation_id)
  if (conversation?.mute_until && Date.parse(conversation.mute_until) > Date.now()) return
  if (item.type === 'message.created' && messaging.selectedId === item.conversation_id && (sideVisible.value || route.name === 'messages') && document.hasFocus()) return
  const owner = messaging.identityKey, key = `rr.connect.claims.${owner}`
  const claim = () => { try { const ids = JSON.parse(localStorage.getItem(key) || '[]') as string[]; if (ids.includes(item.id)) return false; localStorage.setItem(key, JSON.stringify([...ids, item.id].slice(-150))); return true } catch { return true } }
  const claimed = navigator.locks ? await navigator.locks.request(key, claim) : claim()
  if (!claimed || owner !== messaging.identityKey) return
  notice.value = item; clearTimeout(noticeTimer); noticeTimer = setTimeout(() => notice.value = null, 6000)
  sound.soundEnabled.value = !!messaging.preferences?.sound_enabled
  if (sound.soundEnabled.value) void sound.playNotificationSound()
}
onMounted(() => {
  document.addEventListener('visibilitychange', resume); window.addEventListener('focus', resume); window.addEventListener('online', resume); window.addEventListener('offline', resume); window.addEventListener('resize', resize); window.addEventListener('collaboration-notification', notification)
  observer = new MutationObserver(() => preemptSurface([...document.querySelectorAll<HTMLElement>('[aria-modal="true"],dialog[open]')].some(el => !el.closest('.rr-connect,.yl-assistant,.account-menu,.account-menu-overlay') && !!el.getClientRects().length)))
  observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['aria-modal', 'open', 'data-state'] })
})
onBeforeUnmount(() => { unregister(); observer?.disconnect(); release?.(); clearTimeout(noticeTimer); messaging.bind(''); document.removeEventListener('visibilitychange', resume); window.removeEventListener('focus', resume); window.removeEventListener('online', resume); window.removeEventListener('offline', resume); window.removeEventListener('resize', resize); window.removeEventListener('collaboration-notification', notification) })
</script>
<template><Teleport to="body"><Transition name="connect-slide"><aside v-if="sideVisible" ref="root" class="rr-connect connect-chat-side" :style="{ '--chat-width': `${width}px` }" :data-motion="messaging.preferences?.motion || 'rich'" data-connect-overlay :role="small ? 'dialog' : 'region'" :aria-modal="small ? true : undefined" aria-label="私信侧栏" tabindex="-1"><label v-if="!small" class="connect-resize"><span>面板宽度</span><input v-model.number="width" type="range" min="400" max="620" aria-label="聊天面板宽度"></label><ChatPanel @close="close" /></aside></Transition><aside v-if="notice" class="rr-connect connect-notice" role="status"><div><strong>{{ notice.type === 'appreciation.created' ? '收到一份新的感谢' : '收到一条新私信' }}</strong><RouterLink :to="notice.type === 'appreciation.created' ? { path: '/me', query: { section: 'appreciations', item: notice.id } } : { path: '/messages', query: { conversation: notice.conversation_id } }" @click="notice = null">打开查看</RouterLink></div><button class="connect-icon-button" aria-label="关闭协作提醒" @click="notice = null"><X :size="16" /></button></aside></Teleport></template>
