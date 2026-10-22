<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ArrowRight, UserRound, CircleAlert, X } from '@lucide/vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import AuthField from '@/components/auth/AuthField.vue'
import AuthPasswordField from '@/components/auth/AuthPasswordField.vue'
import PasswordRecoveryDialog from '@/components/auth/PasswordRecoveryDialog.vue'
import CuttingAcceptanceNotice from '@/features/cutting-operations/CuttingAcceptanceNotice.vue'
import { readRecentAccount, saveRecentAccount, removeRecentAccount, takeRegistrationUsername } from '@/lib/authAccountPreference'
import { authProblem } from '@/lib/authProblem'
import { focusFirstError, passwordError, type FieldErrors } from '@/lib/authFormValidation'
import { resolvePostLoginRedirect } from '@/lib/postLoginRedirect'
import { useAuthStore } from '@/stores/auth'
import { useAuthDeadline } from '@/composables/useAuthDeadline'
import { usePasswordResetClaim } from '@/composables/usePasswordResetClaim'
const route = useRoute(), router = useRouter(), authStore = useAuthStore()
const recentAccount = ref(readRecentAccount())
const username = ref(takeRegistrationUsername() || recentAccount.value?.username || '')
const password = ref(''), rememberAccount = ref(Boolean(recentAccount.value))
const passwordInput = ref<InstanceType<typeof AuthPasswordField>>()
const isSubmitting = ref(false), errorMessage = ref(''), errors = ref<FieldErrors>({})
const navigationFailed = ref(false), recoveryOpen = ref(false)
const { remaining, setRetryAfter } = useAuthDeadline()
const { claim, refreshing, refreshError, refresh } = usePasswordResetClaim()
let disposed = false
function focusPasswordInput(event: KeyboardEvent) {
  if (event.isComposing || !username.value.trim()) return
  event.preventDefault()
  if (!isSubmitting.value) passwordInput.value?.focus()
}
function clearRecentAccount() { removeRecentAccount(); recentAccount.value = null; rememberAccount.value = false; username.value = '' }
function continueRecent() { username.value = recentAccount.value?.username ?? ''; passwordInput.value?.focus() }
async function navigate() {
  try {
    const target = resolvePostLoginRedirect(router, route.query.redirect)
    const failure = await router.replace(authStore.currentUser?.force_password_change ? { name: 'change-password', query: target === '/' ? {} : { redirect: target } } : target)
    if (failure) throw failure
    navigationFailed.value = false
  } catch { navigationFailed.value = true; errorMessage.value = '已登录，暂时无法打开工作页面。' }
}
async function submitLogin(event?: Event) {
  if ((event as KeyboardEvent | undefined)?.isComposing || isSubmitting.value || remaining.value > 0) return
  if (navigationFailed.value) { await navigate(); return }
  errors.value = {}; errorMessage.value = ''
  if (!username.value.trim()) errors.value.username = '请输入企业账号'
  const invalidPassword = passwordError(password.value, false)
  if (invalidPassword) errors.value.password = invalidPassword
  if (Object.keys(errors.value).length) { errorMessage.value = '请检查账号和密码'; await nextTick(); focusFirstError(errors.value); return }
  isSubmitting.value = true
  try {
    const user = await authStore.login({ username: username.value.trim(), password: password.value })
    if (disposed) return
    if (rememberAccount.value) saveRecentAccount(user)
    else removeRecentAccount()
    password.value = ''
    await navigate()
  } catch (error) {
    if (disposed) return
    const problem = authProblem(error)
    errorMessage.value = problem.message; errors.value = problem.fieldErrors
    if (problem.code === 'AUTH_LOGIN_THROTTLED' || problem.retryAfter > 0) setRetryAfter(problem.retryAfter)
    await nextTick(); focusFirstError(errors.value)
  } finally { if (!disposed) isSubmitting.value = false }
}
onMounted(() => { if (route.query.expired === '1') errorMessage.value = '登录状态已过期，请重新登录后继续。' })
onBeforeUnmount(() => { disposed = true; password.value = '' })
</script>
<template>
  <div class="ng-page-enter">
    <CuttingAcceptanceNotice />
    <header class="ng-form-header"><h1 tabindex="-1">欢迎回来</h1><p>使用企业账号，进入你的工作空间。</p></header>
    <p v-if="route.query.redirect" class="auth-hint">登录后继续刚才的操作</p>
    <div v-if="recentAccount" class="auth-recent"><button type="button" @click="continueRecent">继续使用上次账号<small>{{ recentAccount.displayName || recentAccount.username }} · {{ recentAccount.username }}</small></button><button class="ng-eye" type="button" aria-label="清除记住的账号" @click="clearRecentAccount"><X :size="16" /></button></div>
    <section v-if="claim && claim.status !== 'none'" class="ng-claim" aria-label="密码恢复申请状态"><div><strong>{{ claim.message }}</strong><button type="button" class="ng-text-link" @click="recoveryOpen = true">查看密码恢复申请 →</button></div></section>
    <form novalidate :aria-busy="isSubmitting" @submit.prevent="submitLogin" @keydown.enter="event => { if (event.isComposing) event.preventDefault() }">
      <div v-if="errorMessage" class="ng-alert" data-tone="error" role="alert"><CircleAlert class="ng-icon" aria-hidden="true" />{{ errorMessage }}</div>
      <AuthField id="login-username" label="企业账号 / 工号" :error="errors.username" required v-slot="field">
        <div class="ng-control"><UserRound class="ng-icon" aria-hidden="true" /><input id="login-username" v-model="username" name="username" autocomplete="username" autocapitalize="off" :spellcheck="false" placeholder="企业账号 / 工号" :aria-invalid="field.invalid" :aria-describedby="field.describedby" :disabled="isSubmitting" @input="delete errors.username" @keydown.enter="focusPasswordInput" /></div>
      </AuthField>
      <AuthPasswordField ref="passwordInput" id="login-password" v-model="password" name="password" label="登录密码" autocomplete="current-password" :error="errors.password" :disabled="isSubmitting" @update:model-value="delete errors.password" />
      <div class="ng-form-options"><label class="ng-checkbox"><input v-model="rememberAccount" type="checkbox" />记住账号</label><button class="ng-text-link" type="button" @click="recoveryOpen = true">忘记密码？</button></div>
      <button class="ng-primary" type="submit" :disabled="isSubmitting || remaining > 0"><span v-if="isSubmitting" class="ng-spinner" aria-hidden="true" />{{ isSubmitting ? '正在登录' : remaining > 0 ? `${remaining} 秒后可重试` : '进入工作空间' }}<ArrowRight v-if="!isSubmitting" class="ng-icon ng-arrow" aria-hidden="true" /></button>
      <p class="ng-login-note">仅记住账号，下次仍需输入密码。</p>
    </form>
    <p class="ng-login-signup">还没有企业账号？<RouterLink class="ng-text-link" :to="{ name: 'register', query: route.query.redirect ? { redirect: route.query.redirect } : {} }">申请开通账号</RouterLink></p>
    <PasswordRecoveryDialog v-model:open="recoveryOpen" :username="username" :claim="claim" :refreshing="refreshing" :refresh-error="refreshError" @refresh="refresh" />
  </div>
</template>
