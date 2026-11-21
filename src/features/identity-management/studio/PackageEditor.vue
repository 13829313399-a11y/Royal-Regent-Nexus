<script setup lang="ts">
import { computed, inject, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { routeLocationKey } from 'vue-router'
import { Button } from '@/components/ui/button'
import { iamApi, type RoleSummary } from '@/api/iam'
import { Check, Layers3, Plus } from '@lucide/vue'
import type { PersonIdentity, OrganizationCatalog } from '@/api/identity'
import {
  accessStudioApi,
  type PackageAddition,
  type StudioDraft,
  type StudioPackage,
} from '@/api/accessStudio'
import type { WorkItemDetail, BuiltinPackage } from '@/api/positionReviews'
import { getApiErrorMessage } from '@/lib/http'
import { departmentName, requestedPackageLabel } from '../positionLabels'
import { formatBusinessDateTime } from '@/lib/dateTime'

const props = defineProps<{
  person: PersonIdentity
  catalog: OrganizationCatalog
  packages: StudioPackage[]
  canEdit: boolean
  canReadRoles: boolean
  locked: boolean
  startEditing?: boolean
  review?: WorkItemDetail
  referencePackages?: BuiltinPackage[]
}>()
const emit = defineEmits<{
  draft: [StudioDraft | null]
  dirty: [boolean]
  editing: [boolean]
}>()
const assignmentId = ref(props.person.primary_assignment?.id || '')
const assignments = computed(() => props.person.active_assignments_summary || [])
const assignment = computed(() => assignments.value.find((a) => a.id === assignmentId.value))
const title = ref(props.review?.declaration.position || assignment.value?.official_position_title || '')
const officialOrg = ref(props.review?.declaration.org_unit_id || assignment.value?.org_unit_id || '')
const officialDept = ref(props.review?.declaration.department_code || assignment.value?.department_code || '')
const postingChanged = computed(
  () =>
    !props.review &&
    assignment.value?.is_primary &&
    (officialOrg.value !== assignment.value.org_unit_id ||
      officialDept.value !== assignment.value.department_code),
)
const scopeEdits = ref<Record<string, string[]>>({})
const selection = ref<Record<string, string[]>>({})
const route = inject(routeLocationKey, null)
const surface = ref<HTMLElement>()
watch(
  [() => route?.query.binding, () => props.packages, surface],
  async ([id]) => {
    if (typeof id !== 'string' || !id) return
    await nextTick()
    const node = Array.from(surface.value?.querySelectorAll<HTMLElement>('[data-binding-id]') || []).find(
      (el) => el.dataset.bindingId === id,
    )
    node?.focus({ preventScroll: true })
    node?.scrollIntoView?.({ block: 'nearest' })
  },
  { immediate: true, flush: 'post' },
)
const officialDepartments = computed(
  () => props.catalog.organizations.find((o) => o.id === officialOrg.value)?.departments || [],
)
const requestedRoles = computed(() => props.review?.declaration.requested_role_ids || [])
const requestedFactories = computed(() => props.review?.declaration.requested_factory_ids || [])
const proposedProfileChanged = computed(
  () =>
    !!props.review &&
    (title.value !== props.review.declaration.position ||
      officialOrg.value !== props.review.declaration.org_unit_id ||
      officialDept.value !== props.review.declaration.department_code),
)
const reason = ref(''),
  removing = ref<string[]>([]),
  upgrading = ref<string[]>([]),
  adding = ref<PackageAddition[]>([])
const editing = ref(!!props.startEditing && props.canEdit),
  choosing = ref(false),
  roleId = ref(''),
  department = ref(''),
  factories = ref<string[]>([])
const choices = ref<RoleSummary[]>([]),
  search = ref(''),
  roleError = ref(''),
  loadingRoles = ref(false)
const abilities = ref<Record<string, { code: string; name: string }[]>>({})
const abilityError = ref('')
const groups = computed(() => {
  const result = new Map<string, RoleSummary[]>()
  const query = search.value.trim().toLocaleLowerCase()
  for (const role of choices.value) {
    const label =
      role.position_department_name ||
      (role.position_department ? departmentName(role.position_department) : '通用方案')
    if (
      ![
        role.name,
        role.code,
        role.description,
        label,
        ...(abilities.value[role.id] || []).flatMap((p) => [p.name, p.code]),
      ].some((text) => text?.toLocaleLowerCase().includes(query))
    )
      continue
    const items = result.get(label)
    if (items) items.push(role)
    else result.set(label, [role])
  }
  return result
})
const sourceLabels: Record<string, string> = {
  assignment: '任职授权',
  individual_exception: '独立个人授权',
  external_collaboration: '外部协作',
  system_administration: '独立系统管理',
  legacy_import: '历史来源',
  independent: '独立授权',
}
watch(editing, (value) => emit('editing', value), { immediate: true })
const factoryOrgs = computed(() =>
  props.catalog.organizations.filter((o) => o.status === 'active' && o.kind === 'factory'),
)
const departments = computed(() =>
  Array.from(
    new Map(props.catalog.organizations.flatMap((o) => o.departments).map((d) => [d.code, d])).values(),
  ),
)
const orgName = (id: string) => props.catalog.organizations.find((o) => o.id === id)?.name || id
const titleChanged = computed(() => title.value.trim() !== (assignment.value?.official_position_title || ''))
const changed = computed(
  () =>
    titleChanged.value ||
    postingChanged.value ||
    !!(
      Object.keys(scopeEdits.value).length ||
      removing.value.length ||
      upgrading.value.length ||
      adding.value.length
    ),
)
const draft = computed<StudioDraft | null>(() => {
  if (
    !props.canEdit ||
    !editing.value ||
    choosing.value ||
    Object.keys(selection.value).length > 0 ||
    (!props.review && !changed.value) ||
    ((props.review || postingChanged.value) &&
      (!officialOrg.value || !officialDept.value || !title.value.trim())) ||
    !reason.value.trim() ||
    !assignment.value ||
    (titleChanged.value && !title.value.trim())
  )
    return null
  return {
    base_identity_version: props.person.identity_version,
    base_authorization_version: props.person.authorization_version,
    source_assignment_id: assignment.value.id,
    ...(props.review
      ? {
          position_review: {
            item_key: props.review.item_key,
            expected_source_revision: props.review.source_revision,
            confirmed_profile: {
              org_unit_id: officialOrg.value,
              department_code: officialDept.value,
              position: title.value.trim(),
            },
          },
        }
      : {}),
    reason: reason.value.trim(),
    ...(postingChanged.value
      ? {
          official_posting: {
            org_unit_id: officialOrg.value,
            department_code: officialDept.value,
            position: title.value.trim(),
          },
        }
      : {}),
    ...(Object.keys(scopeEdits.value).length
      ? {
          scope_updates: Object.entries(scopeEdits.value).map(([binding_id, factory_ids]) => ({
            binding_id,
            factory_ids: [...factory_ids],
          })),
        }
      : {}),
    ...(titleChanged.value ? { official_position_title: title.value.trim() } : {}),
    add_packages: adding.value,
    remove_binding_ids: removing.value,
    upgrade_binding_ids: upgrading.value,
  }
})
watch(draft, (value) => emit('draft', value), {
  deep: true,
  immediate: true,
  flush: 'sync',
})
watch(
  () =>
    editing.value &&
    ((props.review
      ? proposedProfileChanged.value ||
        !!(removing.value.length || upgrading.value.length || adding.value.length)
      : changed.value) ||
      !!Object.keys(selection.value).length ||
      !!Object.keys(scopeEdits.value).length ||
      !!reason.value ||
      !!roleId.value ||
      !!department.value ||
      factories.value.length > 0),
  (value) => emit('dirty', value),
  { immediate: true, flush: 'sync' },
)
watch(assignmentId, () => {
  title.value = assignment.value?.official_position_title || ''
  officialOrg.value = assignment.value?.org_unit_id || ''
  officialDept.value = assignment.value?.department_code || ''
  selection.value = {}
  choosing.value = false
  roleId.value = ''
  department.value = ''
  factories.value = []
})
let request = 0
async function loadRoles() {
  const current = ++request
  loadingRoles.value = true
  roleError.value = ''
  try {
    const [items, index] = await Promise.allSettled([iamApi.listRoles(), accessStudioApi.packageAbilities()])
    if (current !== request) return
    if (items.status === 'rejected') throw items.reason
    choices.value = items.value
    if (index.status === 'fulfilled') {
      abilities.value = index.value
      abilityError.value = ''
    } else abilityError.value = getApiErrorMessage(index.reason)
  } catch (e) {
    if (current === request) roleError.value = getApiErrorMessage(e)
  } finally {
    if (current === request) loadingRoles.value = false
  }
}
async function adoptReference(id?: string) {
  if (!props.canReadRoles || props.locked || !props.canEdit) return
  choosing.value = true
  search.value = ''
  await loadRoles()
  if (id && !choices.value.some((r) => r.id === id)) {
    roleError.value = '当前目录不可选用此权限包。'
    return
  }
  roleId.value = id || ''
  department.value = props.referencePackages?.find((r) => r.role_id === id)?.department || ''
  factories.value = requestedFactories.value.filter((f) => factoryOrgs.value.some((o) => o.id === f))
}
function stageScope(id: string) {
  const factories = selection.value[id]
  if (!factories?.length) return
  scopeEdits.value[id] = [...factories]
  delete selection.value[id]
}
function cancelScope(id: string) {
  delete selection.value[id]
  delete scopeEdits.value[id]
}
function cancelChoice() {
  choosing.value = false
  roleId.value = ''
  department.value = ''
  factories.value = []
  search.value = ''
}
function choosePackage() {
  search.value = ''
  choosing.value = true
  void loadRoles()
}
function stage() {
  if (
    !choices.value.some((r) => r.id === roleId.value) ||
    !department.value ||
    !factories.value.length ||
    props.locked
  )
    return
  adding.value.push({
    role_id: roleId.value,
    department: department.value,
    factory_scope: { kind: 'selected', factory_ids: [...factories.value] },
  })
  choosing.value = false
  roleId.value = ''
  department.value = ''
  factories.value = []
}
function mark(id: string, action: 'remove' | 'upgrade') {
  const list = action === 'remove' ? removing : upgrading
  list.value = list.value.includes(id) ? list.value.filter((value) => value !== id) : [...list.value, id]
}
onBeforeUnmount(() => {
  ++request
  emit('draft', null)
  emit('dirty', false)
})
</script>
<template>
  <section ref="surface" class="iam2-editor personnel-editor">
    <section class="personnel-block personnel-profile">
      <header class="personnel-block-heading">
        <h3>{{ review ? '本次确认的任职' : '正式任职信息' }}</h3>
        <Button
          v-if="canEdit && !editing && assignments.length"
          type="button"
          size="sm"
          variant="outline"
          @click="editing = true"
          >调整职位与权限</Button
        >
      </header>
      <fieldset v-if="editing" class="iam2-fields personnel-profile-form" :disabled="locked || !canEdit">
        <label
          >本次办理的任职<select
            v-model="assignmentId"
            :disabled="
              !!review || changed || choosing || !!Object.keys(selection).length || !assignments.length
            "
          >
            <option v-for="a in assignments" :key="a.id" :value="a.id">
              {{ a.org_name }} · {{ a.official_position_title }}{{ a.is_primary ? '（主职）' : '（兼任）' }}
            </option>
          </select></label
        >
        <template v-if="review || assignment?.is_primary">
          <label
            >确认归属组织<select v-model="officialOrg" @change="officialDept = ''">
              <option
                v-for="org in catalog.organizations.filter(
                  (o) => o.status === 'active' && o.kind !== 'group',
                )"
                :key="org.id"
                :value="org.id"
              >
                {{ org.name }}
              </option>
            </select></label
          >
          <label
            >确认归属部门<select v-model="officialDept">
              <option value="">请选择部门</option>
              <option v-for="d in officialDepartments" :key="d.code" :value="d.code">
                {{ d.name }}
              </option>
            </select></label
          >
        </template>
        <label>正式职位名称<input v-model="title" maxlength="128" /></label>
      </fieldset>
      <dl v-else class="personnel-profile-facts">
        <div>
          <dt>所属组织</dt>
          <dd>
            {{
              person.primary_assignment?.org_name ||
              orgName(person.primary_org_unit_id || person.primary_factory_id) ||
              '未登记'
            }}
          </dd>
        </div>
        <div>
          <dt>所属部门</dt>
          <dd>{{ departmentName(person.primary_department) }}</dd>
        </div>
        <div>
          <dt>正式岗位</dt>
          <dd>
            {{ person.primary_assignment?.official_position_title || person.position || '待确认' }}
          </dd>
        </div>
      </dl>
    </section>
    <section
      v-if="review && (requestedRoles.length || requestedFactories.length)"
      class="personnel-block personnel-reference"
    >
      <h3>员工申请参考</h3>
      <p>期望厂区 · {{ requestedFactories.map(orgName).join('、') || '未填写' }}</p>
      <div v-for="id in requestedRoles" :key="id" class="iam2-ops">
        {{ requestedPackageLabel(id, referencePackages) }}
        <Button
          v-if="editing && canReadRoles"
          type="button"
          size="sm"
          variant="outline"
          :disabled="locked || loadingRoles"
          @click="adoptReference(id)"
          >采用为待核对方案</Button
        >
      </div>
      <Button
        v-if="editing && canReadRoles && !requestedRoles.length"
        type="button"
        size="sm"
        variant="outline"
        :disabled="locked || loadingRoles"
        @click="adoptReference()"
        >采用为待核对厂区</Button
      >
    </section>
    <section class="personnel-package-section">
      <header class="personnel-block-heading">
        <h3>
          <Layers3 :size="16" aria-hidden="true" />当前有效权限包
          <span class="personnel-count">{{ packages.length }}</span>
        </h3>
        <Button
          v-if="editing && !choosing"
          type="button"
          size="sm"
          :disabled="locked || !canEdit || !canReadRoles"
          :title="canReadRoles ? undefined : '需要权限目录读取权'"
          @click="choosePackage"
          ><Plus :size="14" aria-hidden="true" />添加权限包</Button
        >
      </header>
      <fieldset
        v-if="editing && choosing"
        class="iam2-fields personnel-picker"
        :disabled="locked || !canEdit"
      >
        <h4>新增权限包</h4>
        <label
          >搜索可见方案<input v-model="search" type="search" placeholder="方案名称、部门、能力名称或代码"
        /></label>
        <p v-if="loadingRoles" role="status">正在读取可见方案…</p>
        <p v-else-if="roleError" class="pw-error" role="alert">
          {{ roleError }}<Button variant="outline" @click="loadRoles">重试</Button>
        </p>
        <div v-else class="personnel-role-choices">
          <p v-if="!groups.size" class="iamx-muted">没有匹配的可见方案。</p>
          <section v-for="[label, items] in groups" :key="label">
            <h5>{{ label }}</h5>
            <div class="personnel-role-grid">
              <button
                v-for="r in items"
                :key="r.id"
                type="button"
                :aria-pressed="roleId === r.id"
                @click="roleId = r.id"
              >
                <strong>{{ r.name }}</strong>
                <small v-if="r.permission_count != null">{{ r.permission_count }} 项能力</small>
                <span v-if="r.description">{{ r.description }}</span>
              </button>
            </div>
          </section>
        </div>
        <p v-if="abilityError" class="pw-notice">
          包内能力暂不可用 · {{ abilityError }}
          <button type="button" @click="loadRoles">重试能力清单</button>
        </p>
        <details v-if="roleId && abilities[roleId]">
          <summary>查看此包的 {{ abilities[roleId]?.length }} 项能力</summary>
          <ul>
            <li v-for="p in abilities[roleId]" :key="p.code">{{ p.name }} · {{ p.code }}</li>
          </ul>
        </details>
        <p v-if="roleId">
          已选方案 ·
          <strong>{{ choices.find((r) => r.id === roleId)?.name || roleId }}</strong>
        </p>
        <label
          >作用部门<select v-model="department">
            <option value="">请选择</option>
            <option v-for="d in departments" :key="d.code" :value="d.code">
              {{ d.name }}
            </option>
          </select></label
        >
        <fieldset>
          <legend>业务厂区</legend>
          <div class="iam2-factories personnel-scope-options">
            <label v-for="o in factoryOrgs" :key="o.id"
              ><input v-model="factories" type="checkbox" :value="o.id" />{{ o.name }}</label
            >
          </div>
        </fieldset>
        <div class="iam2-ops">
          <Button
            type="button"
            size="sm"
            :disabled="!roleId || !department || !factories.length"
            @click="stage"
            >加入待确认方案</Button
          ><Button type="button" size="sm" variant="ghost" @click="cancelChoice">取消</Button>
        </div>
      </fieldset>
      <p v-if="!packages.length" class="personnel-no-packages">当前没有生效的权限包。</p>
      <article
        v-for="b in packages"
        :key="b.binding_id"
        :data-binding-id="b.binding_id"
        tabindex="-1"
        class="iam2-binding personnel-binding"
        :data-change="
          removing.includes(b.binding_id)
            ? 'remove'
            : upgrading.includes(b.binding_id)
              ? 'upgrade'
              : undefined
        "
      >
        <header class="personnel-binding-head">
          <div>
            <strong>{{ b.role_name }}</strong>
            <span class="personnel-chip">{{ b.role_version_id ? '固定版本' : '沿用原版本' }}</span>
            <span v-if="b.version_outdated" class="personnel-chip" data-tone="info">正在使用旧版</span>
            <span v-if="removing.includes(b.binding_id)" class="personnel-chip" data-tone="danger"
              >待结束</span
            >
            <span v-else-if="upgrading.includes(b.binding_id)" class="personnel-chip" data-tone="info"
              >待升级</span
            >
          </div>
          <button
            v-if="
              editing &&
              b.assignment_id === assignmentId &&
              b.role_version_id &&
              b.source_type === 'assignment'
            "
            type="button"
            class="personnel-small-action is-remove"
            :disabled="
              locked ||
              upgrading.includes(b.binding_id) ||
              !!scopeEdits[b.binding_id] ||
              !!selection[b.binding_id]
            "
            :aria-pressed="removing.includes(b.binding_id)"
            @click="mark(b.binding_id, 'remove')"
          >
            {{ removing.includes(b.binding_id) ? '撤销本次结束' : '结束此绑定' }}
          </button>
        </header>
        <p>
          {{ departmentName(b.department) }} · {{ sourceLabels[b.source_type] || b.source_type }} ·
          {{ b.valid_until ? '有效至 ' + formatBusinessDateTime(b.valid_until) : '长期有效' }}
        </p>
        <div class="personnel-binding-scope">
          <span>业务厂区上限</span>
          <div class="personnel-chip-list">
            <span
              v-for="id in scopeEdits[b.binding_id] || b.factory_ceiling"
              :key="id"
              class="personnel-chip"
              data-tone="jade"
              ><Check :size="12" aria-hidden="true" />{{ orgName(id) }}</span
            >
            <span v-if="!scopeEdits[b.binding_id] && !b.factory_ceiling?.length" class="personnel-chip">{{
              b.factory_ceiling === null ? '沿用原批准范围' : '无业务厂区'
            }}</span>
          </div>
        </div>
        <div
          v-if="
            editing &&
            b.assignment_id === assignmentId &&
            b.role_version_id &&
            b.source_type === 'assignment' &&
            !removing.includes(b.binding_id) &&
            !upgrading.includes(b.binding_id)
          "
        >
          <button
            v-if="!selection[b.binding_id]"
            type="button"
            class="personnel-small-action"
            :disabled="locked"
            @click="selection[b.binding_id] = [...(scopeEdits[b.binding_id] || b.factory_ceiling || [])]"
          >
            调整此绑定的厂区上限
          </button>
          <fieldset v-else class="iam2-fields" :disabled="locked">
            <legend>允许的业务厂区上限</legend>
            <div class="iam2-factories">
              <label v-for="o in factoryOrgs" :key="o.id"
                ><input type="checkbox" v-model="selection[b.binding_id]" :value="o.id" />{{ o.name }}</label
              >
            </div>
            <small
              >绑定厂区为 {{ orgName(b.factory_id) }}。实际可用能力由该版本的跨厂规则与此上限共同决定。</small
            >
            <div>
              <Button
                type="button"
                size="sm"
                :disabled="!selection[b.binding_id]?.length"
                @click="stageScope(b.binding_id)"
                >加入本次变更</Button
              >
              <Button type="button" size="sm" variant="ghost" @click="delete selection[b.binding_id]"
                >取消</Button
              >
            </div>
          </fieldset>
          <button
            v-if="scopeEdits[b.binding_id]"
            type="button"
            :disabled="locked"
            class="personnel-small-action"
            @click="cancelScope(b.binding_id)"
          >
            撤销本次厂区变更
          </button>
        </div>
        <div class="personnel-binding-foot">
          <details>
            <summary>版本与来源</summary>
            <p>绑定 {{ b.binding_id }}</p>
            <p>固定版本 {{ b.role_version_id || '沿用原解释' }}</p>
            <p>
              {{ b.assignment_id ? (b.is_primary_assignment ? '主职任职' : '关联任职') : '独立来源' }}
              ·
              {{ sourceLabels[b.source_type] || b.source_type }}
            </p>
          </details>
          <button
            v-if="
              editing &&
              b.assignment_id === assignmentId &&
              b.role_version_id &&
              b.source_type === 'assignment' &&
              b.version_outdated &&
              canReadRoles
            "
            type="button"
            class="personnel-small-action is-upgrade"
            :disabled="
              locked ||
              removing.includes(b.binding_id) ||
              !!scopeEdits[b.binding_id] ||
              !!selection[b.binding_id]
            "
            :aria-pressed="upgrading.includes(b.binding_id)"
            @click="mark(b.binding_id, 'upgrade')"
          >
            {{ upgrading.includes(b.binding_id) ? '撤销本次升级' : '升级到当前版本' }}
          </button>
        </div>
      </article>
      <article v-for="(a, i) in adding" :key="i" class="iam2-binding personnel-binding" data-change="add">
        <header class="personnel-binding-head">
          <div>
            <strong>{{ choices.find((r) => r.id === a.role_id)?.name || a.role_id }}</strong
            ><span class="personnel-chip" data-tone="jade">待加入</span>
          </div>
          <button
            type="button"
            class="personnel-small-action"
            :disabled="locked"
            @click="adding.splice(i, 1)"
          >
            撤销新增
          </button>
        </header>
        <p>{{ departmentName(a.department) }}</p>
        <div class="personnel-chip-list">
          <span v-for="id in a.factory_scope.factory_ids" :key="id" class="personnel-chip" data-tone="jade">{{
            orgName(id)
          }}</span>
        </div>
      </article>
    </section>
    <fieldset v-if="editing" class="iam2-fields" :disabled="locked || !canEdit">
      <label
        >变更原因<textarea v-model="reason" maxlength="2000" rows="2" placeholder="请说明本次变更的原因" />
      </label>
    </fieldset>
  </section>
</template>
