<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { Position } from '@/api/positionReviews'
import { identityApi, type ChangeRecord, type ChangePreview, type ChangePayload, type PersonIdentity, type OrganizationCatalog } from '@/api/identity'
import { accessStudioApi, type StudioPreview, type StudioResult } from '@/api/accessStudio'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
import { Button } from '@/components/ui/button'
import { permissionName } from './positionLabels'
const props = defineProps<{ userId: string; official?: Position | null; studio?: boolean; catalog?: OrganizationCatalog }>()
const emit = defineEmits<{ saved: []; locked: [boolean]; dirty: [boolean] }>()
const person = ref<PersonIdentity>(), error = ref(''), busy = ref(false), preview = ref<ChangePreview | StudioPreview>(), savedDraft = ref<ChangeRecord>()
const pendingReview = ref<StudioResult>()
const orgCorrection = ref(''), departmentCorrection = ref(''), titleCorrection = ref('')
const knownOrg = computed(() => props.official?.org_unit_id || person.value?.primary_assignment?.org_unit_id || person.value?.primary_org_unit_id || person.value?.primary_factory_id || '')
const knownDepartment = computed(() => person.value?.primary_department || props.official?.department_code || '')
const knownTitle = computed(() => person.value?.position || props.official?.position || '')
const confirmedOrg = computed(() => knownOrg.value || orgCorrection.value)
const confirmedDepartment = computed(() => knownDepartment.value || departmentCorrection.value)
const confirmedTitle = computed(() => knownTitle.value || titleCorrection.value.trim())
const departments = computed(() => props.catalog?.organizations.find(o => o.id === confirmedOrg.value)?.departments ?? [])
const sources = ref<Record<string, string>>({}), exceptions = ref<Record<string, string>>({})
let generation = 0
onBeforeUnmount(() => { ++generation; emit('locked', false); emit('dirty', false) })
const selectedSources = computed(() => [...Object.values(sources.value), ...Object.values(exceptions.value), orgCorrection.value, departmentCorrection.value, titleCorrection.value].some(Boolean))
watch(selectedSources, changed => emit('dirty', changed), {flush: 'sync'})
const bindings = computed(() => person.value?.role_bindings.filter(b => b.state === 'active') ?? [])
const activeAllows = computed(() => person.value?.overrides.filter(o => o.effect === 'allow' && o.state === 'active') ?? [])
watch(() => props.userId, async id => {
  const current = ++generation; pendingReview.value = undefined; orgCorrection.value = ''; departmentCorrection.value = ''; titleCorrection.value = ''; person.value = undefined; preview.value = undefined; savedDraft.value = undefined; sources.value = {}; exceptions.value = {}
  try { const value = await identityApi.person(id); if (current === generation) { person.value = value; sources.value = Object.fromEntries(value.role_bindings.map(b => [b.id, ''])) } }
  catch (e) { if (current === generation) error.value = getApiErrorMessage(e) }
}, { immediate: true })
watch([sources, exceptions, orgCorrection, departmentCorrection, titleCorrection], () => { preview.value = undefined }, { deep: true, flush: 'sync' })
async function verify() {
  if (!person.value || busy.value) return
  const current = generation
  busy.value = true; error.value = ''
  try {
    const p = person.value
    const payload: ChangePayload = { request_type: 'confirm_identity', target_user_id: p.id, reason: '岗位工作台核实历史授权来源；保持实际权限',
      base_identity_version: p.identity_version, base_authorization_version: p.authorization_version,
      new_assignment: { org_unit_id: confirmedOrg.value, department_code: confirmedDepartment.value,
        official_position_title: confirmedTitle.value, assignment_type: 'regular', is_primary: true, role_bindings: [] },
      binding_dispositions: bindings.value.map(b => ({ binding_id: b.id, source: sources.value[b.id] || '' })),
      exception_decisions: activeAllows.value.map(o => ({ override_id: o.id, decision: exceptions.value[o.id] || '' })),
    }
    if (props.studio) {
      const value = await accessStudioApi.legacyPreview(p.id, payload)
      if (current === generation) preview.value = value
      return
    }
    const row = await identityApi.draft(payload, savedDraft.value)
    if (current !== generation) return
    savedDraft.value = row
    const result = await identityApi.preview(row.id)
    if (current === generation) preview.value = result
  } catch (e) { if (current === generation) error.value = getApiErrorMessage(e) }
  finally { if (current === generation) busy.value = false }
}
const commandId = ref(''), riskAcknowledged = ref(false)
watch(preview, () => { riskAcknowledged.value = false }, { flush: 'sync' })
watch([busy, commandId], ([pending, command]) => emit('locked', pending || !!command))
const noDrift = computed(() => !!preview.value && (!preview.value.high_risk || riskAcknowledged.value) && (props.studio || !preview.value.requires_approval)
  && !preview.value.permission_diffs.added.length && !preview.value.permission_diffs.removed.length)
function finished() { emit('dirty', false); commandId.value = ''; emit('locked', false); emit('saved') }
function acceptStudioResult(result: StudioResult) {
  if (result.decision === 'applied') { finished(); return }
  pendingReview.value = result
  preview.value = undefined
  commandId.value = ''
  emit('dirty', false)
}
async function readApproval() {
  if (!pendingReview.value || busy.value) return
  const current = generation
  busy.value = true; error.value = ''
  try {
    const row = await identityApi.change(pendingReview.value.change_id)
    if (current !== generation) return
    if (row.state === 'applied') finished()
    else if (row.state === 'cancelled' || row.state === 'rejected') {
      pendingReview.value = undefined
      error.value = '来源确认办理单已结束，请重新核对最新人员资料。'
      const latest = await identityApi.person(props.userId)
      if (current !== generation) return
      person.value = latest; sources.value = {}; exceptions.value = {}
    }
  } catch (e) { if (current === generation) error.value = getApiErrorMessage(e) }
  finally { if (current === generation) busy.value = false }
}
async function confirm() {
  if ((!props.studio && !savedDraft.value) || !preview.value || busy.value || !noDrift.value) return
  const current = generation
  busy.value = true; error.value = ''; commandId.value ||= createRandomUuid()
  try {
    if (props.studio) {
      const result = await accessStudioApi.commit(props.userId, { preview_token: preview.value.preview_token, risk_acknowledged: riskAcknowledged.value, confirm_empty_packages: false }, commandId.value)
      if (current === generation) acceptStudioResult(result)
      return
    }
    const result = await identityApi.commit(savedDraft.value!, preview.value as ChangePreview, commandId.value)
    if (current === generation && result.state === 'applied') finished()
  } catch (e) {
    if (current !== generation) return
    try {
      if (props.studio) {
        const observed = (await accessStudioApi.receipt(commandId.value)).result
        if (current === generation && observed) { acceptStudioResult(observed); return }
      } else {
        const row = await identityApi.change(savedDraft.value!.id)
        if (current === generation && row.state === 'applied') { finished(); return }
      }
    }
    catch { /* Keep original command for retry. */ }
    const status = (e as { response?: { status?: number } }).response?.status
    if (status && status >= 400 && status < 500 && ![408, 429].includes(status)) {
      commandId.value = ''; preview.value = undefined
    }
    error.value = getApiErrorMessage(e)
  } finally { if (current === generation) busy.value = false }
}
</script>
<template>
  <section class="pw-legacy">
    <h3>首次办理：确认旧权限的归属</h3>
    <p>旧账号尚未记录哪些权限跟随岗位、哪些需要独立保留。请先确认归属，避免调岗后旧权限叠加或误删特殊授权。此步骤不增减实际权限，确认后继续办理；以后通常无需重复。</p>
    <p v-if="studio">第一步核对所有历史来源，预览中新增与收回必须均为零。确认后重新读取任职版本，再单独预览本次变更。</p>
    <p v-if="error" role="alert" class="pw-error">{{ error }}</p>
    <div v-if="pendingReview" class="pw-notice" role="status"><strong>历史来源核实已提交，等待独立复核。</strong>
      <p>复核生效后可继续本次权限办理。</p><div class="pw-inline">
        <RouterLink :to="{path:'/system/users',query:{view:'inbox', task:'identity-change:' + pendingReview.change_id}}">查看来源确认办理单</RouterLink>
        <Button variant="outline" :disabled="busy" @click="readApproval">核对复核结果</Button>
      </div>
    </div>
    <template v-else>
    <fieldset v-if="person && (!knownOrg || !knownDepartment || !knownTitle)" class="iam2-fields" :disabled="busy || !!commandId"><legend>补齐缺失的正式任职资料</legend>
      <label v-if="!knownOrg">正式归属组织<select v-model="orgCorrection" @change="departmentCorrection = ''"><option value="">请选择组织</option><option v-for="o in catalog?.organizations.filter(o => o.status === 'active' && o.kind !== 'group')" :key="o.id" :value="o.id">{{ o.name }}</option></select></label>
      <label v-if="!knownDepartment">正式部门<select v-model="departmentCorrection" :disabled="!confirmedOrg"><option value="">请选择部门</option><option v-for="d in departments" :key="d.code" :value="d.code">{{ d.name }}</option></select></label>
      <label v-if="!knownTitle">正式职位名称<input v-model="titleCorrection" maxlength="128"></label>
    </fieldset>
    <label v-for="binding in bindings" :key="binding.id" class="pw-field">
      <span>{{ binding.role_name }} · {{ binding.factory_id }}</span>
      <select v-model="sources[binding.id]" :disabled="busy || !!commandId"><option value="">请选择权限归属</option><option value="assignment">跟随当前主职</option><option value="system_administration">独立系统管理</option><option value="external_collaboration">供应商 / 外部协作</option><option value="individual_exception">独立个人授权</option></select>
    </label>
    <template v-for="o in activeAllows" :key="o.id">
      <label class="pw-check"><input type="checkbox" :checked="exceptions[o.id] === 'keep_original_scope'" :disabled="busy || !!commandId" @change="exceptions[o.id] = ($event.target as HTMLInputElement).checked ? 'keep_original_scope' : ''">确认 {{ permissionName(o.permission_code) }} 保留原范围</label>
    </template>
    <Button v-if="!preview" variant="outline" :disabled="busy || !confirmedOrg || !confirmedDepartment || !confirmedTitle || bindings.some(b => !sources[b.id]) || activeAllows.some(o => !exceptions[o.id])" @click="verify">{{ busy ? '正在核实…' : '核实是否保持原权限' }}</Button>
    <div v-else class="pw-notice"><p>实际新增 {{ preview.permission_diffs.added.length }} 项，停止 {{ preview.permission_diffs.removed.length }} 项。</p>
      <details v-if="preview.permission_diffs.source_changed?.length"><summary>实权保留，其中 {{ preview.permission_diffs.source_changed.length }} 项的授权来源变化</summary>
        <ul><li v-for="t in preview.permission_diffs.source_changed" :key="JSON.stringify([t.permission_code,t.factory_id,t.department])">{{ permissionName(t.permission_code, t.permission_name) }} · {{ t.factory_name }} · {{ t.department_name }}</li></ul>
      </details>
      <label v-if="preview.high_risk" class="pw-check"><input v-model="riskAcknowledged" type="checkbox" :disabled="busy || !!commandId">已核对高风险权限的来源和作用范围</label>
      <Button :disabled="busy || !noDrift" @click="confirm">{{ busy ? '正在确认…' : commandId ? '使用原命令核查并重试' : studio && preview.requires_approval ? '提交来源核实复核' : '确认来源，继续办理' }}</Button></div>
    </template>
  </section>
</template>
