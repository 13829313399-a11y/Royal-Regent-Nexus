<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CircleAlert } from '@lucide/vue'
import AuthPasswordField from '@/components/auth/AuthPasswordField.vue'
import { useAuthStore } from '@/stores/auth'
import { resolvePostLoginRedirect } from '@/lib/postLoginRedirect'
import { authProblem } from '@/lib/authProblem'
import { newPasswordErrors, passwordError, focusFirstError, type FieldErrors } from '@/lib/authFormValidation'
const authStore = useAuthStore(), route = useRoute(), router = useRouter()
const currentPassword = ref(''), newPassword = ref(''), confirmPassword = ref(''), submitting = ref(false), changed = ref(false), errorMessage = ref(''), errors = ref<FieldErrors>({})
let disposed = false
async function navigate() { try { const failure = await router.replace(resolvePostLoginRedirect(router, route.query.redirect)); if (failure) throw failure } catch { errorMessage.value = '密码已更新，暂时无法打开工作页面，请重试进入。' } }
async function submitPasswordChange() {
  if (submitting.value) return
  if (changed.value) { await navigate(); return }
  errors.value = newPasswordErrors(newPassword.value, confirmPassword.value)
  const currentError = passwordError(currentPassword.value, false)
  if (currentError) errors.value = { current_password: currentError, ...errors.value }
  if (newPassword.value && currentPassword.value === newPassword.value) errors.value.new_password = '新密码不能与当前密码相同'
  errorMessage.value = ''
  if (Object.keys(errors.value).length) { errorMessage.value = '请检查标出的密码信息'; await nextTick(); focusFirstError(errors.value); return }
  submitting.value = true
  try {
    await authStore.changePassword({ current_password: currentPassword.value, new_password: newPassword.value, confirm_password: confirmPassword.value })
    if (disposed) return
    currentPassword.value = ''; newPassword.value = ''; confirmPassword.value = ''; changed.value = true
    await navigate()
  } catch (error) { if (!disposed) { const problem = authProblem(error); errorMessage.value = problem.message; errors.value = problem.fieldErrors; await nextTick(); focusFirstError(errors.value) } }
  finally { if (!disposed) submitting.value = false }
}
onBeforeUnmount(() => { disposed = true; currentPassword.value = ''; newPassword.value = ''; confirmPassword.value = '' })
</script>
<template>
  <div class="ng-page-enter"><header class="ng-form-header"><h1 tabindex="-1">设置正式密码</h1><p>请先更新密码，再进入你的工作空间。</p></header>
    <div v-if="errorMessage" class="ng-alert" data-tone="error" role="alert"><CircleAlert class="ng-icon" aria-hidden="true" />{{ errorMessage }}</div>
    <form novalidate :aria-busy="submitting" @submit.prevent="submitPasswordChange" @keydown.enter="event => { if (event.isComposing) event.preventDefault() }">
      <template v-if="!changed">
        <AuthPasswordField id="change-current-password" v-model="currentPassword" name="current_password" label="当前密码" autocomplete="current-password" :error="errors.current_password" :disabled="submitting" @update:model-value="delete errors.current_password" />
        <AuthPasswordField id="change-new-password" v-model="newPassword" name="new_password" label="新密码" hint="6–256 个字符，当前不支持中文。" :error="errors.new_password" :disabled="submitting" @update:model-value="delete errors.new_password" />
        <AuthPasswordField id="change-confirm-password" v-model="confirmPassword" name="confirm_password" label="确认新密码" :error="errors.confirm_password" :disabled="submitting" @update:model-value="delete errors.confirm_password" />
      </template>
      <button class="ng-primary" type="submit" :disabled="submitting">{{ submitting ? '正在更新密码' : changed ? '进入工作空间' : '更新密码并继续' }}</button>
      <p class="ng-form-note">更新后旧会话及旧恢复申请会失效，本浏览器使用新会话继续工作。</p>
    </form>
  </div>
</template>
