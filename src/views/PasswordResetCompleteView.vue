<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  ArrowLeft,
  CheckCircle2,
  CircleAlert,
  Eye,
  EyeOff,
  KeyRound,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
} from '@lucide/vue'
import { useRouter } from 'vue-router'
import { authApi, type PasswordResetClaimResponse } from '@/api/auth'
import AuthAmbientGrid from '@/components/auth/AuthAmbientGrid.vue'
import { formatBusinessDateTime } from '@/lib/dateTime'
import { getApiErrorMessage } from '@/lib/http'

const router = useRouter()
const claim = ref<PasswordResetClaimResponse | null>(null)
const newPassword = ref('')
const confirmPassword = ref('')
const showNewPassword = ref(false)
const showConfirmPassword = ref(false)
const isLoading = ref(true)
const isSubmitting = ref(false)
const errorMessage = ref('')
let redirectTimer: ReturnType<typeof window.setTimeout> | undefined

const chinesePasswordPattern = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/
const chinesePasswordGlobalPattern = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/g

function normalizePassword(value: string) {
  const normalized = value.replace(chinesePasswordGlobalPattern, '')
  if (normalized !== value) {
    errorMessage.value = '密码不能包含中文，请使用英文、数字或符号'
  }
  return normalized
}

const newPasswordModel = computed({
  get: () => newPassword.value,
  set: (value: string) => { newPassword.value = normalizePassword(value) },
})

const confirmPasswordModel = computed({
  get: () => confirmPassword.value,
  set: (value: string) => { confirmPassword.value = normalizePassword(value) },
})

const passwordStrength = computed(() => {
  if (!newPassword.value) return { label: '尚未输入', tone: 'text-slate-400' }
  if (newPassword.value.length < 6) return { label: '长度不足', tone: 'text-red-600' }
  if (newPassword.value.length >= 12) return { label: '强', tone: 'text-emerald-700' }
  return { label: '可用', tone: 'text-amber-700' }
})

const statusTitle = computed(() => ({
  none: '未找到原设备申请',
  pending: '申请等待管理员审核',
  approved: '申请已通过',
  completed: '密码已成功重置',
  rejected: '申请未通过',
  expired: '改密时限已过期',
  legacy_invalid: '旧版申请需重新提交',
}[claim.value?.status ?? 'none']))

async function loadClaim() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    claim.value = await authApi.getPasswordResetClaim()
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isLoading.value = false
  }
}

async function submitPasswordReset() {
  errorMessage.value = ''
  if (!claim.value?.can_complete) {
    errorMessage.value = '当前申请尚不能设置新密码，请刷新状态'
    return
  }
  if (!newPassword.value || !confirmPassword.value) {
    errorMessage.value = '请完整填写新密码和确认密码'
    return
  }
  if (chinesePasswordPattern.test(newPassword.value) || chinesePasswordPattern.test(confirmPassword.value)) {
    errorMessage.value = '密码不能包含中文，请使用英文、数字或符号'
    return
  }
  if (newPassword.value.length < 6) {
    errorMessage.value = '新密码至少需要 6 位'
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    errorMessage.value = '两次输入的新密码不一致'
    return
  }

  isSubmitting.value = true
  try {
    const response = await authApi.completePasswordResetClaim({
      new_password: newPassword.value,
      confirm_password: confirmPassword.value,
    })
    newPassword.value = ''
    confirmPassword.value = ''
    claim.value = {
      status: 'completed',
      request_id: claim.value.request_id,
      can_complete: false,
      expires_at: '',
      message: response.message,
    }
    redirectTimer = window.setTimeout(() => {
      void router.replace({ name: 'login' })
    }, 1200)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isSubmitting.value = false
  }
}

function returnToLogin() {
  void router.replace({ name: 'login' })
}

onMounted(() => { void loadClaim() })

onBeforeUnmount(() => {
  newPassword.value = ''
  confirmPassword.value = ''
  if (redirectTimer) window.clearTimeout(redirectTimer)
})
</script>

<template>
  <main class="relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-950 px-5 py-10 text-slate-950">
    <AuthAmbientGrid class="absolute inset-0 opacity-70" variant="login" />
    <div class="absolute inset-0 bg-[radial-gradient(circle_at_18%_18%,rgba(13,148,136,0.28),transparent_35%),radial-gradient(circle_at_84%_82%,rgba(16,185,129,0.16),transparent_34%)]" aria-hidden="true"></div>

    <section class="relative z-10 w-full max-w-[520px] overflow-hidden rounded-3xl border border-white/15 bg-white shadow-2xl shadow-black/35">
      <header class="border-b border-slate-100 bg-slate-50/80 px-7 py-6">
        <div class="flex items-start gap-4">
          <span class="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-teal-700 text-white shadow-lg shadow-teal-900/20">
            <ShieldCheck class="size-6" aria-hidden="true" />
          </span>
          <div>
            <p class="text-[11px] font-bold uppercase tracking-[0.18em] text-teal-700">Same-browser Password Reset Claim</p>
            <h1 class="mt-1 text-[22px] font-bold text-slate-950">设置新密码</h1>
            <p class="mt-1 text-[13px] leading-5 text-slate-500">系统仅通过当前浏览器中的 HttpOnly 领取凭证核验本次申请。</p>
          </div>
        </div>
      </header>

      <div v-if="isLoading" class="flex items-center justify-center gap-2 px-7 py-12 text-sm text-slate-500">
        <LoaderCircle class="size-4 animate-spin" aria-hidden="true" />
        正在读取申请状态...
      </div>

      <form v-else-if="claim?.can_complete" class="space-y-4 px-7 py-6" novalidate @submit.prevent="submitPasswordReset">
        <div class="rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-[12.5px] leading-5 text-emerald-900">
          <div class="flex gap-2">
            <CheckCircle2 class="mt-0.5 size-4 shrink-0 text-emerald-700" aria-hidden="true" />
            <span>
              管理员已完成审核。请在
              <b>{{ formatBusinessDateTime(claim.expires_at, { includeSeconds: true }) }}</b>
              前设置新密码。
            </span>
          </div>
        </div>

        <label class="block">
          <span class="mb-1.5 block text-[12.5px] font-semibold text-slate-700">新密码</span>
          <span class="flex h-11 items-center rounded-xl border border-slate-200 bg-slate-50 px-3 focus-within:border-teal-700 focus-within:bg-white focus-within:ring-[3px] focus-within:ring-teal-700/15">
            <KeyRound class="size-4 text-slate-400" aria-hidden="true" />
            <input v-model="newPasswordModel" class="ml-2.5 h-full min-w-0 flex-1 bg-transparent text-[14px] outline-none" autocomplete="new-password" :type="showNewPassword ? 'text' : 'password'">
            <button class="flex size-7 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100" type="button" :aria-label="showNewPassword ? '隐藏新密码' : '显示新密码'" @click="showNewPassword = !showNewPassword">
              <EyeOff v-if="showNewPassword" class="size-4" aria-hidden="true" />
              <Eye v-else class="size-4" aria-hidden="true" />
            </button>
          </span>
        </label>

        <label class="block">
          <span class="mb-1.5 block text-[12.5px] font-semibold text-slate-700">确认新密码</span>
          <span class="flex h-11 items-center rounded-xl border border-slate-200 bg-slate-50 px-3 focus-within:border-teal-700 focus-within:bg-white focus-within:ring-[3px] focus-within:ring-teal-700/15">
            <CheckCircle2 class="size-4 text-slate-400" aria-hidden="true" />
            <input v-model="confirmPasswordModel" class="ml-2.5 h-full min-w-0 flex-1 bg-transparent text-[14px] outline-none" autocomplete="new-password" :type="showConfirmPassword ? 'text' : 'password'">
            <button class="flex size-7 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100" type="button" :aria-label="showConfirmPassword ? '隐藏确认密码' : '显示确认密码'" @click="showConfirmPassword = !showConfirmPassword">
              <EyeOff v-if="showConfirmPassword" class="size-4" aria-hidden="true" />
              <Eye v-else class="size-4" aria-hidden="true" />
            </button>
          </span>
        </label>

        <div class="flex items-center justify-between text-[11.5px] leading-5 text-slate-500">
          <span>至少 6 位，不允许中文；最终规则以后端校验为准。</span>
          <span :class="passwordStrength.tone">强度：{{ passwordStrength.label }}</span>
        </div>

        <div v-if="errorMessage" class="flex items-center gap-2 rounded-xl border border-red-100 bg-red-50 px-3 py-2.5 text-[12.5px] font-medium text-red-700" role="alert">
          <CircleAlert class="size-4 shrink-0" aria-hidden="true" />
          <span>{{ errorMessage }}</span>
        </div>

        <button class="flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-teal-700 text-[14px] font-bold text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-300" type="submit" :disabled="isSubmitting">
          <LoaderCircle v-if="isSubmitting" class="size-4 animate-spin" aria-hidden="true" />
          <span>{{ isSubmitting ? '正在重置...' : '确认设置新密码' }}</span>
        </button>
      </form>

      <div v-else class="space-y-4 px-7 py-7 text-center">
        <span class="mx-auto flex size-14 items-center justify-center rounded-2xl" :class="claim?.status === 'completed' ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'">
          <CheckCircle2 v-if="claim?.status === 'completed'" class="size-7" aria-hidden="true" />
          <CircleAlert v-else class="size-7" aria-hidden="true" />
        </span>
        <div>
          <h2 class="text-lg font-bold text-slate-950">{{ statusTitle }}</h2>
          <p class="mt-2 text-[13px] leading-6 text-slate-500">{{ claim?.message || '无法读取申请状态，请稍后重试。' }}</p>
        </div>
        <div v-if="errorMessage" class="rounded-xl border border-red-100 bg-red-50 px-3 py-2.5 text-left text-[12.5px] font-medium text-red-700" role="alert">
          {{ errorMessage }}
        </div>
        <button v-if="claim?.status !== 'completed'" class="flex h-10 w-full items-center justify-center gap-2 rounded-xl border border-slate-200 text-sm font-semibold text-slate-700 hover:bg-slate-50" type="button" @click="loadClaim">
          <RefreshCw class="size-4" aria-hidden="true" />
          刷新状态
        </button>
        <button class="flex h-10 w-full items-center justify-center gap-2 rounded-xl bg-teal-700 text-sm font-semibold text-white hover:bg-teal-800" type="button" @click="returnToLogin">
          <ArrowLeft class="size-4" aria-hidden="true" />
          返回登录
        </button>
      </div>
    </section>
  </main>
</template>
