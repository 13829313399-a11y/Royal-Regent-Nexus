<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { X, CircleAlert } from '@lucide/vue'
import { useRouter } from 'vue-router'
import { authApi, type PasswordResetClaimResponse } from '@/api/auth'
import { authProblem } from '@/lib/authProblem'
import { type FieldErrors } from '@/lib/authFormValidation'
import { formatBusinessDateTime } from '@/lib/dateTime'
import AuthField from './AuthField.vue'
const props = defineProps<{ open: boolean; username: string; claim: PasswordResetClaimResponse | null; refreshing: boolean; refreshError: string }>()
const emit = defineEmits<{ 'update:open': [boolean]; refresh: [] }>()
const router = useRouter()
const form = reactive({ username: '', display_name: '', contact: '', note: '' })
const errors = ref<FieldErrors>({}), message = ref(''), submitting = ref(false)
const submittedId = ref(''), previousClaimId = ref('')
const messageTone = ref<'success' | 'error'>('error'), waitingForSubmittedClaim = ref(false)
watch(() => props.claim, claim => {
  if (waitingForSubmittedClaim.value) {
    const confirmed = submittedId.value === 'submitted'
      ? Boolean(claim?.request_id && claim.request_id !== previousClaimId.value)
      : claim?.request_id === submittedId.value
    if (confirmed) { waitingForSubmittedClaim.value = false; submittedId.value = claim!.request_id }
  } else if (submittedId.value && claim && claim.request_id !== submittedId.value) {
    // After the receipt is confirmed, later cookie/account changes are authoritative.
    submittedId.value = ''; message.value = ''
  }
})
const displayedRequestId = computed(() => waitingForSubmittedClaim.value
  ? (submittedId.value === 'submitted' ? '' : submittedId.value)
  : props.claim?.request_id || (submittedId.value === 'submitted' ? '' : submittedId.value))
const showForm = computed(() => !waitingForSubmittedClaim.value && (!props.claim || ['none','rejected','expired','legacy_invalid'].includes(props.claim.status)))
let opener: HTMLElement | null = null, disposed = false
watch(() => props.open, value => { if (value) { opener = document.activeElement as HTMLElement; if (!form.username) form.username = props.username; emit('refresh') } })
function close() { emit('update:open', false) }
function closed(event: Event) { event.preventDefault(); if (opener?.isConnected) opener.focus() }
function initialFocus(event: Event) { event.preventDefault(); void nextTick(() => (document.querySelector<HTMLElement>('.ng-dialog input') ?? document.querySelector<HTMLElement>('.ng-dialog h2'))?.focus()) }
async function submit() {
  if (submitting.value) return
  errors.value = {}; message.value = ''; messageTone.value = 'error'
  for (const [field, label, max] of [['username','企业账号',64],['display_name','姓名',128],['contact','联系电话或邮箱',128],['note','说明',500]] as const) {
    if (!form[field].trim() && field !== 'note') errors.value[field] = `请填写${label}`
    else if (form[field].trim().length > max) errors.value[field] = `${label}不能超过 ${max} 个字符`
  }
  if (Object.keys(errors.value).length) { message.value = '请检查标出的信息'; await nextTick(); const first = Object.keys(errors.value)[0]; document.querySelector<HTMLElement>(`.ng-dialog [name="${first}"]`)?.focus(); return }
  submitting.value = true
  try {
    const response = await authApi.requestPasswordReset({ username: form.username.trim(), display_name: form.display_name.trim(), contact: form.contact.trim(), note: form.note.trim() })
    if (disposed) return
    previousClaimId.value = props.claim?.request_id ?? ''
    submittedId.value = response.request_id ?? 'submitted'; message.value = response.message
    messageTone.value = 'success'; waitingForSubmittedClaim.value = true; emit('refresh')
  } catch (error) { if (!disposed) { const problem = authProblem(error); message.value = problem.uncertain ? '申请结果暂未确认，请先刷新状态核对，勿连续重复提交。' : problem.message; errors.value = problem.fieldErrors } }
  finally { if (!disposed) submitting.value = false }
}
async function complete() { close(); await router.push({ name: 'reset-password' }) }
onBeforeUnmount(() => { disposed = true })
</script>
<template>
  <DialogRoot :open="open" @update:open="emit('update:open', $event)"><DialogPortal>
    <DialogOverlay class="rr-auth ng-overlay" />
    <DialogContent class="rr-auth ng-dialog" @close-auto-focus="closed" @escape-key-down="event => { if (event.isComposing) event.preventDefault() }" @open-auto-focus="initialFocus">
      <div class="ng-dialog-inner"><header class="ng-dialog-head"><div><DialogTitle tabindex="-1">找回密码</DialogTitle><DialogDescription>由管理员核验身份，在原浏览器完成密码重置。</DialogDescription></div><button class="ng-dialog-close" type="button" aria-label="关闭找回密码" @click="close"><X :size="18" /></button></header>
        <p v-if="refreshError" class="ng-alert" data-tone="error" role="status">{{ refreshError }}</p>
        <div v-if="message" class="ng-alert" :data-tone="messageTone" role="alert"><CircleAlert class="ng-icon" aria-hidden="true" />{{ message }}</div>
        <section v-if="claim && claim.status !== 'none' && !waitingForSubmittedClaim" class="auth-status"><strong>{{ claim.message }}</strong><p v-if="claim.expires_at" class="auth-hint">有效期至 {{ formatBusinessDateTime(claim.expires_at) }}<template v-if="claim.expires_in_seconds != null">（刷新时剩余 {{ Math.ceil(claim.expires_in_seconds / 60) }} 分钟）</template></p><button v-if="claim.can_complete" class="ng-primary" type="button" @click="complete">进入设置密码</button></section>
        <form v-if="showForm" novalidate :aria-busy="submitting" @submit.prevent="submit" @keydown.enter="event => { if (event.isComposing) event.preventDefault() }">
          <AuthField v-for="item in [{key:'username' as const,label:'企业账号'},{key:'display_name' as const,label:'姓名'},{key:'contact' as const,label:'联系电话或邮箱'},{key:'note' as const,label:'说明（选填）'}]" :key="item.key" :id="`recovery-${item.key}`" :label="item.label" :error="errors[item.key]" :required="item.key !== 'note'" v-slot="field"><div class="ng-control"><input :id="`recovery-${item.key}`" v-model="form[item.key]" :name="item.key" :placeholder="item.label" :autocomplete="item.key === 'username' ? 'username' : item.key === 'display_name' ? 'name' : item.key === 'contact' ? 'email' : 'off'" :aria-invalid="field.invalid" :aria-describedby="field.describedby" :disabled="submitting" @input="delete errors[item.key]" /></div></AuthField>
          <button class="ng-primary" type="submit" :disabled="submitting">{{ submitting ? '正在提交' : '提交密码重置申请' }}</button>
        </form>
        <button type="button" class="ng-text-link" :disabled="refreshing || submitting" @click="emit('refresh')">{{ refreshing ? '正在刷新状态' : '刷新申请状态' }}</button>
        <p v-if="displayedRequestId" class="auth-hint">申请编号：{{ displayedRequestId }}</p>
        <p class="ng-dialog-note">请保留当前浏览器。审核通过后有 4 小时设置密码；丢失浏览器凭证需重新申请。</p>
      </div>
    </DialogContent>
  </DialogPortal></DialogRoot>
</template>
