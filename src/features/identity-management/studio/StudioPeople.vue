<script setup lang="ts">
import { computed, ref } from 'vue'
import { Building2, ChevronDown, ChevronLeft, ChevronRight, PanelLeftClose, PanelLeftOpen, UsersRound } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type { Person, OrganizationCatalog, OrgDepartmentCount } from '@/api/identity'
import { departmentName, lastLoginLabel } from '../positionLabels'
import { personOrg } from '../workspace/contracts'
import { personStatusPresentation } from '@/components/iam/workspace/iam-status'

const props = defineProps<{
  catalog?: OrganizationCatalog
  orgCounts?: OrgDepartmentCount[]
  people: Person[]
  org: string
  department: string
  page: number
  total: number | null
  loading: boolean
  failed: boolean
  locked: boolean
  editable?: boolean
  viewerId?: string
}>()
const emit = defineEmits<{
  select: [Person]
  manage: [Person]
  filter: [string, string]
  page: [number]
  task: [string]
}>()
const organizations = computed(
  () => props.catalog?.organizations.filter((o) => o.status === 'active' && o.kind !== 'group') || [],
)
const groups = computed(() =>
  [
    { name: '生产厂区', items: organizations.value.filter((o) => o.kind === 'factory') },
    { name: '集团职能', items: organizations.value.filter((o) => o.kind !== 'factory') },
  ].filter((group) => group.items.length),
)
const selectedOrg = computed(() => organizations.value.find((o) => o.id === props.org))
const treeCollapsed = ref(false)
function countLabel(orgId?: string, department?: string) {
  if (!props.orgCounts) return '—'
  const count = props.orgCounts.reduce((sum, row) =>
    (!orgId || orgId === row.org_unit_id) && (!department || department === row.department)
      ? sum + row.count : sum, 0)
  return count + ' 人'
}
const orgName = (id: string) => organizations.value.find((o) => o.id === id)?.name || id || '未登记'
const canConfigure = (p: Person) =>
  props.editable &&
  p.id !== props.viewerId &&
  p.status === 'active' &&
  (p.employment_status === 'active' ||
    (p.identity_mode === 'legacy' && p.employment_status === 'unconfirmed'))
const selection = computed(() =>
  [selectedOrg.value?.name || props.org, props.department ? departmentName(props.department) : '']
    .filter(Boolean)
    .join(' · '),
)
function readPerson(p: Person) {
  if (!props.locked) emit('select', p)
}
</script>
<template>
  <div class="iam2-people personnel-directory" :class="{ 'tree-collapsed': treeCollapsed }">
    <nav class="iam2-org personnel-org" aria-label="按组织和部门筛选">
      <header>
        <Building2 :size="16" aria-hidden="true" />
        <h2>组织架构</h2>
        <button class="personnel-tree-toggle" type="button" aria-controls="personnel-tree"
          :aria-expanded="!treeCollapsed" :aria-label="treeCollapsed ? '展开组织树' : '收起组织树'"
          :title="treeCollapsed ? '展开组织树' : '收起组织树'" @click="treeCollapsed = !treeCollapsed">
          <component :is="treeCollapsed ? PanelLeftOpen : PanelLeftClose" :size="16" aria-hidden="true" />
        </button>
      </header>
      <div id="personnel-tree" class="personnel-tree">
        <button
          type="button"
          class="personnel-node"
          :aria-pressed="!org"
          :disabled="locked"
          @click="emit('filter', '', '')"
        >
          <UsersRound :size="15" aria-hidden="true" />全部可见人员
          <small class="personnel-count">{{ countLabel() }}</small>
        </button>
        <section v-for="group in groups" :key="group.name">
          <h3>
            {{ group.name }}<span>{{ group.items.length }}</span>
          </h3>
          <div v-for="o in group.items" :key="o.id">
            <button
              type="button"
              class="personnel-node"
              :aria-pressed="org === o.id && !department"
              :aria-expanded="o.departments.length ? org === o.id : undefined"
              :disabled="locked"
              @click="emit('filter', o.id, '')"
            >
              <span>{{ o.name }}</span><small class="personnel-count">{{ countLabel(o.id) }}</small>
              <ChevronDown v-if="o.departments.length" :size="13" aria-hidden="true" />
            </button>
            <div v-if="org === o.id && o.departments.length" class="iam2-departments">
              <button
                v-for="d in o.departments"
                :key="d.code"
                type="button"
                :aria-pressed="department === d.code"
                :disabled="locked"
                @click="emit('filter', o.id, d.code)"
              >
                {{ d.name }}<small class="personnel-count">{{ countLabel(o.id, d.code) }}</small>
              </button>
            </div>
          </div>
        </section>
      </div>
      <div class="personnel-mobile-org">
        <select
          aria-label="筛选组织"
          :value="org"
          :disabled="locked"
          @change="emit('filter', ($event.target as HTMLSelectElement).value, '')"
        >
          <option value="">全部可见人员 · {{ countLabel() }}</option>
          <optgroup v-for="group in groups" :key="group.name" :label="group.name">
            <option v-for="o in group.items" :key="o.id" :value="o.id">{{ o.name }} · {{ countLabel(o.id) }}</option>
          </optgroup>
        </select>
        <select
          v-if="selectedOrg?.departments.length"
          aria-label="筛选部门"
          :value="department"
          :disabled="locked"
          @change="emit('filter', org, ($event.target as HTMLSelectElement).value)"
        >
          <option value="">全部部门</option>
          <option v-for="d in selectedOrg.departments" :key="d.code" :value="d.code">{{ d.name }} · {{ countLabel(org, d.code) }}</option>
        </select>
      </div>
    </nav>
    <section class="iam2-directory" aria-label="人员目录">
      <header class="personnel-toolbar">
        <slot name="filters"
          ><h2>{{ selection || '全部人员' }}</h2></slot
        >
        <span class="personnel-result" aria-live="polite">{{
          total === null ? '数量待核对' : '共 ' + total + ' 人'
        }}</span>
      </header>
      <div v-if="loading" class="pw-empty" role="status">正在读取人员与权限…</div>
      <div v-else-if="failed" class="pw-empty" role="status">人员目录暂不可用</div>
      <div v-else-if="!people.length" class="pw-empty">当前筛选下没有可见人员。</div>
      <div v-else class="iam2-table-scroll">
        <table class="iam2-table personnel-table">
          <colgroup>
            <col class="col-person" />
            <col class="col-position" />
            <col class="col-packages" />
            <col class="col-factories" />
            <col class="col-status" />
            <col class="col-action" />
          </colgroup>
          <thead>
            <tr>
              <th scope="col">人员 / 账号</th>
              <th scope="col">正式主职与归属</th>
              <th scope="col">当前生效权限包</th>
              <th scope="col">业务覆盖厂区</th>
              <th scope="col">状态 / 待办</th>
              <th scope="col">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in people" :key="p.id" @click="readPerson(p)">
              <td data-label="人员">
                <button
                  class="iam2-name"
                  :data-iam-person="p.id"
                  type="button"
                  :disabled="locked"
                  @click.stop="readPerson(p)"
                >
                  <span
                    aria-hidden="true"
                    class="personnel-avatar"
                    :data-mode="p.identity_mode"
                    :data-status="p.status"
                    >{{ p.display_name.slice(0, 1) }}</span
                  >
                  <span
                    ><strong>{{ p.display_name }}</strong
                    ><small>@{{ p.username }}</small></span
                  >
                </button>
              </td>
              <td data-label="主职与归属">
                <div>
                  <strong>{{ p.position || '岗位待确认' }}</strong>
                  <small>{{ orgName(personOrg(p)) }} · {{ departmentName(p.primary_department) }}</small>
                  <span
                    v-if="p.employment_status === 'left' || p.employment_status === 'frozen'"
                    class="personnel-chip"
                    data-tone="warning"
                    >{{ p.employment_status === 'left' ? '已离职' : '已冻结' }}</span
                  >
                </div>
              </td>
              <td data-label="有效权限包">
                <div class="personnel-tags">
                  <template v-if="p.access_summary">
                    <span
                      v-for="b in p.access_summary.active_packages"
                      :key="b.binding_id"
                      class="personnel-chip"
                      :data-tone="b.version_outdated ? 'info' : 'jade'"
                      :title="b.role_version_id || undefined"
                      >{{ b.role_name }}{{ b.version_outdated ? ' · 旧版' : '' }}</span
                    >
                    <span
                      v-if="!p.access_summary.active_packages.length"
                      class="personnel-chip"
                      data-tone="warning"
                      >未配置权限包</span
                    >
                    <span
                      v-if="p.access_summary.override_counts?.allow"
                      class="personnel-chip"
                      data-tone="info"
                      >+{{ p.access_summary.override_counts.allow }} 个人允许</span
                    >
                    <span
                      v-if="p.access_summary.override_counts?.deny"
                      class="personnel-chip"
                      data-tone="danger"
                      >{{ p.access_summary.override_counts.deny }} 明确禁止</span
                    > </template
                  ><span v-else class="personnel-muted">暂不可用</span>
                  <span v-if="p.identity_mode === 'legacy'" class="personnel-chip" data-tone="warning"
                    >历史来源待确认</span
                  >
                </div>
              </td>
              <td data-label="业务厂区">
                <div class="personnel-tags">
                  <span
                    v-for="factory in p.access_summary?.effective_factories"
                    :key="factory"
                    class="personnel-chip"
                    >{{ orgName(factory) }}</span
                  >
                  <span v-if="!p.access_summary?.effective_factories.length" class="personnel-muted">{{
                    p.access_summary ? '无业务厂区' : '暂不可用'
                  }}</span>
                </div>
              </td>
              <td data-label="状态 / 待办">
                <div class="personnel-status">
                  <span
                    class="personnel-chip personnel-state"
                    :data-tone="personStatusPresentation(p.status).tone"
                    >{{ personStatusPresentation(p.status).label }}</span
                  >
                  <button
                    v-if="p.access_summary?.open_task"
                    type="button"
                    class="personnel-chip personnel-task"
                    data-tone="warning"
                    :disabled="locked"
                    @click.stop="emit('task', p.access_summary.open_task.key)"
                  >
                    {{ p.access_summary.open_task.summary }} →
                  </button>
                  <small
                    v-else-if="p.access_summary?.task_coverage_complete"
                    :title="'最近登录 ' + lastLoginLabel(p.last_login_at)"
                    >无待办</small
                  >
                  <small v-else>部分来源不可见</small>
                </div>
              </td>
              <td data-label="操作">
                <button
                  v-if="canConfigure(p)"
                  class="personnel-open"
                  type="button"
                  :disabled="locked"
                  @click.stop="emit('manage', p)"
                >
                  配置权限
                </button>
                <button
                  v-else
                  class="personnel-open"
                  type="button"
                  :disabled="locked"
                  @click.stop="readPerson(p)"
                >
                  查看权限
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <footer class="iw-pagination">
        <span>第 {{ page }} 页</span>
        <div>
          <Button variant="ghost" :disabled="page <= 1 || locked || loading" @click="emit('page', page - 1)"
            ><ChevronLeft :size="15" />上一页</Button
          >
          <Button
            variant="ghost"
            :disabled="locked || loading || total === null || page * 30 >= total"
            @click="emit('page', page + 1)"
            >下一页<ChevronRight :size="15"
          /></Button>
        </div>
      </footer>
    </section>
  </div>
</template>
<style src="./personnel-directory.css"></style>
