<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { ArrowLeft, KeyRound } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import IamLeaveGuard from '@/components/iam/workspace/IamLeaveGuard.vue'
import { systemApi, type PasswordResetReviewRequest } from '@/api/system'
import { iamWorkspaceApi, type WorkspacePasswordDetail } from '@/api/iamWorkspace'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { formatBusinessDateTime } from '@/lib/dateTime'
const props = defineProps<{ requestId: string; readonly?: boolean }>()
const emit = defineEmits<{ back: []; saved: []; locked: [boolean] }>()
const auth = useAuthStore(), row = ref<WorkspacePasswordDetail>(), verified = ref(false), reason = ref('')
const loading = ref(false), busy = ref(false), uncertain = ref(false), error = ref(''), notice = ref('')
const guard = ref<InstanceType<typeof IamLeaveGuard>>()
const viewer = computed(() => `${auth.currentUser?.id}:${auth.authorizationVersion}:${auth.currentUser?.identity?.employment_epoch}:${auth.currentUser?.identity?.effective_context_key}`)
const statusLabels: Record<string, string> = { pending: '待核验', approved: '已开放找回，待本人完成', completed: '本人已完成', expired: '找回窗口已过期', rejected: '已拒绝', legacy_invalid: '需要重新申请' }
const locked = computed(() => busy.value || uncertain.value)
let generation = 0, pendingStatus = '', pendingIssue = 0, pendingOwner = ''
let pending: { id: string; action: 'approve' | 'reject' | 'reissue'; body: PasswordResetReviewRequest } | undefined
const account = computed(() => `${auth.currentUser?.id}:${auth.currentUser?.identity?.employment_epoch}`)
async function read(check = false) {
  const current = ++generation, actor = viewer.value
  loading.value = true; error.value = ''; row.value = undefined
  try {
    const data = await iamWorkspaceApi.passwordReset(props.requestId)
    if (current !== generation || actor !== viewer.value) return
    row.value = data
    if (check && (data.status !== pendingStatus || data.issue_count !== pendingIssue)) { uncertain.value = false; pending = undefined; pendingOwner = ''; reason.value = ''; verified.value = false; notice.value = '已读取最新处理结果。'; emit('saved') }
    else if (check) notice.value = '暂未观察到状态变化。可继续核查，或使用原处理内容重试。'
  } catch (e) {
    if (current !== generation || actor !== viewer.value) return
    error.value = getApiErrorMessage(e)
  } finally { if (current === generation) loading.value = false }
}
async function submit(action: 'approve' | 'reject' | 'reissue', retry = false) {
  if (!row.value?.available_actions.includes(action) || busy.value || loading.value || props.readonly || !auth.can('system:user_manage')) return
  if (retry ? !uncertain.value || !pending || pendingOwner !== account.value || pending.id !== props.requestId : locked.value) return
  if (!retry && (!reason.value.trim() || reason.value.trim().length > 1000 || action !== 'reject' && !verified.value)) return
  const current = generation, actor = viewer.value
  if (!retry) {
    pendingStatus = row.value.status; pendingIssue = row.value.issue_count; pendingOwner = account.value
    pending = { id: props.requestId, action, body: { review_comment: reason.value.trim(), identity_verified: verified.value, expected_issue_count: pendingIssue } }
  }
  const intent = pending!
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const response = intent.action === 'reject' ? await systemApi.rejectPasswordResetRequest(intent.id, intent.body)
      : intent.action === 'reissue' ? (await systemApi.reissuePasswordResetRequest(intent.id, intent.body)).request
      : (await systemApi.approvePasswordResetRequest(intent.id, intent.body)).request
    if (current !== generation || actor !== viewer.value) return
    row.value = { ...response, available_actions: [] }; verified.value = false; reason.value = ''
    uncertain.value = false; pending = undefined; pendingOwner = ''
    notice.value = action === 'reject' ? '已拒绝这条找回申请。' : '找回窗口已开放，仍需申请人在原浏览器完成设置新密码。'
    emit('saved')
  } catch (e) {
    if (current !== generation || actor !== viewer.value) return
    const status = (e as { response?: { status?: number } }).response?.status
    if (!status || status === 408 || status >= 500) { uncertain.value = true; notice.value = '提交结果待确认。请读取此找回申请的当前状态。' }
    else { uncertain.value = false; pending = undefined; pendingOwner = ''; error.value = getApiErrorMessage(e); if (status === 403 || status === 401) row.value = undefined }
  } finally { if (current === generation) busy.value = false }
}
async function retrySubmission() {
  if (!uncertain.value || busy.value || loading.value || pendingOwner !== account.value || !pending) return
  await read(true)
  if (uncertain.value && pending) await submit(pending.action, true)
}
const permitLeave = () => locked.value ? false : guard.value?.permitLeave() ?? true
onBeforeRouteLeave(permitLeave); onBeforeRouteUpdate(permitLeave)
watch([() => props.requestId, viewer], (value, previous) => {
  const retain = previous?.[0] === value[0] && pendingOwner === account.value && locked.value
  ++generation; row.value = undefined; reason.value = ''; verified.value = false; busy.value = false; uncertain.value = retain
  notice.value = retain ? '访问权限已更新。原请求结果仍待核查，请勿重复提交。' : ''
  if (!retain) { pendingOwner = ''; pending = undefined }
  if (auth.can('system:user_manage')) void read()
}, { immediate: true, flush: 'sync' })
watch(locked, value => emit('locked', value), { flush: 'sync' })
onBeforeUnmount(() => { ++generation })
</script>
<template>
  <section class="iw-person-context" aria-label="密码找回办理区">
    <header class="iw-person-heading"><Button variant="ghost" class="iw-mobile-back" :disabled="locked" @click="emit('back')"><ArrowLeft :size="16" />返回列表</Button><KeyRound :size="22" /><div><h2>{{ row?.display_name || '密码找回' }}</h2><p>{{ row?.username }}</p></div></header>
    <div class="iw-detail-scroll"><p v-if="loading" role="status">正在读取找回申请…</p><p v-if="error" class="pw-error" role="alert">{{ error }}</p><p v-if="notice" class="pw-notice" role="status">{{ notice }}</p><Button v-if="uncertain" variant="outline" :disabled="loading || busy" @click="read(true)">核查找回申请结果</Button><Button v-if="uncertain" variant="outline" :disabled="loading || busy || readonly" @click="retrySubmission">使用原处理内容重试</Button>
      <template v-if="row"><h3>{{ statusLabels[row.status] || row.status }}</h3><dl class="iw-facts"><div><dt>申请时间</dt><dd>{{ formatBusinessDateTime(row.submitted_at || row.created_at) }}</dd></div><div><dt>联系方式</dt><dd>{{ row.contact || '未提供' }}</dd></div><div><dt>申请说明</dt><dd>{{ row.note || '未填写' }}</dd></div><div v-if="row.expires_at"><dt>窗口截止</dt><dd>{{ formatBusinessDateTime(row.expires_at) }}</dd></div><div v-if="row.review_comment"><dt>处理意见</dt><dd>{{ row.review_comment }}</dd></div></dl>
        <p class="iw-readonly-note">核验通过仅开放找回窗口。密码由申请人在原浏览器自行设置，管理员不会生成临时密码。</p>
        <template v-if="!readonly && row.available_actions.length > 0"><h3>核验申请人身份</h3><p>{{ row.matched_user ? `匹配账号：${row.matched_user.display_name} · ${row.matched_user.username}` : '未匹配到可办理的账号，不能开放找回。' }}</p><ul><li v-for="(matched, field) in row.match_checks" :key="field">{{ ({ display_name: '姓名', username: '账号', contact: '联系方式', phone: '手机号', email: '邮箱' } as Record<string,string>)[field] || field }}：{{ matched ? '一致' : '需核实' }}</li></ul><label class="pw-check"><input v-model="verified" type="checkbox" :disabled="locked">我已通过线下渠道核实申请人身份</label><label class="pw-field"><span>核验说明 / 拒绝原因</span><textarea v-model="reason" maxlength="1000" :disabled="locked" /></label></template>
      </template>
    </div>
    <footer class="iw-person-footer"><span>{{ row ? statusLabels[row.status] : '资料未就绪' }}</span><div v-if="row && !readonly" class="pw-inline"><Button v-if="row.available_actions.includes('reject')" variant="outline" :disabled="locked || !reason.trim()" @click="submit('reject')">拒绝申请</Button><Button v-if="row.available_actions.includes('approve') || row.available_actions.includes('reissue')" :disabled="locked || !verified || !reason.trim() || !row.matched_user || row.matched_user.status !== 'active'" @click="submit(row.can_reopen ? 'reissue' : 'approve')">{{ busy ? '正在办理…' : row.can_reopen ? '重新开放找回窗口' : '核验并开放找回窗口' }}</Button></div></footer>
    <IamLeaveGuard ref="guard" :dirty="!!reason.trim() || verified" :busy="locked" />
  </section>
</template>
