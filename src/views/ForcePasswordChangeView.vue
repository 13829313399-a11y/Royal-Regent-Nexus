<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import {
  ArrowRight,
  CheckCircle2,
  CircleAlert,
  Eye,
  EyeOff,
  KeyRound,
  LoaderCircle,
  LockKeyhole,
  ShieldCheck,
} from '@lucide/vue'
import { useRoute, useRouter } from 'vue-router'
import AuthAmbientGrid from '@/components/auth/AuthAmbientGrid.vue'
import { getApiErrorMessage } from '@/lib/http'
import { resolvePostLoginRedirect } from '@/lib/postLoginRedirect'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const showCurrentPassword = ref(false)
const showNewPassword = ref(false)
const showConfirmPassword = ref(false)
const isSubmitting = ref(false)
const errorMessage = ref('')

const chinesePasswordPattern = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/

async function submitPasswordChange() {
  errorMessage.value = ''
  if (!currentPassword.value || !newPassword.value || !confirmPassword.value) {
    errorMessage.value = '请完整填写当前密码、新密码和确认密码'
    return
  }
  if (
    chinesePasswordPattern.test(currentPassword.value)
    || chinesePasswordPattern.test(newPassword.value)
    || chinesePasswordPattern.test(confirmPassword.value)
  ) {
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
  if (newPassword.value === currentPassword.value) {
    errorMessage.value = '新密码不能与当前密码相同'
    return
  }

  isSubmitting.value = true
  try {
    await authStore.changePassword({
      current_password: currentPassword.value,
      new_password: newPassword.value,
      confirm_password: confirmPassword.value,
    })
    currentPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
    await router.replace(resolvePostLoginRedirect(router, route.query.redirect))
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isSubmitting.value = false
  }
}

onBeforeUnmount(() => {
  currentPassword.value = ''
  newPassword.value = ''
  confirmPassword.value = ''
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
            <p class="text-[11px] font-bold uppercase tracking-[0.18em] text-teal-700">Royal Regent Nexus</p>
            <h1 class="mt-1 text-[22px] font-bold text-slate-950">设置正式密码</h1>
            <p class="mt-1 text-[13px] leading-5 text-slate-500">当前账号需要先更新密码。完成修改前，系统业务功能保持锁定。</p>
          </div>
        </div>
      </header>

      <form class="space-y-4 px-7 py-6" novalidate @submit.prevent="submitPasswordChange">
        <div class="rounded-xl border border-amber-100 bg-amber-50 px-4 py-3 text-[12.5px] leading-5 text-amber-900">
          <div class="flex gap-2">
            <KeyRound class="mt-0.5 size-4 shrink-0 text-amber-700" aria-hidden="true" />
            <span>请重新输入当前密码，再设置仅由你本人掌握的正式密码。</span>
          </div>
        </div>

        <label class="block">
          <span class="mb-1.5 block text-[12.5px] font-semibold text-slate-700">当前密码</span>
          <span class="flex h-11 items-center rounded-xl border border-slate-200 bg-slate-50 px-3 focus-within:border-teal-700 focus-within:bg-white focus-within:ring-[3px] focus-within:ring-teal-700/15">
            <LockKeyhole class="size-4 text-slate-400" aria-hidden="true" />
            <input v-model="currentPassword" class="ml-2.5 h-full min-w-0 flex-1 bg-transparent text-[14px] outline-none" autocomplete="current-password" :type="showCurrentPassword ? 'text' : 'password'">
            <button class="flex size-7 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100" type="button" :aria-label="showCurrentPassword ? '隐藏当前密码' : '显示当前密码'" @click="showCurrentPassword = !showCurrentPassword">
              <EyeOff v-if="showCurrentPassword" class="size-4" aria-hidden="true" />
              <Eye v-else class="size-4" aria-hidden="true" />
            </button>
          </span>
        </label>

        <label class="block">
          <span class="mb-1.5 block text-[12.5px] font-semibold text-slate-700">新密码</span>
          <span class="flex h-11 items-center rounded-xl border border-slate-200 bg-slate-50 px-3 focus-within:border-teal-700 focus-within:bg-white focus-within:ring-[3px] focus-within:ring-teal-700/15">
            <KeyRound class="size-4 text-slate-400" aria-hidden="true" />
            <input v-model="newPassword" class="ml-2.5 h-full min-w-0 flex-1 bg-transparent text-[14px] outline-none" autocomplete="new-password" :type="showNewPassword ? 'text' : 'password'">
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
            <input v-model="confirmPassword" class="ml-2.5 h-full min-w-0 flex-1 bg-transparent text-[14px] outline-none" autocomplete="new-password" :type="showConfirmPassword ? 'text' : 'password'">
            <button class="flex size-7 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100" type="button" :aria-label="showConfirmPassword ? '隐藏确认密码' : '显示确认密码'" @click="showConfirmPassword = !showConfirmPassword">
              <EyeOff v-if="showConfirmPassword" class="size-4" aria-hidden="true" />
              <Eye v-else class="size-4" aria-hidden="true" />
            </button>
          </span>
        </label>

        <p class="text-[11.5px] leading-5 text-slate-500">至少 6 位，不允许中文；新密码必须与当前密码不同。最终规则以后端校验为准。</p>

        <div v-if="errorMessage" class="flex items-center gap-2 rounded-xl border border-red-100 bg-red-50 px-3 py-2.5 text-[12.5px] font-medium text-red-700">
          <CircleAlert class="size-4 shrink-0" aria-hidden="true" />
          <span>{{ errorMessage }}</span>
        </div>

        <button class="flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-teal-700 text-[14px] font-bold text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-300" type="submit" :disabled="isSubmitting">
          <LoaderCircle v-if="isSubmitting" class="size-4 animate-spin" aria-hidden="true" />
          <span>{{ isSubmitting ? '正在设置...' : '设置正式密码并进入系统' }}</span>
          <ArrowRight v-if="!isSubmitting" class="size-4" aria-hidden="true" />
        </button>
      </form>
    </section>
  </main>
</template>
