<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount, nextTick } from 'vue'
import { RouterLink } from 'vue-router'
import { X, Search, ArrowLeft, ArrowUpRight, Users, Star } from '@lucide/vue'
import { directoryApi, type DirectoryMember, type PresenceFilter } from '@/api/directory'
import { useDirectoryQuery } from '@/composables/useDirectoryQuery'
import { useDialogFocus } from '@/composables/useDialogFocus'
import { acquireBodyScrollLock, type BodyScrollLockRelease } from '@/lib/bodyScrollLock'
import { useAuthStore } from '@/stores/auth'
import { useMessagingStore } from '@/stores/messaging'
import { registerSurface, requestSurface, releaseSurface, businessPreempted, foregroundSurface } from './panelCoordinator'
import MemberCard from './MemberCard.vue'
import AppreciationDialog from './AppreciationDialog.vue'
import './connect.css'
const props = withDefaults(defineProps<{ open: boolean; currentFactoryId?: string; currentDepartment?: string }>(), { currentFactoryId: '', currentDepartment: '' })
const emit = defineEmits<{ close: [] }>()
const auth = useAuthStore(), messaging = useMessagingStore(), root = ref<HTMLElement | null>(null), searchInput = ref<HTMLInputElement | null>(null)
const searchText = ref(''), q = ref(''), presence = ref<PresenceFilter>('online'), scope = ref('mine'), contacts = ref(false)
const selected = ref<DirectoryMember | null>(null), thanks = ref<DirectoryMember | null>(null), detailError = ref('')
const myOrg = computed(() => auth.currentUser?.identity?.primary_assignment?.org_unit_id || auth.currentUser?.profile?.primary_factory_id || '')
const org = computed(() => scope.value === 'mine' ? myOrg.value : scope.value === 'browse' ? (props.currentFactoryId === 'group' ? '' : props.currentFactoryId) : '')
const params = computed(() => ({ page: 1, page_size: 50, q: q.value, presence: presence.value, org_unit_id: org.value, contacts_only: contacts.value }))
const { items, total, counts, loading, error, stale, load } = useDirectoryQuery(params, () => props.open)
const fullQuery = computed(() => ({ ...(q.value ? { q: q.value } : {}), ...(presence.value !== 'all' ? { presence: presence.value } : {}), ...(org.value ? { org_unit_id: org.value } : {}), ...(contacts.value ? { contacts: '1' } : {}) }))
const options = [['online', '在线'], ['away', '最近在线'], ['offline', '离线'], ['all', '全部']] as const
const memberCount = computed(() => counts.value.online + counts.value.away + counts.value.offline)
const resultHeading = computed(() => ({ all: '全部成员', online: '在线成员', away: '最近在线的成员', offline: '离线成员' })[presence.value])
let debounce: ReturnType<typeof setTimeout> | undefined, release: BodyScrollLockRelease | undefined, detailController: AbortController | undefined
const unregister = registerSurface('directory', () => emit('close'))
useDialogFocus(() => props.open && !thanks.value, root, { inertBackground: true, shouldRestoreFocus: () => !thanks.value && !businessPreempted.value && (!foregroundSurface.value || foregroundSurface.value === 'directory'), onEscape: () => selected.value ? selected.value = null : emit('close'), initialFocus: () => searchInput.value })
const composing = ref(false)
function compositionStart() { composing.value = true; clearTimeout(debounce) }
function input() { clearTimeout(debounce); if (!composing.value) debounce = setTimeout(() => { q.value = searchText.value.trim() }, 250) }
async function detail(member: DirectoryMember) { detailController?.abort(); const request = detailController = new AbortController(), owner = messaging.identityKey; selected.value = member; detailError.value = ''; try { const result = await directoryApi.getMember(member.id, request.signal); if (!request.signal.aborted && props.open && owner === messaging.identityKey) selected.value = result } catch { if (!request.signal.aborted) detailError.value = '名片详情暂不可用' } }
async function chat(member: DirectoryMember) { emit('close'); await nextTick(); await messaging.openPeer(member.id) }
watch(() => props.open, open => { if (open) { if (!requestSurface('directory')) { emit('close'); return }; release ??= acquireBodyScrollLock() } else { release?.(); release = undefined; detailController?.abort(); selected.value = null; thanks.value = null; releaseSurface('directory') } }, { immediate: true })
watch(() => messaging.identityKey, () => { selected.value = null; thanks.value = null; detailController?.abort() })
onBeforeUnmount(() => { unregister(); release?.(); clearTimeout(debounce); detailController?.abort() })
</script>
<template><Teleport to="body"><Transition name="connect-slide"><div v-if="open" class="rr-connect connect-backdrop" :data-motion="messaging.preferences?.motion || 'rich'" data-connect-overlay @click.self="emit('close')"><section ref="root" class="connect-directory-drawer" role="dialog" aria-modal="true" aria-label="组织成员目录" tabindex="-1">
  <header class="connect-hero connect-hero--small"><div><p class="connect-eyebrow">同频 · NEXUS CONNECT</p><h2>成员目录</h2><p>看看谁在线，找到可以联系的同事</p></div><button class="connect-icon-button" aria-label="关闭成员目录" @click="emit('close')"><X /></button><div class="connect-hero-orbit" aria-hidden="true" /></header>
  <template v-if="!selected">
    <div class="connect-directory-filters">
      <label class="connect-search"><Search :size="18" /><input ref="searchInput" v-model="searchText" type="search" maxlength="64" aria-label="搜索成员" placeholder="找姓名、岗位、组织或专长" @input="input" @compositionstart="compositionStart" @compositionend="composing = false; input()"></label>
      <div class="connect-presence-filters" role="group" aria-label="连接状态">
        <button v-for="[value, label] in options" :key="value" type="button" :data-presence="value" :aria-pressed="presence === value" :aria-label="`${label}成员`" @click="presence = value">
          <span class="connect-presence-label"><Users v-if="value === 'all'" :size="13" aria-hidden="true" /><i v-else aria-hidden="true" />{{ label }}</span>
          <strong>{{ loading && !items.length && !memberCount ? '—' : value === 'all' ? memberCount : counts[value] }}</strong>
        </button>
      </div>
      <div class="connect-filter-row">
        <select v-model="scope" aria-label="成员范围"><option value="mine">我的组织</option><option value="browse">浏览范围{{ currentFactoryId === 'group' ? ' · 集团' : '' }}</option><option value="all">全部组织</option></select>
        <button v-if="messaging.ready" type="button" class="connect-contact-filter" :aria-pressed="contacts" @click="contacts = !contacts"><Star :size="15" />常联系</button>
        <span class="connect-refresh-note">{{ error ? '更新暂缓' : '自动更新在线状态' }}</span>
      </div>
    </div>
    <div class="connect-directory-scroll" :aria-busy="loading">
      <div class="connect-roster-heading"><h3>{{ resultHeading }}</h3><span>{{ total }} 位{{ total > items.length ? ` · 已显示 ${items.length} 位` : '' }}</span></div>
      <p v-if="error" class="connect-error" role="alert">{{ error }} <button @click="load()">重试</button></p><p v-if="stale" role="status">更新暂缓，以下是最近一次结果</p><p v-if="loading" role="status">正在查找成员…</p>
      <div v-else-if="!items.length && !error" class="connect-empty"><Users :size="30" aria-hidden="true" /><p>{{ presence === 'online' ? '当前范围暂无在线成员' : '没有符合条件的成员' }}</p><p class="connect-empty-hint">{{ contacts ? '可以取消常联系筛选，或查看其他状态的成员。' : '试试其他状态、关键词或组织范围。' }}</p><button v-if="presence !== 'all'" class="connect-button" @click="presence = 'all'">查看全部状态</button></div>
      <MemberCard v-for="member in items" :key="member.id" :member="member" compact @select="detail" @chat="chat" @contact="load(true)" />
    </div>
    <footer class="connect-drawer-footer"><span>{{ presence === 'online' ? '绿点表示当前在线' : '在线状态自动更新' }}</span><RouterLink :to="{ name: 'people-directory', query: fullQuery }" @click="emit('close')">打开完整目录 <ArrowUpRight :size="16" /></RouterLink></footer>
  </template>
  <div v-else class="connect-directory-scroll"><button class="connect-button" @click="selected = null"><ArrowLeft :size="16" />返回成员列表</button><p v-if="detailError" class="connect-error">{{ detailError }}</p><MemberCard :member="selected" detailed @chat="chat" @appreciate="thanks = $event" @contact="detail(selected); load(true)" /></div>
</section></div></Transition></Teleport><AppreciationDialog v-if="thanks" :member="thanks" @close="thanks = null" /></template>
