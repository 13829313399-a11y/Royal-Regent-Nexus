<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { Position } from '@/api/positionReviews'
import { identityApi, type ChangeRecord, type ChangePreview, type PersonIdentity } from '@/api/identity'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
import { Button } from '@/components/ui/button'
import { permissionName } from './positionLabels'
const props = defineProps<{ userId: string; official?: Position | null }>()
const emit = defineEmits<{ saved: []; locked: [boolean] }>()
const person = ref<PersonIdentity>(), error = ref(''), busy = ref(false), preview = ref<ChangePreview>(), savedDraft = ref<ChangeRecord>()
const sources = ref<Record<string, string>>({}), exceptions = ref<Record<string, string>>({})
let generation = 0
onBeforeUnmount(() => { ++generation; emit('locked', false) })
const bindings = computed(() => person.value?.role_bindings.filter(b => b.state === 'active') ?? [])
watch(() => props.userId, async id => {
  const current = ++generation; person.value = undefined; preview.value = undefined; savedDraft.value = undefined; sources.value = {}; exceptions.value = {}
  try { const value = await identityApi.person(id); if (current === generation) { person.value = value; sources.value = Object.fromEntries(value.role_bindings.map(b => [b.id, ''])) } }
  catch (e) { if (current === generation) error.value = getApiErrorMessage(e) }
}, { immediate: true })
watch([sources, exceptions], () => { preview.value = undefined }, { deep: true, flush: 'sync' })
async function verify() {
  if (!person.value || busy.value) return
  const current = generation
  busy.value = true; error.value = ''
  try {
    const p = person.value
    const row = await identityApi.draft({ request_type: 'confirm_identity', target_user_id: p.id, reason: '岗位工作台核实历史授权来源；保持实际权限',
      base_identity_version: p.identity_version, base_authorization_version: p.authorization_version,
      new_assignment: { org_unit_id: props.official?.org_unit_id || p.primary_assignment?.org_unit_id || p.primary_factory_id, department_code: p.primary_department,
        official_position_title: p.position, assignment_type: 'regular', is_primary: true, role_bindings: [] },
      binding_dispositions: bindings.value.map(b => ({ binding_id: b.id, source: sources.value[b.id] || '' })),
      exception_decisions: (p.overrides ?? []).filter(o => o.effect === 'allow').map(o => ({ override_id: o.id, decision: exceptions.value[o.id] || '' })),
    }, savedDraft.value)
    if (current !== generation) return
    savedDraft.value = row
    const result = await identityApi.preview(row.id)
    if (current === generation) preview.value = result
  } catch (e) { if (current === generation) error.value = getApiErrorMessage(e) }
  finally { if (current === generation) busy.value = false }
}
const commandId = ref('')
watch([busy, commandId], ([pending, command]) => emit('locked', pending || !!command))
const noDrift = computed(() => !!preview.value && !preview.value.high_risk && !preview.value.requires_approval
  && !preview.value.permission_diffs.added.length && !preview.value.permission_diffs.removed.length)
function finished() { commandId.value = ''; emit('locked', false); emit('saved') }
async function confirm() {
  if (!savedDraft.value || !preview.value || busy.value || !noDrift.value) return
  const current = generation
  busy.value = true; error.value = ''; commandId.value ||= createRandomUuid()
  try {
    const result = await identityApi.commit(savedDraft.value, preview.value, commandId.value)
    if (current === generation && result.state === 'applied') finished()
  } catch (e) {
    if (current !== generation) return
    try { const result = await identityApi.change(savedDraft.value.id); if (current === generation && result.state === 'applied') { finished(); return } }
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
    <p v-if="error" role="alert" class="pw-error">{{ error }}</p>
    <label v-for="binding in bindings" :key="binding.id" class="pw-field">
      <span>{{ binding.role_name }} · {{ binding.factory_id }}</span>
      <select v-model="sources[binding.id]" :disabled="busy || !!commandId"><option value="">请选择权限归属</option><option value="assignment">跟随当前主职</option><option value="system_administration">独立系统管理</option><option value="external_collaboration">供应商 / 外部协作</option><option value="individual_exception">独立个人授权</option></select>
    </label>
    <template v-for="o in person?.overrides ?? []" :key="o.id">
      <label v-if="o.effect === 'allow'" class="pw-check"><input type="checkbox" :checked="exceptions[o.id] === 'keep_original_scope'" :disabled="busy || !!commandId" @change="exceptions[o.id] = ($event.target as HTMLInputElement).checked ? 'keep_original_scope' : ''">确认 {{ permissionName(o.permission_code) }} 保留原范围</label>
    </template>
    <Button v-if="!preview" variant="outline" :disabled="busy || bindings.some(b => !sources[b.id])" @click="verify">{{ busy ? '正在核实…' : '核实是否保持原权限' }}</Button>
    <div v-else class="pw-notice"><p>实际新增 {{ preview.permission_diffs.added.length }} 项，停止 {{ preview.permission_diffs.removed.length }} 项。</p><Button :disabled="busy || !noDrift" @click="confirm">{{ busy ? '正在确认…' : commandId ? '使用原命令核查并重试' : '确认来源，继续办理' }}</Button></div>
  </section>
</template>
