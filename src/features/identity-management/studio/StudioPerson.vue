<script setup lang="ts">
import { computed, defineComponent, h, onBeforeUnmount, ref, watch } from 'vue'
import { ChevronDown, GitCompareArrows } from '@lucide/vue'
import { DropdownMenuRoot, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from 'reka-ui'
import { useAuthStore } from '@/stores/auth'
import {
  identityApi,
  type PersonIdentity,
  type OrganizationCatalog,
  type ChangePayload,
} from '@/api/identity'
import type { WorkItemDetail, BuiltinPackage } from '@/api/positionReviews'
import { accessStudioApi, type StudioDraft, type StudioResult } from '@/api/accessStudio'
import { getApiErrorMessage } from '@/lib/http'
import { parseBusinessTimestamp } from '@/lib/dateTime'
import type { UserPermissionOverride } from '@/api/iam'
import { Button } from '@/components/ui/button'
import IamDialogSurface from '@/components/iam/workspace/IamDialogSurface.vue'
import { personStatusPresentation } from '@/components/iam/workspace/iam-status'
import LegacySourceReview from '../LegacySourceReview.vue'
import AccessExplanation from '../AccessExplanation.vue'
import DelegationEditor from '../DelegationEditor.vue'
import PersonContext from '../workspace/PersonContext.vue'
import { departmentName, permissionName, lastLoginLabel } from '../positionLabels'
import { workspaceCapabilities, type PersonPanel } from '../workspace/contracts'
import PackageEditor from './PackageEditor.vue'
import PersonnelAction, { type PersonnelActionKind } from './PersonnelAction.vue'
import StudioTimeline from './StudioTimeline.vue'
import { useStudioSubmission } from './useStudioSubmission'

const props = defineProps<{
  personId: string
  tab: string
  panel: PersonPanel
  catalog?: OrganizationCatalog
  review?: WorkItemDetail
  referencePackages?: BuiltinPackage[]
}>()
const emit = defineEmits<{
  close: []
  saved: []
  confirmed: [StudioResult]
  reloadReview: []
  panel: [PersonPanel]
  tab: [string]
  locked: [boolean]
  dirty: [boolean]
  task: [string, boolean]
}>()
const InlineSurface = defineComponent({
  inheritAttrs: false,
  setup(_, { slots }) {
    return () => h('section', { class: 'iam2-review-surface' }, slots.default?.())
  },
})
const auth = useAuthStore()
const caps = computed(() => workspaceCapabilities((p) => auth.can(p)))
const viewer = computed(() =>
  [
    auth.currentUser?.id,
    auth.currentUser?.identity?.employment_epoch,
    auth.authorizationVersion,
    auth.currentUser?.identity?.effective_context_key,
  ].join(':'),
)
const primaryView = computed(() => ['profile', 'manage'].includes(props.panel))
const person = ref<PersonIdentity>(),
  access = ref<Awaited<ReturnType<typeof accessStudioApi.effective>>>()
const loading = ref(false),
  error = ref(''),
  accessError = ref(''),
  notice = ref('')
const externalBusy = ref(false),
  dirty = ref(false),
  legacyDirty = ref(false),
  draft = ref<StudioDraft | ChangePayload | null>(null)
const action = ref<{ kind: PersonnelActionKind; sourceId?: string }>()
const accountIntent = ref<'active' | 'suspended'>()
const submission = useStudioSubmission(
  () => props.personId,
  () => draft.value,
  (result) => {
    notice.value =
      result.message || (result.decision === 'pending_approval' ? '已提交独立复核' : '本次变更已生效')
    dirty.value = false
    if (props.review) emit('confirmed', result)
    else {
      emit('saved')
      void read()
    }
  },
)
const { preview, state, locked: submitting, acknowledge, empty, ready } = submission
const locked = computed(() => externalBusy.value || submitting.value)
const submissionAlert = ref<HTMLParagraphElement>()
watch(
  state,
  (value) => {
    if (value === 'uncertain' || value === 'conflict') submissionAlert.value?.focus()
  },
  { flush: 'post' },
)
const tabs = [
  { id: 'packages', label: '权限配置' },
  { id: 'effective', label: '有效权限' },
  { id: 'timeline', label: '档案与时间线' },
]
const diffs = {
  added: '新增权限',
  removed: '收回权限',
  retained: '实权保留',
  source_changed: '其中来源变化',
}
const metrics = [
  { key: 'added', label: '新增权限', prefix: '+' },
  { key: 'removed', label: '收回权限', prefix: '−' },
  { key: 'retained', label: '保持不变', prefix: '' },
] as const
const editing = ref(false)
const secondaryAssignments = computed(
  () => person.value?.active_assignments_summary?.filter((a) => !a.is_primary) || [],
)
const orgName = (id: string) => props.catalog?.organizations.find((o) => o.id === id)?.name || id
function overrideStatus(o: UserPermissionOverride) {
  if (o.state !== 'active') return o.state === 'suspended' ? '已暂停' : '已撤销'
  const now = parseBusinessTimestamp(person.value?.server_now) ?? Date.now()
  const end = parseBusinessTimestamp(o.valid_until)
  const start = parseBusinessTimestamp(o.valid_from)
  if (end !== null && end <= now) return '已结束'
  return start !== null && start > now ? '待生效' : '已启用'
}
const accessSourceName = (id: string) =>
  access.value?.current_packages.find((b) => b.binding_id === id)?.role_name ||
  (person.value?.overrides.some((o) => o.id === id && o.effect === 'allow') ? '个人允许' : id)
watch(locked, (value) => emit('locked', value), {
  immediate: true,
  flush: 'sync',
})
watch([dirty, legacyDirty], ([edit, source]) => emit('dirty', edit || source), {
  immediate: true,
  flush: 'sync',
})
let request = 0
async function read() {
  const current = ++request
  person.value = undefined
  access.value = undefined
  draft.value = null
  dirty.value = false
  editing.value = false
  action.value = undefined
  error.value = ''
  accessError.value = ''
  loading.value = false
  if (!caps.value.people || !primaryView.value) return
  loading.value = true
  const [identity, effective] = await Promise.allSettled([
    identityApi.person(props.personId),
    accessStudioApi.effective(props.personId),
  ])
  if (current !== request) return
  if (identity.status === 'fulfilled') person.value = identity.value
  else error.value = getApiErrorMessage(identity.reason)
  if (effective.status === 'fulfilled') access.value = effective.value
  else accessError.value = getApiErrorMessage(effective.reason)
  loading.value = false
}
watch(
  [() => props.personId, primaryView, viewer],
  () => {
    notice.value = ''
    void read()
  },
  { immediate: true, flush: 'sync' },
)
onBeforeUnmount(() => {
  ++request
  emit('dirty', false)
  emit('locked', false)
})
const canEdit = computed(
  () =>
    !!props.catalog?.writes_enabled &&
    props.catalog.studio_writes_enabled === true &&
    caps.value.people &&
    caps.value.exceptions,
)
const canConfigure = computed(
  () =>
    canEdit.value &&
    (!props.review ||
      (props.review.status === 'pending' &&
        props.review.available_actions.includes('preview') &&
        props.review.studio_writes_enabled === true)) &&
    person.value?.identity_mode === 'v2' &&
    person.value.status === 'active' &&
    person.value.employment_status === 'active' &&
    person.value.id !== auth.currentUser?.id,
)
const canAct = computed(
  () =>
    canEdit.value &&
    !props.review &&
    person.value?.identity_mode === 'v2' &&
    person.value.id !== auth.currentUser?.id,
)
function startAction(kind: PersonnelActionKind, sourceId?: string) {
  if (!canAct.value || locked.value || dirty.value || legacyDirty.value) return
  action.value = { kind, sourceId }
  draft.value = null
  editing.value = true
  if (props.tab !== 'packages') emit('tab', 'packages')
}
function cancelAction() {
  if (locked.value) return
  action.value = undefined
  draft.value = null
  dirty.value = false
  editing.value = false
}
function openAccount(desired?: 'active' | 'suspended') {
  accountIntent.value = desired
  emit('panel', 'account')
}
function reloadAfterConflict() {
  state.value = 'idle'
  if (props.review) emit('reloadReview')
  else void read()
}
function legacySaved() {
  notice.value = '历史授权来源已确认。请重新核对本次岗位和权限变更。'
  externalBusy.value = false
  if (props.review) emit('reloadReview')
  else {
    emit('saved')
    void read()
  }
}
</script>
<template>
  <component
    :is="review ? InlineSurface : IamDialogSurface"
    :open="true"
    :title="person?.display_name || '人员详情'"
    :description="
      person
        ? [
            person.username && '@' + person.username,
            person.primary_assignment?.org_name ||
              orgName(person.primary_org_unit_id || person.primary_factory_id),
            departmentName(person.primary_department),
            person.position || '岗位待确认',
            person.last_login_at && '最近登录 ' + lastLoginLabel(person.last_login_at),
          ]
            .filter(Boolean)
            .join(' · ')
        : '查看人员任职、权限和办理记录'
    "
    drawer
    :busy="locked"
    @update:open="emit('close')"
  >
    <template #identity>
      <span
        v-if="person"
        class="personnel-avatar personnel-drawer-avatar"
        aria-hidden="true"
        :data-mode="person.identity_mode"
        :data-status="person.status"
        >{{ person.display_name.slice(0, 1) }}</span
      >
    </template>
    <template #status>
      <template v-if="person">
        <span
          class="personnel-chip personnel-state"
          :data-tone="personStatusPresentation(person.status).tone"
          >{{ personStatusPresentation(person.status).label }}</span
        >
        <span class="personnel-chip" :data-tone="person.identity_mode === 'legacy' ? 'warning' : 'jade'">{{
          person.identity_mode === 'legacy' ? '历史来源待核实' : '正式任职'
        }}</span>
      </template>
    </template>
    <template #actions>
      <DropdownMenuRoot v-if="person && caps.people" :modal="false">
        <DropdownMenuTrigger as-child>
          <Button type="button" variant="outline" size="sm" :disabled="locked" class="personnel-life-trigger"
            >账号生命周期 <ChevronDown :size="14" aria-hidden="true"
          /></Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" :side-offset="5" class="personnel-life-menu">
          <DropdownMenuItem
            @select="openAccount()"
            >账号资料与状态</DropdownMenuItem
          >
          <DropdownMenuItem
            v-if="
              !review &&
              !dirty &&
              !legacyDirty &&
              person.employment_status !== 'left' &&
              ['active', 'suspended'].includes(person.status)
            "
            @select="openAccount(person.status === 'active' ? 'suspended' : 'active')"
            >{{ person.status === 'active' ? '停用账号' : '恢复账号' }}</DropdownMenuItem
          >
          <template v-if="canAct && !dirty && !legacyDirty">
            <DropdownMenuItem
              v-if="person.employment_status === 'active' && person.status === 'active'"
              @select="startAction('freeze')"
              >冻结账号</DropdownMenuItem
            >
            <DropdownMenuItem
              v-if="person.status === 'suspended' && person.employment_status !== 'left'"
              @select="startAction('unfreeze')"
              >恢复冻结账号</DropdownMenuItem
            >
            <DropdownMenuItem v-if="person.employment_status !== 'left'" @select="startAction('leave')"
              >办理离职</DropdownMenuItem
            >
            <DropdownMenuItem v-else @select="startAction('rehire')">办理复职</DropdownMenuItem>
          </template>
        </DropdownMenuContent>
      </DropdownMenuRoot>
    </template>
    <template #navigation
      ><nav v-if="caps.people" class="iam2-tabs" aria-label="人员详情页签">
        <button
          v-for="t in tabs"
          :key="t.id"
          type="button"
          :aria-pressed="primaryView && tab === t.id"
          :disabled="locked"
          @click="emit('tab', t.id)"
        >
          {{ t.label }}
        </button>
      </nav></template
    >
    <div
      class="iam2-person personnel-studio"
      :class="{
        'personnel-packages': primaryView && tab === 'packages' && person,
      }"
    >
      <p v-if="notice" class="pw-notice" role="status">{{ notice }}</p>
      <p v-if="submission.error.value" ref="submissionAlert" class="pw-error" role="alert" tabindex="-1">
        {{ submission.error.value }}
      </p>
      <div v-if="state === 'uncertain'" class="iam2-ops">
        <Button variant="outline" @click="submission.receipt">查询提交回执</Button
        ><Button variant="outline" @click="submission.retry">使用原命令重试</Button>
      </div>
      <PersonContext
        v-if="!primaryView"
        :person-id="personId"
        :panel="panel"
        :catalog="catalog"
        :account-intent="accountIntent"
        @intent-read="accountIntent = undefined"
        @panel="emit('panel', $event)"
        @back="emit('close')"
        @saved="emit('saved')"
        @task="(key, reused) => emit('task', key, reused)"
        @locked="externalBusy = $event"
      />
      <p v-else-if="!caps.people" class="pw-notice">当前账号没有人员资料查看权限。</p>
      <p v-else-if="loading" role="status">正在读取人员资料…</p>
      <p v-else-if="error" class="pw-error" role="alert">
        {{ error }}<Button variant="outline" @click="read">重试</Button>
      </p>
      <template v-else-if="person">
        <template v-if="tab === 'timeline'">
          <dl class="iw-facts">
            <div>
              <dt>正式岗位</dt>
              <dd>{{ person.position || '待确认' }}</dd>
            </div>
            <div>
              <dt>账号状态</dt>
              <dd>{{ personStatusPresentation(person.status).label }}</dd>
            </div>
            <div>
              <dt>雇佣周期</dt>
              <dd>{{ person.employment_epoch }}</dd>
            </div>
            <div>
              <dt>部门</dt>
              <dd>{{ departmentName(person.primary_department) }}</dd>
            </div>
          </dl>
          <details v-if="person.assignments.length">
            <summary>任职历史（{{ person.assignments.length }}）</summary>
            <p v-for="a in person.assignments" :key="a.id">
              {{ a.official_position_title }} · {{ a.org_name }} · {{ a.valid_from }} 至
              {{ a.valid_until || '长期' }}
            </p>
          </details>
          <StudioTimeline :target-user-id="person.id" />
          <div class="iam2-ops">
            <Button variant="outline" @click="emit('panel', 'account')">账号资料与状态</Button>
          </div>
        </template>
        <template v-else-if="tab === 'effective'">
          <section v-if="catalog && caps.exceptions" class="personnel-block personnel-explain">
            <h3>权限验算器</h3>
            <AccessExplanation
              :user-id="person.id"
              :catalog="catalog"
              :default-factory="person.primary_factory_id"
              :default-department="person.primary_department"
            />
          </section>
          <h3>分模块有效能力</h3>
          <p v-if="accessError" class="pw-error" role="alert">
            {{ accessError }}<Button variant="outline" @click="read">重试</Button>
          </p>
          <p v-else-if="!access?.effective_permissions_grouped.length">当前没有生效的能力。</p>
          <details
            v-for="(group, index) in access?.effective_permissions_grouped"
            :key="group.module_code"
            class="iam2-disclosure personnel-module"
            :open="index === 0"
          >
            <summary>{{ group.module_name }} · {{ group.items.length }} 项</summary>
            <ul>
              <li v-for="p in group.items" :key="p.code + p.access_kind">
                <strong>{{ permissionName(p.code, p.name) }}</strong
                ><small>{{ p.code }}</small>
                <div class="personnel-chip-list">
                  <span v-for="factory in p.factory_names" :key="factory" class="personnel-chip">{{
                    factory
                  }}</span>
                  <span v-if="!p.factory_names.length" class="personnel-chip">无业务厂区</span>
                  <span v-for="id in p.source_ids" :key="id" class="personnel-chip" data-tone="jade"
                    >来源 · {{ accessSourceName(id) }}</span
                  >
                </div>
                <details v-if="p.scopes?.length">
                  <summary>各厂区有效部门</summary>
                  <p v-for="scope in p.scopes" :key="scope.factory_id">
                    {{ p.factory_names[p.factory_ids.indexOf(scope.factory_id)] || scope.factory_id }}
                    ·
                    {{ scope.department_codes.map(departmentName).join('、') }}
                  </p>
                </details>
              </li>
            </ul>
          </details>
          <details v-if="person.overrides.length" class="iam2-disclosure">
            <summary>个人允许与禁止记录 · {{ person.overrides.length }}</summary>
            <ul>
              <li v-for="o in person.overrides" :key="o.id">
                {{ o.effect === 'deny' ? '明确禁止' : '个人允许' }} ·
                {{ permissionName(o.permission_code) }} · {{ o.factory_id }} ·
                {{ departmentName(o.department) }}
                <small
                  >{{ o.state === 'active' ? '已启用' : o.state === 'suspended' ? '已暂停' : '已撤销' }} ·
                  {{ o.valid_from || '起始时间未限定' }} 至 {{ o.valid_until || '长期' }}</small
                >
              </li>
            </ul>
          </details>
          <Button v-if="caps.exceptions" variant="outline" @click="emit('panel', 'exceptions')"
            >查看个人例外</Button
          >
          <DelegationEditor
            v-if="catalog?.can_manage_delegations && person.id !== auth.currentUser?.id"
            :user-id="person.id"
            :catalog="catalog"
            :default-org="
              person.primary_assignment?.org_unit_id ||
              person.primary_org_unit_id ||
              person.primary_factory_id
            "
            :default-department="person.primary_department"
          />
        </template>
        <template v-else>
          <div class="personnel-workspace">
            <div class="personnel-assembly">
              <p v-if="catalog?.studio_writes_enabled === false" class="pw-notice" role="status">
                新版人工办理已关闭，当前可查看人员与授权资料。
              </p>
              <LegacySourceReview
                v-if="person.identity_mode === 'legacy' && canEdit"
                :key="person.id + viewer"
                studio
                :catalog="catalog"
                :user-id="person.id"
                :official="{
                  org_unit_id: person.primary_org_unit_id || person.primary_factory_id,
                  department_code: person.primary_department,
                  position: person.position,
                }"
                @locked="externalBusy = $event"
                @saved="legacySaved"
                @dirty="legacyDirty = $event"
              />
              <p v-if="accessError" class="pw-error" role="alert">
                {{ accessError }}<Button variant="outline" @click="read">重试读取授权</Button>
              </p>
              <p v-else-if="!catalog" class="pw-notice">组织目录暂不可用，请从工作区重新读取。</p>
              <PersonnelAction
                v-if="action && catalog"
                :key="[action.kind, action.sourceId].join(':')"
                :kind="action.kind"
                :source-id="action.sourceId"
                :person="person"
                :catalog="catalog"
                :locked="locked"
                :can-read-roles="caps.catalog"
                @draft="draft = $event"
                @dirty="dirty = $event"
                @cancel="cancelAction"
              />
              <PackageEditor
                v-else-if="access && catalog"
                :key="panel"
                :start-editing="panel === 'manage'"
                :review="review"
                :reference-packages="referencePackages"
                :person="person"
                :catalog="catalog"
                :packages="access.current_packages"
                :can-edit="canConfigure && state !== 'uncertain'"
                :can-read-roles="caps.catalog"
                :locked="locked"
                @draft="draft = $event"
                @dirty="dirty = $event"
                @editing="editing = $event"
              />
              <template v-if="!review">
                <section class="personnel-block">
                  <header class="personnel-block-heading">
                    <h3>
                      兼任与临时支援
                      <span class="personnel-count">{{ secondaryAssignments.length }}</span>
                    </h3>
                    <button
                      v-if="canConfigure && !action"
                      type="button"
                      class="personnel-small-action"
                      :disabled="locked || dirty"
                      @click="startAction('add_assignment')"
                    >
                      新增兼任
                    </button>
                  </header>
                  <ul v-if="secondaryAssignments.length" class="personnel-record-list">
                    <li v-for="a in secondaryAssignments" :key="a.id">
                      <strong>{{ a.official_position_title }}</strong
                      ><small
                        >{{ a.org_name }} · {{ departmentName(a.department_code) }} ·
                        {{ a.valid_until || '长期有效' }}</small
                      >
                      <button
                        v-if="canConfigure && !action"
                        type="button"
                        class="personnel-small-action"
                        :disabled="locked || dirty"
                        @click="startAction('end_assignment', a.id)"
                      >
                        结束此兼任
                      </button>
                    </li>
                  </ul>
                  <p v-else>暂无兼任或临时支援任职。</p>
                </section>
                <section class="personnel-block">
                  <header class="personnel-block-heading">
                    <h3>
                      个人例外与明确禁止
                      <span class="personnel-count">{{ person.overrides.length }}</span>
                    </h3>
                    <button
                      v-if="canConfigure && caps.catalog && !action"
                      type="button"
                      class="personnel-small-action"
                      :disabled="locked || dirty"
                      @click="startAction('add_override')"
                    >
                      新增例外
                    </button>
                    <button
                      v-if="caps.exceptions"
                      type="button"
                      class="personnel-small-action"
                      :disabled="locked"
                      @click="emit('panel', 'exceptions')"
                    >
                      查看个人例外
                    </button>
                  </header>
                  <ul v-if="person.overrides.length" class="personnel-record-list">
                    <li v-for="o in person.overrides" :key="o.id">
                      <span class="personnel-chip" :data-tone="o.effect === 'deny' ? 'danger' : 'info'">{{
                        o.effect === 'deny' ? '明确禁止' : '个人允许'
                      }}</span>
                      <strong>{{ permissionName(o.permission_code) }}</strong>
                      <button
                        v-if="canConfigure && ['待生效', '已启用'].includes(overrideStatus(o)) && !action"
                        type="button"
                        class="personnel-small-action"
                        :disabled="locked || dirty"
                        @click="startAction('end_override', o.id)"
                      >
                        结束此例外
                      </button>
                      <small
                        >{{ orgName(o.factory_id) }} · {{ departmentName(o.department) }} ·
                        {{ overrideStatus(o) }}</small
                      >
                    </li>
                  </ul>
                  <p v-else>暂无个人例外或明确禁止记录。</p>
                </section>
              </template>
            </div>
            <aside class="personnel-impact" aria-label="本次配置实时影响">
              <header class="personnel-block-heading">
                <h3><GitCompareArrows :size="16" aria-hidden="true" />本次权限影响</h3>
                <span class="personnel-chip" :data-tone="dirty || legacyDirty ? 'warning' : undefined">{{
                  dirty || legacyDirty ? '有未保存变更' : '当前配置'
                }}</span>
              </header>
              <div class="personnel-metrics" aria-label="权限差异统计">
                <div v-for="m in metrics" :key="m.key" :class="'metric-' + m.key">
                  <strong>{{ preview ? m.prefix + preview.permission_diffs[m.key].length : '—' }}</strong
                  ><span>{{ m.label }}</span>
                </div>
              </div>
              <div class="personnel-impact-body" aria-live="polite">
                <p v-if="state === 'conflict'" class="pw-notice">
                  资料或方案版本发生冲突，请重新读取后再办理。
                </p>
                <Button v-if="state === 'conflict'" variant="outline" @click="reloadAfterConflict"
                  >重新读取人员版本</Button
                >
                <p v-else-if="state === 'previewing'">正在核对实际权限范围…</p>
                <template v-else-if="preview">
                  <details
                    v-for="(label, k) in diffs"
                    :key="k"
                    class="personnel-diff"
                    :data-kind="k"
                    :open="k === 'added' || (k === 'removed' && preview.permission_diffs.removed.length > 0)"
                  >
                    <summary>
                      <span>{{ label }}</span
                      ><span>{{ preview.permission_diffs[k].length }} 项</span>
                    </summary>
                    <ul v-if="preview.permission_diffs[k].length">
                      <li
                        v-for="t in preview.permission_diffs[k]"
                        :key="[t.permission_code, t.factory_id, t.department].join(':')"
                      >
                        <b>{{ permissionName(t.permission_code, t.permission_name) }}</b
                        ><small
                          >{{ t.factory_name || t.factory_id }} · {{ departmentName(t.department) }}</small
                        >
                      </li>
                    </ul>
                    <p v-else>无相关权限变化。</p>
                  </details>
                  <p v-if="preview.handover_summary" class="pw-notice">
                    {{ preview.handover_summary }}
                  </p>
                  <p v-if="preview.high_risk" class="pw-notice">本次变更需要高风险确认。</p>
                  <p v-for="b in preview.blocked_reasons" :key="b" class="pw-notice">
                    {{ b }}
                  </p>
                  <details
                    v-if="preview.explicit_denials?.length"
                    class="personnel-diff"
                    data-kind="removed"
                    open
                  >
                    <summary>继续生效的明确禁止 · {{ preview.explicit_denials.length }}</summary>
                    <ul>
                      <li
                        v-for="d in preview.explicit_denials"
                        :key="[d.permission_code, d.factory_id, d.department].join(':')"
                      >
                        <b>{{ permissionName(d.permission_code, d.permission_name) }}</b
                        ><small
                          >{{ d.factory_name || d.factory_id }} · {{ departmentName(d.department) }}</small
                        >
                      </li>
                    </ul>
                  </details>
                </template>
                <template v-else>
                  <p v-if="person.identity_mode === 'legacy'" class="personnel-impact-note">
                    历史授权来源需先核实。完成后可核对新的权限变更。
                  </p>
                  <p v-else class="personnel-impact-note">
                    {{
                      editing
                        ? '调整岗位或权限包并填写变更原因后，这里将显示实际影响。'
                        : '进入调整模式后，可在这里核对实际新增、收回和保留的权限。'
                    }}
                  </p>
                  <Button v-if="draft && !locked" variant="outline" size="sm" @click="submission.check"
                    >重新核对本次变更</Button
                  >
                </template>
              </div>
            </aside>
          </div>
          <footer
            v-if="(editing || action) && (canConfigure || (action && canAct) || locked)"
            class="personnel-review-footer"
          >
            <div>
              <label v-if="preview?.high_risk" class="pw-risk"
                ><input
                  v-model="acknowledge"
                  type="checkbox"
                  :disabled="locked"
                />我已核对高风险变动及其范围</label
              >
              <label v-if="preview?.requires_empty_confirmation" class="pw-risk"
                ><input
                  v-model="empty"
                  type="checkbox"
                  :disabled="locked"
                />确认结束所选任职的全部有效权限包</label
              >
              <span v-if="state === 'saving'" role="status">正在提交本次变更…</span>
              <span v-else-if="state === 'uncertain'">提交结果待确认，请查询原命令回执。</span>
              <span v-else-if="!preview && state !== 'conflict'">提交前请核对本次权限影响。</span>
            </div>
            <Button
              v-if="state !== 'conflict' && state !== 'uncertain'"
              :disabled="!ready || locked"
              @click="submission.commit"
              >{{ preview?.requires_approval ? '提交独立复核' : '确认本次变更' }}</Button
            >
          </footer>
        </template>
      </template>
    </div>
  </component>
</template>
<style src="./personnel-drawer.css"></style>
