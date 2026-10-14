<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { ArrowLeft } from '@lucide/vue'
import { identityApi, type PersonIdentity, type OrganizationCatalog } from '@/api/identity'
import { positionReviewsApi } from '@/api/positionReviews'
import { iamWorkspaceApi } from '@/api/iamWorkspace'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { Button } from '@/components/ui/button'
import IamDialogSurface from '@/components/iam/workspace/IamDialogSurface.vue'
import { rememberIdentityMode } from '@/components/iam/workspace/identity-ui-context'
import IdentityWizard from '../IdentityWizard.vue'
import AccessExplanation from '../AccessExplanation.vue'
import DelegationEditor from '../DelegationEditor.vue'
import { departmentName } from '../positionLabels'
import { workspaceCapabilities, type PersonPanel } from './contracts'
const AccessPanel = defineAsyncComponent(() => import('@/views/UserAccessManagementView.vue'))
const props = defineProps<{ personId: string; panel: PersonPanel; catalog?: OrganizationCatalog }>()
const emit = defineEmits<{ panel: [PersonPanel]; task: [string, boolean]; back: []; saved: []; locked: [boolean] }>()
const auth = useAuthStore(), person = ref<PersonIdentity>(), loading = ref(false), error = ref(''), notice = ref('')
const caps = computed(() => workspaceCapabilities(p => auth.can(p)))
const viewer = computed(() => `${auth.currentUser?.id}:${auth.authorizationVersion}:${auth.currentUser?.identity?.employment_epoch}:${auth.currentUser?.identity?.effective_context_key}`)
const dialog = ref<InstanceType<typeof IamDialogSurface>>(), dirty = ref(false), busy = ref(false), savedDraft = ref('')
const pendingVerification = ref(false)
const account = computed(() => `${auth.currentUser?.id}:${auth.currentUser?.identity?.employment_epoch}`)
let pendingChange: { id: string; revision: number; state: string; owner: string } | undefined
const locked = computed(() => busy.value || pendingVerification.value)
const beforeUnload = (event: BeforeUnloadEvent) => { if (locked.value || dirty.value) { event.preventDefault(); event.returnValue = '' } }
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
function rememberPending(value: { id: string; revision: number; state: string } | null) { pendingChange = value ? { ...value, owner: account.value } : undefined }
async function verifyPending() {
  if (!pendingChange || busy.value) return
  const anchor = pendingChange, current = generation
  busy.value = true
  try {
    const result = await iamWorkspaceApi.change(anchor.id)
    if (current !== generation) return
    if (result.revision !== anchor.revision || result.state !== anchor.state) {
      pendingChange = undefined; pendingVerification.value = false; notice.value = '已读取原办理单的新状态，请在操作记录查看结果。'
    } else notice.value = '尚未观察到原办理单变化。请稍后重新核查，勿重复提交。'
  } catch (e) { if (current === generation) error.value = getApiErrorMessage(e) }
  finally { if (current === generation) busy.value = false }
}
let generation = 0
const orgName = (id: string) => props.catalog?.organizations.find(o => o.id === id)?.name || id || '未登记'
const bindings = computed(() => person.value?.role_bindings.filter(b => b.state === 'active') || [])
async function read() {
  const current = ++generation, actor = viewer.value
  person.value = undefined; error.value = ''; notice.value = ''; dirty.value = false; loading.value = false
  if (!caps.value.people || props.panel === 'exceptions') return
  loading.value = true
  try {
    const data = await identityApi.person(props.personId)
    if (current !== generation || actor !== viewer.value) return
    person.value = data; rememberIdentityMode(auth.currentUser?.id || '', data.id, data.identity_mode)
  } catch (e) { if (current === generation && actor === viewer.value) error.value = getApiErrorMessage(e) }
  finally { if (current === generation) loading.value = false }
}
async function start() {
  const target = person.value, current = generation, actor = viewer.value
  if (!target || locked.value || !caps.value.people || !caps.value.exceptions || !props.catalog?.writes_enabled) return
  busy.value = true; error.value = ''
  try {
    const result = await positionReviewsApi.adjust(target.id, {
      org_unit_id: target.primary_assignment?.org_unit_id || target.primary_factory_id,
      department_code: target.primary_department, position: target.position || '待核对岗位',
    })
    if (current !== generation || actor !== viewer.value) return
    notice.value = result.reused ? '已打开现有岗位待办。' : '岗位待办已创建；离开编辑不会撤销这条待办。'
    busy.value = false
    emit('task', result.item_key, result.reused)
  } catch (e) { if (current === generation && actor === viewer.value) error.value = getApiErrorMessage(e) }
  finally { if (current === generation) busy.value = false }
}
async function saved() { pendingChange = undefined; pendingVerification.value = false; dirty.value = false; emit('panel', 'profile'); await read(); emit('saved') }
const permitLeave = async () => locked.value ? false : props.panel === 'advanced' ? (await dialog.value?.permitLeave()) ?? true : true
onBeforeRouteLeave(permitLeave); onBeforeRouteUpdate(permitLeave)
watch(viewer, () => { ++generation; person.value = undefined; busy.value = false; dirty.value = false; savedDraft.value = ''; pendingVerification.value = !!pendingChange && pendingChange.owner === account.value; if (!pendingVerification.value) pendingChange = undefined }, { flush: 'sync' })
watch([() => props.personId, viewer], read, { immediate: true, flush: 'sync' })
watch(() => props.panel, panel => { if (panel !== 'exceptions' && !person.value && !loading.value) void read() })
watch(locked, value => emit('locked', value), { flush: 'sync' })
onBeforeUnmount(() => { ++generation })
</script>
<template>
  <section class="iw-person-context" aria-label="人员只读详情">
    <header class="iw-person-heading"><Button class="iw-mobile-back" variant="ghost" :disabled="locked" @click="emit('back')"><ArrowLeft :size="16" />返回列表</Button><div><h2>{{ person?.display_name || '人员详情' }}</h2><p>{{ person?.position || (panel === 'exceptions' ? '个人例外与供应商授权' : '岗位与授权资料') }}</p></div><span class="pw-badge">只读查看</span></header>
    <nav class="iw-person-tabs" aria-label="人员详情栏目"><button v-if="caps.people" :aria-pressed="panel === 'profile'" @click="emit('panel', 'profile')">岗位与权限</button><button v-if="caps.exceptions" :aria-pressed="panel === 'exceptions'" @click="emit('panel', 'exceptions')">个人例外</button><button v-if="caps.people" :aria-pressed="panel === 'account'" @click="emit('panel', 'account')">账号状态</button></nav>
    <div class="iw-detail-scroll">
      <p v-if="loading" role="status">正在读取人员资料…</p>
      <p v-if="error" class="pw-error" role="alert">{{ error }}<Button variant="outline" @click="read">重新读取</Button></p>
      <p v-if="notice" class="pw-notice" role="status">{{ notice }}</p>
      <div v-if="pendingVerification" class="pw-notice" role="status">访问权限已更新，原办理请求的结果仍待核查。<Button :disabled="busy" @click="verifyPending">核查原办理结果</Button></div>
      <AccessPanel v-if="panel === 'exceptions' && caps.exceptions" :key="`${personId}:${viewer}`" :target-user-id="personId" embedded />
      <p v-else-if="!caps.people" class="pw-notice">人员资料受保护。请使用已授权的个人例外面板。</p>
      <template v-else-if="person">
        <p class="iw-readonly-note">查看、切换人员和刷新不会创建办理单。</p>
        <dl class="iw-facts"><div><dt>正式岗位</dt><dd>{{ person.position || '待确认' }}</dd></div><div><dt>组织 / 部门</dt><dd>{{ orgName(person.primary_assignment?.org_unit_id || person.primary_factory_id) }} · {{ departmentName(person.primary_department) }}</dd></div><div><dt>账号状态</dt><dd>{{ ({ active: '在用', suspended: '已冻结', pending: '待开通', rejected: '已拒绝' } as Record<string,string>)[person.status] || person.status }}</dd></div><div><dt>任职状态</dt><dd>{{ person.employment_status === 'left' ? '已离职' : person.identity_mode === 'v2' ? '正式任职已确认' : '历史来源待核实' }}</dd></div></dl>
        <template v-if="panel !== 'account'">
          <h3>当前授权来源</h3><p v-if="!bindings.length" class="pw-subtle">当前没有在用的方案绑定。</p>
          <div v-for="b in bindings" :key="b.id" class="iw-source"><strong>{{ b.role_name }}</strong><small>{{ b.assignment_id ? '任职绑定' : '独立来源' }} · {{ b.role_version_id ? '已固定版本' : '保留原解释' }} · {{ departmentName(b.department) }}</small><p>{{ b.factory_ceiling?.map(orgName).join('、') || '保留原批准范围' }}</p></div>
          <details v-if="person.assignments.length"><summary>全部任职与历史 · {{ person.assignments.length }}</summary><p v-for="a in person.assignments" :key="a.id">{{ a.official_position_title }} · {{ a.org_name }} · {{ a.state }} · {{ a.valid_from }}{{ a.valid_until ? ` 至 ${a.valid_until}` : '' }}</p></details>
          <AccessExplanation v-if="catalog && caps.exceptions" :key="person.id" :user-id="person.id" :catalog="catalog" :default-factory="person.primary_factory_id" :default-department="person.primary_department" />
          <DelegationEditor v-if="catalog?.can_manage_delegations && person.id !== auth.currentUser?.id" :user-id="person.id" :catalog="catalog" :default-org="person.primary_assignment?.org_unit_id || person.primary_factory_id" :default-department="person.primary_department" />
        </template>
        <div class="pw-inline"><Button variant="outline" :disabled="!caps.exceptions || !catalog?.writes_enabled" @click="emit('panel', 'advanced')">任职、冻结与离职</Button><RouterLink :to="{ path: '/system/iam/audit', query: { source: 'position', person: person.id } }" class="iamx-link-button">查看此人记录</RouterLink></div>
      </template>
    </div>
    <footer v-if="person && panel !== 'exceptions'" class="iw-person-footer"><span>当前为只读资料</span><Button :disabled="locked || !caps.exceptions || !catalog?.writes_enabled" @click="start">{{ busy ? '正在发起…' : '发起岗位 / 权限调整' }}</Button></footer>
    <IamDialogSurface ref="dialog" :open="panel === 'advanced' && !pendingVerification && !!person && !!catalog && caps.exceptions" title="任职、预约与账号状态" :description="person?.display_name" drawer :dirty="dirty" :busy="busy" :saved-description="savedDraft" @update:open="emit('panel', 'profile')" @discarded="dirty = false"><IdentityWizard v-if="person && catalog && panel === 'advanced'" :person="person" :catalog="catalog" @dirty="dirty = $event" @busy="busy = $event" @draft="savedDraft = $event" @pending="rememberPending" @saved="saved" /></IamDialogSurface>
  </section>
</template>
