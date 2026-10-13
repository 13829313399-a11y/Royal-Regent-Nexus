<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Check, CircleAlert } from '@lucide/vue'
import { authApi } from '@/api/auth'
import AuthPasswordField from '@/components/auth/AuthPasswordField.vue'
import { usePasswordResetClaim } from '@/composables/usePasswordResetClaim'
import { authProblem } from '@/lib/authProblem'
import { newPasswordErrors, focusFirstError, type FieldErrors } from '@/lib/authFormValidation'
import { formatBusinessDateTime } from '@/lib/dateTime'
import { useAuthStore } from '@/stores/auth'
import { announceSessionBoundary } from '@/lib/authenticationGeneration'
const { claim, refreshing, refreshError, refresh } = usePasswordResetClaim()
const auth = useAuthStore()
const newPassword = ref(''), confirmPassword = ref(''), submitting = ref(false), completed = ref(false), message = ref(''), errors = ref<FieldErrors>({})
const title = computed(() => completed.value ? '密码已成功重置' : claim.value?.can_complete ? '设置新密码' : '密码恢复申请')
let disposed = false
async function submit() {
  if (submitting.value || !claim.value?.can_complete || completed.value) return
  errors.value = newPasswordErrors(newPassword.value, confirmPassword.value)
  message.value = ''
  if (Object.keys(errors.value).length) { message.value = '请检查标出的密码信息'; await nextTick(); focusFirstError(errors.value); return }
  submitting.value = true
  try {
    const result = await authApi.completePasswordResetClaim({ new_password: newPassword.value, confirm_password: confirmPassword.value })
    if (disposed) return
    newPassword.value = ''; confirmPassword.value = ''; completed.value = true; message.value = result.message
    auth.clearSession(); announceSessionBoundary()
    await nextTick(); document.querySelector<HTMLElement>('h1')?.focus()
  } catch (error) {
    if (disposed) return
    const problem = authProblem(error); message.value = problem.message; errors.value = problem.fieldErrors
    if (problem.code === 'AUTH_RESET_INVALIDATED') await refresh()
    await nextTick(); focusFirstError(errors.value)
  } finally { if (!disposed) submitting.value = false }
}
onBeforeUnmount(() => { disposed = true; newPassword.value = ''; confirmPassword.value = '' })
</script>
<template>
  <div class="ng-page-enter">
    <div v-if="completed" class="ng-success-icon"><Check class="ng-icon" aria-hidden="true" /></div>
    <header class="ng-form-header"><h1 tabindex="-1">{{ title }}</h1><p>{{ completed ? '所有旧会话已退出，请使用新密码登录。' : '在原浏览器完成密码重置，重新进入工作空间。' }}</p></header>
    <p v-if="refreshing && !claim" class="auth-status" role="status">正在确认申请状态</p>
    <p v-if="refreshError && !completed" class="ng-alert" data-tone="error" role="status">{{ refreshError }}</p>
    <div v-if="message" class="ng-alert" :data-tone="completed ? 'success' : 'error'" role="alert"><CircleAlert class="ng-icon" aria-hidden="true" />{{ message }}</div>
    <template v-if="!completed">
      <p v-if="claim" class="auth-status">{{ claim.message }}</p>
      <p v-if="claim?.expires_at" class="auth-hint">有效期至 {{ formatBusinessDateTime(claim.expires_at) }}<template v-if="claim.expires_in_seconds != null">（刷新时剩余 {{ Math.ceil(claim.expires_in_seconds / 60) }} 分钟）</template></p>
      <form v-if="claim?.can_complete" novalidate :aria-busy="submitting" @submit.prevent="submit" @keydown.enter="event => { if (event.isComposing) event.preventDefault() }">
        <AuthPasswordField id="reset-new-password" v-model="newPassword" name="new_password" label="新密码" hint="6–256 个字符，当前不支持中文。" :error="errors.new_password" :disabled="submitting" @update:model-value="delete errors.new_password" />
        <AuthPasswordField id="reset-confirm-password" v-model="confirmPassword" name="confirm_password" label="确认新密码" :error="errors.confirm_password" :disabled="submitting" @update:model-value="delete errors.confirm_password" />
        <button class="ng-primary" type="submit" :disabled="submitting">{{ submitting ? '正在设置密码' : '确认设置新密码' }}</button>
      </form>
      <button class="ng-text-link" type="button" :disabled="refreshing || submitting" @click="refresh">{{ refreshing ? '正在刷新' : '刷新申请状态' }}</button>
    </template>
    <RouterLink :class="completed ? 'ng-primary' : 'ng-text-link auth-restart'" :to="{ name: 'login', query: completed ? { logged_out: '1' } : {} }">返回登录</RouterLink>
  </div>
</template>
