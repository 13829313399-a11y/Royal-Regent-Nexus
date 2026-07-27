<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { Database, LoaderCircle, Save, ServerCog, X } from '@lucide/vue'
import type {
  InjectionArmType,
  InjectionMachineCreateInput,
  InjectionFormalMachineStatus,
  InjectionMachineRecord,
} from '@/types/injectionSchedule'

const props = withDefaults(defineProps<{
  open: boolean
  factoryName: string
  machine?: InjectionMachineRecord | null
  busy?: boolean
  error?: string
}>(), {
  machine: null,
  busy: false,
  error: '',
})

const emit = defineEmits<{
  close: []
  save: [payload: {
    machineId: string | null
    expectedRevision: number | null
    input: InjectionMachineCreateInput
  }]
}>()

type NullableNumberField =
  | 'tonnage'
  | 'maxShotWeightG'
  | 'tieBarWidthMm'
  | 'tieBarHeightMm'
  | 'minMoldThicknessMm'
  | 'maxMoldThicknessMm'
  | 'maxOpeningStrokeMm'
  | 'maxEjectorClearanceMm'

interface MachineForm {
  machineNo: string
  workshop: 'old' | 'new'
  machineClass: string
  tonnage: string
  speedType: string
  screwType: string
  armType: InjectionArmType
  supportedFixtures: string
  fixturesReviewed: boolean
  capabilities: string
  capabilitiesReviewed: boolean
  materialRules: string
  materialRulesReviewed: boolean
  maxShotWeightG: string
  tieBarWidthMm: string
  tieBarHeightMm: string
  minMoldThicknessMm: string
  maxMoldThicknessMm: string
  maxOpeningStrokeMm: string
  maxEjectorClearanceMm: string
  status: InjectionFormalMachineStatus
  schedulingLocked: boolean
}

function emptyForm(): MachineForm {
  return {
    machineNo: '',
    workshop: 'old',
    machineClass: '',
    tonnage: '',
    speedType: '',
    screwType: '',
    armType: 'none',
    supportedFixtures: '',
    fixturesReviewed: false,
    capabilities: '',
    capabilitiesReviewed: false,
    materialRules: '',
    materialRulesReviewed: false,
    maxShotWeightG: '',
    tieBarWidthMm: '',
    tieBarHeightMm: '',
    minMoldThicknessMm: '',
    maxMoldThicknessMm: '',
    maxOpeningStrokeMm: '',
    maxEjectorClearanceMm: '',
    status: 'available',
    schedulingLocked: false,
  }
}

const dialog = ref<HTMLElement | null>(null)
const form = reactive<MachineForm>(emptyForm())

watch(() => [props.open, props.machine?.id] as const, async ([open]) => {
  const source = props.machine
  Object.assign(form, emptyForm(), source
    ? {
        machineNo: source.machineCode,
        workshop: source.workshop === 'new' ? 'new' : 'old',
        machineClass: source.machineClass,
        tonnage: source.tonnageT?.toString() ?? '',
        speedType: source.processType ?? '',
        screwType: source.screwType ?? '',
        armType: /双|double/i.test(source.robotType)
          ? 'double'
          : /单|single/i.test(source.robotType) ? 'single' : 'none',
        supportedFixtures: source.fixtureType ?? '',
        fixturesReviewed: Boolean(source.fixtureType) || source.qualityStatus === 'ready',
        capabilities: source.capabilities.join('、'),
        capabilitiesReviewed: source.qualityStatus === 'ready' || source.capabilities.length > 0,
        materialRules: source.materialRules.join('、'),
        materialRulesReviewed: source.qualityStatus === 'ready' || source.materialRules.length > 0,
        maxShotWeightG: source.maxShotWeightG?.toString() ?? '',
        tieBarWidthMm: source.tieBarXMm?.toString() ?? '',
        tieBarHeightMm: source.tieBarYMm?.toString() ?? '',
        minMoldThicknessMm: source.moldThicknessMinMm?.toString() ?? '',
        maxMoldThicknessMm: source.moldThicknessMaxMm?.toString() ?? '',
        maxOpeningStrokeMm: source.openingStrokeMm?.toString() ?? '',
        maxEjectorClearanceMm: source.ejectorStrokeMm?.toString() ?? '',
        status: source.status,
        schedulingLocked: source.status === 'retired',
      }
    : {})
  if (open) {
    await nextTick()
    dialog.value?.querySelector<HTMLInputElement>('input')?.focus()
  }
}, { immediate: true })

function numberOrNull(field: NullableNumberField) {
  const raw = form[field].trim()
  if (!raw) return null
  const value = Number(raw)
  return Number.isFinite(value) ? value : null
}

function listValue(value: string) {
  return [...new Set(value
    .split(/[、,，]/)
    .map((entry) => entry.trim())
    .filter(Boolean))]
}

const validationMessage = computed(() => {
  if (!form.machineNo.trim()) return '请填写机台编号'
  if (!form.machineClass.trim()) return '请填写机安 / 吨位等级'
  const numericFields: Array<{ field: NullableNumberField; label: string }> = [
    { field: 'tonnage', label: '公称吨位' },
    { field: 'maxShotWeightG', label: '最大射胶量' },
    { field: 'tieBarWidthMm', label: '拉杆内距宽' },
    { field: 'tieBarHeightMm', label: '拉杆内距高' },
    { field: 'minMoldThicknessMm', label: '最小模厚' },
    { field: 'maxMoldThicknessMm', label: '最大模厚' },
    { field: 'maxOpeningStrokeMm', label: '最大开模行程' },
    { field: 'maxEjectorClearanceMm', label: '最大顶出空间' },
  ]
  const invalid = numericFields.find(({ field }) => {
    const raw = form[field].trim()
    return raw && (!Number.isFinite(Number(raw)) || Number(raw) < 0)
  })
  if (invalid) return `${invalid.label}必须是非负数字`
  const minThickness = numberOrNull('minMoldThicknessMm')
  const maxThickness = numberOrNull('maxMoldThicknessMm')
  if (minThickness != null && maxThickness != null && minThickness > maxThickness) {
    return '最小模厚不能大于最大模厚'
  }
  return ''
})

function submit() {
  if (validationMessage.value || props.busy) return
  const fixtureList = listValue(form.supportedFixtures)
  const capabilityList = listValue(form.capabilities)
  const materialRuleList = listValue(form.materialRules)
  emit('save', {
    machineId: props.machine?.id ?? null,
    expectedRevision: props.machine?.revision ?? null,
    input: {
      machineCode: form.machineNo.trim(),
      machineName: props.machine?.machineName || form.machineNo.trim(),
      workshop: form.workshop,
      machineClass: form.machineClass.trim(),
      tonnageT: numberOrNull('tonnage'),
      processType: form.speedType.trim(),
      screwType: form.screwType.trim(),
      robotType: form.armType === 'double'
        ? '双臂'
        : form.armType === 'single' ? '单臂' : '无',
      fixtureType: form.fixturesReviewed ? fixtureList.join('、') : '',
      maxShotWeightG: numberOrNull('maxShotWeightG'),
      tieBarXMm: numberOrNull('tieBarWidthMm'),
      tieBarYMm: numberOrNull('tieBarHeightMm'),
      moldThicknessMinMm: numberOrNull('minMoldThicknessMm'),
      moldThicknessMaxMm: numberOrNull('maxMoldThicknessMm'),
      openingStrokeMm: numberOrNull('maxOpeningStrokeMm'),
      ejectorStrokeMm: numberOrNull('maxEjectorClearanceMm'),
      status: form.schedulingLocked ? 'retired' : form.status,
      availableAt: props.machine?.availableAt ?? '',
      capabilities: form.capabilitiesReviewed ? capabilityList : [],
      materialRules: form.materialRulesReviewed ? materialRuleList : [],
      qualityStatus: form.fixturesReviewed
        && form.capabilitiesReviewed
        && form.materialRulesReviewed
        ? 'ready'
        : 'incomplete',
    },
  })
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="machine-editor-backdrop" @click.self="emit('close')">
      <section
        ref="dialog"
        class="machine-editor"
        role="dialog"
        aria-modal="true"
        aria-labelledby="machine-editor-title"
        @keydown.esc="emit('close')"
      >
        <header>
          <span><ServerCog aria-hidden="true" /></span>
          <div>
            <small>Phase 3 · {{ factoryName }}主数据</small>
            <h2 id="machine-editor-title">{{ machine ? `编辑 ${machine.machineCode}` : '新增机台' }}</h2>
            <p>已确认空值和未知值分开保存；更新使用 revision 乐观锁。</p>
          </div>
          <button type="button" aria-label="关闭机台编辑器" @click="emit('close')">
            <X aria-hidden="true" />
          </button>
        </header>

        <form @submit.prevent="submit">
          <fieldset>
            <legend>基本资料</legend>
            <label>
              <span>机台编号 *</span>
              <input
                v-model="form.machineNo"
                maxlength="40"
                placeholder="例如：旧2"
                :disabled="Boolean(machine)"
              >
            </label>
            <label>
              <span>车间 *</span>
              <select v-model="form.workshop">
                <option value="old">旧车间</option>
                <option value="new">新车间</option>
              </select>
            </label>
            <label>
              <span>机安 / 吨位等级 *</span>
              <input v-model="form.machineClass" maxlength="60" placeholder="例如：180T">
            </label>
            <label>
              <span>公称吨位</span>
              <input v-model="form.tonnage" inputmode="decimal" placeholder="未知可留空">
            </label>
            <label>
              <span>机型</span>
              <input v-model="form.speedType" maxlength="60" placeholder="普通 / 高速">
            </label>
            <label>
              <span>螺杆类型</span>
              <input v-model="form.screwType" maxlength="60" placeholder="例如：通用 / PVC / PC合金">
            </label>
            <label>
              <span>机械手</span>
              <select v-model="form.armType">
                <option value="none">无机械手</option>
                <option value="single">单臂</option>
                <option value="double">双臂</option>
              </select>
            </label>
          </fieldset>

          <fieldset>
            <legend>自动匹配硬约束</legend>
            <label><span>最大射胶量（g）</span><input v-model="form.maxShotWeightG" inputmode="decimal"></label>
            <label><span>拉杆内距宽（mm）</span><input v-model="form.tieBarWidthMm" inputmode="decimal"></label>
            <label><span>拉杆内距高（mm）</span><input v-model="form.tieBarHeightMm" inputmode="decimal"></label>
            <label><span>最小模厚（mm）</span><input v-model="form.minMoldThicknessMm" inputmode="decimal"></label>
            <label><span>最大模厚（mm）</span><input v-model="form.maxMoldThicknessMm" inputmode="decimal"></label>
            <label><span>最大开模行程（mm）</span><input v-model="form.maxOpeningStrokeMm" inputmode="decimal"></label>
            <label><span>最大顶出空间（mm）</span><input v-model="form.maxEjectorClearanceMm" inputmode="decimal"></label>
          </fieldset>

          <fieldset class="machine-editor__review">
            <legend>能力资料：未知 ≠ 已确认没有</legend>
            <label>
              <span>夹具 / 吸盘</span>
              <input v-model="form.supportedFixtures" :disabled="!form.fixturesReviewed" placeholder="用逗号分隔">
              <em><input v-model="form.fixturesReviewed" type="checkbox"> 已核对；留空表示确认无夹具</em>
            </label>
            <label>
              <span>工艺能力</span>
              <input v-model="form.capabilities" :disabled="!form.capabilitiesReviewed" placeholder="用逗号分隔">
              <em><input v-model="form.capabilitiesReviewed" type="checkbox"> 已核对；留空表示确认无特殊能力</em>
            </label>
            <label>
              <span>材料限制</span>
              <input
                v-model="form.materialRules"
                :disabled="!form.materialRulesReviewed"
                placeholder="允许材料，用逗号分隔；例如 ABS、PC"
              >
              <em>
                <input v-model="form.materialRulesReviewed" type="checkbox">
                已核对；留空表示确认无材料限制
              </em>
            </label>
            <label>
              <span>机台状态</span>
              <select v-model="form.status">
                <option value="available">可用</option>
                <option value="maintenance">保养</option>
                <option value="stopped">停机</option>
                <option value="retired">退役</option>
              </select>
              <em><input v-model="form.schedulingLocked" type="checkbox"> 禁止参与排产</em>
            </label>
          </fieldset>

          <p v-if="validationMessage || error" class="machine-editor__error" role="alert">
            {{ validationMessage || error }}
          </p>
          <p class="machine-editor__factory">
            <Database aria-hidden="true" />
            只写入 {{ factoryName }}；跨厂查看权限不会扩大写入范围
          </p>

          <footer>
            <button type="button" @click="emit('close')">取消</button>
            <button type="submit" :disabled="Boolean(validationMessage) || busy">
              <LoaderCircle v-if="busy" class="spin" aria-hidden="true" />
              <Save v-else aria-hidden="true" />
              {{ machine ? '保存机台资料' : '建立机台' }}
            </button>
          </footer>
        </form>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.machine-editor-backdrop {
  position: fixed;
  z-index: 130;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgb(15 23 42 / 46%);
}

.machine-editor {
  width: min(940px, 100%);
  max-height: min(860px, calc(100vh - 48px));
  overflow: auto;
  border: 1px solid #d9e3e6;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 28px 80px rgb(15 23 42 / 24%);
}

.machine-editor > header {
  position: sticky;
  z-index: 2;
  top: 0;
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 14px;
  align-items: start;
  padding: 20px 22px;
  border-bottom: 1px solid #e2e8f0;
  background: rgb(255 255 255 / 96%);
  backdrop-filter: blur(10px);
}

.machine-editor > header > span {
  display: grid;
  width: 42px;
  height: 42px;
  place-items: center;
  border-radius: 12px;
  color: #0f766e;
  background: #e6f7f4;
}

.machine-editor > header svg {
  width: 21px;
}

.machine-editor h2 {
  margin: 2px 0 3px;
  color: #0f172a;
  font-size: 20px;
}

.machine-editor header small {
  color: #0f766e;
  font-weight: 750;
}

.machine-editor header p {
  margin: 0;
  color: #64748b;
  font-size: 13px;
}

.machine-editor header button {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  border: 0;
  border-radius: 10px;
  color: #64748b;
  background: #f1f5f9;
}

.machine-editor form {
  padding: 20px 22px 22px;
}

.machine-editor fieldset {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin: 0 0 18px;
  padding: 17px;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  background: #fbfcfc;
}

.machine-editor legend {
  padding: 0 8px;
  color: #334155;
  font-size: 13px;
  font-weight: 800;
}

.machine-editor label {
  display: grid;
  gap: 6px;
  min-width: 0;
  color: #475569;
  font-size: 12px;
  font-weight: 700;
}

.machine-editor input,
.machine-editor select {
  width: 100%;
  min-height: 40px;
  border: 1px solid #cbd5e1;
  border-radius: 9px;
  padding: 0 11px;
  color: #0f172a;
  background: #fff;
  font: inherit;
}

.machine-editor input:focus,
.machine-editor select:focus {
  border-color: #0f766e;
  outline: 3px solid rgb(20 184 166 / 14%);
}

.machine-editor input:disabled {
  color: #94a3b8;
  background: #f1f5f9;
}

.machine-editor__review {
  grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
}

.machine-editor label em {
  display: flex;
  gap: 7px;
  align-items: center;
  color: #64748b;
  font-size: 11px;
  font-style: normal;
  font-weight: 600;
}

.machine-editor label em input {
  width: 15px;
  min-height: 15px;
}

.machine-editor__error {
  padding: 10px 12px;
  border: 1px solid #fecaca;
  border-radius: 10px;
  color: #b91c1c;
  background: #fef2f2;
  font-size: 13px;
}

.machine-editor__factory {
  display: flex;
  gap: 7px;
  align-items: center;
  color: #64748b;
  font-size: 12px;
}

.machine-editor__factory svg {
  width: 15px;
}

.machine-editor footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding-top: 16px;
  border-top: 1px solid #e2e8f0;
}

.machine-editor footer button {
  display: inline-flex;
  min-height: 42px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  padding: 0 18px;
  color: #334155;
  background: #fff;
  font-weight: 800;
}

.machine-editor footer button:last-child {
  border-color: #0f766e;
  color: #fff;
  background: #0f766e;
}

.machine-editor footer button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.spin {
  animation: machine-editor-spin 0.8s linear infinite;
}

@keyframes machine-editor-spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 860px) {
  .machine-editor fieldset {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 600px) {
  .machine-editor-backdrop {
    align-items: end;
    padding: 0;
  }

  .machine-editor {
    max-height: 94vh;
    border-radius: 18px 18px 0 0;
  }

  .machine-editor fieldset,
  .machine-editor__review {
    grid-template-columns: 1fr !important;
  }
}
</style>
