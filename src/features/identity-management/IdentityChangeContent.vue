<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { changeLabels, identityApi, type ChangeRecord, type OrganizationCatalog, type PersonIdentity } from '@/api/identity'
import { iamApi, type RoleSummary } from '@/api/iam'
import { useAuthStore } from '@/stores/auth'
import { factoryContexts } from '@/data/enterpriseMock'
import { formatBusinessDateTime } from '@/lib/dateTime'
import IamDisclosure from '@/components/iam/workspace/IamDisclosure.vue'
import { departmentName, permissionName } from './positionLabels'

const props = defineProps<{ record: ChangeRecord; catalog?: OrganizationCatalog }>()
const auth = useAuthStore()
const person = ref<PersonIdentity>()
const requester = ref<PersonIdentity>()
const localCatalog = ref<OrganizationCatalog>()
const roles = ref<RoleSummary[]>([])
const loading = ref(false)
const namesUnavailable = ref(false)
const payload = computed(() => props.record.payload)
const assignment = computed(() => payload.value.new_assignment)
const organizations = computed(() => (props.catalog || localCatalog.value)?.organizations || [])
const viewer = computed(() => `${auth.currentUser?.id}:${auth.authorizationVersion}:${auth.currentUser?.identity?.employment_epoch}:${auth.currentUser?.identity?.effective_context_key}`)
let generation = 0

// Name lookups use the existing scoped readers and never change the request.
watch(() => [props.record.id, props.record.revision, props.record.target_user_id, props.record.requester_user_id, viewer.value], async () => {
  const current = ++generation, record = props.record
  person.value = undefined; requester.value = undefined; localCatalog.value = undefined; roles.value = []
  namesUnavailable.value = false; loading.value = true
  if (!auth.currentUser || !auth.can('system:user_manage')) { loading.value = false; return }
  const result = await Promise.allSettled([
    identityApi.person(record.target_user_id),
    record.requester_user_id === auth.currentUser?.id || record.requester_user_id === record.target_user_id
      ? Promise.resolve(undefined) : identityApi.person(record.requester_user_id),
    props.catalog ? Promise.resolve(undefined) : identityApi.catalog(),
    record.payload.new_assignment?.role_bindings?.length && auth.can('system:permission_catalog_read')
      ? iamApi.listRoles() : Promise.resolve([]),
  ])
  if (current !== generation) return
  const [targetResult, requesterResult, catalogResult, rolesResult] = result
  if (targetResult.status === 'fulfilled') person.value = targetResult.value
  if (requesterResult.status === 'fulfilled') requester.value = requesterResult.value
  if (catalogResult.status === 'fulfilled') localCatalog.value = catalogResult.value
  if (rolesResult.status === 'fulfilled') roles.value = rolesResult.value
  namesUnavailable.value = result.some(r => r.status === 'rejected')
  loading.value = false
}, { immediate: true, flush: 'sync' })
onBeforeUnmount(() => { ++generation })

function personName(id: string) {
  if (id === auth.currentUser?.id) return auth.currentUser.display_name || auth.currentUser.username || '当前账号'
  const match = [person.value, requester.value].find(p => p?.id === id)
  return match?.display_name || (loading.value ? '正在读取姓名…' : '姓名暂不可读取')
}
function orgName(id: string) {
  if (!id) return '未登记'
  if (id === '*') return '全部厂区'
  return organizations.value.find(o => o.id === id || o.factory_id === id)?.name
    || factoryContexts.find(o => o.id === id)?.shortName || '组织名称待核实'
}
function deptName(code: string, org?: string) {
  const catalog = org ? organizations.value.filter(o => o.id === org) : organizations.value
  const name = catalog.flatMap(o => o.departments).find(d => d.code === code)?.name
    || departmentName(code)
  return name === code ? '部门名称待核实' : name
}
function roleName(id: string) {
  return roles.value.find(r => r.id === id)?.name
    || person.value?.role_bindings.find(r => r.role_id === id)?.role_name || '权限方案名称待核实'
}
function scopeName(scope: { kind: string; factory_ids: string[] }) {
  if (scope.kind === 'home') return '本次任职所在厂区'
  if (scope.kind === 'all_current') return '办理时的全部生产厂区（固定范围）'
  if (scope.kind === 'selected') return scope.factory_ids.length ? scope.factory_ids.map(orgName).join('、') : '未选择生产厂区'
  return '业务范围待核实'
}
function dateName(value: string) {
  return `${formatBusinessDateTime(value, { fallback: '时间待核实' })}（北京时间）`
}
const effectiveTime = computed(() => {
  const time = props.record.effective_at || payload.value.effective_at
  return time ? dateName(time) : ['draft', 'pending_approval'].includes(props.record.state)
    ? '办理通过后生效，未预约未来时间' : '生效时间未记录'
})
const assignmentType = computed(() => ({ regular: '长期任职', part_time: '兼任', temporary: '临时支援', acting: '临时代理' } as Record<string, string>)[assignment.value?.assignment_type || ''] || '任职类型待核实')
const sourceAssignment = computed(() => person.value?.assignments.find(a => a.id === payload.value.source_assignment_id))
const sources: Record<string, string> = { assignment: '归入本次主职', individual_exception: '保留为独立个人能力', external_collaboration: '保留为独立外部协作', system_administration: '保留为独立系统管理' }
function bindingName(id: string, index: number) {
  const binding = person.value?.role_bindings.find(b => b.id === id)
  return binding ? `${binding.role_name} · ${orgName(binding.factory_id)} · ${deptName(binding.department)}` : `历史授权第 ${index + 1} 项（名称待核实）`
}
function exceptionName(id: string, index: number) {
  const exception = person.value?.overrides.find(o => o.id === id)
  if (!exception) return `个人例外第 ${index + 1} 项（名称待核实）`
  const name = permissionName(exception.permission_code)
  return `${exception.effect === 'deny' ? '明确禁止' : '单独允许'}：${name === exception.permission_code ? '权限名称待核实' : name} · ${orgName(exception.factory_id)} · ${deptName(exception.department)}`
}
</script>

<template>
  <div class="iamx-change-content">
    <section class="iamx-change-section" aria-label="办理说明">
      <h3>办理说明</h3>
      <dl class="iamx-change-facts">
        <div><dt>办理人员</dt><dd>{{ personName(record.target_user_id) }}</dd></div>
        <div><dt>申请人</dt><dd>{{ personName(record.requester_user_id) }}</dd></div>
        <div><dt>办理事项</dt><dd>{{ changeLabels[record.request_type] }}</dd></div>
        <div><dt>申请原因</dt><dd>{{ record.reason || '未填写原因' }}</dd></div>
        <div><dt>生效时间</dt><dd>{{ effectiveTime }}</dd></div>
        <div v-if="record.created_at"><dt>申请时间</dt><dd>{{ dateName(record.created_at) }}</dd></div>
      </dl>
      <p v-if="namesUnavailable" class="iamx-muted" role="status">部分名称暂不可读取，请在人员详情中核对。</p>
    </section>
    <section v-if="payload.source_assignment_id" class="iamx-change-section" aria-label="涉及的原任职">
      <h3>涉及的原任职</h3>
      <p v-if="sourceAssignment">{{ sourceAssignment.org_name || orgName(sourceAssignment.org_unit_id) }} · {{ deptName(sourceAssignment.department_code, sourceAssignment.org_unit_id) }} · {{ sourceAssignment.official_position_title }}</p>
      <p v-else class="iamx-muted">原任职名称暂不可读取，请在人员详情中核对。</p>
    </section>
    <section v-if="assignment" class="iamx-change-section" aria-label="调整后的任职">
      <h3>调整后的任职</h3>
      <dl class="iamx-change-facts">
        <div><dt>任职组织</dt><dd>{{ orgName(assignment.org_unit_id) }}</dd></div>
        <div><dt>所属部门</dt><dd>{{ deptName(assignment.department_code, assignment.org_unit_id) }}</dd></div>
        <div><dt>正式岗位</dt><dd>{{ assignment.official_position_title || '未填写岗位' }}</dd></div>
        <div><dt>任职类型</dt><dd>{{ assignmentType }}</dd></div>
        <div><dt>是否主职</dt><dd>{{ assignment.is_primary ? '是，作为主要任职' : '否，作为其他任职' }}</dd></div>
        <div><dt>结束时间</dt><dd>{{ assignment.valid_until ? dateName(assignment.valid_until) : '未设置结束时间' }}</dd></div>
      </dl>
    </section>
    <section v-if="payload.display_name || payload.official_position_title" class="iamx-change-section" aria-label="更正后的资料">
      <h3>更正后的资料</h3>
      <dl class="iamx-change-facts">
        <div v-if="payload.display_name"><dt>姓名</dt><dd>{{ payload.display_name }}</dd></div>
        <div v-if="payload.official_position_title"><dt>正式岗位</dt><dd>{{ payload.official_position_title }}</dd></div>
      </dl>
    </section>
    <section v-if="assignment" class="iamx-change-section" aria-label="权限方案与业务范围">
      <h3>权限方案与业务范围</h3>
      <ul v-if="assignment.role_bindings?.length" class="iamx-change-packages">
        <li v-for="(binding, index) in assignment.role_bindings" :key="index">
          <strong>{{ roleName(binding.role_id) }}</strong>
          <dl class="iamx-change-facts">
            <div><dt>权限作用部门</dt><dd>{{ deptName(binding.department) }}</dd></div>
            <div><dt>业务范围</dt><dd>{{ scopeName(binding.factory_scope) }}</dd></div>
          </dl>
        </li>
      </ul>
      <p v-else class="iamx-muted">本次未单独选择权限方案。</p>
      <p class="iamx-muted">实际权限以“权限影响”中的核对结果为准。</p>
    </section>
    <IamDisclosure v-if="payload.binding_dispositions?.length || payload.exception_decisions?.length" title="历史授权与个人例外处理" default-open>
      <ul class="iamx-change-decisions">
        <li v-for="(binding, index) in payload.binding_dispositions" :key="binding.binding_id">
          <strong>{{ bindingName(binding.binding_id, index) }}</strong><span>{{ sources[binding.source] || '授权来源待核实' }}</span>
        </li>
        <li v-for="(decision, index) in payload.exception_decisions" :key="decision.override_id">
          <strong>{{ exceptionName(decision.override_id, index) }}</strong><span>{{ decision.decision === 'keep_original_scope' ? '按原范围保留' : decision.decision === 'end' ? '明确终止' : '处理方式待核实' }}</span>
        </li>
      </ul>
    </IamDisclosure>
  </div>
</template>

<style scoped>
.iamx-change-content { display: grid; gap: 16px; min-width: 0; }
.iamx-change-section { padding: 16px; border: 1px solid var(--iamx-stroke, #d9e5e9); border-radius: 10px; background: var(--iamx-surface, white); min-width: 0; }
.iamx-change-section h3 { margin: 0 0 12px; font-size: 15px; font-weight: 650; }
.iamx-change-facts { display: grid; gap: 9px; margin: 0; font-size: 13px; line-height: 1.6; }
.iamx-change-facts > div { display: grid; grid-template-columns: 96px minmax(0, 1fr); gap: 12px; }
.iamx-change-facts dt { color: var(--iamx-subtle, #526779); }
.iamx-change-facts dd { margin: 0; overflow-wrap: anywhere; white-space: pre-wrap; }
.iamx-change-section p { margin-top: 10px; font-size: 13px; overflow-wrap: anywhere; }
.iamx-change-packages, .iamx-change-decisions { display: grid; gap: 12px; padding: 0; margin: 0; list-style: none; }
.iamx-change-packages li { display: grid; gap: 8px; padding: 12px; background: var(--iamx-selected, #eef7f6); border-radius: 8px; }
.iamx-change-decisions li { display: grid; gap: 4px; font-size: 13px; overflow-wrap: anywhere; }
.iamx-change-decisions span { color: var(--iamx-subtle, #526779); }
@media (max-width: 600px) { .iamx-change-section { padding: 12px; } .iamx-change-facts > div { grid-template-columns: 82px minmax(0, 1fr); gap: 8px; } }
</style>
