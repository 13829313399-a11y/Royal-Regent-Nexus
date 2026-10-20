<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { ArrowLeft, ArrowRight, ArrowRightLeft, BriefcaseBusiness, Check, CircleCheck, CircleMinus, CirclePlus, Files, Search, ShieldCheck, Clock3, CircleAlert } from '@lucide/vue'
import type { OrganizationCatalog } from '@/api/identity'
import type { ReviewResult } from '@/api/positionReviews'
import { positionStatus } from '@/api/positionReviews'
import { formatBusinessDateTime } from '@/lib/dateTime'
import { Button } from '@/components/ui/button'
import { usePositionReview } from './usePositionReview'
import LegacySourceReview from './LegacySourceReview.vue'
import { permissionName } from './positionLabels'
import PermissionPackageSummary from '@/components/iam/workspace/PermissionPackageSummary.vue'
const props = defineProps<{ itemKey: string; catalog?: OrganizationCatalog; compact?: boolean }>()
const emit = defineEmits<{ saved: [ReviewResult]; back: []; next: []; locked: [boolean]; dirty: [boolean] }>()
const review = usePositionReview(value => emit('saved', value))
const { detail, draft, packages, scope, selectedRole, preview, state, error, result, risk, locked, canCommit, packagesLoading } = review
const legacyLocked = ref(false)
function legacySaved() { legacyLocked.value = false; void review.select(props.itemKey) }
const errorPanel = ref<HTMLElement>(), successTitle = ref<HTMLElement>(), returnInput = ref<HTMLTextAreaElement>(), returnButton = ref<InstanceType<typeof Button>>()
async function userAction(action: () => Promise<unknown>) { await action(); if (error.value) { await nextTick(); errorPanel.value?.focus() } }
watch(error, async value => { if (value && !['previewing', 'editing'].includes(state.value)) { await nextTick(); errorPanel.value?.focus() } })
watch(result, async value => { if (value) { await nextTick(); successTitle.value?.focus() } })
const title = ref<HTMLElement>(), search = ref(''), reason = ref(''), returning = ref(false)
watch(returning, async value => { await nextTick(); if (value) returnInput.value?.focus(); else if (!result.value) returnButton.value?.$el?.focus() })
watch(() => props.itemKey, async (key, _, onCleanup) => { let current = true; onCleanup(() => { current = false }); search.value = ''; reason.value = ''; returning.value = false; await review.select(key); await nextTick(); if (current) title.value?.focus({ preventScroll: true }) }, { immediate: true })
watch([locked, legacyLocked], ([pending, legacy]) => emit('locked', pending || legacy))
watch([review.dirty, reason], ([changed, text]) => emit('dirty', changed || !!text.trim()), { flush: 'sync' })
const organizations = computed(() => props.catalog?.organizations.filter(o => o.kind !== 'group' && o.status === 'active') ?? [])
const departments = computed(() => organizations.value.find(o => o.id === draft.value?.confirmed_profile.org_unit_id)?.departments ?? [])
const matches = computed(() => packages.value.filter(p => `${departmentName(p.department)}${p.name} ${p.description} ${p.capability_summary.map(c => permissionName(c)).join(' ')}`.includes(search.value.trim())))
const ordered = computed(() => [...matches.value].sort((a, b) => Number(b.department === draft.value?.confirmed_profile.department_code) - Number(a.department === draft.value?.confirmed_profile.department_code)))
const orgName = (id: string) => organizations.value.find(o => o.id === id)?.name || id
const departmentName = (id: string) => organizations.value.flatMap(o => o.departments).find(d => d.code === id)?.name || id
const registrationValue = (value: string | null | undefined) => value == null ? '未记录' : value.trim() || '未填写'
const currentRoles = computed(() => detail.value?.current_bindings.filter(b => b.assignment_id === detail.value?.primary_assignment_id).map(b => b.role_id) ?? [])
const primaryLabel = computed(() => detail.value?.kind === 'registration' ? '通过并分配权限' : draft.value?.decision === 'keep_permissions' ? '确认岗位，保留原权限' : detail.value?.origin === 'admin' ? '保存权限调整' : '确认调整权限')
function organizationChanged() {
  if (!draft.value) return
  if (!departments.value.some(d => d.code === draft.value?.confirmed_profile.department_code)) draft.value.confirmed_profile.department_code = departments.value[0]?.code || ''
  if (organizations.value.find(o => o.id === draft.value?.confirmed_profile.org_unit_id)?.kind === 'functional_unit') scope.value = { kind: 'selected', factory_ids: [] }
}
function exception(id: string, event: Event) {
  if (!draft.value) return
  const value = (event.target as HTMLSelectElement).value as 'keep_original_scope' | 'end' | ''
  draft.value.independent_allow_decisions = draft.value.independent_allow_decisions.filter(d => d.override_id !== id)
  if (value) draft.value.independent_allow_decisions.push({ override_id: id, decision: value })
}
defineExpose({ locked, state })
</script>
<template>
  <section class="pw-pane" :class="{ 'iw-review-pane': compact }" aria-label="岗位与权限办理区" :aria-busy="state === 'loading'">
    <Button variant="ghost" class="pw-mobile-back" :disabled="locked || legacyLocked" @click="emit('back')"><ArrowLeft :size="16" />返回队列</Button>
    <p v-if="state === 'loading'" class="pw-empty" role="status">正在读取岗位与当前授权…</p>
    <div v-if="error" ref="errorPanel" tabindex="-1" class="pw-error" role="alert"><CircleAlert :size="18" /><span>{{ error }}</span><Button v-if="!locked && state !== 'forbidden'" variant="outline" @click="review.select(itemKey)">读取最新资料</Button></div>
    <div v-if="state === 'uncertain'" class="pw-notice" role="status"><h3>正在核查提交结果</h3><p>提交可能已经成功。请查询回执，或使用相同命令重试。</p><div class="pw-inline"><Button variant="outline" @click="userAction(review.checkReceipt)">查询提交结果</Button><Button variant="outline" @click="userAction(review.retry)">使用原命令重试</Button></div></div>
    <div v-if="result" class="pw-success" role="status"><span class="pw-success-icon"><Check :size="26" /></span><h2 ref="successTitle" tabindex="-1">{{ result.decision === 'return_position' ? '已退回补充' : result.decision === 'reject_registration' ? '已拒绝注册' : '岗位与权限已确认' }}</h2><p>{{ detail?.user.display_name }} · {{ formatBusinessDateTime(result.committed_at) }}</p><p>{{ result.notification_state === 'delivered' ? '办理结果已保存，结果通知已送达。' : result.notification_state === 'retrying' ? '办理结果已保存，结果通知正在重试。' : '办理结果已保存，结果通知已进入发送队列。' }}</p><Button @click="emit('next')">办理下一位<ArrowRight :size="16" /></Button></div>
    <template v-else-if="detail && draft">
      <header class="pw-person"><span class="pw-avatar" aria-hidden="true">{{ detail.user.display_name.slice(0, 1) }}</span><div><div class="pw-inline"><h2 ref="title" tabindex="-1">{{ detail.user.display_name }}</h2><span class="pw-badge iw-review-status" :data-state="detail.status">{{ positionStatus[detail.status] || detail.status }}</span></div><p>{{ detail.user.username }} · {{ orgName(detail.declaration.org_unit_id) }} · {{ departmentName(detail.declaration.department_code) }}</p></div><time class="pw-time"><Clock3 :size="14" />{{ formatBusinessDateTime(detail.created_at) }}</time></header>
      <div class="pw-review-scroll">
      <section v-if="detail.kind === 'registration'" class="pw-registration-info" aria-label="注册申请资料">
        <header><h3>注册申请资料</h3><p>申请时间：{{ formatBusinessDateTime(detail.created_at) }}（北京时间）</p></header>
        <dl>
          <div><dt>注册账号</dt><dd>{{ registrationValue(detail.user.username) }}</dd></div>
          <div><dt>申请姓名</dt><dd>{{ registrationValue(detail.registration_details?.display_name) }}</dd></div>
          <div><dt>手机号码</dt><dd>{{ registrationValue(detail.registration_details?.phone) }}</dd></div>
          <div><dt>邮箱</dt><dd>{{ registrationValue(detail.registration_details?.email) }}</dd></div>
        </dl>
      </section>
      <div class="pw-comparison"><div class="iw-position-before"><span>当前确认岗位</span><strong><BriefcaseBusiness :size="20" aria-hidden="true" />{{ detail.current_official?.position || '尚未确认' }}</strong><small v-if="detail.current_official">{{ orgName(detail.current_official.org_unit_id) }} · {{ departmentName(detail.current_official.department_code) }}</small></div><ArrowRight :size="20" aria-hidden="true" /><div class="iw-position-after"><span>{{ detail.origin === 'admin' ? '管理员拟核对岗位' : '本次提交的岗位' }}</span><strong><BriefcaseBusiness :size="20" aria-hidden="true" />{{ detail.declaration.position }}</strong><small>{{ orgName(detail.declaration.org_unit_id) }} · {{ departmentName(detail.declaration.department_code) }}</small></div></div>
      <p v-if="detail.declaration.note" class="pw-subtle">员工备注：{{ detail.declaration.note }}</p>
      <p v-for="message in detail.blocked_reasons" :key="message" class="pw-notice">{{ message }}</p>
      <LegacySourceReview v-if="detail.identity_mode === 'legacy' && detail.available_actions.includes('preview')" :user-id="detail.user.id" :official="detail.current_official" @locked="legacyLocked = $event" @saved="legacySaved" />
      <p v-if="detail.review_comment" class="pw-notice">处理意见：{{ detail.review_comment }}</p>
      <p v-if="detail.confirmed_profile" class="pw-notice">确认结果：{{ detail.confirmed_profile.position }} · {{ orgName(detail.confirmed_profile.org_unit_id) }} · {{ departmentName(detail.confirmed_profile.department_code) }}</p>
      <fieldset :disabled="!detail.available_actions.includes('preview') || locked || legacyLocked || detail.status !== 'pending' || detail.identity_mode === 'legacy'" class="pw-fields">
        <details class="pw-disclosure"><summary>核对 / 更正确认资料 <span>原始申报会保留</span></summary><div class="pw-field-grid"><label class="pw-field"><span>确认岗位</span><input v-model="draft.confirmed_profile.position" maxlength="128" required></label><label class="pw-field"><span>确认组织</span><select v-model="draft.confirmed_profile.org_unit_id" @change="organizationChanged"><option v-for="o in organizations" :key="o.id" :value="o.id">{{ o.name }}</option></select></label><label class="pw-field"><span>确认部门</span><select v-model="draft.confirmed_profile.department_code"><option v-for="d in departments" :key="d.code" :value="d.code">{{ d.name }}</option></select></label></div>
          <div v-if="draft.registration_details_correction" class="pw-field-grid"><label class="pw-field"><span>确认姓名</span><input v-model="draft.registration_details_correction.display_name" maxlength="128"></label><label class="pw-field"><span>手机号</span><input v-model="draft.registration_details_correction.phone" maxlength="64"></label><label class="pw-field"><span>邮箱</span><input v-model="draft.registration_details_correction.email" maxlength="128"></label></div>
        </details>
        <div class="pw-review-columns"><div class="pw-choice"><div class="pw-section-heading"><div><h3><ShieldCheck :size="18" aria-hidden="true" />选择内置权限方案</h3><p>岗位名称供参考，实际能力由管理员确认。</p></div><label class="pw-search"><Search :size="16" aria-hidden="true" /><span class="sr-only">搜索方案</span><input v-model="search" type="search" placeholder="搜索方案或权限"></label></div>
        <div class="pw-decisions" role="radiogroup" aria-label="办理方式"><label class="pw-check"><input v-model="draft.decision" type="radio" value="apply_package">选择并分配内置方案</label><label v-if="detail.kind === 'position'" class="pw-check"><input v-model="draft.decision" type="radio" value="keep_permissions" :disabled="!detail.can_keep_permissions">确认岗位，保留原权限</label></div>
        <template v-if="draft.decision === 'apply_package'">
          <details class="pw-disclosure" :open="draft.confirmed_profile.org_unit_id === 'group-management'"><summary>业务作用范围 <span>正式归属与业务厂区分别核对</span></summary><label class="pw-field"><span>范围方式</span><select v-model="scope.kind"><option value="home">正式归属厂区</option><option value="selected">明确选择业务厂区</option><option value="all_current">当前所有生产厂区（固定上限）</option></select></label><div v-if="scope.kind === 'selected'" class="pw-inline"><label v-for="o in organizations.filter(o => o.kind === 'factory')" :key="o.id" class="pw-check"><input v-model="scope.factory_ids" type="checkbox" :value="o.id">{{ o.name }}</label></div></details>
          <p v-if="packagesLoading" role="status" class="pw-subtle">正在核对可分配范围…</p>
          <div class="pw-packages" role="radiogroup" aria-label="内置权限方案"><label v-for="p in ordered" :key="p.role_id" class="pw-package" :class="{ 'is-selected': selectedRole === p.role_id, 'is-disabled': !p.assignable }"><div class="pw-inline"><PermissionPackageSummary :name="p.name" :department="departmentName(p.department)" :count="p.capability_summary.length" /><input v-model="selectedRole" type="radio" name="builtin-package" :value="p.role_id" :disabled="!p.assignable || packagesLoading"></div><small v-if="currentRoles.includes(p.role_id)">当前使用</small><small v-else-if="p.department === draft.confirmed_profile.department_code">与{{ departmentName(p.department) }}匹配</small><p>{{ p.description }}</p><span>{{ departmentName(p.department) }} · {{ p.scope_mode === 'own_factory' ? '指定厂区操作' : p.scope_mode === 'cross_factory_read' ? '跨厂查看，按范围操作' : '按确认范围操作' }}</span><p v-if="p.blocked_reason" class="pw-package-reason">{{ p.blocked_reason }}</p><details v-if="p.capability_summary.length"><summary>查看 {{ p.capability_summary.length }} 项能力</summary><ul><li v-for="capability in p.capability_summary" :key="capability">{{ permissionName(capability) }}</li></ul></details></label></div>
          <p v-if="!packagesLoading && !ordered.length" class="pw-empty">没有匹配的方案，请调整搜索词。</p>
        </template>
        <section v-if="detail.independent_allows.length" class="pw-exceptions"><h3>逐项核对独立授权</h3><p>这些授权不属于主职方案，请明确保留或终止。</p><label v-for="o in detail.independent_allows" :key="o.override_id" class="pw-field"><span>{{ permissionName(o.permission_code, o.permission_name) }} · {{ orgName(o.factory_id) }} · {{ departmentName(o.department) }}</span><select :value="draft.independent_allow_decisions.find(d => d.override_id === o.override_id)?.decision || ''" @change="exception(o.override_id, $event)"><option value="">请选择处理方式</option><option value="keep_original_scope">保留于原范围</option><option value="end" :disabled="draft.decision === 'keep_permissions'">终止此独立允许</option></select></label></section>
        <details v-if="detail.current_bindings.some(b => b.assignment_id !== detail?.primary_assignment_id)" class="pw-disclosure"><summary>保留其他授权来源</summary><p v-for="b in detail.current_bindings.filter(b => b.assignment_id !== detail?.primary_assignment_id)" :key="b.binding_id">{{ b.role_name }} · {{ b.factory_ids.map(orgName).join('、') }}</p></details>
        </div><section class="pw-impact" aria-live="polite"><h3><ShieldCheck :size="18" />本次实际权限变化</h3><p v-if="state === 'previewing'">正在核对实际权限影响…</p><template v-else-if="preview"><div class="pw-impact-counts">
            <span data-change="added"><CirclePlus :size="21" aria-hidden="true" /><span><strong>{{ preview.permission_diffs.added.length }}</strong><small>新增</small></span></span>
            <span data-change="removed"><CircleMinus :size="21" aria-hidden="true" /><span><strong>{{ preview.permission_diffs.removed.length }}</strong><small>将停止</small></span></span>
            <span data-change="retained"><Files :size="21" aria-hidden="true" /><span><strong>{{ preview.permission_diffs.retained.length }}</strong><small>保持</small></span></span>
            <span data-change="source_changed"><ArrowRightLeft :size="21" aria-hidden="true" /><span><strong>{{ preview.permission_diffs.source_changed.length }}</strong><small>来源变化</small></span></span>
          </div><details v-for="group in (['added', 'removed', 'retained', 'source_changed'] as const)" :key="group" :data-change="group"><summary>{{ ({ added: '新增权限', removed: '将停止的权限', retained: '保持的权限', source_changed: '来源变化' })[group] }} · {{ preview.permission_diffs[group].length }}</summary><ul><li v-for="t in preview.permission_diffs[group]" :key="`${t.permission_code}:${t.factory_id}:${t.department}`">{{ permissionName(t.permission_code, t.permission_name) }} · {{ t.factory_name }} · {{ t.department_name }}</li></ul></details><p>{{ preview.handover_summary }}</p><p v-for="blocked in preview.blocked_reasons" :key="blocked" class="pw-error">{{ blocked }}</p></template><p v-else>完成资料和方案选择后，将自动核对权限影响。</p><Button v-if="!preview && review.valid.value && state !== 'previewing'" variant="outline" @click="userAction(review.makePreview)">重新核对影响</Button>
          <div v-if="detail.explicit_denials.length" class="pw-notice"><strong>以下操作仍被明确禁止</strong><p v-for="t in detail.explicit_denials" :key="`${t.permission_code}:${t.factory_id}:${t.department}`">{{ permissionName(t.permission_code, t.permission_name) }} · {{ t.factory_name }} · {{ t.department_name }}</p></div>
        </section>
      </div></fieldset></div>
      <footer v-if="detail.status === 'pending'" class="pw-actionbar">
        <p class="pw-action-context">{{ detail.user.display_name }} · {{ detail.current_official?.position || '未确认' }} → {{ draft.confirmed_profile.position }}</p>
        <label v-if="preview?.high_risk" class="pw-risk"><input v-model="risk" type="checkbox" :disabled="locked">我已核对本次新增的 {{ preview.permission_diffs.added.length }} 项权限及其作用范围</label>
        <p v-else class="pw-subtle iw-preview-status" :class="{ 'is-ready': !!preview }" role="status"><CircleCheck v-if="preview" :size="17" aria-hidden="true" />{{ state === 'previewing' ? '正在核对权限…' : preview ? '权限影响已核对' : '等待完整有效的预览' }}</p>
        <div v-if="returning" class="pw-return"><label class="pw-field"><span>{{ detail.kind === 'registration' ? '拒绝原因' : '退回原因' }}（必填）</span><textarea ref="returnInput" v-model="reason" maxlength="2000" :disabled="locked" /></label><Button variant="outline" :disabled="locked || !reason.trim()" @click="userAction(() => review.decide(reason))">确认{{ detail.kind === 'registration' ? '拒绝注册' : '退回补充' }}</Button><Button variant="ghost" :disabled="locked || legacyLocked" @click="returning = false">取消</Button></div>
        <div v-else class="pw-inline"><Button ref="returnButton" variant="ghost" :disabled="locked || legacyLocked || !detail.available_actions.includes(detail.kind === 'registration' ? 'reject_registration' : 'return_position')" @click="returning = true">{{ detail.kind === 'registration' ? '拒绝注册' : '退回补充' }}</Button><Button :disabled="!canCommit || locked" @click="userAction(review.submit)"><Check :size="16" />{{ state === 'committing' ? '正在确认…' : primaryLabel }}</Button></div>
      </footer>
    </template>
  </section>
</template>
