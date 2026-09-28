<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Search, RefreshCw, X, BriefcaseBusiness, ArrowUpRight } from '@lucide/vue'
import { identityApi, stateLabels, type Person, type PersonIdentity, type OrganizationCatalog } from '@/api/identity'
import { getApiErrorMessage } from '@/lib/http'
import { formatBusinessDateTime } from '@/lib/dateTime'
import { useAuthStore } from '@/stores/auth'
import { Button } from '@/components/ui/button'
import IdentityShell from './IdentityShell.vue'
import IdentityWizard from './IdentityWizard.vue'
import AccessExplanation from './AccessExplanation.vue'
import DelegationEditor from './DelegationEditor.vue'
const route = useRoute(); const auth = useAuthStore()
const personStateLabels: Record<string, string> = { ...stateLabels, pending: '待审核' }
const catalog = ref<OrganizationCatalog>(); const people = ref<Person[]>([]); const total = ref(0)
const q = ref(''); const org = ref(''); const status = ref(''); const page = ref(1)
const loading = ref(false); const error = ref(''); const notice = ref(''); const selected = ref<PersonIdentity>()
const dialog = ref<HTMLDialogElement>(); const wizardOpen = ref(false); const dirty = ref(false); const detailLoading = ref(false)
let listGeneration = 0; let detailGeneration = 0
let dialogOpener: HTMLElement | undefined
const departmentName = (code: string) => catalog.value?.organizations.flatMap(o => o.departments).find(d => d.code === code)?.name || code || '部门待确认'
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / 30)))
async function load(reset = false) {
  if (reset) page.value = 1
  const generation = ++listGeneration; loading.value = true; error.value = ''
  try {
    if (!catalog.value) {
      const result = await identityApi.catalog()
      if (generation !== listGeneration) return
      catalog.value = result
    }
    const result = await identityApi.people({ q: q.value, org_unit_id: org.value, status: status.value, page: page.value })
    if (generation !== listGeneration) return
    people.value = result.items; total.value = result.total
  }
  catch (e) { if (generation === listGeneration) error.value = getApiErrorMessage(e) } finally { if (generation === listGeneration) loading.value = false }
}
async function inspect(id: string) {
  if (!dialog.value?.open && document.activeElement instanceof HTMLElement) dialogOpener = document.activeElement
  const generation = ++detailGeneration; detailLoading.value = true; error.value = ''; wizardOpen.value = false
  try { const result = await identityApi.person(id); if (generation !== detailGeneration) return; selected.value = result; await nextTick(); if (!dialog.value?.open) dialog.value?.showModal() }
  catch (e) { error.value = getApiErrorMessage(e) } finally { if (generation === detailGeneration) detailLoading.value = false }
}
function close(event?: Event) {
  if (dirty.value && !window.confirm('尚未确认办理。关闭后可到变更办理中查看已保存草稿。确定关闭？')) { event?.preventDefault(); return }
  event?.preventDefault()
  dirty.value = false; dialog.value?.close(); wizardOpen.value = false
  const opener = dialogOpener?.isConnected ? dialogOpener : [...document.querySelectorAll<HTMLElement>('[data-person-id]')].find(el => el.dataset.personId === selected.value?.id)
  opener?.focus()
}
function trapDialogFocus(event: KeyboardEvent) {
  if (event.key !== 'Tab' || !dialog.value) return
  const controls = [...dialog.value.querySelectorAll<HTMLElement>('button,a[href],input,select,textarea,summary,[tabindex]')]
    .filter(el => el.tabIndex >= 0 && !el.hasAttribute('disabled') && el.checkVisibility() &&
      (!el.closest('details:not([open])') || el.tagName === 'SUMMARY'))
  const first = controls[0]; const last = controls.at(-1)
  if (!first || !last) return
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}
function backToDetails() {
  if (dirty.value && !window.confirm('返回详情会关闭当前编辑，已保存草稿仍可在变更办理中查看。确定返回？')) return
  dirty.value = false; wizardOpen.value = false
}
async function saved() {
  dirty.value = false; wizardOpen.value = false; notice.value = '办理已保存，当前身份与交接状态已刷新。'
  if (selected.value) { const id = selected.value.id; await inspect(id); if (id === auth.currentUser?.id) await auth.refreshSession() }
  window.dispatchEvent(new Event('iam-identity-changed'))
  await load()
}
onMounted(async () => {
  try { await load(); if (!error.value && typeof route.query.person === 'string') await inspect(route.query.person) }
  catch (e) { error.value = getApiErrorMessage(e) }
})
</script>
<template>
  <IdentityShell>
    <template #actions><RouterLink to="/system/users/registration" class="iam-link-button">注册审核与密码找回 <ArrowUpRight :size="16" /></RouterLink></template>
    <p v-if="notice" role="status" class="iam-success">{{ notice }}</p>
    <p v-if="catalog && !catalog.writes_enabled" class="iam-notice">人员资料可查看。任职办理尚未启用，请先完成存量来源核实与授权模式验收。</p>
    <div class="iam-layout">
      <aside class="iam-organizations"><p class="iam-eyebrow">管理范围</p><h2>组织目录</h2><button :aria-pressed="!org" @click="org = ''; load(true)">全部可见人员</button><button v-for="o in catalog?.organizations.filter(o => o.kind !== 'group')" :key="o.id" :aria-pressed="org === o.id" @click="org = o.id; load(true)">{{ o.name }}<small>{{ o.kind === 'functional_unit' ? '集团职能' : '厂区' }}</small></button><p class="iam-muted">总务归属与业务操作范围分别管理。</p></aside>
      <section class="iam-panel" aria-label="人员列表"><div class="iam-panel-heading"><div><p class="iam-eyebrow">PEOPLE</p><h2>人员名册 <span>{{ total }}</span></h2></div><Button variant="outline" :disabled="loading" @click="load()"><RefreshCw :size="15" />刷新</Button></div>
        <form class="iam-filters" @submit.prevent="load(true)"><label class="iam-search"><Search :size="17" /><input v-model="q" placeholder="搜索姓名或账号" aria-label="搜索姓名或账号" /></label><select v-model="status" aria-label="账号状态" @change="load(true)"><option value="">全部状态</option><option value="active">在用</option><option value="suspended">冻结 / 停用</option><option value="left">离职</option><option value="pending">待审核</option></select><Button type="submit">查询</Button></form>
        <div v-if="error" role="alert" class="iam-error">{{ error }} <Button variant="outline" @click="load()">重试</Button></div>
        <p v-if="loading" role="status" class="iam-empty">正在读取人员资料…</p>
        <template v-else-if="!error"><p v-if="!people.length" class="iam-empty">{{ q || org || status ? '当前筛选没有匹配人员。请调整筛选条件。' : '当前管理范围没有人员。' }}</p>
          <div v-else class="iam-table"><div class="iam-table-head"><span>人员</span><span>正式主职</span><span>状态</span><span>详情</span></div><button v-for="person in people" :key="person.id" class="iam-person-row" :data-person-id="person.id" :disabled="detailLoading" @click="inspect(person.id)"><span class="iam-person-name"><span class="iam-avatar">{{ person.display_name.slice(-2) }}</span><span><strong>{{ person.display_name }}</strong><small>{{ person.username }}</small></span></span><span><strong>{{ person.position || '正式资料待确认' }}</strong><small>{{ catalog?.organizations.find(o => o.id === (person.primary_org_unit_id || person.primary_factory_id))?.name || '集团 / 未确认组织' }} · {{ departmentName(person.primary_department) }}</small></span><span class="iam-status">{{ personStateLabels[person.employment_status === 'left' ? 'left' : person.status] || person.status }}<small>{{ person.identity_mode === 'v2' ? '正式任职' : '来源待核实' }}</small></span><ArrowUpRight :size="18" /></button></div>
          <footer class="iam-pagination"><span>第 {{ page }} / {{ pageCount }} 页 · {{ total }} 人</span><div><Button variant="outline" :disabled="page <= 1" @click="page--; load()">上一页</Button><Button variant="outline" :disabled="page >= pageCount" @click="page++; load()">下一页</Button></div></footer>
        </template>
      </section>
    </div>
    <dialog ref="dialog" class="iam-workspace iam-inspector" aria-labelledby="person-title" @cancel="close" @keydown="trapDialogFocus"><template v-if="selected"><header><div><p class="iam-eyebrow">人员详情</p><h2 id="person-title">{{ selected.display_name }}</h2></div><Button variant="ghost" aria-label="关闭人员详情" @click="close()"><X :size="21" /></Button></header><div class="iam-inspector-body"><div class="iam-inspector-summary"><BriefcaseBusiness :size="22" /><div><strong>{{ selected.primary_assignment?.org_name || selected.primary_factory_id || '主组织待确认' }} · {{ selected.position || '无当前主职' }}</strong><p>{{ personStateLabels[selected.employment_status === 'left' ? 'left' : selected.status] || selected.status }} · {{ selected.active_assignments_summary.filter(a => !a.is_primary).length }} 项兼任</p></div></div>
      <div class="iam-actions"><Button :disabled="detailLoading || !catalog?.writes_enabled" @click="wizardOpen ? backToDetails() : wizardOpen = true">{{ detailLoading ? '正在刷新任职…' : wizardOpen ? '返回任职详情' : '办理变更' }}</Button><RouterLink :to="`/system/users/${selected.id}/access`" class="iam-link-button">个人例外与供应商授权</RouterLink><RouterLink :to="`/system/iam/requests?person=${selected.id}`" class="iam-link-button">变更与交接记录</RouterLink></div>
      <IdentityWizard v-if="wizardOpen && catalog && !detailLoading" :key="`${selected.id}:${selected.identity_version}`" :person="selected" :catalog="catalog" @saved="saved" @dirty="dirty = $event" />
      <template v-else><h3>任职时间线</h3><p v-if="!selected.assignments.length" class="iam-notice">尚未建立正式任职。请核实历史授权来源后确认，当前授权仍按原规则解释。</p><article v-for="a in [...selected.assignments].reverse()" :key="a.id" class="iam-assignment"><div><span class="iam-tag">{{ a.is_primary ? '主职' : '兼任 / 支援' }}</span><span>{{ stateLabels[a.state] || a.state }}</span></div><h3>{{ a.official_position_title }}</h3><p>{{ a.org_name }} · {{ departmentName(a.department_code) }}</p><small>{{ formatBusinessDateTime(a.valid_from) }} 至 {{ a.valid_until ? formatBusinessDateTime(a.valid_until) : '长期' }}</small><RouterLink v-if="a.source_request_id" :to="`/system/iam/requests?person=${selected.id}`">查看办理记录</RouterLink></article><h3>权限来源</h3><p>以下保留授权来源记录；实际可用权限请查看授权依据。</p><article v-for="b in selected.role_bindings" :key="b.id" class="iam-assignment"><strong>{{ b.role_name }}</strong><p>{{ b.assignment_id ? '关联任职：' + (stateLabels[selected.assignments.find(a => a.id === b.assignment_id)?.state || ''] || '待核实') : '独立授权来源' }} · 来源记录{{ stateLabels[b.state] || b.state }} · {{ departmentName(b.department) }}</p><small>{{ b.factory_ceiling ? b.factory_ceiling.map(f => catalog?.organizations.find(o => o.id === f)?.name || f).join('、') : '保留原批准范围' }}</small></article><AccessExplanation v-if="catalog" :user-id="selected.id" :catalog="catalog" /><DelegationEditor v-if="catalog?.can_manage_delegations && selected.id !== auth.currentUser?.id" :user-id="selected.id" :catalog="catalog" /><h3>工作交接覆盖</h3><p>已识别 {{ selected.handover.count }} 项责任，未覆盖模块仍需人工检查。</p><ul class="iam-coverage"><li v-for="item in selected.handover.coverage" :key="item.module"><strong>{{ item.module }}</strong><span>{{ item.status === 'uncovered' ? '需人工核实' : item.status === 'role_queue' ? '按当前角色队列办理' : '已接入' }}</span><small>{{ item.basis }}</small></li></ul></template>
    </div></template></dialog>
  </IdentityShell>
</template>
