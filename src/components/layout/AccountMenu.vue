<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  BriefcaseBusiness,
  Building2,
  Camera,
  ChevronDown,
  Factory,
  ImagePlus,
  LoaderCircle,
  LogOut,
  RotateCcw,
  UserRound,
  X,
} from '@lucide/vue'
import { useRouter, RouterLink } from 'vue-router'
import { useMessagingStore } from '@/stores/messaging'
import { registerSurface, requestSurface, releaseSurface } from '@/features/collaboration/panelCoordinator'
import UserAvatar from '@/components/common/UserAvatar.vue'
import { authApi } from '@/api/auth'
import { departmentMap, factoryContexts } from '@/data/enterpriseMock'
import { useDialogFocus } from '@/composables/useDialogFocus'
import { acquireBodyScrollLock, type BodyScrollLockRelease } from '@/lib/bodyScrollLock'
import { getApiErrorMessage } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'

withDefaults(defineProps<{
  compact?: boolean
  variant?: 'light' | 'obsidian'
}>(), {
  compact: false,
  variant: 'light',
})

const MAX_AVATAR_FILE_SIZE = 2 * 1024 * 1024
const ACCEPTED_AVATAR_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp'])

const router = useRouter()
const authStore = useAuthStore()
const messaging = useMessagingStore()
const owner = computed(() => `${authStore.currentUser?.id ?? ''}:${authStore.currentUser?.identity?.employment_epoch ?? 0}`)
const trigger = ref<HTMLElement | null>(null), profileRoot = ref<HTMLElement | null>(null), menuStyle = ref<Record<string,string>>({})
const unregister = registerSurface('account', () => { isMenuOpen.value = false })
let disposed = false, releaseProfile: BodyScrollLockRelease | undefined
const menuRoot = ref<HTMLElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const isMenuOpen = ref(false)
const isAvatarPreviewOpen = ref(false)
const isProfileDialogOpen = ref(false)
const avatarPreviewRoot = ref<HTMLElement | null>(null)
const avatarPreviewCloseButton = ref<HTMLButtonElement | null>(null)
const isLoggingOut = ref(false)
const isSavingAvatar = ref(false)
const isRemovingAvatar = ref(false)
const selectedAvatarFile = ref<File | null>(null)
const previewAvatarUrl = ref('')
const profileError = ref('')
const profileNotice = ref('')
useDialogFocus(() => isProfileDialogOpen.value, profileRoot, { inertBackground: true, returnFocus: () => trigger.value, onEscape: closeProfileDialog })
watch(isProfileDialogOpen, open => { if (open) releaseProfile ??= acquireBodyScrollLock(); else { releaseProfile?.(); releaseProfile = undefined } })
watch(owner, () => { isMenuOpen.value = false; isProfileDialogOpen.value = false; isAvatarPreviewOpen.value = false; clearSelectedAvatar(); isSavingAvatar.value = false; isRemovingAvatar.value = false; profileError.value = ''; profileNotice.value = '' })
watch(isMenuOpen, open => { if (open) positionMenu(); else releaseSurface('account') })
function positionMenu() { if (!trigger.value) return; const r = trigger.value.getBoundingClientRect(), viewport = window.visualViewport, w = viewport?.width ?? innerWidth, h = viewport?.height ?? innerHeight, top = (viewport?.offsetTop ?? 0)+Math.min(r.bottom+10,h-160); menuStyle.value = { position: 'fixed', top: `${top}px`, left: `${Math.max(12,Math.min(r.right-320,w-332))}px`, width: `${Math.min(320,w-24)}px`, maxHeight: `${Math.max(120,h-top-12)}px`, overflowY: 'auto' } }

const displayName = computed(() =>
  authStore.currentUser?.display_name
  || authStore.currentUser?.username
  || '已登录账号',
)

const registeredProfile = computed(() => authStore.currentUser?.profile)
const registeredIdentity = computed(() => authStore.currentUser?.identity)
const registeredPosition = computed(() => registeredIdentity.value ? registeredIdentity.value.primary_assignment?.official_position_title?.trim() || registeredIdentity.value.position?.trim() || '' : registeredProfile.value?.position?.trim() || '')
const roleLabel = computed(() => registeredPosition.value || authStore.roles[0] || '系统用户')
const accountName = computed(() => authStore.currentUser?.username ?? '当前账号')

function resolveAvatarUrl(value: string | undefined) {
  const avatarUrl = value?.trim()
  if (!avatarUrl || /^https?:\/\//i.test(avatarUrl)) {
    return avatarUrl ?? ''
  }

  const apiBaseUrl = import.meta.env?.VITE_API_BASE_URL
  if (!apiBaseUrl || !/^https?:\/\//i.test(apiBaseUrl)) {
    return avatarUrl
  }

  try {
    return new URL(avatarUrl, apiBaseUrl).toString()
  } catch {
    return avatarUrl
  }
}

const avatarUrl = computed(() => resolveAvatarUrl(authStore.currentUser?.avatar_url))
const dialogAvatarUrl = computed(() => previewAvatarUrl.value || avatarUrl.value)
const hasServerAvatar = computed(() => Boolean(avatarUrl.value))
const isAvatarBusy = computed(() => isSavingAvatar.value || isRemovingAvatar.value)
let releaseAvatarPreviewScrollLock: BodyScrollLockRelease | null = null

useDialogFocus(
  () => isAvatarPreviewOpen.value,
  avatarPreviewRoot,
  {
    inertBackground: true,
    onEscape: () => closeAvatarPreview(),
    openAnnouncement: () => `已打开${displayName.value}的头像预览`,
    initialFocus: () => avatarPreviewCloseButton.value,
  },
)

watch(isAvatarPreviewOpen, (open) => {
  if (open) {
    releaseAvatarPreviewScrollLock ??= acquireBodyScrollLock()
  } else {
    releaseAvatarPreviewScrollLock?.()
    releaseAvatarPreviewScrollLock = null
  }
})

const internalDepartmentLabels: Record<string, string> = {
  system: '系统管理',
  management: '综合管理',
  molding: '啤机部',
  warehouse: '仓管部',
  'carton-warehouse': '纸箱仓管',
}

const factoryLabel = computed(() => {
  if (authStore.currentUser?.identity?.primary_assignment?.org_name) return authStore.currentUser.identity.primary_assignment.org_name
  const factoryId = (registeredIdentity.value ? registeredIdentity.value.primary_factory_id : registeredProfile.value?.primary_factory_id)?.trim()
  if (!factoryId) {
    return '未登记'
  }

  return factoryContexts.find((factory) => factory.id === factoryId)?.shortName ?? factoryId
})

const departmentLabel = computed(() => {
  const departmentId = (registeredIdentity.value ? registeredIdentity.value.primary_assignment?.department_code || registeredIdentity.value.primary_department : registeredProfile.value?.primary_department)?.trim()
  if (!departmentId) {
    return '未登记'
  }

  return internalDepartmentLabels[departmentId]
    ?? departmentMap[departmentId as keyof typeof departmentMap]?.name
    ?? departmentId
})

const positionLabel = computed(() => registeredPosition.value || '未登记')

function revokePreviewUrl() {
  if (previewAvatarUrl.value) {
    URL.revokeObjectURL(previewAvatarUrl.value)
  }
  previewAvatarUrl.value = ''
}

function clearSelectedAvatar() {
  revokePreviewUrl()
  selectedAvatarFile.value = null
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

function closeMenuWhenClickingOutside(event: PointerEvent) {
  if (isAvatarPreviewOpen.value) {
    return
  }

  if (!menuRoot.value?.contains(event.target as Node)) {
    isMenuOpen.value = false
  }
}

function toggleMenu() {
  if (!isMenuOpen.value && !requestSurface('account')) return
  isMenuOpen.value = !isMenuOpen.value
}

function openAvatarPreview() {
  isAvatarPreviewOpen.value = true
}

function closeAvatarPreview() {
  isAvatarPreviewOpen.value = false
}

function openProfileDialog() {
  isMenuOpen.value = false
  profileError.value = ''
  profileNotice.value = ''
  clearSelectedAvatar()
  isProfileDialogOpen.value = true
}

function closeProfileDialog() {
  if (isAvatarBusy.value) {
    return
  }

  clearSelectedAvatar()
  profileError.value = ''
  isProfileDialogOpen.value = false
}

function openAvatarFilePicker() {
  if (!isAvatarBusy.value) {
    fileInput.value?.click()
  }
}

function selectAvatar(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) {
    return
  }

  profileError.value = ''
  profileNotice.value = ''

  if (!ACCEPTED_AVATAR_TYPES.has(file.type)) {
    clearSelectedAvatar()
    profileError.value = '请选择 JPG、PNG 或 WebP 格式的图片。'
    return
  }
  if (file.size > MAX_AVATAR_FILE_SIZE) {
    clearSelectedAvatar()
    profileError.value = '头像文件不能超过 2 MB。'
    return
  }

  revokePreviewUrl()
  selectedAvatarFile.value = file
  previewAvatarUrl.value = URL.createObjectURL(file)
}

async function saveAvatar() {
  const key = owner.value
  const file = selectedAvatarFile.value
  if (!file || isAvatarBusy.value) {
    return
  }

  isSavingAvatar.value = true
  profileError.value = ''
  profileNotice.value = ''
  try {
    const user = await authApi.uploadAvatar(file)
    if (disposed || key !== owner.value) return
    authStore.applySession(user)
    clearSelectedAvatar()
    profileNotice.value = '头像已保存，顶栏会立即更新。'
  } catch (error) {
    if (!disposed && key === owner.value) profileError.value = getApiErrorMessage(error)
  } finally {
    if (!disposed && key === owner.value) isSavingAvatar.value = false
  }
}

async function removeAvatar() {
  const key = owner.value
  if (!hasServerAvatar.value || isAvatarBusy.value) {
    return
  }

  isRemovingAvatar.value = true
  profileError.value = ''
  profileNotice.value = ''
  try {
    const user = await authApi.deleteAvatar()
    if (disposed || key !== owner.value) return
    authStore.applySession(user)
    clearSelectedAvatar()
    profileNotice.value = '已恢复为默认头像。'
  } catch (error) {
    if (!disposed && key === owner.value) profileError.value = getApiErrorMessage(error)
  } finally {
    if (!disposed && key === owner.value) isRemovingAvatar.value = false
  }
}

async function handleLogout() {
  if (isLoggingOut.value) {
    return
  }

  isLoggingOut.value = true
  try {
    await authStore.logout()
  } catch {
    authStore.clearSession()
  } finally {
    isMenuOpen.value = false
    await router.replace({ name: 'login', query: { logged_out: '1' } })
    isLoggingOut.value = false
  }
}

onMounted(() => {
  window.addEventListener('resize', positionMenu); window.addEventListener('scroll', positionMenu, true); window.visualViewport?.addEventListener('resize', positionMenu)
  document.addEventListener('pointerdown', closeMenuWhenClickingOutside)
})

onBeforeUnmount(() => {
  disposed = true; unregister(); releaseProfile?.(); window.removeEventListener('resize', positionMenu); window.removeEventListener('scroll', positionMenu, true); window.visualViewport?.removeEventListener('resize', positionMenu)
  document.removeEventListener('pointerdown', closeMenuWhenClickingOutside)
  releaseAvatarPreviewScrollLock?.()
  revokePreviewUrl()
})
</script>

<template>
  <div
    ref="menuRoot"
    class="account-menu relative"
    :class="`account-menu--${variant}`"
    :data-variant="variant"
    @keydown.esc="isMenuOpen = false"
  >
    <button
      ref="trigger"
      type="button"
      class="account-menu__trigger inline-flex h-9 items-center gap-2 rounded-lg border px-2 py-1 transition-[transform,border-color,background-color,box-shadow,color] duration-150 focus-visible:outline-none focus-visible:ring-2 active:scale-[0.98]"
      :class="variant === 'obsidian'
        ? 'border-white/15 bg-white/[0.065] text-slate-100 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)] hover:border-cyan-200/30 hover:bg-white/[0.11] focus-visible:ring-cyan-300/35'
        : 'border-slate-200 bg-white text-slate-700 hover:border-teal-200 hover:bg-teal-50/60 focus-visible:ring-teal-500/30'"
      aria-label="账号与头像设置"
      aria-haspopup="dialog"
      :aria-expanded="isMenuOpen"
      @click="toggleMenu"
    >
      <UserAvatar :src="avatarUrl" :name="displayName" size="sm" />
      <span v-if="!compact" class="account-menu__details hidden min-w-0 text-left leading-tight sm:block">
        <span class="block max-w-28 truncate text-[12px] font-semibold" :class="variant === 'obsidian' ? 'text-white' : 'text-slate-800'">{{ displayName }}</span>
        <span class="block max-w-28 truncate text-[10px] text-slate-400">{{ roleLabel === displayName ? '我的空间' : roleLabel }}</span>
      </span>
      <ChevronDown
        class="account-menu__chevron size-3.5 shrink-0 transition-transform"
        :class="[isMenuOpen ? 'rotate-180' : '', variant === 'obsidian' ? 'text-slate-300' : 'text-slate-400']"
        aria-hidden="true"
      />
    </button>

    <Transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="translate-y-1 opacity-0"
      enter-to-class="translate-y-0 opacity-100"
      leave-active-class="transition duration-100 ease-in"
      leave-from-class="translate-y-0 opacity-100"
      leave-to-class="translate-y-1 opacity-0"
    >
      <section
        v-if="isMenuOpen"
        class="z-50 rounded-xl border border-slate-200 bg-white/98 text-left text-slate-700 shadow-2xl shadow-slate-900/12 backdrop-blur-xl"
        :style="menuStyle"
        role="dialog"
        aria-label="账号菜单"
      >
        <div class="flex items-center gap-3 border-b border-slate-100 px-4 py-3.5">
          <button
            type="button"
            class="shrink-0 rounded-full transition duration-150 hover:scale-105 hover:ring-4 hover:ring-teal-50 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-teal-100 active:scale-95"
            :aria-label="`放大查看${displayName}的头像`"
            title="点击放大头像"
            @click="openAvatarPreview"
          >
            <UserAvatar :src="avatarUrl" :name="displayName" size="lg" loading="eager" />
          </button>
          <span class="min-w-0 flex-1">
            <span class="block truncate text-sm font-bold text-slate-900">{{ displayName }}</span>
            <span class="mt-0.5 block truncate text-[11px] text-slate-500">{{ accountName }}</span>
            <span class="mt-1 inline-flex rounded-full bg-teal-50 px-2 py-0.5 text-[10px] font-semibold text-teal-700">{{ roleLabel }}</span>
          </span>
        </div>

        <div class="space-y-2 border-b border-slate-100 px-3 py-3">
          <div class="flex items-start gap-2 rounded-lg bg-slate-50 px-2.5 py-2">
            <Factory class="mt-0.5 size-4 shrink-0 text-teal-600" aria-hidden="true" />
            <span class="min-w-0">
              <span class="block text-[11px] font-semibold text-slate-400">正式组织</span>
              <span class="block break-words text-[12px] font-semibold text-slate-800">{{ factoryLabel }}</span>
            </span>
          </div>
          <div class="flex items-start gap-2 rounded-lg bg-slate-50 px-2.5 py-2">
            <Building2 class="mt-0.5 size-4 shrink-0 text-sky-600" aria-hidden="true" />
            <span class="min-w-0">
              <span class="block text-[11px] font-semibold text-slate-400">部门</span>
              <span class="block break-words text-[12px] font-semibold text-slate-800">{{ departmentLabel }}</span>
            </span>
          </div>
          <div class="flex items-start gap-2 rounded-lg bg-slate-50 px-2.5 py-2">
            <BriefcaseBusiness class="mt-0.5 size-4 shrink-0 text-amber-600" aria-hidden="true" />
            <span class="min-w-0">
              <span class="block text-[11px] font-semibold text-slate-400">职位</span>
              <span class="block break-words text-[12px] font-semibold text-slate-800">{{ positionLabel }}</span>
            </span>
          </div>
        </div>

        <div class="space-y-1 p-2">
          <RouterLink v-if="messaging.ready" to="/me" class="flex h-10 items-center gap-2 rounded-lg bg-teal-50 px-2.5 text-sm font-semibold text-teal-800" @click="isMenuOpen = false"><UserRound class="size-4" />我的空间</RouterLink>
          <RouterLink v-if="messaging.ready" to="/messages" class="flex h-10 items-center gap-2 rounded-lg px-2.5 text-sm text-slate-700" @click="isMenuOpen = false">私信 <span v-if="messaging.unread">{{ messaging.unread }} 未读</span></RouterLink>
          <button
            type="button"
            class="flex h-9 w-full items-center gap-2 rounded-lg px-2.5 text-[12px] font-semibold text-slate-700 transition hover:bg-teal-50 hover:text-teal-800"
            @click="openProfileDialog"
          >
            <Camera class="size-4 text-teal-700" aria-hidden="true" />
            个人资料与头像
          </button>
          <button
            type="button"
            class="flex h-9 w-full items-center gap-2 rounded-lg px-2.5 text-[12px] font-semibold text-slate-700 transition hover:bg-red-50 hover:text-red-600 disabled:cursor-wait disabled:opacity-60"
            :disabled="isLoggingOut"
            @click="handleLogout"
          >
            <LogOut class="size-4" aria-hidden="true" />
            {{ isLoggingOut ? '退出中…' : '退出登录' }}
          </button>
        </div>
      </section>
    </Transition>

    <Teleport to="body">
      <Transition name="nav-backdrop">
        <div
          v-if="isAvatarPreviewOpen"
          class="account-menu-overlay fixed inset-0 z-[90] grid place-items-center bg-slate-950/55 p-4 backdrop-blur-sm"
          role="presentation"
          @click.self="closeAvatarPreview"
        >
          <section
            ref="avatarPreviewRoot"
            role="dialog"
            aria-modal="true"
            aria-labelledby="account-avatar-preview-title"
            tabindex="-1"
            class="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl outline-none"
          >
            <header class="flex items-start justify-between gap-4">
              <div>
                <p class="text-[11px] font-bold tracking-[0.16em] text-teal-700">账户头像</p>
                <h2 id="account-avatar-preview-title" class="mt-1 text-lg font-semibold text-slate-950">
                  {{ displayName }}
                </h2>
              </div>
              <button
                ref="avatarPreviewCloseButton"
                type="button"
                aria-label="关闭头像预览"
                class="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
                @click="closeAvatarPreview"
              >
                <X class="size-5" aria-hidden="true" />
              </button>
            </header>
            <div class="mt-5 flex justify-center rounded-2xl bg-slate-50 p-6">
              <UserAvatar
                :src="avatarUrl"
                :name="displayName"
                size="xl"
                loading="eager"
                class="!h-64 !w-64 max-h-[min(64vw,320px)] max-w-[min(64vw,320px)] !text-6xl ring-1 ring-slate-200"
              />
            </div>
            <p class="mt-4 text-center text-sm text-slate-600">
              {{ roleLabel }} · {{ factoryLabel }} · {{ departmentLabel }}
            </p>
          </section>
        </div>
      </Transition>

      <div
        v-if="isProfileDialogOpen"
        class="account-menu-overlay fixed inset-0 z-[70] flex items-center justify-center overflow-y-auto bg-slate-950/45 px-4 py-6 backdrop-blur-sm"
        role="presentation"
        @click.self="closeProfileDialog"
      >
        <section
        ref="profileRoot" tabindex="-1"
        class="flex max-h-[calc(100vh-48px)] w-full max-w-[460px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl shadow-slate-950/20"
        role="dialog"
        aria-modal="true"
        aria-labelledby="avatar-profile-title"
      >
        <header class="flex shrink-0 items-start justify-between gap-4 border-b border-slate-100 px-5 py-4">
          <span class="flex gap-3">
            <span class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-teal-50 text-teal-700">
              <UserRound class="size-5" aria-hidden="true" />
            </span>
            <span>
              <span id="avatar-profile-title" class="block text-[16px] font-bold text-slate-950">个人资料与头像</span>
              <span class="mt-1 block text-[12.5px] leading-5 text-slate-500">头像仅供当前账号在系统内展示与识别。</span>
            </span>
          </span>
          <button
            type="button"
            class="flex size-8 shrink-0 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 disabled:cursor-not-allowed"
            aria-label="关闭个人资料与头像"
            :disabled="isAvatarBusy"
            @click="closeProfileDialog"
          >
            <X class="size-4" aria-hidden="true" />
          </button>
        </header>

        <div class="space-y-4 overflow-y-auto px-5 py-5">
          <div class="flex flex-col items-center rounded-xl border border-slate-100 bg-slate-50 px-4 py-4 text-center sm:flex-row sm:text-left">
            <UserAvatar :src="dialogAvatarUrl" :name="displayName" size="xl" />
            <div class="mt-3 min-w-0 sm:ml-4 sm:mt-0 sm:flex-1">
              <p class="truncate text-[14px] font-bold text-slate-900">{{ displayName }}</p>
              <p class="mt-1 truncate text-[12px] text-slate-500">账号：{{ accountName }}</p>
              <p class="mt-1 truncate text-[12px] text-slate-500">角色：{{ roleLabel }}</p>
            </div>
          </div>

          <div class="rounded-xl border border-dashed border-teal-200 bg-teal-50/45 p-3.5">
            <input
              ref="fileInput"
              class="sr-only"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              aria-label="选择头像图片"
              :disabled="isAvatarBusy"
              @change="selectAvatar"
            >
            <div class="flex flex-wrap items-center gap-2">
              <button
                type="button"
                class="inline-flex h-9 items-center gap-2 rounded-lg bg-teal-700 px-3 text-[12px] font-semibold text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-300"
                :disabled="isAvatarBusy"
                @click="openAvatarFilePicker"
              >
                <ImagePlus class="size-4" aria-hidden="true" />
                {{ selectedAvatarFile ? '重新选择图片' : '选择图片' }}
              </button>
              <button
                v-if="selectedAvatarFile"
                type="button"
                class="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-600 transition hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed"
                :disabled="isAvatarBusy"
                @click="clearSelectedAvatar"
              >
                <X class="size-4" aria-hidden="true" />
                取消本次选择
              </button>
            </div>
            <p class="mt-2 text-[11.5px] leading-5 text-slate-500">支持 JPG、PNG、WebP，最大 2 MB。选择后先预览，点击保存才会更新。</p>
          </div>

          <p
            v-if="profileError"
            class="rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-[12px] font-medium text-red-600"
            role="alert"
          >
            {{ profileError }}
          </p>
          <p
            v-if="profileNotice"
            class="rounded-lg border border-emerald-100 bg-emerald-50 px-3 py-2 text-[12px] font-medium text-emerald-700"
          >
            {{ profileNotice }}
          </p>
        </div>

        <footer class="flex shrink-0 flex-wrap items-center justify-end gap-2 border-t border-slate-100 bg-slate-50/70 px-5 py-3.5">
          <button
            v-if="hasServerAvatar && !selectedAvatarFile"
            type="button"
            class="mr-auto inline-flex h-9 items-center gap-1.5 rounded-lg px-2 text-[12px] font-semibold text-slate-500 transition hover:bg-white hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="isAvatarBusy"
            @click="removeAvatar"
          >
            <RotateCcw class="size-4" aria-hidden="true" />
            {{ isRemovingAvatar ? '恢复中…' : '恢复默认头像' }}
          </button>
          <button
            type="button"
            class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed"
            :disabled="isAvatarBusy"
            @click="closeProfileDialog"
          >
            取消
          </button>
          <button
            type="button"
            class="inline-flex h-9 items-center gap-2 rounded-lg bg-teal-700 px-3 text-[12px] font-semibold text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-300"
            :disabled="!selectedAvatarFile || isAvatarBusy"
            @click="saveAvatar"
          >
            <LoaderCircle v-if="isSavingAvatar" class="size-4 animate-spin" aria-hidden="true" />
            <Camera v-else class="size-4" aria-hidden="true" />
            {{ isSavingAvatar ? '保存中…' : '保存头像' }}
          </button>
        </footer>
        </section>
      </div>
    </Teleport>
  </div>
</template>
