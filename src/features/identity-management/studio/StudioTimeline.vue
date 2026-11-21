<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import { getAuditEvents, type AuditEventOut } from '@/api/iam-audit'
import { iamWorkspaceApi } from '@/api/iamWorkspace'
import { getApiErrorMessage } from '@/lib/http'
import { formatBusinessDateTime, parseBusinessTimestamp } from '@/lib/dateTime'
import { changeLabels } from '@/api/identity'
import AuditSnapshot from './AuditSnapshot.vue'
import { permissionName } from '../positionLabels'
import { taskLabels, taskStatusText, workspaceCapabilities, type WorkspaceTask } from '../workspace/contracts'
import './audit-timeline.css'

const props = defineProps<{ targetUserId?: string }>()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const caps = computed(() => workspaceCapabilities(permission => auth.can(permission)))
const options = computed(() => [
  { id: 'all', name: '全部记录' },
  ...(caps.value.people && caps.value.exceptions ? [{id: 'registration', name: '注册开通'}, {id: 'position', name: '岗位更新'}] : []),
  ...(caps.value.people ? [{id: 'password', name: '密码找回'}, {id: 'identity-change', name: '任职变更与复核'}] : []),
  ...(caps.value.audit ? [{id: 'access', name: '授权事件'}] : []),
])
const localType = ref('all')
const limit = ref(100)
const taskPage = ref(1)
const reload = ref(0)
const active = computed(() => props.targetUserId ? localType.value : String(route.query.type || 'all'))
const person = computed(() => props.targetUserId || String(route.query.person || ''))
const includesAudit = computed(() => caps.value.audit && ['all', 'access'].includes(active.value))
const viewer = computed(() => [auth.currentUser?.id, auth.authorizationVersion, auth.currentUser?.identity?.employment_epoch, auth.currentUser?.identity?.effective_context_key].join(':'))
function selectType(id: string) {
  if (props.targetUserId) localType.value = id
  else void router.replace({ query: { ...route.query, type: id } })
}
const tasks = ref<WorkspaceTask[]>([])
const events = ref<AuditEventOut[]>([])
const loading = ref(false)
const problems = ref<string[]>([])
const more = ref(false)
watch([active, person, viewer], () => { taskPage.value = 1 }, { flush: 'sync' })
watch([active, person, viewer, taskPage, limit, reload, caps], async (_, __, cleanup) => {
  let current = true
  cleanup(() => { current = false })
  const kind = active.value
  const target = person.value
  tasks.value = []
  events.value = []
  problems.value = []
  more.value = false
  loading.value = true
  if (!options.value.some(option => option.id === kind) || (!caps.value.audit && !caps.value.people)) {
    problems.value = ['当前账号无此来源的查看权限。']
    loading.value = false
    return
  }
  const jobs: Promise<void>[] = []
  if (caps.value.people && kind !== 'access') {
    jobs.push(iamWorkspaceApi.tasks({
      kind: kind === 'all' ? '' : kind === 'password' ? 'password-reset' : kind,
      sort: 'activity', state: '', target_user_id: target, page_size: 30, page: taskPage.value,
    }).then(result => {
      if (!current) return
      tasks.value = result.items
      more.value = result.visible_total == null ? result.items.length === 30 : result.visible_total > taskPage.value * 30
      for (const item of result.coverage) if (item.state === 'unavailable') problems.value.push(taskLabels[item.kind] + '暂不可用')
    }).catch(error => { if (current) problems.value.push('办理单暂不可用 · ' + getApiErrorMessage(error)) }))
  }
  if (includesAudit.value) {
    jobs.push(getAuditEvents({ actor_user_id: '', target_user_id: target, module_code: '', factory_id: '', department: '', from: '', to: '', limit: limit.value })
      .then(result => { if (current) events.value = result })
      .catch(error => { if (current) problems.value.push('授权事件暂不可用 · ' + getApiErrorMessage(error)) }))
  }
  await Promise.all(jobs)
  if (current) loading.value = false
}, { immediate: true })

const labels: Record<string, string> = {
  role_template_updated: '权限方案调整', permission_override_removed: '移除个人例外', permission_override_set: '设置个人例外',
  role_binding_add: '新增授权来源', role_binding_revoke: '撤销授权来源', identity_enrollment: '注册建立正式任职',
  access_request_approved: '授权申请获批', access_request_rejected: '授权申请驳回', access_request_submitted: '提交授权申请',
  system_position_assign: '分配旧权限职位', identity_cancelled: '撤回人员变更', identity_rejected: '驳回人员变更',
  ...Object.fromEntries(Object.entries(changeLabels).map(([key, name]) => ['identity_' + key, name])),
}
function fields(value: unknown): Record<string, unknown> | undefined {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : undefined
}
function codesOf(value: unknown): string[] | undefined {
  const codes = fields(value)?.permission_codes
  return Array.isArray(codes) && codes.every(code => typeof code === 'string') ? codes : undefined
}
function changedPermissions(event: AuditEventOut) {
  const before = codesOf(event.before_value)
  const after = codesOf(event.after_value)
  if (!before || !after) return []
  const left = new Set(before)
  const right = new Set(after)
  return [
    ...after.filter(code => !left.has(code)).map(code => ({code, added: true})),
    ...before.filter(code => !right.has(code)).map(code => ({code, added: false})),
  ]
}
function eventTarget(event: AuditEventOut) {
  if (event.target_user_name || event.target_user_id) return event.target_user_name || event.target_user_id
  if (!event.target_id) return ''
  const names: Record<string, string> = {role:'权限方案', role_binding:'绑定', permission_override:'个人例外', access_request:'授权申请', identity_change:'任职变更'}
  return [names[event.target_type || ''] || event.target_type, event.target_id].filter(Boolean).join(' · ')
}
const rows = computed(() => [
  ...tasks.value.map(task => ({
    key: task.key, kind: task.kind, category: taskLabels[task.kind], title: taskStatusText(task),
    target: task.subject.display_name || task.subject.username, actor: task.record_actor_id, date: task.record_completed_at || task.record_decision_at || task.created_at,
    before: task.record_before, after: task.record_after, hasDiff: Boolean(task.record_before || task.record_after),
    reason: task.record_reason, proposed: task.proposed_position, task, event: undefined, changed: [],
  })),
  ...events.value.map(event => ({
    key: 'audit:' + event.id, kind: 'access', category: '授权事件', title: labels[event.event_type] || event.event_type,
    target: eventTarget(event), actor: event.actor_name || event.actor_user_id, date: event.occurred_at || event.created_at,
    before: event.before_value, after: event.after_value,
    hasDiff: Boolean(Object.keys(fields(event.before_value) ?? {}).length || Object.keys(fields(event.after_value) ?? {}).length
      || (event.before_value != null && !fields(event.before_value)) || (event.after_value != null && !fields(event.after_value))),
    reason: event.reason, proposed: '', task: undefined, event, changed: changedPermissions(event),
  })),
].sort((a, b) => (parseBusinessTimestamp(b.date) ?? 0) - (parseBusinessTimestamp(a.date) ?? 0) || b.key.localeCompare(a.key)))
</script>
<template>
  <section class="iam-audit-stream" :class="{ 'iam-audit-embedded': targetUserId }" aria-label="审计时间线">
    <header class="iam-audit-heading">
      <div><component :is="targetUserId ? 'h3' : 'h1'">{{ targetUserId ? '档案与变更时间线' : '审计与操作记录' }}</component>
        <p>{{ targetUserId ? '此人员可见的办理与授权记录' : '按时间查看办理结果、操作人和权限变更。' }}</p>
      </div>
      <nav aria-label="筛选事件"><button v-for="option in options" :key="option.id" type="button" :aria-pressed="active === option.id" @click="selectType(option.id)">{{ option.name }}</button></nav>
    </header>
    <p v-if="loading" class="iam-audit-notice" role="status">正在读取记录…</p>
    <p v-for="message in problems" :key="message" class="iam-audit-notice" role="alert">{{ message }} <button type="button" @click="reload++">重试</button></p>
    <article v-for="row in rows" :key="row.key" class="iam-audit-record">
      <header>
        <div class="iam-audit-record-title"><span class="iam-audit-kind" :data-kind="row.kind">{{ row.category }}</span><strong>{{ row.title }}</strong><span v-if="row.target" class="iam-audit-subtle">对象：{{ row.target }}</span></div>
        <div class="iam-audit-meta"><time :datetime="row.date">{{ row.task ? (row.task.record_completed_at ? '完成' : row.task.record_decision_at ? '办理' : '申请') : '发生' }} · {{ formatBusinessDateTime(row.date) }}</time><span v-if="row.actor">经办：{{ row.actor }}</span></div>
      </header>
      <p v-if="row.task && (row.task.record_decision_at || row.task.record_completed_at)" class="iam-audit-context">
        申请 · {{ formatBusinessDateTime(row.task.created_at) }}
        <template v-if="row.task.record_completed_at && row.task.record_decision_at"> · 核验 {{ formatBusinessDateTime(row.task.record_decision_at) }}</template>
      </p>
      <p v-else-if="row.task?.state === 'closed'" class="iam-audit-context">办理时间未记录</p>
      <div v-if="row.hasDiff" class="iam-audit-diff">
        <div><small>{{ row.task ? '原岗位' : '变更前' }}</small><AuditSnapshot :value="row.before" /></div>
        <ArrowRight :size="16" aria-hidden="true" />
        <div><small>{{ row.task ? '确认岗位' : '变更后' }}</small><AuditSnapshot :value="row.after" /></div>
      </div>
      <p v-else-if="row.event || row.task?.state === 'closed'" class="iam-audit-context">未记录变更前后明细</p>
      <p v-if="row.proposed && !row.hasDiff" class="iam-audit-context">申报岗位 · {{ row.proposed }}</p>
      <div v-if="row.changed.length" class="iam-audit-chips"><span v-for="item in row.changed" :key="item.code" :class="item.added ? 'iam-audit-added' : 'iam-audit-removed'" :title="item.code">{{ item.added ? '+' : '−' }} {{ permissionName(item.code) }}</span></div>
      <p v-if="row.reason" class="iam-audit-context">事由 · {{ row.reason }}</p>
      <footer v-if="row.task"><span>办理单 <code>{{ row.task.source_id }}</code><template v-if="row.task.record_receipt_id"> · 回执 <code>{{ row.task.record_receipt_id }}</code></template></span><RouterLink :to="{path: '/system/iam/audit', query: {source: row.task.kind, task: row.task.key}}">查看原始办理单</RouterLink></footer>
      <footer v-if="row.event"><span>事件 <code>{{ row.event.id }}</code><template v-if="row.event.request_id"> · 授权申请 <code>{{ row.event.request_id }}</code></template></span>
        <details v-if="row.hasDiff"><summary>原始差异</summary><div><strong>变更前</strong><pre>{{ JSON.stringify(row.event.before_value, null, 2) }}</pre><strong>变更后</strong><pre>{{ JSON.stringify(row.event.after_value, null, 2) }}</pre></div></details>
      </footer>
    </article>
    <p v-if="!rows.length && !loading && !problems.length" class="iam-audit-notice">当前范围暂无可见记录。</p>
    <div v-if="includesAudit || more || taskPage > 1" class="iam-audit-controls">
      <label v-if="includesAudit">授权事件读取上限 <select v-model.number="limit"><option v-for="n in [100, 200, 500]" :key="n" :value="n">{{ n }} 条</option></select></label>
      <div v-if="more || taskPage > 1"><button :disabled="taskPage <= 1 || loading" @click="taskPage--">上一页办理单</button><span>办理单第 {{ taskPage }} 页</span><button :disabled="!more || loading" @click="taskPage++">下一页办理单</button></div>
    </div>
  </section>
</template>
