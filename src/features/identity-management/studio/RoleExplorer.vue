<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { iamApi, type RoleAccessResponse, type RoleSummary, type PermissionCatalogItem } from '@/api/iam'
import type { StudioPackage } from '@/api/accessStudio'
import { http, getApiErrorMessage } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'
import { factoryContexts } from '@/data/enterpriseMock'
import { permissionDisplayLabel, roleScopeModeLabel } from '@/components/iam/permissionCatalogLabels'
import { departmentName } from '../positionLabels'

const props = defineProps<{
  role: RoleAccessResponse
  summary?: RoleSummary
  roles: RoleSummary[]
  permissions: PermissionCatalogItem[]
  module: string
}>()
const emit = defineEmits<{ filter: [module: string]; definition: [] }>()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const memberTab = computed(() => route.query.tab === 'members')
const comparisonId = computed(() => typeof route.query.compare === 'string' && route.query.compare !== props.role.id ? route.query.compare : '')
const canReadPeople = computed(() => auth.can('system:user_manage'))
const viewer = computed(() => [auth.currentUser?.id, auth.authorizationVersion, auth.currentUser?.identity?.employment_epoch, auth.currentUser?.identity?.effective_context_key].join(':'))
const peer = ref<RoleAccessResponse>()
const comparing = ref(false)
const compareError = ref('')
const members = ref<MemberPage>()
const memberError = ref('')
const loading = ref(false)
const query = ref('')
const submittedQuery = ref('')
const page = ref(1)
const outdated = ref(false)
const retry = ref(0)
interface MemberPage {
  members_restricted: boolean
  total: number | null
  items: {
    user_id: string
    display_name: string
    username: string
    position: string
    primary_org_unit_id: string
    primary_department: string
    bindings: StudioPackage[]
  }[]
}
function factoryName(id: string) {
  if (id === '*') return '全局范围'
  if (id === 'group-management') return '集团总务'
  return factoryContexts.find(factory => factory.id === id)?.shortName || id
}
function scopeText(binding: StudioPackage) {
  if (binding.factory_ceiling == null) return '原批准范围 · ' + factoryName(binding.factory_id)
  return binding.factory_ceiling.map(factoryName).join('、') || '无业务厂区'
}
function searchMembers() {
  page.value = 1
  submittedQuery.value = query.value.trim()
}
function navigate(tab: string, compare = '') {
  void router.replace({ query: { ...route.query, role: props.role.id, tab, compare: compare || undefined } })
}
watch([() => props.role.id, comparisonId, viewer, retry], async (_, __, cleanup) => {
  let current = true
  cleanup(() => { current = false })
  peer.value = undefined
  compareError.value = ''
  comparing.value = false
  const id = comparisonId.value
  if (!id) return
  if (!props.roles.some(role => role.id === id)) {
    compareError.value = '对比方案不存在或不可见。'
    return
  }
  comparing.value = true
  try {
    const result = await iamApi.getRoleAccess(id)
    if (current) peer.value = result
  } catch (error) {
    if (current) compareError.value = getApiErrorMessage(error)
  } finally {
    if (current) comparing.value = false
  }
}, { immediate: true })

watch([() => props.role.id, memberTab, viewer], () => {
  page.value = 1
  query.value = ''
  submittedQuery.value = ''
  outdated.value = false
}, { flush: 'sync' })
watch([memberTab, comparisonId, () => props.role.id, viewer, canReadPeople, page, submittedQuery, outdated, retry], async (_, __, cleanup) => {
  const controller = new AbortController()
  cleanup(() => controller.abort())
  members.value = undefined
  memberError.value = ''
  loading.value = false
  if (!memberTab.value || comparisonId.value || !canReadPeople.value) return
  loading.value = true
  try {
    const result = await http.get<MemberPage>(`/iam/roles/${encodeURIComponent(props.role.id)}/members`, {
      params: { q: submittedQuery.value, page: page.value, page_size: 30, only_outdated: outdated.value }, signal: controller.signal })
    if (!controller.signal.aborted) members.value = result.data
  } catch (error) {
    if (!controller.signal.aborted) memberError.value = getApiErrorMessage(error)
  } finally {
    if (!controller.signal.aborted) loading.value = false
  }
}, { immediate: true })
const coverage = computed(() => {
  const included = new Set(props.role.permission_codes)
  const groups = new Map<string, {code: string; name: string; count: number; total: number}>()
  for (const permission of props.permissions) {
    const group = groups.get(permission.module_code) ?? { code: permission.module_code, name: permission.module_name, count: 0, total: 0 }
    group.total++
    if (included.has(permission.code)) group.count++
    groups.set(group.code, group)
  }
  return [...groups.values()]
})
const comparison = computed(() => {
  if (!peer.value) return []
  const left = new Set(props.role.permission_codes)
  const right = new Set(peer.value.permission_codes)
  const directory = new Map(props.permissions.map(permission => [permission.code, permission]))
  return [
    { key: 'left', name: '仅「' + props.role.name + '」拥有', codes: [...left].filter(code => !right.has(code)) },
    { key: 'common', name: '两方案共同拥有', codes: [...left].filter(code => right.has(code)) },
    { key: 'right', name: '仅「' + peer.value.name + '」拥有', codes: [...right].filter(code => !left.has(code)) },
  ].map(group => {
    const modules = new Map<string, {code: string; name: string}[]>()
    for (const code of group.codes) {
      const permission = directory.get(code)
      const name = permission?.module_name || '目录异常'
      const items = modules.get(name) ?? []
      items.push({ code, name: permission ? permissionDisplayLabel(permission) : code })
      modules.set(name, items)
    }
    return { ...group, modules: [...modules.entries()] }
  })
})
</script>
<template>
  <section class="iam-role-detail" data-testid="role-viewer-panel">
    <header class="iam-role-banner" data-testid="role-summary-panel">
      <div class="iam-role-intro">
        <div class="iam-role-title"><h2>{{ role.name }}</h2>
          <span class="iam-catalog-badge tone-blue">{{ roleScopeModeLabel(role.scope_mode) }}</span>
          <span v-if="role.definition_version" class="iam-catalog-badge iam-version">{{ role.definition_version }}</span>
          <span class="iam-catalog-badge tone-green">{{ role.permission_codes.length }} / {{ permissions.length }} 权限</span>
          <template v-if="canReadPeople && summary?.scoped_binding_count != null && summary?.scoped_member_count != null">
            <span class="iam-catalog-badge">{{ summary.scoped_binding_count }} 条可见绑定</span>
            <span class="iam-catalog-badge">{{ summary.scoped_member_count }} 名可见成员（去重）</span>
          </template>
        </div>
        <p>{{ [role.position_department_name, role.description || role.code].filter(Boolean).join(' · ') }}</p>
      </div>
      <div class="iam-role-actions">
        <select aria-label="对比另一方案" :value="comparisonId" @change="navigate('permissions', ($event.target as HTMLSelectElement).value)">
          <option value="">对比另一方案…</option>
          <option v-for="item in roles.filter(item => item.id !== role.id)" :key="item.id" :value="item.id">{{ item.position_department_name }} {{ item.name }}</option>
        </select>
        <button type="button" class="iam-role-definition" data-testid="definition-details-trigger" @click="emit('definition')">查看定义信息</button>
      </div>
      <p v-if="role.id === 'position_general_manager'" class="iam-role-boundary" data-testid="general-manager-boundary">跨厂操作 · 全业务部门。此方案不包含账号与权限管理，业务状态、审批隔离、版本校验和审计规则仍然生效。</p>
    </header>

    <div v-if="comparisonId" class="iam-role-compare">
      <div class="iam-compare-banner"><span><strong>方案对比</strong> · {{ role.name }} <template v-if="peer">与 {{ peer.name }}</template></span><button @click="navigate('permissions')">退出对比</button></div>
      <p v-if="comparing" class="iam-catalog-notice" role="status">正在读取对比方案…</p>
      <p v-else-if="compareError" class="iam-catalog-notice" role="alert">{{ compareError }} <button @click="retry++">重试</button></p>
      <div v-else class="iam-comparison-columns">
        <section v-for="group in comparison" :key="group.key" :class="'iam-compare-' + group.key">
          <h3>{{ group.name }} <b>{{ group.codes.length }}</b></h3>
          <div v-for="[moduleName, items] in group.modules" :key="moduleName" class="iam-compare-group"><h4>{{ moduleName }}</h4><ul><li v-for="item in items" :key="item.code" :title="item.code">{{ item.name }}</li></ul></div>
          <p v-if="!group.codes.length" class="iam-catalog-notice">无匹配能力</p>
        </section>
      </div>
    </div>
    <template v-else>
      <div v-if="!memberTab" class="iam-role-coverage" aria-label="模块覆盖">
        <button type="button" :aria-pressed="module === 'all'" @click="emit('filter', 'all')">全部模块</button>
        <button v-for="group in coverage" :key="group.code" type="button" :class="{ full: group.count === group.total, uncovered: !group.count }" :aria-pressed="module === group.code" @click="emit('filter', module === group.code ? 'all' : group.code)">
          {{ group.name }} <b>{{ group.count }}/{{ group.total }}</b>
        </button>
      </div>
      <nav class="iam-role-tabs" aria-label="方案详情">
        <button type="button" :aria-pressed="!memberTab" @click="navigate('permissions')">能力清单</button>
        <button type="button" :aria-pressed="memberTab" @click="navigate('members')">已绑定人员<template v-if="canReadPeople && summary?.scoped_member_count != null">（{{ summary.scoped_member_count }} 人）</template></button>
      </nav>
      <template v-if="!memberTab"><slot name="filters" /><slot /></template>
      <section v-else class="iam-role-members">
        <p v-if="!canReadPeople || members?.members_restricted" class="iam-catalog-notice">成员资料受保护。</p>
        <template v-else>
          <form class="iam-member-filters" @submit.prevent="searchMembers">
            <input v-model="query" type="search" aria-label="搜索绑定人员" placeholder="搜索姓名或账号">
            <button type="submit">查询</button>
            <label><input v-model="outdated" type="checkbox" @change="page = 1">仅旧版本</label>
            <span v-if="members">当前筛选可见 {{ members.total ?? '—' }} 人</span>
          </form>
          <p v-if="loading" class="iam-catalog-notice" role="status">正在读取绑定人员…</p>
          <p v-else-if="memberError" class="iam-catalog-notice" role="alert">{{ memberError }} <button @click="retry++">重试</button></p>
          <template v-else-if="members">
            <div v-if="members.items.length" class="iam-members-scroll">
              <table><thead><tr><th>员工</th><th>归属组织 / 岗位</th><th>绑定来源与业务厂区</th><th>操作</th></tr></thead>
                <tbody>
                  <tr v-for="member in members.items" :key="member.user_id">
                    <td><strong>{{ member.display_name }}</strong><small>@{{ member.username }}</small></td>
                    <td>{{ factoryName(member.primary_org_unit_id) || '未登记' }}<small>{{ [departmentName(member.primary_department), member.position].filter(Boolean).join(' · ') }}</small></td>
                    <td><details><summary>{{ member.bindings.length }} 条绑定来源 <span v-if="member.bindings.some(b => b.version_outdated)" class="iam-catalog-badge tone-amber">含旧版本</span></summary>
                      <ul><li v-for="binding in member.bindings" :key="binding.binding_id">
                        <strong>{{ binding.assignment_id ? '关联任职' : binding.source_type === 'legacy_import' ? '历史来源' : '独立来源' }} · {{ departmentName(binding.department) }}</strong>
                        <small>{{ scopeText(binding) }}</small>
                        <small>{{ binding.version_outdated ? '旧版本' : binding.role_version_id ? '已固定版本' : '未固定版本' }} {{ binding.role_version_id }}</small>
                        <RouterLink v-if="binding.version_outdated && auth.can('system:access_manage')" :to="{path:'/system/users',query:{view:'people',person:member.user_id,panel:'manage',tab:'packages',binding:binding.binding_id}}">定位此旧绑定</RouterLink>
                      </li></ul></details></td>
                    <td><RouterLink :to="{path:'/system/users',query:{view:'people',person:member.user_id,panel:'profile',tab:'packages'}}">查看人员与授权</RouterLink></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p v-else class="iam-catalog-notice">当前筛选没有可见成员。</p>
            <div v-if="page > 1 || (members.total ?? 0) > 30" class="iam-member-pagination"><button :disabled="page === 1" @click="page--">上一页</button><span>第 {{ page }} 页</span><button :disabled="page * 30 >= (members.total ?? 0)" @click="page++">下一页</button></div>
          </template>
        </template>
      </section>
    </template>
  </section>
</template>
