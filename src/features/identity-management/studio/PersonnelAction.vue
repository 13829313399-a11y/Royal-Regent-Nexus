<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { ChangePayload, OrganizationCatalog, PersonIdentity } from '@/api/identity'
import type { PackageAddition, StudioDraft } from '@/api/accessStudio'
import { iamApi, type PermissionCatalogItem, type RoleSummary } from '@/api/iam'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { departmentName, permissionName } from '../positionLabels'

export type PersonnelActionKind =
  | 'add_assignment'
  | 'end_assignment'
  | 'freeze'
  | 'unfreeze'
  | 'leave'
  | 'rehire'
  | 'add_override'
  | 'end_override'
const props = defineProps<{
  kind: PersonnelActionKind
  sourceId?: string
  person: PersonIdentity
  catalog: OrganizationCatalog
  locked: boolean
  canReadRoles: boolean
}>()
const emit = defineEmits<{
  draft: [StudioDraft | ChangePayload | null]
  dirty: [boolean]
  cancel: []
}>()
const titles: Record<PersonnelActionKind, string> = {
  add_assignment: '新增兼任或临时支援',
  end_assignment: '结束所选兼任',
  add_override: '新增个人允许或明确禁止',
  end_override: '结束所选个人例外',
  freeze: '冻结账号',
  unfreeze: '恢复冻结账号',
  leave: '办理离职',
  rehire: '办理复职',
}
const notes: Partial<Record<PersonnelActionKind, string>> = {
  freeze: '冻结后停止访问，已登录会话失效。',
  unfreeze: '恢复后按当前有效来源重新判定权限。',
  leave: '离职将结束任职、撤销权限包与个人允许、失效登录会话，并进入新的雇佣周期。',
  rehire: '请核对复职后的主职。旧雇佣周期的权限包不会自动恢复。',
  end_assignment: '结束后，此兼任及其关联来源停止生效。其他任职继续按各自有效期执行。',
}
const org = ref(''),
  department = ref(''),
  title = ref(''),
  reason = ref(''),
  until = ref(''),
  type = ref('part_time')
const code = ref(''),
  effect = ref<'allow' | 'deny'>('allow'),
  permissions = ref<PermissionCatalogItem[]>([])
const loading = ref(false),
  error = ref(''),
  alive = ref(true)
const selected = computed(() => props.catalog.organizations.find((o) => o.id === org.value))
const posting = computed(() => props.kind === 'add_assignment' || props.kind === 'rehire')
const roles = ref<RoleSummary[]>([]),
  packages = ref<PackageAddition[]>([]),
  roleId = ref(''),
  roleDept = ref(''),
  roleFactories = ref<string[]>([])
const choosingRole = ref(false)
const roleDepts = computed(() =>
  Array.from(
    new Map(
      props.catalog.organizations.flatMap((o) => o.departments.map((d) => [d.code, d] as const)),
    ).values(),
  ),
)
async function chooseRole() {
  choosingRole.value = true
  loading.value = true
  error.value = ''
  try {
    const items = await iamApi.listRoles()
    if (alive.value) roles.value = items
  } catch (e) {
    if (alive.value) error.value = getApiErrorMessage(e)
  } finally {
    if (alive.value) loading.value = false
  }
}
function cancelRole() {
  choosingRole.value = false
  roleId.value = roleDept.value = ''
  roleFactories.value = []
}
function stageRole() {
  if (!roleId.value || !roleDept.value || !roleFactories.value.length) return
  packages.value.push({
    role_id: roleId.value,
    department: roleDept.value,
    factory_scope: { kind: 'selected', factory_ids: [...roleFactories.value] },
  })
  roleId.value = roleDept.value = ''
  roleFactories.value = []
  choosingRole.value = false
}
const secondary = computed(() =>
  props.person.active_assignments_summary.find((a) => !a.is_primary && a.id === props.sourceId),
)
const exception = computed(() =>
  props.person.overrides.find((o) => o.id === props.sourceId && o.state === 'active'),
)
const zoned = computed(() =>
  until.value ? until.value + (until.value.length === 16 ? ':00+08:00' : '+08:00') : undefined,
)
async function loadPermissions() {
  loading.value = true
  error.value = ''
  try {
    const result = await iamApi.listPermissions('active')
    if (alive.value) permissions.value = result
  } catch (e) {
    if (alive.value) error.value = getApiErrorMessage(e)
  } finally {
    if (alive.value) loading.value = false
  }
}
onMounted(() => {
  if (props.kind === 'add_override') void loadPermissions()
})
onBeforeUnmount(() => {
  alive.value = false
})
const draft = computed<StudioDraft | ChangePayload | null>(() => {
  if (!reason.value.trim() || choosingRole.value) return null
  const base = {
    reason: reason.value.trim(),
    base_identity_version: props.person.identity_version,
    base_authorization_version: props.person.authorization_version,
  }
  if (props.kind === 'add_override' || props.kind === 'end_override') {
    if (!props.person.primary_assignment || (props.kind === 'end_override' && !exception.value)) return null
    const change: StudioDraft = {
      ...base,
      source_assignment_id: props.person.primary_assignment.id,
      add_packages: [],
      remove_binding_ids: [],
      upgrade_binding_ids: [],
    }
    if (props.kind === 'add_override') {
      if (
        !org.value ||
        !department.value ||
        !code.value ||
        !permissions.value.some((p) => p.code === code.value)
      )
        return null
      change.add_overrides = [
        {
          permission_code: code.value,
          effect: effect.value,
          factory_id: org.value,
          department: department.value,
          valid_until: zoned.value,
        },
      ]
    } else change.end_override_ids = [exception.value!.id]
    return change
  }
  const change: ChangePayload = {
    ...base,
    target_user_id: props.person.id,
    request_type: props.kind,
    binding_dispositions: [],
    exception_decisions: [],
  }
  if (posting.value) {
    if (
      !org.value ||
      !department.value ||
      !title.value.trim() ||
      (['temporary', 'acting'].includes(type.value) && !until.value)
    )
      return null
    change.new_assignment = {
      org_unit_id: org.value,
      department_code: department.value,
      official_position_title: title.value.trim(),
      assignment_type: props.kind === 'rehire' ? 'regular' : type.value,
      is_primary: props.kind === 'rehire',
      valid_until: zoned.value,
      role_bindings: packages.value,
    }
  }
  if (props.kind === 'end_assignment') {
    if (!secondary.value) return null
    change.source_assignment_id = secondary.value.id
  }
  return change
})
watch(draft, (value) => emit('draft', value), {
  immediate: true,
  flush: 'sync',
})
watch([org, department, title, reason, until, code, effect, type, choosingRole], () => emit('dirty', true), {
  flush: 'sync',
})
</script>
<template>
  <fieldset class="personnel-block iam2-fields" :disabled="locked" aria-label="单项人员办理">
    <legend>{{ titles[kind] }}</legend>
    <p>
      办理对象 · {{ person.display_name }}<span v-if="person.username">（{{ person.username }}）</span>
    </p>
    <p v-if="notes[kind]">{{ notes[kind] }}</p>
    <details v-if="kind === 'leave' && person.handover">
      <summary>交接核查 · {{ person.handover.count }} 项待交接</summary>
      <ul>
        <li v-for="c in person.handover.coverage" :key="c.module">{{ c.module }} · {{ c.basis }}</li>
      </ul>
    </details>
    <p v-if="secondary">
      {{ secondary.official_position_title }} · {{ secondary.org_name }} ·
      {{ departmentName(secondary.department_code) }}
    </p>
    <p v-if="exception">
      {{ exception.effect === 'deny' ? '明确禁止' : '个人允许' }} ·
      {{ permissionName(exception.permission_code) }} · {{ exception.factory_id }} ·
      {{ departmentName(exception.department) }}
    </p>
    <template v-if="posting || kind === 'add_override'">
      <label
        >{{ posting ? '正式组织' : '业务厂区'
        }}<select v-model="org" @change="department = ''">
          <option value="">请选择</option>
          <option v-if="kind === 'add_override'" value="*">全部厂区（集团范围）</option>
          <option
            v-for="o in catalog.organizations.filter(
              (o) => o.status === 'active' && (posting ? o.kind !== 'group' : o.kind === 'factory'),
            )"
            :key="o.id"
            :value="o.id"
          >
            {{ o.name }}
          </option>
        </select></label
      >
      <label
        >{{ posting ? '正式部门' : '作用部门'
        }}<select v-model="department">
          <option value="">请选择</option>
          <option v-if="kind === 'add_override'" value="*">全部部门</option>
          <option v-for="d in org === '*' ? roleDepts : selected?.departments" :key="d.code" :value="d.code">
            {{ d.name }}
          </option>
        </select></label
      >
    </template>
    <template v-if="posting"
      ><label>职位名称<input v-model="title" maxlength="128" /></label>
      <label v-if="kind === 'add_assignment'"
        >任职类型<select v-model="type">
          <option value="part_time">兼任</option>
          <option value="temporary">临时支援</option>
          <option value="acting">代理</option>
        </select></label
      >
      <ul v-if="packages.length">
        <li v-for="(pkg, i) in packages" :key="i">
          {{ roles.find((r) => r.id === pkg.role_id)?.name }} · {{ departmentName(pkg.department) }} ·
          {{
            pkg.factory_scope.factory_ids
              .map((f) => catalog.organizations.find((o) => o.id === f)?.name || f)
              .join('、')
          }}
          <button type="button" @click="packages.splice(i, 1)">撤销新增</button>
        </li>
      </ul>
      <Button
        v-if="canReadRoles && !choosingRole"
        type="button"
        variant="outline"
        :disabled="packages.length >= 20"
        @click="chooseRole"
        >给本次任职添加权限包</Button
      >
      <fieldset v-if="choosingRole" class="iam2-fields">
        <legend>为新任职选包</legend>
        <p v-if="loading" role="status">正在读取方案…</p>
        <p v-else-if="error" role="alert">{{ error }} <button @click="chooseRole">重试</button></p>
        <label
          >权限包<select v-model="roleId">
            <option value="">请选择</option>
            <option v-for="r in roles" :key="r.id" :value="r.id">
              {{ r.name }}
            </option>
          </select></label
        >
        <label
          >作用部门<select v-model="roleDept">
            <option value="">请选择</option>
            <option v-for="d in roleDepts" :key="d.code" :value="d.code">
              {{ d.name }}
            </option>
          </select></label
        >
        <div class="iam2-factories">
          <label
            v-for="o in catalog.organizations.filter((o) => o.kind === 'factory' && o.status === 'active')"
            :key="o.id"
            ><input v-model="roleFactories" type="checkbox" :value="o.id" />{{ o.name }}</label
          >
        </div>
        <div>
          <Button
            type="button"
            size="sm"
            :disabled="!roleId || !roleDept || !roleFactories.length"
            @click="stageRole"
            >加入本次任职</Button
          >
          <Button
            type="button"
            variant="ghost"
            @click="cancelRole"
            >取消选包</Button
          >
        </div>
      </fieldset>
    </template>
    <template v-if="kind === 'add_override'">
      <label
        >例外类型<select v-model="effect">
          <option value="allow">个人允许</option>
          <option value="deny">明确禁止</option>
        </select></label
      >
      <label
        >具体能力<select v-model="code">
          <option value="">请选择</option>
          <option v-for="p in permissions" :key="p.code" :value="p.code">{{ p.name }} · {{ p.code }}</option>
        </select></label
      >
      <p v-if="loading" role="status">正在读取可见能力…</p>
      <p v-if="error" role="alert">
        {{ error }}
        <Button variant="outline" @click="loadPermissions">重试</Button>
      </p>
    </template>
    <label v-if="posting || kind === 'add_override'"
      >结束时间（北京时间）<input v-model="until" type="datetime-local"
    /></label>
    <label>办理原因<textarea v-model="reason" maxlength="2000" rows="2" /></label>
    <Button type="button" variant="outline" @click="emit('cancel')">取消本次办理</Button>
  </fieldset>
</template>
