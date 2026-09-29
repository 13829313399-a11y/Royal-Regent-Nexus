<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { BriefcaseBusiness } from '@lucide/vue'
import {
  identityApi,
  changeLabels,
  type ChangeKind,
  type ChangePayload,
  type ChangeRecord,
  type ChangePreview,
  type PersonIdentity,
  type OrganizationCatalog,
} from '@/api/identity'
import { iamApi, type RoleSummary } from '@/api/iam'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
import Button from '@/components/ui/button/Button.vue'
import AccessImpact from './AccessImpact.vue'
const props = defineProps<{ person: PersonIdentity; catalog: OrganizationCatalog }>()
const emit = defineEmits<{
  saved: [row: ChangeRecord]
  dirty: [value: boolean]
  busy: [value: boolean]
  draft: [description: string]
}>()
const step = ref(1)
const stepHeading = ref<HTMLElement>()
const kind = ref<ChangeKind>(
  props.person.employment_status === 'left'
    ? 'rehire'
    : props.person.identity_mode === 'legacy'
      ? 'confirm_identity'
      : 'primary_assignment_transfer',
)
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
const busy = ref(false)
const error = ref('')
const record = ref<ChangeRecord>()
const impact = ref<ChangePreview>()
const checked = ref(false)
const uncertain = ref(false)
const savedNotice = ref('')
const submitKey = ref(createRandomUuid())
const clock = ref(Date.now())
let revision = 0
let previewRevision = -1
let alive = true
const timer = window.setInterval(() => {
  clock.value = Date.now()
}, 1000)
const expired = computed(() =>
  Boolean(impact.value && Date.parse(impact.value.expires_at) <= clock.value),
)
const needsAssignment = computed(() =>
  ['confirm_identity', 'primary_assignment_transfer', 'add_assignment', 'rehire'].includes(
    kind.value,
  ),
)
const confirmedLegacy = computed(() =>
  Boolean(
    props.person.primary_factory_id &&
    props.person.primary_department &&
    props.person.confirmation_status === 'confirmed',
  ),
)
const roleDepartments = computed(() => [
  ...new Map(
    props.catalog.organizations.flatMap((o) => o.departments).map((d) => [d.code, d]),
  ).values(),
])
const currentOrg = computed(() => props.catalog.organizations.find((o) => o.id === org.value))
watch(org, () => {
  if (!currentOrg.value?.departments.some((d) => d.code === department.value)) department.value = ''
})
const choices = computed(
  () =>
    (props.person.employment_status === 'left'
      ? ['rehire']
      : props.person.identity_mode === 'legacy'
        ? ['confirm_identity', 'freeze', 'unfreeze', 'leave']
        : Object.keys(changeLabels).filter(
            (k) => !['confirm_identity', 'rehire'].includes(k),
          )) as ChangeKind[],
)
void iamApi
  .listRoles()
  .then((result) => {
    if (alive) roles.value = result.filter((r) => r.id !== 'admin')
  })
  .catch((e) => {
    if (alive) error.value = getApiErrorMessage(e)
  })
watch(busy, (value) => emit('busy', value), { flush: 'sync' })
watch(
  [
    kind,
    org,
    department,
    title,
    name,
    source,
    reason,
    assignmentType,
    until,
    effectiveAt,
    selectedRoles,
    disposition,
    exceptionDecisions,
  ],
  () => {
    ++revision
    impact.value = undefined
    checked.value = false
    emit('dirty', true)
  },
  { deep: true, flush: 'sync' },
)
watch(kind, () => {
  if (record.value && record.value.request_type !== kind.value) {
    savedNotice.value = `原事项草稿 ${record.value.id} 已保留，可到变更办理继续处理。`
    record.value = undefined
  }
  assignmentType.value = kind.value === 'add_assignment' ? 'part_time' : 'regular'
})
function go(value: number) {
  if (busy.value || uncertain.value) return
  step.value = value
  void nextTick(() => stepHeading.value?.focus())
}
function addRole() {
  if (!roleId.value || !roleDepartment.value) return
  if (
    selectedRoles.value.some(
      (r) => r.role_id === roleId.value && r.department === roleDepartment.value,
    )
  ) {
    error.value = '此权限包和部门已添加，请移除后调整范围'
    return
  }
  selectedRoles.value.push({
    role_id: roleId.value,
    department: roleDepartment.value,
    factory_scope: { kind: scopeKind.value, factory_ids: [...factories.value] },
  })
}
const beijing = (value: string) => `${value.length === 16 ? value + ':00' : value}+08:00`
function payload(): ChangePayload {
  const value: ChangePayload = {
    request_type: kind.value,
    target_user_id: props.person.id,
    reason: reason.value || changeLabels[kind.value],
    base_identity_version: props.person.identity_version,
    base_authorization_version: props.person.authorization_version,
    binding_dispositions:
      kind.value === 'confirm_identity'
        ? props.person.role_bindings
            .filter((b) => b.state === 'active')
            .map((b) => ({ binding_id: b.id, source: disposition.value[b.id] || '' }))
        : [],
    exception_decisions: props.person.overrides
      .filter((o) => exceptionDecisions.value[o.id])
      .map((o) => ({ override_id: o.id, decision: exceptionDecisions.value[o.id]! })),
  }
  if (['primary_assignment_transfer', 'end_assignment', 'upgrade_packages'].includes(kind.value))
    value.source_assignment_id = source.value
  if (kind.value === 'profile_correction') {
    value.official_position_title = title.value
    value.display_name = name.value
  }
  if (needsAssignment.value)
    value.new_assignment = {
      org_unit_id: org.value,
      department_code: department.value,
      official_position_title: title.value,
      assignment_type: assignmentType.value,
      is_primary: kind.value !== 'add_assignment',
      role_bindings:
        kind.value === 'confirm_identity' ? [] : JSON.parse(JSON.stringify(selectedRoles.value)),
      ...(until.value ? { valid_until: beijing(until.value) } : {}),
    }
  if (
    effectiveAt.value &&
    props.catalog.scheduling_enabled &&
    ['primary_assignment_transfer', 'add_assignment', 'end_assignment'].includes(kind.value)
  )
    value.effective_at = beijing(effectiveAt.value)
  return value
}
async function makePreview() {
  if (busy.value || uncertain.value) return
  const version = revision
  const submitted = payload()
  busy.value = true
  error.value = ''
  impact.value = undefined
  checked.value = false
  try {
    const draft = await identityApi.draft(submitted, record.value)
    if (!alive) return
    record.value = draft
    savedNotice.value = `草稿已保存：${draft.id}。关闭后可在变更办理中查看。`
    emit('draft', savedNotice.value)
    if (version === revision) emit('dirty', false)
    const result = await identityApi.preview(draft.id)
    if (!alive || version !== revision || record.value.id !== draft.id) return
    impact.value = result
    previewRevision = version
    submitKey.value = createRandomUuid()
    step.value = 3
    void nextTick(() => stepHeading.value?.focus())
  } catch (e) {
    if (alive && version === revision) error.value = getApiErrorMessage(e)
  } finally {
    if (alive) busy.value = false
  }
}
function finish(row: ChangeRecord) {
  emit('dirty', false)
  uncertain.value = false
  emit('saved', row)
}
async function verifyResult() {
  if (!record.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    const previousRevision = record.value.revision
    const result = await identityApi.change(record.value.id)
    if (!alive) return
    record.value = result
    if (['applied', 'scheduled', 'pending_approval'].includes(result.state)) finish(result)
    else if (result.state === 'draft') {
      uncertain.value = false
      if (result.revision !== previousRevision) {
        impact.value = undefined
        checked.value = false
        step.value = 2
        error.value = '草稿版本已变化，请重新核对并预览。'
      } else error.value = '服务器仍为草稿。可使用同一办理凭据再次确认，或返回重新预览。'
    } else {
      uncertain.value = false
      impact.value = undefined
      error.value = `当前状态：${result.state}，请到变更办理查看。`
    }
  } catch (e) {
    if (alive) error.value = `结果仍待核查：${getApiErrorMessage(e)}`
  } finally {
    if (alive) busy.value = false
  }
}
async function submit() {
  if (
    busy.value ||
    uncertain.value ||
    !record.value ||
    !impact.value ||
    !checked.value ||
    expired.value ||
    previewRevision !== revision
  )
    return
  busy.value = true
  error.value = ''
  try {
    const row = await identityApi.commit(record.value, impact.value, submitKey.value)
    if (alive) finish(row)
  } catch (e) {
    if (!alive) return
    const status = (e as { response?: { status?: number } }).response?.status
    uncertain.value = !status || status >= 500
    error.value = uncertain.value
      ? '提交结果待核查。请先查询服务器结果，避免重复办理。'
      : getApiErrorMessage(e)
    if (!uncertain.value) {
      impact.value = undefined
      checked.value = false
      step.value = 2
    }
  } finally {
    if (alive) busy.value = false
  }
}
onBeforeUnmount(() => {
  alive = false
  window.clearInterval(timer)
  emit('busy', false)
})
</script>
<template>
  <div class="iamx-wizard">
    <nav class="iamx-stepper" aria-label="办理步骤">
      <button
        v-for="(label, index) in ['选择事项', '填写资料', '核对影响']"
        :key="label"
        :aria-current="step === index + 1 ? 'step' : undefined"
        :disabled="busy || uncertain || index + 1 > step"
        @click="go(index + 1)"
      >
        <span>{{ index + 1 }}</span
        >{{ label }}
      </button>
    </nav>
    <p v-if="error" role="alert" class="iamx-error">{{ error }}</p>
    <p v-if="savedNotice" role="status" class="iamx-notice">{{ savedNotice }}</p>
    <p v-if="uncertain" class="iamx-notice">
      页面关闭不会取消服务器办理。<Button variant="outline" :disabled="busy" @click="verifyResult"
        >核查提交结果</Button
      >
    </p>
    <Transition name="iamx-step" mode="out-in" @after-enter="stepHeading?.focus()"
      ><section :key="step">
        <h3 ref="stepHeading" tabindex="-1">
          {{ step === 1 ? '这次需要办理什么？' : step === 2 ? changeLabels[kind] : '确认此次变更' }}
        </h3>
        <template v-if="step === 1"
          ><p class="iamx-muted">为 {{ person.display_name }} 选择一项办理事项</p>
          <div class="iamx-task-choices">
            <button
              v-for="choice in choices"
              :key="choice"
              :aria-pressed="kind === choice"
              @click="kind = choice"
            >
              <BriefcaseBusiness :size="20" /><span
                >{{ changeLabels[choice]
                }}<small>{{
                  choice === 'confirm_identity'
                    ? '核实原有授权，建立正式任职'
                    : choice === 'primary_assignment_transfer'
                      ? '调整主职组织、部门和职位'
                      : choice === 'add_assignment'
                        ? '增加兼任或临时支援'
                        : '核对资料后预览实际影响'
                }}</small></span
              >
            </button>
          </div>
          <footer class="iamx-action-bar">
            <p>选择事项不会改变现有权限。</p>
            <Button @click="go(2)">下一步：填写资料</Button>
          </footer></template
        >
        <form v-else-if="step === 2" class="iam-wizard" @submit.prevent="makePreview">
          <fieldset :disabled="busy || uncertain" class="iamx-form">
            <label
              v-if="
                ['primary_assignment_transfer', 'end_assignment', 'upgrade_packages'].includes(kind)
              "
              >来源任职<select v-model="source">
                <option v-for="a in person.active_assignments_summary" :key="a.id" :value="a.id">
                  {{ a.org_name }} · {{ a.official_position_title
                  }}{{ a.is_primary ? '（主职）' : '（兼任）' }}
                </option>
              </select></label
            >
            <div v-if="needsAssignment" class="iam-fields">
              <label
                >正式组织<select
                  v-model="org"
                  :disabled="kind === 'confirm_identity' && confirmedLegacy"
                >
                  <option
                    v-for="o in catalog.organizations.filter(
                      (o) => o.kind !== 'group' && o.status === 'active',
                    )"
                    :key="o.id"
                    :value="o.id"
                  >
                    {{ o.name }}
                  </option>
                </select></label
              >
              <label
                >正式部门<select
                  v-model="department"
                  :disabled="kind === 'confirm_identity' && confirmedLegacy"
                >
                  <option v-for="d in currentOrg?.departments" :key="d.code" :value="d.code">
                    {{ d.name }}
                  </option>
                </select></label
              >
              <label
                >正式职位<input
                  v-model="title"
                  required
                  maxlength="128"
                  :readonly="kind === 'confirm_identity' && confirmedLegacy"
              /></label>
              <label
                >任职类型<select v-model="assignmentType">
                  <option value="regular">长期任职</option>
                  <option value="part_time">兼任</option>
                  <option value="temporary">临时支援</option>
                  <option value="acting">临时代理</option>
                </select></label
              >
              <label v-if="kind !== 'confirm_identity'"
                >结束时间（北京时间，可空）<input v-model="until" type="datetime-local"
              /></label>
            </div>
            <div v-if="kind === 'profile_correction'" class="iam-fields">
              <label>姓名<input v-model="name" required /></label
              ><label>正式职位<input v-model="title" required /></label>
            </div>
            <fieldset v-if="needsAssignment && kind !== 'confirm_identity'">
              <legend>权限包与业务范围</legend>
              <p>正式部门和权限包作用部门分别确认。未选择权限包的任职不产生操作权限。</p>
              <div class="iam-fields">
                <label
                  >权限包<select v-model="roleId">
                    <option value="">请选择</option>
                    <option v-for="r in roles" :key="r.id" :value="r.id">{{ r.name }}</option>
                  </select></label
                ><label
                  >权限作用部门<select v-model="roleDepartment">
                    <option v-for="d in roleDepartments" :key="d.code" :value="d.code">
                      {{ d.name }}
                    </option>
                  </select></label
                ><label
                  >业务范围<select v-model="scopeKind">
                    <option value="home">本任职厂区</option>
                    <option value="selected">选择厂区</option>
                    <option value="all_current">当前全部厂区</option>
                  </select></label
                >
              </div>
              <div v-if="scopeKind === 'selected'" class="iam-checks">
                <label
                  v-for="o in catalog.organizations.filter((o) => o.kind === 'factory')"
                  :key="o.id"
                  ><input v-model="factories" type="checkbox" :value="o.id" />{{ o.name }}</label
                >
              </div>
              <Button type="button" variant="outline" @click="addRole">添加权限包</Button>
              <ul class="iam-package-list">
                <li v-for="(r, i) in selectedRoles" :key="i">
                  {{ roles.find((role) => role.id === r.role_id)?.name }} · {{ r.department }} ·
                  {{
                    r.factory_scope.kind === 'home'
                      ? '本厂'
                      : r.factory_scope.kind === 'all_current'
                        ? '当前全部厂区'
                        : r.factory_scope.factory_ids.join('、')
                  }}
                  <button type="button" @click="selectedRoles.splice(i, 1)">移除</button>
                </li>
              </ul>
            </fieldset>
            <fieldset v-if="kind === 'confirm_identity'">
              <legend>逐项核实历史授权来源</legend>
              <p>确认会保留当前正式资料及原有权限范围。请选择每条授权的真实归属。</p>
              <label
                v-for="b in person.role_bindings.filter((b) => b.state === 'active')"
                :key="b.id"
                >{{ b.role_name }} · {{ b.factory_id }} / {{ b.department
                }}<select v-model="disposition[b.id]" required>
                  <option value="">请核实来源</option>
                  <option value="assignment">属于本次主职</option>
                  <option value="individual_exception">独立个人能力</option>
                  <option value="external_collaboration">独立外部协作</option>
                  <option value="system_administration">独立系统管理</option>
                </select></label
              >
            </fieldset>
            <fieldset
              v-if="
                person.overrides.length &&
                ['confirm_identity', 'primary_assignment_transfer'].includes(kind)
              "
            >
              <legend>个人例外处理</legend>
              <label v-for="o in person.overrides" :key="o.id"
                >{{ o.effect === 'deny' ? '明确禁止' : '单独允许' }}：{{ o.permission_code }} ·
                {{ o.factory_id
                }}<select v-model="exceptionDecisions[o.id]">
                  <option value="">
                    {{ o.effect === 'deny' ? '按原范围保留' : '请确认处理方式' }}
                  </option>
                  <option value="keep_original_scope">按原范围保留</option>
                  <option value="end">明确终止</option>
                </select></label
              >
            </fieldset>
            <label
              v-if="
                catalog.scheduling_enabled &&
                ['primary_assignment_transfer', 'add_assignment', 'end_assignment'].includes(kind)
              "
              >预约生效时间（北京时间，留空立即）<input v-model="effectiveAt" type="datetime-local"
            /></label>
            <p v-else class="iam-muted">本次按立即办理；临时任职到期由服务器时间判断。</p>
            <label
              >办理原因<textarea
                v-model="reason"
                rows="2"
                maxlength="2000"
                :placeholder="changeLabels[kind]"
              />
            </label>
          </fieldset>
          <footer class="iamx-action-bar">
            <Button type="button" variant="outline" :disabled="busy" @click="go(1)">上一步</Button
            ><Button type="submit" :disabled="busy || uncertain">{{
              busy ? '正在核对…' : '保存草稿并预览影响'
            }}</Button>
          </footer>
        </form>
        <template v-else
          ><AccessImpact v-if="impact" :preview="impact" />
          <p v-if="expired" role="alert" class="iamx-error">预览已过期，请返回资料页重新预览。</p>
          <label v-if="impact" class="iamx-actions"
            ><input
              v-model="checked"
              type="checkbox"
              :disabled="busy || uncertain || expired"
            />我已核对组织、权限差异及交接范围</label
          >
          <footer class="iamx-action-bar">
            <Button variant="outline" :disabled="busy || uncertain" @click="go(2)">返回修改</Button
            ><Button
              :disabled="busy || uncertain || !impact || !checked || expired"
              @click="submit"
              >{{
                busy ? '正在办理…' : impact?.requires_approval ? '提交审核' : '确认办理'
              }}</Button
            >
          </footer></template
        >
      </section></Transition
    >
  </div>
</template>
