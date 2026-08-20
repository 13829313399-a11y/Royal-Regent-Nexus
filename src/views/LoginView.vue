<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  ArrowRight,
  Building2,
  CheckCircle2,
  CircleAlert,
  Eye,
  EyeOff,
  Gauge,
  GitBranch,
  KeyRound,
  LayoutGrid,
  LifeBuoy,
  LoaderCircle,
  Lock,
  RefreshCw,
  ShieldCheck,
  ShieldQuestion,
  UserPlus,
  UserRound,
  X,
} from '@lucide/vue'
import { useRoute, useRouter } from 'vue-router'
import { authApi, type PasswordResetClaimResponse } from '@/api/auth'
import AuthAmbientGrid from '@/components/auth/AuthAmbientGrid.vue'
import { getApiErrorMessage } from '@/lib/http'
import { resolvePostLoginRedirect } from '@/lib/postLoginRedirect'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const LAST_LOGIN_ACCOUNT_STORAGE_KEY = 'rr:last-login-account'

interface LastLoginAccount {
  username: string
  displayName: string
  savedAt: string
}

const username = ref('')
const password = ref('')
const rememberAccount = ref(true)
const showPassword = ref(false)
const isSubmitting = ref(false)
const errorMessage = ref('')
const recentAccount = ref<LastLoginAccount | null>(null)
const passwordInput = ref<HTMLInputElement | null>(null)
const passwordInputMessage = ref('')
const showPasswordHelp = ref(false)
const passwordHelpMessage = ref('')
const passwordResetForm = ref({
  username: '',
  display_name: '',
  contact: '',
  note: '',
})
const isPasswordResetSubmitting = ref(false)
const passwordResetSubmitted = ref(false)
const passwordResetRequestId = ref('')
const passwordResetInvalidField = ref<'username' | 'display_name' | 'contact' | ''>('')
const passwordResetUsernameInput = ref<HTMLInputElement | null>(null)
const passwordResetDisplayNameInput = ref<HTMLInputElement | null>(null)
const passwordResetContactInput = ref<HTMLInputElement | null>(null)
const passwordResetClaim = ref<PasswordResetClaimResponse | null>(null)
const isPasswordResetClaimRefreshing = ref(false)
let passwordResetPollTimer: ReturnType<typeof window.setTimeout> | undefined

const chinesePasswordPattern = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/
const chinesePasswordGlobalPattern = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/g
const passwordChineseMessage = '密码不能包含中文，请使用英文、数字或符号'
const brandLogoUrl = '/brand/huadeng_group_dynamic_logo.svg'

const recentAccountTitle = computed(() => {
  if (!recentAccount.value) {
    return ''
  }

  return recentAccount.value.displayName || recentAccount.value.username
})

const recentAccountDetail = computed(() => {
  if (!recentAccount.value) {
    return ''
  }

  const account = recentAccount.value
  return account.displayName && account.displayName !== account.username
    ? `${account.username} · 密码不会保存在本系统`
    : '密码不会保存在本系统'
})

const passwordHelpAccount = computed(() =>
  passwordResetForm.value.username.trim()
  || username.value.trim()
  || recentAccount.value?.username
  || '',
)

const passwordModel = computed({
  get: () => password.value,
  set: (value: string) => {
    const normalizedValue = value.replace(chinesePasswordGlobalPattern, '')
    password.value = normalizedValue
    passwordInputMessage.value = normalizedValue === value ? '' : passwordChineseMessage
  },
})

const passwordResetClaimTitle = computed(() => ({
  pending: '密码重置申请',
  approved: '密码重置申请已通过',
  completed: '密码已成功重置',
  rejected: '密码重置申请未通过',
  expired: '本次改密时限已过期',
  legacy_invalid: '旧版申请需重新提交',
  none: '',
}[passwordResetClaim.value?.status ?? 'none']))

const passwordResetClaimTone = computed(() => ({
  pending: 'border-amber-100 bg-amber-50 text-amber-900',
  approved: 'border-emerald-100 bg-emerald-50 text-emerald-900',
  completed: 'border-emerald-100 bg-emerald-50 text-emerald-900',
  rejected: 'border-red-100 bg-red-50 text-red-900',
  expired: 'border-slate-200 bg-slate-50 text-slate-800',
  legacy_invalid: 'border-slate-200 bg-slate-50 text-slate-800',
  none: '',
}[passwordResetClaim.value?.status ?? 'none']))

const brandFeatures = [
  {
    title: '多厂区协同',
    detail: '华康A/B · 华登 · 华兴统一调度',
    icon: Building2,
  },
  {
    title: '部门模块中心',
    detail: '工程 / PMC / 生产 / QA / 业务',
    icon: LayoutGrid,
  },
  {
    title: '全流程审批',
    detail: '单据流转留痕、权责清晰',
    icon: GitBranch,
  },
  {
    title: '运营驾驶舱',
    detail: '在线服务 23/24 · 实时监控',
    icon: Gauge,
  },
]

function getLoginStorage() {
  if (typeof window === 'undefined' || !window.localStorage) {
    return null
  }

  try {
    return window.localStorage
  } catch {
    return null
  }
}

function readRecentAccount() {
  const storage = getLoginStorage()
  if (!storage) {
    return null
  }

  try {
    const rawValue = storage.getItem(LAST_LOGIN_ACCOUNT_STORAGE_KEY)
    if (!rawValue) {
      return null
    }

    const parsedValue = JSON.parse(rawValue) as Partial<LastLoginAccount>
    const savedUsername = typeof parsedValue.username === 'string' ? parsedValue.username.trim() : ''
    if (!savedUsername) {
      return null
    }

    return {
      username: savedUsername,
      displayName: typeof parsedValue.displayName === 'string' ? parsedValue.displayName.trim() : '',
      savedAt: typeof parsedValue.savedAt === 'string' ? parsedValue.savedAt : '',
    }
  } catch {
    storage.removeItem(LAST_LOGIN_ACCOUNT_STORAGE_KEY)
    return null
  }
}

function saveRecentAccount(user: { username: string; display_name?: string }) {
  const storage = getLoginStorage()
  if (!storage) {
    return
  }

  const account = {
    username: user.username,
    displayName: user.display_name?.trim() || user.username,
    savedAt: new Date().toISOString(),
  }

  storage.setItem(LAST_LOGIN_ACCOUNT_STORAGE_KEY, JSON.stringify(account))
  recentAccount.value = account
}

function clearRecentAccount() {
  getLoginStorage()?.removeItem(LAST_LOGIN_ACCOUNT_STORAGE_KEY)
  recentAccount.value = null
  username.value = ''
  password.value = ''
  rememberAccount.value = false
}

function continueWithRecentAccount() {
  if (!recentAccount.value) {
    return
  }

  username.value = recentAccount.value.username
  password.value = ''
  requestAnimationFrame(() => passwordInput.value?.focus())
}

function focusPasswordInput(event: KeyboardEvent) {
  if (event.isComposing || !username.value.trim()) {
    return
  }

  event.preventDefault()

  if (isSubmitting.value) {
    return
  }

  passwordInput.value?.focus()
}

function openPasswordHelp() {
  passwordHelpMessage.value = ''
  passwordResetInvalidField.value = ''
  passwordResetSubmitted.value = false
  passwordResetRequestId.value = ''
  passwordResetForm.value = {
    ...passwordResetForm.value,
    username: passwordHelpAccount.value,
    display_name: recentAccount.value?.displayName ?? '',
  }
  showPasswordHelp.value = true
}

function closePasswordHelp() {
  showPasswordHelp.value = false
  passwordHelpMessage.value = ''
  passwordResetInvalidField.value = ''
  passwordResetSubmitted.value = false
  passwordResetRequestId.value = ''
}

function showPasswordResetValidation(
  field: 'username' | 'display_name' | 'contact',
  message: string,
  input: () => HTMLInputElement | null,
) {
  passwordResetInvalidField.value = field
  passwordHelpMessage.value = message
  requestAnimationFrame(() => input()?.focus())
}

function clearPasswordResetValidation(field: 'username' | 'display_name' | 'contact') {
  if (passwordResetInvalidField.value !== field) return
  passwordResetInvalidField.value = ''
  passwordHelpMessage.value = ''
}

async function submitPasswordResetRequest() {
  const payload = {
    username: passwordResetForm.value.username.trim(),
    display_name: passwordResetForm.value.display_name.trim(),
    contact: passwordResetForm.value.contact.trim(),
    note: passwordResetForm.value.note.trim(),
  }

  passwordHelpMessage.value = ''
  passwordResetInvalidField.value = ''
  passwordResetSubmitted.value = false

  if (!payload.username) {
    showPasswordResetValidation(
      'username',
      '请先填写需要重置密码的企业账号',
      () => passwordResetUsernameInput.value,
    )
    return
  }
  if (!payload.display_name) {
    showPasswordResetValidation(
      'display_name',
      '请填写姓名，方便管理员核验身份',
      () => passwordResetDisplayNameInput.value,
    )
    return
  }
  if (!payload.contact) {
    showPasswordResetValidation(
      'contact',
      '请填写联系电话或邮箱，方便管理员核验',
      () => passwordResetContactInput.value,
    )
    return
  }

  isPasswordResetSubmitting.value = true
  try {
    const response = await authApi.requestPasswordReset(payload)
    passwordResetSubmitted.value = true
    passwordResetRequestId.value = response.request_id ?? ''
    passwordHelpMessage.value = response.message
    await refreshPasswordResetClaim()
  } catch (error) {
    passwordHelpMessage.value = getApiErrorMessage(error)
  } finally {
    isPasswordResetSubmitting.value = false
  }
}

function clearPasswordResetPoll() {
  if (!passwordResetPollTimer) return
  window.clearTimeout(passwordResetPollTimer)
  passwordResetPollTimer = undefined
}

function schedulePasswordResetPoll() {
  clearPasswordResetPoll()
  if (passwordResetClaim.value?.status !== 'pending' || document.visibilityState !== 'visible') return
  passwordResetPollTimer = window.setTimeout(() => {
    void refreshPasswordResetClaim(true)
  }, 15_000)
}

async function refreshPasswordResetClaim(quiet = false) {
  if (!quiet) isPasswordResetClaimRefreshing.value = true
  try {
    passwordResetClaim.value = await authApi.getPasswordResetClaim()
  } catch {
    if (!quiet) passwordResetClaim.value = null
  } finally {
    if (!quiet) isPasswordResetClaimRefreshing.value = false
    schedulePasswordResetPoll()
  }
}

function handlePasswordResetVisibilityChange() {
  if (document.visibilityState === 'visible') {
    void refreshPasswordResetClaim(true)
  } else {
    clearPasswordResetPoll()
  }
}

function openPasswordResetCompletion() {
  void router.push({ name: 'reset-password' })
}

async function submitLogin() {
  errorMessage.value = ''

  if (!username.value.trim() || !password.value) {
    errorMessage.value = !username.value.trim() && !password.value
      ? '请输入账号和密码'
      : !username.value.trim() ? '请输入企业账号' : '请输入登录密码'
    return
  }

  if (chinesePasswordPattern.test(password.value)) {
    passwordInputMessage.value = passwordChineseMessage
    return
  }

  isSubmitting.value = true

  try {
    const user = await authStore.login({
      username: username.value.trim(),
      password: password.value,
    })

    if (rememberAccount.value) {
      saveRecentAccount(user)
    } else {
      getLoginStorage()?.removeItem(LAST_LOGIN_ACCOUNT_STORAGE_KEY)
      recentAccount.value = null
    }

    const target = resolvePostLoginRedirect(router, route.query.redirect)
    await router.replace(user.force_password_change
      ? { name: 'change-password', query: target === '/' ? {} : { redirect: target } }
      : target)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isSubmitting.value = false
  }
}

onMounted(() => {
  recentAccount.value = readRecentAccount()
  if (recentAccount.value && !username.value.trim()) {
    username.value = recentAccount.value.username
  }
  document.addEventListener('visibilitychange', handlePasswordResetVisibilityChange)
  void refreshPasswordResetClaim()
})

onBeforeUnmount(() => {
  clearPasswordResetPoll()
  document.removeEventListener('visibilitychange', handlePasswordResetVisibilityChange)
})
</script>

<template>
  <main class="flex min-h-screen bg-white font-sans text-slate-950">
    <aside class="brand-panel relative hidden w-[56%] flex-col overflow-hidden bg-slate-950 text-white lg:flex">
      <AuthAmbientGrid class="brand-grid" variant="login" />
      <div class="brand-glow absolute inset-0" aria-hidden="true"></div>

      <div class="relative z-10 flex items-center gap-4 px-14 pt-12">
        <span class="flex size-20 shrink-0 items-center justify-center rounded-xl bg-white/95 p-2 shadow-lg shadow-black/20">
          <img
            :src="brandLogoUrl"
            alt="华登集团"
            class="h-full w-full object-contain"
          >
        </span>
        <div>
          <div class="text-[21px] font-semibold leading-tight">Royal Regent Nexus</div>
          <div class="mt-1 text-[13px] text-slate-400">华登集团 · 集团级业务中台</div>
        </div>
      </div>

      <section class="relative z-10 flex flex-1 flex-col justify-center px-14">
        <div class="mb-3 inline-flex w-fit items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-[12px] font-medium text-teal-300">
          <span class="size-1.5 rounded-full bg-teal-400"></span>
          多厂区 · 多部门统一门户
        </div>
        <h1 class="max-w-lg text-[34px] font-bold leading-[1.25]">
          一个平台，贯通集团<br>制造全业务链
        </h1>
        <p class="mt-4 max-w-md text-[14px] leading-relaxed text-slate-300">
          从工程开单、PMC 排产到生产执行与质量放行，跨华康、华登、华兴多厂区协同，让订单、模具、审批与看板在同一中台实时流转。
        </p>

        <div class="mt-10 grid max-w-xl grid-cols-2 gap-3">
          <div
            v-for="feature in brandFeatures"
            :key="feature.title"
            class="login-feature-card rounded-xl border border-white/10 bg-white/[0.045] p-4"
          >
            <span class="login-feature-icon flex size-9 shrink-0 items-center justify-center rounded-[10px] border border-teal-300/20 bg-teal-400/10 text-teal-300">
              <component :is="feature.icon" class="size-4" aria-hidden="true" />
            </span>
            <div>
              <div class="mt-3 text-[13.5px] font-semibold text-slate-200">{{ feature.title }}</div>
              <div class="mt-1 text-[11.5px] leading-5 text-slate-500">{{ feature.detail }}</div>
            </div>
          </div>
        </div>
      </section>

      <div class="relative z-10 flex items-center justify-between px-14 pb-9 text-[11px] text-slate-500">
        <span>© 2026 华登集团 · 数字化中心</span>
        <span class="flex items-center gap-1.5">
          <ShieldCheck class="size-3.5" aria-hidden="true" />
          内部系统，仅限授权访问
        </span>
      </div>
    </aside>

    <section class="flex w-full flex-col lg:w-[44%]">
      <div class="flex items-center gap-3 border-b border-slate-800 bg-slate-950 px-6 py-3 text-white lg:hidden">
        <span class="flex size-12 shrink-0 items-center justify-center rounded-lg bg-white/95 p-1.5">
          <img :src="brandLogoUrl" alt="华登集团" class="h-full w-full object-contain">
        </span>
        <div>
          <div class="text-[16px] font-semibold leading-tight">Royal Regent Nexus</div>
          <div class="text-[11px] text-slate-400">华登集团 · 集团级业务中台</div>
        </div>
      </div>

      <div class="flex flex-1 items-center justify-center bg-white px-6 py-10 sm:px-14">
        <div class="fade-in w-full max-w-[400px]">
          <div class="mb-8">
            <h2 class="text-[24px] font-semibold text-slate-950">欢迎回来</h2>
            <p class="mt-1.5 text-[13.5px] text-slate-500">登录华登集团业务中台，请使用企业统一账号</p>
          </div>

          <div
            v-if="recentAccount"
            class="mb-5 flex items-center gap-3 rounded-xl border border-teal-100 bg-teal-50/75 p-3 shadow-sm shadow-teal-950/[0.03]"
          >
            <button
              class="flex min-w-0 flex-1 items-center gap-3 text-left"
              type="button"
              @click="continueWithRecentAccount"
            >
              <span class="flex size-10 shrink-0 items-center justify-center rounded-lg bg-white text-teal-700 shadow-sm">
                <ShieldCheck class="size-5" aria-hidden="true" />
              </span>
              <span class="min-w-0">
                <span class="block truncate text-[13px] font-semibold text-slate-900">继续使用上次账号</span>
                <span class="mt-0.5 block truncate text-[12px] leading-5 text-slate-500">
                  {{ recentAccountTitle }} · {{ recentAccountDetail }}
                </span>
              </span>
            </button>
            <button
              class="shrink-0 rounded-md px-2.5 py-1.5 text-[12px] font-semibold text-teal-700 transition hover:bg-white hover:text-teal-800"
              type="button"
              @click="clearRecentAccount"
            >
              切换账号
            </button>
          </div>

          <section
            v-if="passwordResetClaim && passwordResetClaim.status !== 'none'"
            class="mb-5 rounded-xl border p-4"
            :class="passwordResetClaimTone"
            aria-live="polite"
          >
            <div class="flex items-start gap-3">
              <span class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-white/80">
                <CheckCircle2 v-if="passwordResetClaim.status === 'approved' || passwordResetClaim.status === 'completed'" class="size-4" aria-hidden="true" />
                <KeyRound v-else class="size-4" aria-hidden="true" />
              </span>
              <div class="min-w-0 flex-1">
                <h3 class="text-[13px] font-bold">{{ passwordResetClaimTitle }}</h3>
                <p class="mt-1 text-[12px] leading-5 opacity-80">{{ passwordResetClaim.message }}</p>
                <p v-if="passwordResetClaim.request_id" class="mt-1 truncate font-mono text-[10.5px] opacity-70">申请编号：{{ passwordResetClaim.request_id }}</p>
              </div>
            </div>
            <div class="mt-3 flex flex-wrap gap-2">
              <button
                v-if="passwordResetClaim.can_complete"
                class="rounded-lg bg-teal-700 px-3 py-2 text-[12px] font-bold text-white hover:bg-teal-800"
                type="button"
                @click="openPasswordResetCompletion"
              >
                立即设置新密码
              </button>
              <button
                v-if="passwordResetClaim.status === 'pending'"
                class="flex items-center gap-1.5 rounded-lg border border-current/15 bg-white/70 px-3 py-2 text-[12px] font-semibold"
                type="button"
                :disabled="isPasswordResetClaimRefreshing"
                @click="refreshPasswordResetClaim()"
              >
                <LoaderCircle v-if="isPasswordResetClaimRefreshing" class="size-3.5 animate-spin" aria-hidden="true" />
                <RefreshCw v-else class="size-3.5" aria-hidden="true" />
                刷新状态
              </button>
              <button
                v-if="['rejected', 'expired', 'legacy_invalid'].includes(passwordResetClaim.status)"
                class="rounded-lg border border-current/15 bg-white/70 px-3 py-2 text-[12px] font-semibold"
                type="button"
                @click="openPasswordHelp"
              >
                重新申请
              </button>
            </div>
          </section>

          <form class="space-y-4" novalidate @submit.prevent="submitLogin">
            <label class="block">
              <span class="mb-1.5 block text-[12.5px] font-medium text-slate-700">企业账号</span>
              <span class="field flex h-11 items-center rounded-lg border border-slate-200 bg-slate-50 px-3 transition-colors focus-within:border-teal-700 focus-within:bg-white focus-within:ring-[3px] focus-within:ring-teal-700/15">
                <UserRound class="field-icon size-4 text-slate-400 transition-colors" aria-hidden="true" />
                <input
                  v-model="username"
                  class="ml-2.5 h-full w-full bg-transparent text-[14px] outline-none placeholder:text-slate-400"
                  autocomplete="username"
                  @keydown.enter="focusPasswordInput"
                  :placeholder="recentAccount ? '确认账号或输入新账号' : '工号 / 企业邮箱'"
                  type="text"
                >
              </span>
            </label>

            <label class="block">
              <span class="mb-1.5 block text-[12.5px] font-medium text-slate-700">登录密码</span>
              <span class="field flex h-11 items-center rounded-lg border border-slate-200 bg-slate-50 px-3 transition-colors focus-within:border-teal-700 focus-within:bg-white focus-within:ring-[3px] focus-within:ring-teal-700/15">
                <Lock class="field-icon size-4 text-slate-400 transition-colors" aria-hidden="true" />
                <input
                  ref="passwordInput"
                  v-model="passwordModel"
                  class="ml-2.5 h-full w-full bg-transparent text-[14px] outline-none placeholder:text-slate-400"
                  autocapitalize="off"
                  autocomplete="current-password"
                  placeholder="请输入密码"
                  spellcheck="false"
                  :type="showPassword ? 'text' : 'password'"
                >
                <button
                  class="ml-2 flex size-7 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
                  type="button"
                  :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                  @click="showPassword = !showPassword"
                >
                  <EyeOff v-if="showPassword" class="size-4" aria-hidden="true" />
                  <Eye v-else class="size-4" aria-hidden="true" />
                </button>
              </span>
              <span v-if="passwordInputMessage" class="mt-1.5 block text-[11.5px] font-medium text-red-500">
                {{ passwordInputMessage }}
              </span>
            </label>

            <div class="flex items-center justify-between pt-0.5">
              <label class="flex cursor-pointer select-none items-center gap-2 text-[12.5px] text-slate-600">
                <input
                  v-model="rememberAccount"
                  class="size-4 rounded border-slate-300 text-teal-700 focus:ring-teal-600/40"
                  type="checkbox"
                >
                记住账号
              </label>
              <button
                class="text-[12.5px] font-medium text-teal-700 transition-colors hover:text-teal-800"
                type="button"
                @click="openPasswordHelp"
              >
                忘记密码？
              </button>
            </div>
            <p class="-mt-2 text-[11.5px] leading-5 text-slate-400">
              主动退出后需要重新验证密码；系统只保留账号，密码交由浏览器或企业密码管理器填写。
            </p>

            <div
              v-if="errorMessage"
              class="flex items-center gap-1.5 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-[12.5px] font-medium text-red-600"
            >
              <CircleAlert class="size-4 shrink-0" aria-hidden="true" />
              <span>{{ errorMessage }}</span>
            </div>

            <button
              class="flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-teal-700 text-[14.5px] font-semibold text-white transition hover:bg-teal-800 active:scale-[0.99] disabled:cursor-not-allowed disabled:bg-slate-300 disabled:active:scale-100"
              type="submit"
              :disabled="isSubmitting"
            >
              <LoaderCircle v-if="isSubmitting" class="size-4 animate-spin" aria-hidden="true" />
              <span>{{ isSubmitting ? '登录中...' : '登录' }}</span>
              <ArrowRight v-if="!isSubmitting" class="size-4" aria-hidden="true" />
            </button>
          </form>

          <RouterLink
            class="mt-5 flex items-center gap-3 rounded-xl border border-teal-100 bg-teal-50 px-4 py-3 text-left transition hover:border-teal-200 hover:bg-teal-100/70"
            to="/register"
          >
            <span class="flex size-10 shrink-0 items-center justify-center rounded-lg bg-white text-teal-700 shadow-sm">
              <UserPlus class="size-5" aria-hidden="true" />
            </span>
            <span class="min-w-0 flex-1">
              <span class="block text-[13px] font-semibold text-slate-900">没有企业账号？</span>
              <span class="mt-0.5 block text-[12px] leading-5 text-slate-500">提交账号申请，管理员审批通过后即可登录系统</span>
            </span>
            <ArrowRight class="size-4 shrink-0 text-teal-700" aria-hidden="true" />
          </RouterLink>

          <p class="mt-8 text-center text-[12px] text-slate-400">
            账号由集团数字化中心统一开通 · 审批通过后使用企业账号登录
          </p>
        </div>
      </div>
    </section>

    <div
      v-if="showPasswordHelp"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 px-4 py-4 backdrop-blur-sm sm:py-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="password-help-title"
      @click.self="closePasswordHelp"
    >
      <section class="flex max-h-[calc(100vh-32px)] w-full max-w-[430px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl shadow-slate-950/20">
        <header class="flex shrink-0 items-start justify-between gap-4 border-b border-slate-100 px-5 py-3.5">
          <span class="flex gap-3">
            <span class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-teal-50 text-teal-700">
              <ShieldQuestion class="size-5" aria-hidden="true" />
            </span>
            <span>
              <span id="password-help-title" class="block text-[16px] font-bold text-slate-950">密码重置协助</span>
              <span class="mt-1 block text-[12.5px] leading-5 text-slate-500">提交后由管理员核验，通过后可在当前浏览器直接设置新密码。</span>
            </span>
          </span>
          <button
            class="flex size-8 shrink-0 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
            type="button"
            aria-label="关闭密码重置协助"
            @click="closePasswordHelp"
          >
            <X class="size-4" aria-hidden="true" />
          </button>
        </header>

        <div class="password-help-body space-y-3 overflow-y-auto px-5 py-3">
          <div class="rounded-xl border border-amber-100 bg-amber-50 px-3 py-2 text-[12.5px] leading-5 text-amber-800">
            为保护内部系统账号安全，系统不会透露账号是否匹配，也不会发送短信、邮件或临时密码。请保留当前浏览器，审核通过后可在此直接设置新密码。
          </div>

          <div class="grid gap-2">
            <div class="flex gap-3 rounded-xl border border-slate-100 bg-slate-50 px-3 py-2.5">
              <KeyRound class="mt-0.5 size-4 shrink-0 text-teal-700" aria-hidden="true" />
              <span>
                <span class="block text-[12.5px] font-bold text-slate-900">1. 提交申请</span>
                <span class="mt-0.5 block text-[12px] leading-5 text-slate-500">填写企业账号、姓名、联系方式与核验说明。</span>
              </span>
            </div>
            <div class="flex gap-3 rounded-xl border border-slate-100 bg-slate-50 px-3 py-2.5">
              <LifeBuoy class="mt-0.5 size-4 shrink-0 text-sky-700" aria-hidden="true" />
              <span>
                <span class="block text-[12.5px] font-bold text-slate-900">2. 管理员核验</span>
                <span class="mt-0.5 block text-[12px] leading-5 text-slate-500">管理员对照系统员工资料审核申请。</span>
              </span>
            </div>
            <div class="flex gap-3 rounded-xl border border-slate-100 bg-slate-50 px-3 py-2.5">
              <CheckCircle2 class="mt-0.5 size-4 shrink-0 text-emerald-700" aria-hidden="true" />
              <span>
                <span class="block text-[12.5px] font-bold text-slate-900">3. 原浏览器领取</span>
                <span class="mt-0.5 block text-[12px] leading-5 text-slate-500">管理员批准后，当前浏览器会显示设置新密码入口。</span>
              </span>
            </div>
            <div class="flex gap-3 rounded-xl border border-slate-100 bg-slate-50 px-3 py-2.5">
              <ShieldCheck class="mt-0.5 size-4 shrink-0 text-teal-700" aria-hidden="true" />
              <span>
                <span class="block text-[12.5px] font-bold text-slate-900">4. 设置正式密码</span>
                <span class="mt-0.5 block text-[12px] leading-5 text-slate-500">无需旧密码或临时密码，直接设置仅由本人掌握的新密码。</span>
              </span>
            </div>
          </div>

          <div v-if="passwordResetSubmitted" class="rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-4 text-center">
            <CheckCircle2 class="mx-auto size-8 text-emerald-700" aria-hidden="true" />
            <h3 class="mt-2 text-[14px] font-bold text-emerald-900">申请已提交</h3>
            <p class="mt-1 text-[12px] leading-5 text-emerald-800">{{ passwordHelpMessage }}</p>
            <p class="mt-2 text-[12px] font-semibold leading-5 text-emerald-900">请保留当前浏览器。审核通过后，本页面会显示“设置新密码”入口。</p>
            <p v-if="passwordResetRequestId" class="mt-2 font-mono text-[11.5px] text-emerald-700">申请编号：{{ passwordResetRequestId }}</p>
          </div>

          <form v-else class="grid gap-2.5" novalidate @submit.prevent="submitPasswordResetRequest">
            <label class="grid gap-1.5">
              <span class="text-[12px] font-bold text-slate-600">企业账号 / 工号</span>
              <input
                ref="passwordResetUsernameInput"
                v-model="passwordResetForm.username"
                class="h-9 rounded-lg border border-slate-200 bg-slate-50 px-3 text-[13px] outline-none transition focus:border-teal-700 focus:bg-white focus:ring-[3px] focus:ring-teal-700/15"
                :class="{ 'border-red-300 bg-red-50/40 focus:border-red-500 focus:ring-red-500/15': passwordResetInvalidField === 'username' }"
                autocomplete="username"
                :aria-describedby="passwordHelpMessage ? 'password-reset-feedback' : undefined"
                :aria-invalid="passwordResetInvalidField === 'username'"
                placeholder="请输入需要重置的账号"
                required
                type="text"
                @input="clearPasswordResetValidation('username')"
              >
            </label>
            <label class="grid gap-1.5">
              <span class="text-[12px] font-bold text-slate-600">姓名</span>
              <input
                ref="passwordResetDisplayNameInput"
                v-model="passwordResetForm.display_name"
                class="h-9 rounded-lg border border-slate-200 bg-slate-50 px-3 text-[13px] outline-none transition focus:border-teal-700 focus:bg-white focus:ring-[3px] focus:ring-teal-700/15"
                :class="{ 'border-red-300 bg-red-50/40 focus:border-red-500 focus:ring-red-500/15': passwordResetInvalidField === 'display_name' }"
                autocomplete="name"
                :aria-describedby="passwordHelpMessage ? 'password-reset-feedback' : undefined"
                :aria-invalid="passwordResetInvalidField === 'display_name'"
                placeholder="便于管理员核验身份"
                required
                type="text"
                @input="clearPasswordResetValidation('display_name')"
              >
            </label>
            <label class="grid gap-1.5">
              <span class="text-[12px] font-bold text-slate-600">联系电话或邮箱</span>
              <input
                ref="passwordResetContactInput"
                v-model="passwordResetForm.contact"
                class="h-9 rounded-lg border border-slate-200 bg-slate-50 px-3 text-[13px] outline-none transition focus:border-teal-700 focus:bg-white focus:ring-[3px] focus:ring-teal-700/15"
                :class="{ 'border-red-300 bg-red-50/40 focus:border-red-500 focus:ring-red-500/15': passwordResetInvalidField === 'contact' }"
                autocomplete="email"
                :aria-describedby="passwordHelpMessage ? 'password-reset-feedback' : undefined"
                :aria-invalid="passwordResetInvalidField === 'contact'"
                placeholder="例如手机号或企业邮箱"
                required
                type="text"
                @input="clearPasswordResetValidation('contact')"
              >
            </label>
            <label class="grid gap-1.5">
              <span class="text-[12px] font-bold text-slate-600">补充说明</span>
              <textarea
                v-model="passwordResetForm.note"
                class="min-h-16 resize-none rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-[13px] outline-none transition focus:border-teal-700 focus:bg-white focus:ring-[3px] focus:ring-teal-700/15"
                placeholder="可填写厂区、部门或其他核验说明"
              ></textarea>
            </label>

            <p
              v-if="passwordHelpMessage && !passwordResetSubmitted"
              id="password-reset-feedback"
              aria-live="polite"
              class="flex items-start gap-1.5 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-[12px] font-medium text-red-600"
              role="alert"
            >
              <CircleAlert class="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
              <span>{{ passwordHelpMessage }}</span>
            </p>

            <button
              class="flex h-9 w-full items-center justify-center gap-2 rounded-lg bg-teal-700 text-[13px] font-bold text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-300"
              type="submit"
              :disabled="isPasswordResetSubmitting || passwordResetSubmitted"
            >
              <LoaderCircle v-if="isPasswordResetSubmitting" class="size-4 animate-spin" aria-hidden="true" />
              <CheckCircle2 v-else-if="passwordResetSubmitted" class="size-4" aria-hidden="true" />
              <LifeBuoy v-else class="size-4" aria-hidden="true" />
              {{ isPasswordResetSubmitting ? '提交中...' : passwordResetSubmitted ? '申请已提交' : '提交重置申请' }}
            </button>
          </form>
        </div>
      </section>
    </div>
  </main>
</template>

<style scoped>
.brand-panel {
  isolation: isolate;
}

.brand-panel::after {
  position: absolute;
  inset: 0 0 0 auto;
  z-index: 1;
  width: 96px;
  background: linear-gradient(90deg, transparent, rgb(2 6 23 / 22%));
  content: '';
  pointer-events: none;
}

.brand-glow {
  z-index: 0;
  background:
    radial-gradient(680px circle at 18% 12%, rgb(13 148 136 / 28%), transparent 55%),
    radial-gradient(560px circle at 88% 92%, rgb(5 207 99 / 16%), transparent 52%);
}

.login-feature-card,
.login-feature-icon {
  transition:
    transform 190ms cubic-bezier(0.2, 0.8, 0.2, 1),
    border-color 190ms cubic-bezier(0.2, 0.8, 0.2, 1),
    background-color 190ms cubic-bezier(0.2, 0.8, 0.2, 1),
    box-shadow 190ms cubic-bezier(0.2, 0.8, 0.2, 1);
}

@media (hover: hover) and (pointer: fine) {
  .login-feature-card:hover {
    transform: translateY(-1px);
    border-color: rgb(255 255 255 / 18%);
    background: rgb(255 255 255 / 6%);
  }

  .login-feature-card:hover .login-feature-icon {
    border-color: rgb(94 234 212 / 28%);
    background: rgb(45 212 191 / 13%);
    box-shadow: inset 0 0 14px rgb(45 212 191 / 8%);
  }
}

.fade-in {
  animation: fade 0.45s ease both;
}

.field:focus-within .field-icon {
  color: #0f766e;
}

@keyframes fade {
  from {
    opacity: 0;
    transform: translateY(8px);
  }

  to {
    opacity: 1;
    transform: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .fade-in {
    animation: none;
  }

  .login-feature-card,
  .login-feature-card:hover,
  .login-feature-icon {
    transform: none;
    transition: none;
  }
}

@media (max-height: 720px) {
  .password-help-body {
    padding-bottom: 0.625rem;
    padding-top: 0.625rem;
  }

  .password-help-body :deep(label) {
    gap: 0.25rem;
  }
}
</style>
