<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { BriefcaseBusiness, ShieldCheck, Send, ArrowLeft } from '@lucide/vue'
import { positionReviewsApi as api, positionStatus, type Declaration, type PositionReview, type SelfPositionProfile } from '@/api/positionReviews'
import type { OrganizationCatalog } from '@/api/identity'
import { useAuthStore } from '@/stores/auth'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { formatBusinessDateTime } from '@/lib/dateTime'
import './position-workbench.css'
import { permissionName } from './positionLabels'
const auth = useAuthStore(), data = ref<SelfPositionProfile>(), catalog = ref<OrganizationCatalog>(), history = ref<PositionReview[]>([])
const draft = ref<Declaration>({ org_unit_id: '', department_code: '', position: '', note: '' })
const editing = ref(false), loading = ref(false), busy = ref(false), error = ref(''), notice = ref(''), showPermissions = ref(false)
const historyPage = ref(1), historyTotal = ref(0)
const positionInput = ref<HTMLInputElement>(), editButton = ref<InstanceType<typeof Button>>(), errorPanel = ref<HTMLElement>(), noticePanel = ref<HTMLElement>()
let generation = 0
let alive = true
watch(editing, async value => { await nextTick(); if (value) positionInput.value?.focus(); else if (!notice.value && !error.value) editButton.value?.$el?.focus() })
watch(error, async value => { if (value) { await nextTick(); errorPanel.value?.focus() } })
watch(notice, async value => { if (value) { await nextTick(); noticePanel.value?.focus() } })
const viewer = computed(() => `${auth.currentUser?.id ?? ''}:${auth.currentUser?.identity?.employment_epoch ?? ''}`)
const organizations = computed(() => catalog.value?.organizations.filter(o => o.kind !== 'group' && o.status === 'active') ?? [])
const departments = computed(() => organizations.value.find(o => o.id === draft.value.org_unit_id)?.departments ?? [])
const orgName = (id: string) => organizations.value.find(o => o.id === id)?.name || id
async function load(preserve = false) {
  const current = ++generation, identity = viewer.value
  loading.value = true; error.value = ''
  try {
    const [profile, directory, records] = await Promise.all([api.profile(), api.catalog(), api.history()])
    if (current !== generation || identity !== viewer.value) return
    data.value = profile; catalog.value = directory; history.value = records.items; historyPage.value = 1; historyTotal.value = records.total
    if (!preserve) draft.value = { ...(profile.open_review?.declaration || profile.official_position || { org_unit_id: '', department_code: '', position: '' }), note: profile.open_review?.declaration.note || '' }
  } catch (e) { if (current === generation) { error.value = getApiErrorMessage(e); if ([401, 403].includes((e as { response?: { status?: number } }).response?.status ?? 0)) { data.value = undefined; history.value = [] } } }
  finally { if (current === generation) loading.value = false }
}
async function save() {
  if (busy.value || !data.value?.can_submit || !draft.value.position.trim()) return
  const identity = viewer.value
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const declaration = { ...draft.value, position: draft.value.position.trim(), note: draft.value.note.trim() }
    const result = data.value.open_review ? await api.edit(data.value.open_review, declaration) : await api.submit(declaration)
    if (identity !== viewer.value) return
    notice.value = result.message; editing.value = false; await load()
  } catch (e) { if (alive && identity === viewer.value) { if ((e as { response?: { status?: number } }).response?.status === 409) await load(true); if (alive && identity === viewer.value) error.value = getApiErrorMessage(e) } }
  finally { if (alive && identity === viewer.value) busy.value = false }
}
async function withdraw() {
  const row = data.value?.open_review
  if (!row || busy.value) return
  const identity = viewer.value
  busy.value = true
  try { const result = await api.withdraw(row); if (identity !== viewer.value) return; notice.value = result.message; editing.value = false; await load() }
  catch (e) { if (identity === viewer.value) error.value = getApiErrorMessage(e) }
  finally { if (identity === viewer.value) busy.value = false }
}
async function moreHistory() {
  const current = generation, identity = viewer.value
  try { const records = await api.history(historyPage.value + 1); if (current !== generation || identity !== viewer.value) return; history.value.push(...records.items); historyPage.value++; historyTotal.value = records.total }
  catch (e) { if (current === generation) error.value = getApiErrorMessage(e) }
}
function organizationChanged() { if (!departments.value.some(d => d.code === draft.value.department_code)) draft.value.department_code = departments.value[0]?.code || '' }
function refresh() { if (document.visibilityState === 'visible' && !busy.value) { void auth.refreshSession(); void load(editing.value) } }
watch(viewer, () => { ++generation; data.value = undefined; history.value = []; editing.value = false; busy.value = false; notice.value = ''; void load() })
onMounted(() => { void load(); window.addEventListener('focus', refresh); window.addEventListener('authorization-context-changed', refresh) })
onBeforeUnmount(() => { alive = false; ++generation; window.removeEventListener('focus', refresh); window.removeEventListener('authorization-context-changed', refresh) })
</script>
<template>
  <main class="pw-root pw-self"><RouterLink to="/" class="pw-back-link"><ArrowLeft :size="16" />返回工作区</RouterLink><header class="pw-heading"><div><h1>我的岗位与权限</h1><p>告诉管理员你现在做什么，权限由管理员核对后调整。</p></div><BriefcaseBusiness :size="30" /></header><p v-if="notice" ref="noticePanel" tabindex="-1" class="pw-notice" role="status">{{ notice }}</p><p v-if="error" ref="errorPanel" tabindex="-1" class="pw-error" role="alert">{{ error }}<Button variant="outline" @click="load(editing)">重新读取</Button></p><p v-if="loading && !data" class="pw-empty" role="status">正在读取岗位资料…</p>
    <template v-if="data"><section class="pw-self-card"><span class="pw-eyebrow">当前确认岗位</span><h2>{{ data.official_position?.position || '岗位待管理员确认' }}</h2><p v-if="data.official_position">{{ orgName(data.official_position.org_unit_id) }} · {{ organizations.flatMap(o => o.departments).find(d => d.code === data?.official_position?.department_code)?.name }}</p><Button v-if="!editing" ref="editButton" type="button" :disabled="!data.can_submit" @click="editing = true">{{ data.open_review ? '修改待处理内容' : '修改岗位' }}</Button><p v-if="data.blocked_reason" class="pw-notice">{{ data.blocked_reason }}</p></section>
      <section v-if="data.open_review" class="pw-self-card pw-pending"><span class="pw-badge">{{ positionStatus[data.open_review.status] }}</span><h2>我提交的岗位：{{ data.open_review.declaration.position }}</h2><p>管理员确认前，正式岗位和权限保持不变。</p><p v-if="data.open_review.origin === 'admin'">管理员正在核对，更新资料后将重新核对。</p><p v-if="data.open_review.review_comment" class="pw-notice">处理意见：{{ data.open_review.review_comment }}</p><small>{{ formatBusinessDateTime(data.open_review.updated_at) }}</small><Button variant="ghost" :disabled="busy || !data.can_submit" @click="withdraw">撤回岗位更新</Button></section>
      <form v-if="editing" class="pw-self-card" @submit.prevent="save"><fieldset :disabled="busy || !data.can_submit"><legend>修改岗位</legend><label class="pw-field"><span>岗位名称 <small>必填</small></span><input ref="positionInput" v-model="draft.position" maxlength="128" required placeholder="填写你实际担任的岗位"><small>1–128 字；填写岗位名称不会自动获得权限。</small></label><details class="pw-disclosure"><summary>组织或部门也变了</summary><label class="pw-field"><span>正式组织</span><select v-model="draft.org_unit_id" required @change="organizationChanged"><option value="" disabled>选择组织</option><option v-for="o in organizations" :key="o.id" :value="o.id">{{ o.name }}</option></select></label><label class="pw-field"><span>部门</span><select v-model="draft.department_code" required><option value="" disabled>选择部门</option><option v-for="d in departments" :key="d.code" :value="d.code">{{ d.name }}</option></select></label><p>总务是职能组织，业务厂区由管理员另外确认。</p></details><label class="pw-field"><span>备注 <small>选填</small></span><textarea v-model="draft.note" maxlength="1000" rows="3" placeholder="有需要管理员了解的情况，可以写在这里。" /></label><footer class="pw-self-actions"><Button type="button" variant="ghost" :disabled="busy" @click="editing = false">取消</Button><Button type="submit" :disabled="busy || !draft.position.trim()"><Send :size="16" />{{ busy ? '正在保存…' : '保存并通知管理员' }}</Button></footer></fieldset></form>
      <section class="pw-self-card"><h2><ShieldCheck :size="20" />当前可用权限</h2><p>这里显示当前实际可用能力，待处理的岗位申报不会提前改变权限。</p><ul class="pw-permission-list"><li v-for="name in (showPermissions ? data.effective_permission_summary : data.effective_permission_summary.slice(0, 8))" :key="name">{{ permissionName(name) }}</li></ul><p v-if="!data.effective_permission_summary.length">暂未分配业务权限，可联系管理员核对。</p><Button v-if="data.effective_permission_summary.length > 8" variant="ghost" @click="showPermissions = !showPermissions">{{ showPermissions ? '收起' : `查看全部 ${data.effective_permission_summary.length} 项` }}</Button></section>
      <details v-if="history.length" class="pw-self-card"><summary>我的提交与处理记录</summary><article v-for="row in history" :key="row.id" class="pw-history"><strong>{{ row.declaration.position }}</strong><span class="pw-badge">{{ positionStatus[row.status] }}</span><p v-if="row.confirmed_profile">管理员确认：{{ row.confirmed_profile.position }}</p><p v-if="row.review_comment">{{ row.review_comment }}</p><small>{{ formatBusinessDateTime(row.updated_at) }}</small></article><Button v-if="history.length < historyTotal" variant="outline" @click="moreHistory">加载更多记录</Button></details>
    </template>
  </main>
</template>
