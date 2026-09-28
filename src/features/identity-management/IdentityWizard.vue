<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { identityApi, changeLabels, type ChangeKind, type ChangePayload, type ChangeRecord, type ChangePreview, type PersonIdentity, type OrganizationCatalog } from '@/api/identity'
import { iamApi, type RoleSummary } from '@/api/iam'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
import Button from '@/components/ui/button/Button.vue'
import AccessImpact from './AccessImpact.vue'
const props = defineProps<{ person: PersonIdentity; catalog: OrganizationCatalog }>()
const emit = defineEmits<{ saved: []; dirty: [value: boolean] }>()
const kind = ref<ChangeKind>(props.person.identity_mode === 'legacy' ? 'confirm_identity' : 'primary_assignment_transfer')
const org = ref(props.person.primary_assignment?.org_unit_id || props.person.primary_factory_id)
const department = ref(props.person.primary_department)
const title = ref(props.person.position)
const name = ref(props.person.display_name)
const source = ref(props.person.primary_assignment?.id || '')
const reason = ref('')
const assignmentType = ref('regular')
const until = ref('')
const effectiveAt = ref('')
const roleId = ref('')
const roleDepartment = ref(props.person.primary_department)
const factories = ref<string[]>([])
const scopeKind = ref('home')
const roles = ref<RoleSummary[]>([])
const selectedRoles = ref<NonNullable<ChangePayload['new_assignment']>['role_bindings']>([])
const disposition = ref<Record<string, string>>({})
const exceptionDecisions = ref<Record<string, string>>({})
const busy = ref(false); const error = ref(''); const record = ref<ChangeRecord>(); const impact = ref<ChangePreview>()
const submitKey = ref(createRandomUuid())
const checked = ref(false)
const needsAssignment = computed(() => ['confirm_identity', 'primary_assignment_transfer', 'add_assignment', 'rehire'].includes(kind.value))
const confirmedLegacy = computed(() => Boolean(props.person.primary_factory_id && props.person.primary_department && props.person.confirmation_status === 'confirmed'))
const roleDepartments = computed(() => [...new Map(props.catalog.organizations.flatMap(o => o.departments).map(d => [d.code, d])).values()])
const currentOrg = computed(() => props.catalog.organizations.find(o => o.id === org.value))
const choices = computed(() => props.person.employment_status === 'left' ? ['rehire'] : props.person.identity_mode === 'legacy' ? ['confirm_identity', 'freeze', 'unfreeze', 'leave'] : Object.keys(changeLabels).filter(k => !['confirm_identity', 'rehire'].includes(k)))
void iamApi.listRoles().then(result => { roles.value = result.filter(r => r.id !== 'admin') }).catch(e => { error.value = getApiErrorMessage(e) })
watch([kind, org, department, title, name, source, reason, assignmentType, until, effectiveAt, selectedRoles, disposition, exceptionDecisions], () => { impact.value = undefined; checked.value = false; emit('dirty', true) }, { deep: true })
watch(kind, () => { record.value = undefined; assignmentType.value = kind.value === 'add_assignment' ? 'part_time' : 'regular' })
function addRole() {
  if (!roleId.value || !roleDepartment.value) return
  if (selectedRoles.value.some(r => r.role_id === roleId.value && r.department === roleDepartment.value)) { error.value = '此权限包和部门已添加，请移除后调整范围'; return }
  selectedRoles.value.push({ role_id: roleId.value, department: roleDepartment.value, factory_scope: { kind: scopeKind.value, factory_ids: [...factories.value] } })
}
async function makePreview() {
  busy.value = true; error.value = ''; impact.value = undefined
  try {
    const payload: ChangePayload = { request_type: kind.value, target_user_id: props.person.id, reason: reason.value || changeLabels[kind.value],
      base_identity_version: props.person.identity_version, base_authorization_version: props.person.authorization_version,
      binding_dispositions: kind.value === 'confirm_identity' ? props.person.role_bindings.filter(b => b.state === 'active').map(b => ({ binding_id: b.id, source: disposition.value[b.id] || '' })) : [],
      exception_decisions: props.person.overrides.filter(o => exceptionDecisions.value[o.id]).map(o => ({ override_id: o.id, decision: exceptionDecisions.value[o.id]! })) }
    if (['primary_assignment_transfer', 'end_assignment', 'upgrade_packages'].includes(kind.value)) payload.source_assignment_id = source.value
    if (kind.value === 'profile_correction') { payload.official_position_title = title.value; payload.display_name = name.value }
    if (needsAssignment.value) payload.new_assignment = { org_unit_id: org.value, department_code: department.value, official_position_title: title.value,
      assignment_type: assignmentType.value, is_primary: kind.value !== 'add_assignment', role_bindings: kind.value === 'confirm_identity' ? [] : selectedRoles.value,
      ...(until.value ? { valid_until: `${until.value.length === 16 ? until.value + ':00' : until.value}+08:00` } : {}) }
    if (effectiveAt.value && props.catalog.scheduling_enabled && ['primary_assignment_transfer', 'add_assignment', 'end_assignment'].includes(kind.value)) payload.effective_at = `${effectiveAt.value.length === 16 ? effectiveAt.value + ':00' : effectiveAt.value}+08:00`
    record.value = await identityApi.draft(payload, record.value)
    impact.value = await identityApi.preview(record.value.id)
    submitKey.value = createRandomUuid()
  } catch (e) { error.value = getApiErrorMessage(e) } finally { busy.value = false }
}
async function submit() {
  if (!record.value || !impact.value || !checked.value) return
  busy.value = true; error.value = ''
  try { await identityApi.commit(record.value, impact.value, submitKey.value); emit('dirty', false); emit('saved') }
  catch (e) { error.value = getApiErrorMessage(e) } finally { busy.value = false }
}
</script>
<template>
  <form class="iam-wizard" @submit.prevent="makePreview">
    <div v-if="error" role="alert" class="iam-error">{{ error }}<p>输入已保留。人员版本冲突时，请关闭办理并刷新人员资料，再核对后重新预览。</p></div>
    <label>办理事项<select v-model="kind" :disabled="busy"><option v-for="choice in choices" :key="choice" :value="choice">{{ changeLabels[choice as ChangeKind] }}</option></select></label>
    <label v-if="['primary_assignment_transfer', 'end_assignment', 'upgrade_packages'].includes(kind)">来源任职<select v-model="source"><option v-for="a in person.active_assignments_summary" :key="a.id" :value="a.id">{{ a.org_name }} · {{ a.official_position_title }}{{ a.is_primary ? '（主职）' : '（兼任）' }}</option></select></label>
    <div v-if="needsAssignment" class="iam-fields">
      <label>正式组织<select v-model="org" :disabled="kind === 'confirm_identity' && confirmedLegacy"><option v-for="o in catalog.organizations.filter(o => o.kind !== 'group' && o.status === 'active')" :key="o.id" :value="o.id">{{ o.name }}</option></select></label>
      <label>正式部门<select v-model="department" :disabled="kind === 'confirm_identity' && confirmedLegacy"><option v-for="d in currentOrg?.departments" :key="d.code" :value="d.code">{{ d.name }}</option></select></label>
      <label>正式职位<input v-model="title" required maxlength="128" :readonly="kind === 'confirm_identity' && confirmedLegacy" /></label>
      <label>任职类型<select v-model="assignmentType"><option value="regular">长期任职</option><option value="part_time">兼任</option><option value="temporary">临时支援</option><option value="acting">临时代理</option></select></label>
      <label v-if="kind !== 'confirm_identity'">结束时间（北京时间，可空）<input v-model="until" type="datetime-local" /></label>
    </div>
    <div v-if="kind === 'profile_correction'" class="iam-fields"><label>姓名<input v-model="name" required /></label><label>正式职位<input v-model="title" required /></label></div>
    <fieldset v-if="needsAssignment && kind !== 'confirm_identity'"><legend>权限包与业务范围</legend><p>正式部门和权限包作用部门分别确认。未选择权限包的任职不产生操作权限。</p>
      <div class="iam-fields"><label>权限包<select v-model="roleId"><option value="">请选择</option><option v-for="r in roles" :key="r.id" :value="r.id">{{ r.name }}</option></select></label><label>权限作用部门<select v-model="roleDepartment"><option v-for="d in roleDepartments" :key="d.code" :value="d.code">{{ d.name }}</option></select></label><label>业务范围<select v-model="scopeKind"><option value="home">本任职厂区</option><option value="selected">选择厂区</option><option value="all_current">当前全部厂区</option></select></label></div>
      <div v-if="scopeKind === 'selected'" class="iam-checks"><label v-for="o in catalog.organizations.filter(o => o.kind === 'factory')" :key="o.id"><input v-model="factories" type="checkbox" :value="o.id" />{{ o.name }}</label></div>
      <Button type="button" variant="outline" @click="addRole">添加权限包</Button><ul class="iam-package-list"><li v-for="(r, i) in selectedRoles" :key="i">{{ roles.find(role => role.id === r.role_id)?.name }} · {{ r.department }} · {{ r.factory_scope.kind === 'home' ? '本厂' : r.factory_scope.kind === 'all_current' ? '当前全部厂区' : r.factory_scope.factory_ids.join('、') }} <button type="button" @click="selectedRoles.splice(i, 1)">移除</button></li></ul>
    </fieldset>
    <fieldset v-if="kind === 'confirm_identity'"><legend>逐项核实历史授权来源</legend><p>确认会保留当前正式资料及原有权限范围。请选择每条授权的真实归属。</p><label v-for="b in person.role_bindings.filter(b => b.state === 'active')" :key="b.id">{{ b.role_name }} · {{ b.factory_id }} / {{ b.department }}<select v-model="disposition[b.id]" required><option value="">请核实来源</option><option value="assignment">属于本次主职</option><option value="individual_exception">独立个人能力</option><option value="external_collaboration">独立外部协作</option><option value="system_administration">独立系统管理</option></select></label></fieldset>
    <fieldset v-if="person.overrides.length && ['confirm_identity', 'primary_assignment_transfer'].includes(kind)"><legend>个人例外处理</legend><label v-for="o in person.overrides" :key="o.id">{{ o.effect === 'deny' ? '明确禁止' : '单独允许' }}：{{ o.permission_code }} · {{ o.factory_id }}<select v-model="exceptionDecisions[o.id]"><option value="">{{ o.effect === 'deny' ? '按原范围保留' : '请确认处理方式' }}</option><option value="keep_original_scope">按原范围保留</option><option value="end">明确终止</option></select></label></fieldset>
    <label v-if="catalog.scheduling_enabled && ['primary_assignment_transfer', 'add_assignment', 'end_assignment'].includes(kind)">预约生效时间（北京时间，留空立即）<input v-model="effectiveAt" type="datetime-local" /></label>
    <p v-else class="iam-muted">本次按立即办理；临时任职到期由服务器时间判断。</p>
    <label>办理原因<textarea v-model="reason" rows="2" maxlength="2000" :placeholder="changeLabels[kind]" /></label>
    <Button type="submit" variant="outline" :disabled="busy">{{ busy ? '正在核对…' : '保存草稿并预览影响' }}</Button>
    <AccessImpact v-if="impact" :preview="impact" />
    <template v-if="impact"><label class="iam-check"><input v-model="checked" type="checkbox" />我已核对组织、权限差异及交接范围</label><Button type="button" :disabled="busy || !checked" @click="submit">{{ busy ? '正在办理…' : impact.requires_approval ? '提交审核' : '确认办理' }}</Button></template>
  </form>
</template>
