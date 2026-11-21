<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import IamDialogSurface from '@/components/iam/workspace/IamDialogSurface.vue'
import { BriefcaseBusiness, ShieldCheck, Send, ArrowLeft } from '@lucide/vue'
import { positionReviewsApi as api, positionStatus, type Declaration, type PositionReview, type SelfPositionProfile } from '@/api/positionReviews'
import type { OrganizationCatalog } from '@/api/identity'
import { useAuthStore } from '@/stores/auth'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { formatBusinessDateTime } from '@/lib/dateTime'
import './position-workbench.css'
import './studio/self-access.css'
import { iamStudioEnabled } from '@/components/iam/workspace/iam-navigation'
import SelfAccess from './studio/SelfAccess.vue'
import { departmentName, permissionName } from './positionLabels'
const auth = useAuthStore(), data = ref<SelfPositionProfile>(), catalog = ref<OrganizationCatalog>(), history = ref<PositionReview[]>([])
const draft = ref<Declaration>({ org_unit_id: '', department_code: '', position: '', note: '' })
const editing = ref(false), loading = ref(false), busy = ref(false), error = ref(''), notice = ref(''), showPermissions = ref(false)
const historyPage = ref(1), historyTotal = ref(0)
const positionInput = ref<HTMLInputElement>(), editButton = ref<InstanceType<typeof Button>>(), errorPanel = ref<HTMLElement>(), noticePanel = ref<HTMLElement>()
let generation = 0
let alive = true
const dialog = ref<InstanceType<typeof IamDialogSurface>>()
const originalDraft = ref('')
const editingReview = ref<PositionReview | null>(null)
const reviewKey = (row?: PositionReview | null) => row ? row.id + ':' + row.revision : ''
const dirty = computed(() => editing.value && JSON.stringify(draft.value) !== originalDraft.value)
const changedOnServer = computed(() => editing.value && reviewKey(editingReview.value) !== reviewKey(data.value?.open_review))
const valid = computed(() => !!draft.value.position.trim() && (!iamStudioEnabled || (!!draft.value.note.trim() && !changedOnServer.value)))
const packages = computed(() => [...new Map(data.value?.current_packages?.map(pack => [pack.role_id, pack])).values()])
const referenceQuery = ref('')
const referencePackages = computed(() => {
  const query = referenceQuery.value.trim().toLocaleLowerCase()
  return (data.value?.reference_packages ?? []).filter(pack =>
    [pack.name, pack.role_id, departmentName(pack.department_code), pack.description]
      .some(value => value?.toLocaleLowerCase().includes(query)))
})
watch(editing, async value => { await nextTick(); if (value) positionInput.value?.focus(); else if (!notice.value && !error.value) editButton.value?.$el?.focus() })
watch(error, async value => { if (value) { await nextTick(); errorPanel.value?.focus() } })
watch(notice, async value => { if (value) { await nextTick(); noticePanel.value?.focus() } })
const viewer = computed(() => `${auth.currentUser?.id ?? ''}:${auth.currentUser?.identity?.employment_epoch ?? ''}`)
const viewerContext = computed(() => iamStudioEnabled ? viewer.value + ':' + auth.authorizationVersion + ':' + auth.currentUser?.identity?.effective_context_key : viewer.value)
const organizations = computed(() => catalog.value?.organizations.filter(o => o.kind !== 'group' && o.status === 'active') ?? [])
const departments = computed(() => organizations.value.find(o => o.id === draft.value.org_unit_id)?.departments ?? [])
const orgName = (id: string) => organizations.value.find(o => o.id === id)?.name || id
async function load(preserve = false) {
  const current = ++generation, identity = viewerContext.value
  loading.value = true; error.value = ''
  try {
    const [profile, directory, records] = await Promise.all([api.profile(), api.catalog(), api.history()])
    if (current !== generation || identity !== viewerContext.value) return
    data.value = profile; catalog.value = directory; history.value = records.items; historyPage.value = 1; historyTotal.value = records.total
    if (!preserve) draft.value = { ...(profile.open_review?.declaration || profile.official_position || { org_unit_id: '', department_code: '', position: '' }), note: profile.open_review?.declaration.note || '', ...(iamStudioEnabled ? { requested_role_ids: [...(profile.open_review?.declaration.requested_role_ids || [])], requested_factory_ids: [...(profile.open_review?.declaration.requested_factory_ids || [])] } : {}) }
  } catch (e) { if (current === generation) { error.value = getApiErrorMessage(e); if ([401, 403].includes((e as { response?: { status?: number } }).response?.status ?? 0)) { data.value = undefined; history.value = [] } } }
  finally { if (current === generation) loading.value = false }
}
async function save() {
  if (busy.value || !data.value?.can_submit || !valid.value) return
  const identity = viewerContext.value
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const declaration = { ...draft.value, position: draft.value.position.trim(), note: draft.value.note.trim() }
    const target = iamStudioEnabled ? editingReview.value : data.value.open_review
    const result = target ? await api.edit(target, declaration) : await api.submit(declaration)
    if (identity !== viewerContext.value) return
    notice.value = result.message; editing.value = false; await load()
  } catch (e) { if (alive && identity === viewerContext.value) { if ((e as { response?: { status?: number } }).response?.status === 409) await load(true); if (alive && identity === viewerContext.value) error.value = getApiErrorMessage(e) } }
  finally { if (alive && identity === viewerContext.value) busy.value = false }
}
async function withdraw() {
  const row = data.value?.open_review
  if (!row || busy.value) return
  const identity = viewerContext.value
  busy.value = true
  try { const result = await api.withdraw(row); if (identity !== viewerContext.value) return; notice.value = result.message; editing.value = false; await load() }
  catch (e) { if (identity === viewerContext.value) error.value = getApiErrorMessage(e) }
  finally { if (identity === viewerContext.value) busy.value = false }
}
async function moreHistory() {
  const current = generation, identity = viewerContext.value
  try { const records = await api.history(historyPage.value + 1); if (current !== generation || identity !== viewerContext.value) return; history.value.push(...records.items); historyPage.value++; historyTotal.value = records.total }
  catch (e) { if (current === generation) error.value = getApiErrorMessage(e) }
}
function startEditing() {
  referenceQuery.value = ''
  const open = data.value?.open_review?.declaration
  const official = data.value?.official_position
  draft.value = {
    org_unit_id: open?.org_unit_id ?? official?.org_unit_id ?? '',
    department_code: open?.department_code ?? official?.department_code ?? '',
    position: open?.position ?? official?.position ?? '',
    note: open?.note ?? '',
    ...(iamStudioEnabled ? {requested_role_ids: [...(open?.requested_role_ids ?? [])],
      requested_factory_ids: [...(open?.requested_factory_ids ?? [])]} : {}),
  }
  editingReview.value = data.value?.open_review ?? null
  originalDraft.value = JSON.stringify(draft.value)
  editing.value = true
}
function cancelEdit() {
  if (iamStudioEnabled) void dialog.value?.requestClose()
  else editing.value = false
}
if (iamStudioEnabled) onBeforeRouteLeave(() => editing.value ? dialog.value?.permitLeave() ?? false : true)
function beforeUnload(event: BeforeUnloadEvent) {
  if (iamStudioEnabled && (dirty.value || busy.value)) { event.preventDefault(); event.returnValue = '' }
}
function organizationChanged() { if (!departments.value.some(d => d.code === draft.value.department_code)) draft.value.department_code = departments.value[0]?.code || '' }
function refresh() { if (document.visibilityState === 'visible' && !busy.value) { void auth.refreshSession(); void load(editing.value) } }
let lastViewer = viewer.value
watch(viewerContext, () => {
  const preserve = iamStudioEnabled && lastViewer === viewer.value && editing.value && !busy.value
  lastViewer = viewer.value
  ++generation
  if (!preserve) { data.value = undefined; history.value = []; editing.value = false }
  busy.value = false; notice.value = ''; void load(preserve)
})
let polling = false, timer: number | undefined
const progressError = ref('')
async function pollProgress() {
  if (document.visibilityState !== 'visible' || loading.value || busy.value || polling || !data.value) return
  const current = generation
  polling = true
  try {
    const page = await api.history(1, 1)
    if (current !== generation || busy.value) return
    progressError.value = ''
    if (reviewKey(page.items[0]) !== reviewKey(history.value[0]) || page.total !== historyTotal.value) await load(editing.value)
  } catch (e) {
    if (current === generation) progressError.value = '申请进度暂时未能同步。' + getApiErrorMessage(e)
  } finally { polling = false }
}
onMounted(() => {
  void load()
  window.addEventListener('focus', refresh)
  window.addEventListener('authorization-context-changed', refresh)
  window.addEventListener('beforeunload', beforeUnload)
  if (iamStudioEnabled) timer = window.setInterval(pollProgress, 30000)
})
onBeforeUnmount(() => {
  alive = false; ++generation; window.clearInterval(timer)
  window.removeEventListener('focus', refresh)
  window.removeEventListener('authorization-context-changed', refresh)
  window.removeEventListener('beforeunload', beforeUnload)
})
</script>
<template>
  <header v-if="iamStudioEnabled" class="self-nav">
    <RouterLink to="/"><ArrowLeft :size="16" />返回工作台</RouterLink>
    <strong><ShieldCheck :size="21" />权限与组织</strong>
    <span>员工自助</span>
  </header>
  <main class="pw-root pw-self" :class="{ 'self-studio': iamStudioEnabled }"><RouterLink v-if="!iamStudioEnabled" to="/" class="pw-back-link"><ArrowLeft :size="16" />返回工作区</RouterLink><header v-if="!iamStudioEnabled" class="pw-heading"><div><h1>我的岗位与权限</h1><p>告诉管理员你现在做什么，权限由管理员核对后调整。</p></div><BriefcaseBusiness :size="30" /></header><p v-if="notice" ref="noticePanel" tabindex="-1" class="pw-notice" role="status">{{ notice }}</p><p v-if="error" ref="errorPanel" tabindex="-1" class="pw-error" role="alert">{{ error }}<Button variant="outline" @click="load(editing)">重新读取</Button></p><p v-if="loading && !data" class="pw-empty" role="status">正在读取岗位资料…</p>
    <template v-if="data">
      <section v-if="iamStudioEnabled" class="self-identity">
        <div class="self-identity-copy">
          <p class="self-kicker"><BriefcaseBusiness :size="16" />我的岗位与权限</p>
          <h1>{{ auth.currentUser?.display_name || auth.currentUser?.username }}<span v-if="auth.currentUser"> · </span>{{ data.official_position?.position || '岗位待管理员确认' }}</h1>
          <p class="self-byline">
            <span v-if="data.official_position">{{ orgName(data.official_position.org_unit_id) }} · {{ departmentName(data.official_position.department_code) }}</span>
            <span v-if="auth.currentUser?.username">@{{ auth.currentUser.username }}</span>
          </p>
          <ul v-if="packages.length" class="self-pills" aria-label="生效权限包"><li v-for="pack in packages" :key="pack.role_id"><ShieldCheck :size="13" /><span>{{ pack.role_name }}<small v-if="pack.description">{{ pack.description }}</small></span></li></ul>
          <span v-else class="self-no-pack">{{ data.current_packages ? '当前没有生效的权限包' : '权限包明细暂不可用' }}</span>
          <p class="self-factory-list"><strong>有效业务厂区</strong> {{ data.effective_business_factories?.map(f => f.name).join('、') || (data.effective_business_factories ? '暂无' : '暂不可用') }}</p>
        </div>
        <div class="self-edit"><Button v-if="!editing" ref="editButton" type="button" :disabled="!data.can_submit" @click="startEditing"><BriefcaseBusiness :size="15" />{{ data.open_review ? '修改待处理内容' : '修改岗位' }}</Button>
          <small>{{ data.blocked_reason || '岗位申请由管理员核对后生效' }}</small>
        </div>
      </section>
      <section v-else class="pw-self-card"><span class="pw-eyebrow">当前确认岗位</span><h2>{{ data.official_position?.position || '岗位待管理员确认' }}</h2><p v-if="data.official_position">{{ orgName(data.official_position.org_unit_id) }} · {{ organizations.flatMap(o => o.departments).find(d => d.code === data?.official_position?.department_code)?.name }}</p><Button v-if="!editing" ref="editButton" type="button" :disabled="!data.can_submit" @click="startEditing">{{ data.open_review ? '修改待处理内容' : '修改岗位' }}</Button><p v-if="data.blocked_reason" class="pw-notice">{{ data.blocked_reason }}</p></section>
      <section v-if="data.open_review" class="pw-self-card pw-pending"><span class="pw-badge">{{ positionStatus[data.open_review.status] }}</span><h2>我提交的岗位：{{ data.open_review.declaration.position }}</h2><p>管理员确认前，正式岗位和权限保持不变。</p><p v-if="data.open_review.origin === 'admin'">管理员正在核对，更新资料后将重新核对。</p><p v-if="data.open_review.review_comment" class="pw-notice">处理意见：{{ data.open_review.review_comment }}</p><small>{{ formatBusinessDateTime(data.open_review.updated_at) }}</small><Button variant="ghost" :disabled="busy || !data.can_submit" @click="withdraw">撤回岗位更新</Button></section>
      <component v-if="editing" :is="iamStudioEnabled ? IamDialogSurface : 'div'" ref="dialog"
        :open="editing" title="修改岗位" description="填写实际岗位与申请原因，交由管理员核对。"
        :dirty="dirty" :busy="busy" @update:open="editing = $event">
      <p v-if="iamStudioEnabled && changedOnServer" class="pw-notice" role="alert">此申请已由其他人处理。请关闭草稿，查看最新结果后重新填写。</p>
      <p v-if="iamStudioEnabled && error" class="pw-error" role="alert">{{ error }}</p>
      <form class="pw-self-card self-request-form" :class="{'pw-root':iamStudioEnabled}" @submit.prevent="save"><fieldset aria-label="岗位申请" :disabled="busy || !data.can_submit"><legend v-if="!iamStudioEnabled">修改岗位</legend><label class="pw-field"><span>岗位名称 <small>必填</small></span><input ref="positionInput" v-model="draft.position" maxlength="128" required placeholder="填写你实际担任的岗位"><small>1–128 字；填写岗位名称不会自动获得权限。</small></label><details class="pw-disclosure"><summary>组织或部门也变了</summary><label class="pw-field"><span>正式组织</span><select v-model="draft.org_unit_id" required @change="organizationChanged"><option value="" disabled>选择组织</option><option v-for="o in organizations" :key="o.id" :value="o.id">{{ o.name }}</option></select></label><label class="pw-field"><span>部门</span><select v-model="draft.department_code" required><option value="" disabled>选择部门</option><option v-for="d in departments" :key="d.code" :value="d.code">{{ d.name }}</option></select></label><p>总务是职能组织，业务厂区由管理员另外确认。</p></details><label class="pw-field"><span>{{ iamStudioEnabled ? '申请原因' : '备注' }} <small>{{ iamStudioEnabled ? '必填' : '选填' }}</small></span><textarea v-model="draft.note" :required="iamStudioEnabled" maxlength="1000" rows="3" placeholder="请说明岗位或业务范围的变化。" /></label><details v-if="iamStudioEnabled" class="pw-disclosure iams-references"><summary>参考职位和期望厂区（选填）</summary>
          <p>已选 {{ draft.requested_role_ids?.length || 0 }} / 3 个公开业务职位，供管理员核对。</p>
          <input v-model="referenceQuery" type="search" aria-label="筛选参考职位" placeholder="查找职位、部门或业务说明">
          <label v-for="pack in referencePackages" :key="pack.role_id"><input type="checkbox" v-model="draft.requested_role_ids" :value="pack.role_id" :disabled="(draft.requested_role_ids?.length ?? 0) >= 3 && !draft.requested_role_ids?.includes(pack.role_id)"> {{ departmentName(pack.department_code) }} · {{ pack.name }} <small v-if="pack.description">{{ pack.description }}</small></label>
          <p v-if="!referencePackages.length">没有匹配的公开参考职位。</p>
          <h3>期望业务厂区</h3><label v-for="factory in data.reference_factories" :key="factory.id"><input type="checkbox" v-model="draft.requested_factory_ids" :value="factory.id"> {{ factory.name }}</label>
        </details><footer class="pw-self-actions"><Button type="button" variant="ghost" :disabled="busy" @click="cancelEdit">取消</Button><Button type="submit" :disabled="busy || !valid"><Send :size="16" />{{ busy ? '正在保存…' : '保存并通知管理员' }}</Button></footer></fieldset></form></component>
      <p v-if="progressError" class="pw-notice" role="status">{{ progressError }} <Button variant="outline" @click="pollProgress">刷新进度</Button></p>
      <SelfAccess v-if="iamStudioEnabled" :data="data" :latest="data.open_review || history[0]" /><section v-else class="pw-self-card"><h2><ShieldCheck :size="20" />当前可用权限</h2><p>这里显示当前实际可用能力，待处理的岗位申报不会提前改变权限。</p><ul class="pw-permission-list"><li v-for="name in (showPermissions ? data.effective_permission_summary : data.effective_permission_summary.slice(0, 8))" :key="name">{{ permissionName(name) }}</li></ul><p v-if="!data.effective_permission_summary.length">暂未分配业务权限，可联系管理员核对。</p><Button v-if="data.effective_permission_summary.length > 8" variant="ghost" @click="showPermissions = !showPermissions">{{ showPermissions ? '收起' : `查看全部 ${data.effective_permission_summary.length} 项` }}</Button></section>
      <details v-if="history.length" class="pw-self-card"><summary>我的提交与处理记录</summary><article v-for="row in history" :key="row.id" class="pw-history"><strong>{{ row.declaration.position }}</strong><span class="pw-badge">{{ positionStatus[row.status] }}</span><p v-if="row.confirmed_profile">管理员确认：{{ row.confirmed_profile.position }}</p><p v-if="row.review_comment">{{ row.review_comment }}</p><small>{{ formatBusinessDateTime(row.updated_at) }}</small></article><Button v-if="history.length < historyTotal" variant="outline" @click="moreHistory">加载更多记录</Button></details>
    </template>
  </main>
</template>
