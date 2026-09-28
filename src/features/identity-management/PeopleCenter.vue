<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { Search, RefreshCw, ChevronRight, Building2 } from '@lucide/vue'
import { TabsRoot, TabsList, TabsTrigger, TabsContent } from 'reka-ui'
import {
  identityApi,
  type ChangeRecord,
  type Person,
  type PersonIdentity,
  type OrganizationCatalog,
} from '@/api/identity'
import { getApiErrorMessage } from '@/lib/http'
import { formatBusinessDateTime } from '@/lib/dateTime'
import { useAuthStore } from '@/stores/auth'
import { Button } from '@/components/ui/button'
import IamDialogSurface from '@/components/iam/workspace/IamDialogSurface.vue'
import IamDisclosure from '@/components/iam/workspace/IamDisclosure.vue'
import IamStatusBadge from '@/components/iam/workspace/IamStatusBadge.vue'
import {
  personStatusPresentation,
  assignmentStatusPresentation,
  changeStatusPresentation,
} from '@/components/iam/workspace/iam-status'
import { rememberIdentityMode } from '@/components/iam/workspace/identity-ui-context'
import IdentityShell from './IdentityShell.vue'
import IdentityWizard from './IdentityWizard.vue'
import AccessExplanation from './AccessExplanation.vue'
import DelegationEditor from './DelegationEditor.vue'
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const catalog = ref<OrganizationCatalog>()
const people = ref<Person[]>([])
const total = ref(0)
const q = ref('')
const appliedQ = ref('')
const org = ref('')
const status = ref('')
const page = ref(1)
const appliedFilters = ref('')
const loaded = ref(false)
const loading = ref(false)
const error = ref('')
const notice = ref('')
const selected = ref<PersonIdentity>()
const detailError = ref('')
const detailLoading = ref(false)
const inspectorOpen = ref(false)
const wizardOpen = ref(false)
const dirty = ref(false)
const wizardBusy = ref(false)
const savedDraft = ref('')
const tab = ref('overview')
const dialog = ref<InstanceType<typeof IamDialogSurface>>()
let listGeneration = 0
let detailGeneration = 0
const departmentName = (code: string) =>
  catalog.value?.organizations.flatMap((o) => o.departments).find((d) => d.code === code)?.name ||
  code ||
  '部门待确认'
const orgName = (id: string) =>
  catalog.value?.organizations.find((o) => o.id === id || o.factory_id === id)?.name ||
  id ||
  '组织待确认'
const sourceGroups = computed(() => {
  const bindings = selected.value?.role_bindings ?? []
  const independent = ['system_administration', 'external_collaboration', 'individual_exception']
  return [
    { label: '任职来源', rows: bindings.filter((b) => b.assignment_id) },
    {
      label: '独立来源',
      rows: bindings.filter((b) => !b.assignment_id && independent.includes(b.source_type)),
    },
    {
      label: '来源待核实',
      rows: bindings.filter((b) => !b.assignment_id && !independent.includes(b.source_type)),
    },
  ].filter((group) => group.rows.length)
})
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / 30)))
const currentAssignments = computed(
  () => selected.value?.assignments.filter((a) => a.state === 'current') ?? [],
)
const futureAssignments = computed(
  () => selected.value?.assignments.filter((a) => ['scheduled', 'future'].includes(a.state)) ?? [],
)
const historyAssignments = computed(
  () =>
    selected.value?.assignments.filter(
      (a) => !['current', 'scheduled', 'future'].includes(a.state),
    ) ?? [],
)
function selectOrganization(id: string) {
  org.value = id
  void load(true)
}
function changePage(delta: number) {
  page.value += delta
  void load()
}
async function load(reset = false) {
  if (reset) page.value = 1
  const generation = ++listGeneration
  loading.value = true
  error.value = ''
  const params = {
    q: appliedQ.value,
    org_unit_id: org.value,
    status: status.value,
    page: page.value,
  }
  try {
    if (!catalog.value) {
      const result = await identityApi.catalog()
      if (generation !== listGeneration) return
      catalog.value = result
    }
    const result = await identityApi.people(params)
    if (generation !== listGeneration) return
    people.value = result.items
    total.value = result.total
    loaded.value = true
    appliedFilters.value = [
      params.q && `搜索：${params.q}`,
      params.org_unit_id && orgName(params.org_unit_id),
      params.status && personStatusPresentation(params.status).label,
    ]
      .filter(Boolean)
      .join(' · ')
  } catch (e) {
    if (generation !== listGeneration) return
    error.value = getApiErrorMessage(e)
    if ((e as { response?: { status?: number } }).response?.status === 403) {
      people.value = []
      total.value = 0
      loaded.value = false
    }
  } finally {
    if (generation === listGeneration) loading.value = false
  }
}
function search() {
  appliedQ.value = q.value.trim()
  void load(true)
}
async function inspect(id: string) {
  const generation = ++detailGeneration
  inspectorOpen.value = true
  selected.value = undefined
  detailLoading.value = true
  detailError.value = ''
  wizardOpen.value = false
  dirty.value = false
  savedDraft.value = ''
  tab.value = 'overview'
  try {
    const result = await identityApi.person(id)
    if (generation === detailGeneration) {
      selected.value = result
      rememberIdentityMode(auth.currentUser?.id || '', result.id, result.identity_mode)
    }
  } catch (e) {
    if (generation === detailGeneration) detailError.value = getApiErrorMessage(e)
  } finally {
    if (generation === detailGeneration) detailLoading.value = false
  }
}
async function openPerson(id: string) {
  if (route.query.person === id) {
    await inspect(id)
    return
  }
  await router.push({ query: { ...route.query, person: id } })
}
function close() {
  inspectorOpen.value = false
  ++detailGeneration
  const query = { ...route.query }
  delete query.person
  void router.replace({ query })
}
async function leaveWizard() {
  if (await dialog.value?.permitLeave()) {
    dirty.value = false
    wizardOpen.value = false
  }
}
async function saved(row?: ChangeRecord) {
  dirty.value = false
  wizardOpen.value = false
  notice.value = row ? `办理${changeStatusPresentation(row.state).label}。` : '办理已保存。'
  const id = selected.value?.id
  if (id) {
    await inspect(id)
    if (id === auth.currentUser?.id) await auth.refreshSession()
  }
  window.dispatchEvent(new Event('iam-identity-changed'))
  await load()
}
watch(
  () => route.query.person,
  (value) => {
    if (typeof value === 'string' && value) void inspect(value)
    else {
      ++detailGeneration
      inspectorOpen.value = false
    }
  },
  { immediate: true },
)
onBeforeRouteUpdate(async (to, from) => {
  if (to.query.person !== from.query.person && (dirty.value || wizardBusy.value))
    return await dialog.value?.permitLeave()
})
onBeforeRouteLeave(async () => {
  if (dirty.value || wizardBusy.value) return await dialog.value?.permitLeave()
})
onMounted(() => load())
onBeforeUnmount(() => {
  ++listGeneration
  ++detailGeneration
})
</script>
<template>
  <IdentityShell>
    <p v-if="notice" role="status" class="iamx-success">{{ notice }}</p>
    <p v-if="catalog && !catalog.writes_enabled" class="iamx-notice">
      任职办理尚未启用，当前可查看人员及授权来源。
    </p>
    <div class="iamx-people-layout">
      <aside class="iamx-org-rail" aria-label="组织目录">
        <h2>组织目录</h2>
        <button :aria-pressed="!org" @click="selectOrganization('')">
          <Building2 :size="17" />全部可见人员</button
        ><template
          v-for="group in [
            { kind: 'factory', label: '厂区' },
            { kind: 'functional_unit', label: '集团职能' },
          ]"
          :key="group.kind"
          ><h3>{{ group.label }}</h3>
          <button
            v-for="o in catalog?.organizations.filter((o) => o.kind === group.kind)"
            :key="o.id"
            :aria-pressed="org === o.id"
            @click="selectOrganization(o.id)"
          >
            {{ o.name }}
          </button></template
        >
        <p class="iamx-muted">组织归属与业务操作范围分别管理。</p>
      </aside>
      <label class="iamx-org-select"
        >组织范围<select v-model="org" @change="load(true)">
          <option value="">全部可见人员</option>
          <option
            v-for="o in catalog?.organizations.filter((o) => o.kind !== 'group')"
            :key="o.id"
            :value="o.id"
          >
            {{ o.name }}
          </option>
        </select></label
      >
      <section class="iamx-surface" aria-label="人员列表">
        <header class="iamx-section-head">
          <div>
            <h2>
              人员中心 <span class="iamx-count">{{ loaded ? total + ' 人' : '' }}</span>
            </h2>
            <p>查看任职与授权，办理人员变更</p>
          </div>
          <Button variant="outline" :disabled="loading" @click="load()"
            ><RefreshCw :size="15" />刷新</Button
          >
        </header>
        <form class="iamx-toolbar" @submit.prevent="search">
          <label class="iamx-search"
            ><Search :size="17" /><input
              v-model="q"
              data-iam-focus-fallback
              placeholder="搜索姓名或账号，回车查询"
              aria-label="搜索姓名或账号" /></label
          ><select v-model="status" aria-label="账号状态" @change="load(true)">
            <option value="">全部状态</option>
            <option value="active">在用</option>
            <option value="suspended">冻结 / 停用</option>
            <option value="left">离职</option>
            <option value="pending">待审核</option></select
          ><Button type="submit" :disabled="loading">查询</Button>
        </form>
        <p v-if="appliedFilters" class="iamx-filters-applied">当前列表：{{ appliedFilters }}</p>
        <div v-if="error" role="alert" class="iamx-error">
          {{ error }} <Button variant="outline" @click="load()">重试</Button>
          <p v-if="loaded">以下保留上次成功读取的结果。</p>
        </div>
        <p v-if="loading" role="status" class="iamx-filters-applied">正在读取人员资料…</p>
        <div v-if="loading && !loaded" class="iamx-skeleton" aria-hidden="true">
          <span v-for="n in 4" :key="n" />
        </div>
        <template v-if="loaded"
          ><p v-if="!people.length && !error" class="iamx-empty">
            {{
              appliedQ || org || status
                ? '当前筛选没有匹配人员。请调整筛选条件。'
                : '当前管理范围没有人员。'
            }}
          </p>
          <table v-if="people.length" class="iamx-roster">
            <thead>
              <tr>
                <th scope="col">人员</th>
                <th scope="col">正式主职</th>
                <th scope="col">状态</th>
                <th scope="col"><span class="sr-only">详情</span></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="person in people" :key="person.id">
                <td>
                  <button
                    class="iamx-person-link iam-person-row"
                    :data-person-id="person.id"
                    @click="openPerson(person.id)"
                  >
                    <span class="iamx-avatar" aria-hidden="true">{{
                      person.display_name.slice(-2)
                    }}</span
                    ><span
                      ><strong>{{ person.display_name }}</strong
                      ><small>{{ person.username }}</small
                      ><span class="iamx-mobile-assignment"
                        >{{ person.position || '正式资料待确认' }}<br />{{
                          orgName(person.primary_org_unit_id || person.primary_factory_id)
                        }}
                        · {{ departmentName(person.primary_department) }}</span
                      ></span
                    >
                  </button>
                </td>
                <td>
                  <strong>{{ person.position || '正式资料待确认' }}</strong
                  ><small
                    >{{ orgName(person.primary_org_unit_id || person.primary_factory_id) }} ·
                    {{ departmentName(person.primary_department) }}</small
                  >
                </td>
                <td>
                  <IamStatusBadge
                    :presentation="
                      personStatusPresentation(
                        person.employment_status === 'left' ? 'left' : person.status,
                      )
                    "
                  /><span class="iamx-identity-label">{{
                    person.identity_mode === 'v2' ? '正式任职' : '来源待核实'
                  }}</span>
                </td>
                <td>
                  <button
                    class="iamx-icon-button"
                    :aria-label="`查看${person.display_name}的详情`"
                    @click="openPerson(person.id)"
                  >
                    <ChevronRight :size="18" />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <footer class="iamx-pagination">
            <span>第 {{ page }} / {{ pageCount }} 页 · {{ total }} 人</span>
            <div class="iamx-actions">
              <Button variant="outline" :disabled="loading || page <= 1" @click="changePage(-1)"
                >上一页</Button
              ><Button
                variant="outline"
                :disabled="loading || page >= pageCount"
                @click="changePage(1)"
                >下一页</Button
              >
            </div>
          </footer>
        </template>
      </section>
    </div>
    <IamDialogSurface
      ref="dialog"
      :open="inspectorOpen"
      :title="selected?.display_name || '人员详情'"
      :description="
        selected
          ? `${orgName(selected.primary_assignment?.org_unit_id || selected.primary_factory_id)} · ${selected.position || '无当前主职'}`
          : '正在核对人员资料'
      "
      drawer
      :dirty="dirty"
      :busy="wizardBusy"
      :saved-description="savedDraft"
      @update:open="close"
      @discarded="dirty = false"
      @closed="selected = undefined"
    >
      <div v-if="detailLoading" role="status" class="iamx-skeleton">
        <p>正在刷新任职…</p>
        <span v-for="n in 3" :key="n" />
      </div>
      <p v-else-if="detailError" role="alert" class="iamx-error">
        {{ detailError }}
        <Button variant="outline" @click="inspect(String(route.query.person))">重试</Button>
      </p>
      <template v-else-if="selected">
        <IdentityWizard
          v-if="wizardOpen && catalog"
          :key="`${selected.id}:${selected.identity_version}`"
          :person="selected"
          :catalog="catalog"
          @saved="saved"
          @dirty="dirty = $event"
          @busy="wizardBusy = $event"
          @draft="savedDraft = $event"
        />
        <TabsRoot v-else v-model="tab"
          ><TabsList class="iamx-tabs" aria-label="人员详情栏目"
            ><TabsTrigger value="overview">任职概览</TabsTrigger
            ><TabsTrigger value="sources">授权来源</TabsTrigger
            ><TabsTrigger value="handover">工作交接</TabsTrigger></TabsList
          >
          <TabsContent value="overview"
            ><p v-if="!selected.assignments.length" class="iamx-notice">
              尚未建立正式任职。请核实历史授权来源后确认，当前授权仍按原规则解释。
            </p>
            <template
              v-for="group in [
                { label: '当前任职', rows: currentAssignments },
                { label: '未来任职', rows: futureAssignments },
              ]"
              :key="group.label"
              ><h3 v-if="group.rows.length" class="mt-5">{{ group.label }}</h3>
              <article
                v-for="a in group.rows"
                :key="a.id"
                class="iamx-assignment"
                :class="{ 'iamx-primary-assignment': a.is_primary }"
              >
                <div class="iamx-actions">
                  <IamStatusBadge :presentation="assignmentStatusPresentation(a.state)" /><small>{{
                    a.is_primary ? '主职' : '兼任 / 支援'
                  }}</small>
                </div>
                <h3>{{ a.official_position_title }}</h3>
                <p>{{ a.org_name }} · {{ departmentName(a.department_code) }}</p>
                <small
                  >{{ formatBusinessDateTime(a.valid_from) }} 至
                  {{ a.valid_until ? formatBusinessDateTime(a.valid_until) : '长期' }}</small
                >
              </article></template
            ><IamDisclosure
              v-if="historyAssignments.length"
              :title="`历史任职 · ${historyAssignments.length}`"
              ><article v-for="a in historyAssignments" :key="a.id" class="iamx-assignment">
                <IamStatusBadge :presentation="assignmentStatusPresentation(a.state)" />
                <h3>{{ a.official_position_title }}</h3>
                <p>{{ a.org_name }} · {{ departmentName(a.department_code) }}</p>
                <small
                  >{{ formatBusinessDateTime(a.valid_from) }} 至
                  {{ a.valid_until ? formatBusinessDateTime(a.valid_until) : '长期' }}</small
                >
              </article></IamDisclosure
            ></TabsContent
          >
          <TabsContent value="sources"
            ><p class="iamx-notice">以下是授权来源记录；实际可用权限请通过“查看授权依据”核对。</p>
            <section v-for="group in sourceGroups" :key="group.label">
              <h3>{{ group.label }}</h3>
              <article v-for="b in group.rows" :key="b.id" class="iamx-assignment">
                <strong>{{ b.role_name }}</strong>
                <p>
                  {{
                    b.assignment_id
                      ? '关联任职：' +
                        (selected.assignments.find((a) => a.id === b.assignment_id)
                          ?.official_position_title || '待核实')
                      : group.label
                  }}
                  · 来源记录{{
                    b.state === 'active' ? '在用' : b.state === 'revoked' ? '已撤销' : b.state
                  }}
                  · {{ departmentName(b.department) }}
                </p>
                <small>{{
                  b.factory_ceiling ? b.factory_ceiling.map(orgName).join('、') : '保留原批准范围'
                }}</small>
              </article>
            </section>
            <h3 v-if="selected.overrides.length">个人例外来源</h3>
            <article v-for="o in selected.overrides" :key="o.id" class="iamx-assignment">
              <strong>个人例外 · {{ o.effect === 'deny' ? '明确禁止' : '单独允许' }}</strong>
              <p>{{ o.permission_code }} · {{ orgName(o.factory_id) }}</p>
            </article>
            <AccessExplanation
              v-if="catalog"
              :key="selected.id"
              :user-id="selected.id"
              :catalog="catalog"
              :default-factory="selected.primary_factory_id"
              :default-department="selected.primary_department" /><DelegationEditor
              v-if="catalog?.can_manage_delegations && selected.id !== auth.currentUser?.id"
              :key="selected.id"
              :user-id="selected.id"
              :catalog="catalog"
              :default-org="selected.primary_assignment?.org_unit_id || selected.primary_factory_id"
              :default-department="selected.primary_department"
          /></TabsContent>
          <TabsContent value="handover"
            ><p class="iamx-notice">
              已识别 {{ selected.handover.count }} 项责任，未覆盖模块仍需人工检查。
            </p>
            <ul class="iamx-coverage">
              <li v-for="item in selected.handover.coverage" :key="item.module">
                <strong>{{ item.module }}</strong
                ><span>{{
                  item.status === 'uncovered'
                    ? '需人工核实'
                    : item.status === 'role_queue'
                      ? '按当前角色队列办理'
                      : '已接入'
                }}</span
                ><small>{{ item.basis }}</small>
              </li>
            </ul>
            <RouterLink :to="`/system/iam/requests?person=${selected.id}`" class="iamx-link-button"
              >变更与交接记录</RouterLink
            ></TabsContent
          >
        </TabsRoot>
      </template>
      <template #footer
        ><RouterLink
          v-if="selected && !wizardOpen"
          :to="`/system/users/${selected.id}/access`"
          class="iamx-link-button"
          >个人例外与供应商授权</RouterLink
        >
        <div class="iam-actions">
          <Button v-if="wizardOpen" variant="outline" @click="leaveWizard">返回任职详情</Button
          ><Button
            v-else
            :disabled="detailLoading || !selected || !catalog?.writes_enabled"
            @click="wizardOpen = true"
            >{{ detailLoading ? '正在刷新任职…' : '办理变更' }}</Button
          >
        </div></template
      >
    </IamDialogSurface>
  </IdentityShell>
</template>
