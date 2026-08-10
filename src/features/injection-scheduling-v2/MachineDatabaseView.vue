<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  AlertTriangle,
  ArrowLeft,
  Bot,
  CheckCircle2,
  Database,
  Gauge,
  House,
  Plus,
  RefreshCw,
  Save,
  Search,
  Server,
  Wrench,
  X,
} from '@lucide/vue'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import { useAuthStore } from '@/stores/auth'
import {
  createMachineMaster,
  listMachineMasters,
  updateMachineMaster,
  type MachineMasterInput,
} from './api/injectionSchedulingV2Api'
import type { MachineRecord } from './types'
import './injection-scheduling-v2.css'
import './styles/tokens.css'
import './styles/polish.css'
import './shared-mold-database.css'
import './machine-database.css'

const factoryNames: Record<string, string> = {
  huaxing: '华兴',
  'huakang-a': '华康 A',
  'huakang-b': '华康 B',
  'huakang-c': '华康 C',
  'huakang-d': '华康 D',
  huadeng: '华登',
}
const schedulingDepartments = ['production', 'molding', 'pmc-warehouse', 'warehouse', 'management']
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const requestedFactory = typeof route.query.factory === 'string' ? route.query.factory : 'huaxing'
const factoryId = ref(factoryNames[requestedFactory] ? requestedFactory : 'huaxing')
const search = ref('')
const status = ref('')
const machines = ref<MachineRecord[]>([])
const loading = ref(false)
const loadError = ref('')
const editorOpen = ref(false)
const editing = ref<MachineRecord | null>(null)
const saving = ref(false)
const feedback = reactive({ message: '', tone: 'success' as 'success' | 'error' })
let searchTimer: ReturnType<typeof setTimeout> | null = null
let feedbackTimer: ReturnType<typeof setTimeout> | null = null

const canManage = computed(() => schedulingDepartments.some((department) => authStore.can('injection_scheduling:manage_master', factoryId.value, department)))
const availableCount = computed(() => machines.value.filter((item) => item.status === 'available').length)
const attentionCount = computed(() => machines.value.filter((item) => ['maintenance', 'offline'].includes(item.status)).length)
const completeCount = computed(() => machines.value.filter((item) => item.normalizationStatus === 'COMPLETE' && item.injectionCapacityG).length)

interface MachineForm {
  machineCode: string
  area: string
  position: string
  machineClassRaw: string
  clampingForceTons: number | null
  injectionCapacityG: number | null
  tieBarXmm: number | null
  tieBarYmm: number | null
  machineType: string
  specialMachineType: string
  processTags: string
  robotCapabilities: string
  fixtureCapabilities: string
  processRestrictions: string
  status: MachineRecord['status']
  remarks: string
  manufacturer: string
  model: string
  totalPowerRaw: string
  injectionSpecRaw: string
  manufactureYear: string
  machineTypeRaw: string
  robotTypeRaw: string
  robotModel: string
  robotPurchaseYear: string
  chillerModel: string
  chillerPowerRaw: string
  sprueCrusherModel: string
  sprueCrusherPowerRaw: string
  loaderModel: string
  loaderPowerRaw: string
}

const blankForm = (): MachineForm => ({
  machineCode: '', area: '', position: '', machineClassRaw: '', clampingForceTons: null,
  injectionCapacityG: null, tieBarXmm: null, tieBarYmm: null, machineType: 'standard',
  specialMachineType: '', processTags: '', robotCapabilities: '', fixtureCapabilities: '',
  processRestrictions: '', status: 'available', remarks: '', manufacturer: '', model: '',
  totalPowerRaw: '', injectionSpecRaw: '', manufactureYear: '', machineTypeRaw: '',
  robotTypeRaw: '', robotModel: '', robotPurchaseYear: '', chillerModel: '', chillerPowerRaw: '',
  sprueCrusherModel: '', sprueCrusherPowerRaw: '', loaderModel: '', loaderPowerRaw: '',
})
const form = reactive<MachineForm>(blankForm())
const csv = (value: string) => value.split(/[，,\n]/).map((item) => item.trim()).filter(Boolean)
const detailText = (machine: MachineRecord, key: string) => {
  const value = machine.equipmentDetails[key]
  return value == null ? '' : String(value)
}
const machineTypeLabel = (value: string) => ({ standard: '普通', high_speed: '高速', all_electric: '全电动机', vertical: '立式', two_color: '双色机' } as Record<string, string>)[value] || value || '—'
const statusLabel = (value: MachineRecord['status']) => ({ available: '可用', running: '生产中', maintenance: '维护中', offline: '停用' } as const)[value]

function errorMessage(error: unknown) {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && typeof (detail as { message?: unknown }).message === 'string') return String((detail as { message: string }).message)
  return error instanceof Error ? error.message : '请求失败，请稍后重试'
}

function notify(message: string, tone: 'success' | 'error' = 'success') {
  feedback.message = message
  feedback.tone = tone
  if (feedbackTimer) clearTimeout(feedbackTimer)
  feedbackTimer = setTimeout(() => { feedback.message = '' }, 4200)
}

async function loadMachines() {
  loading.value = true
  loadError.value = ''
  try {
    machines.value = await listMachineMasters(factoryId.value, { search: search.value.trim(), status: status.value })
  } catch (error) {
    loadError.value = errorMessage(error)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  Object.assign(form, blankForm())
  editorOpen.value = true
}

function openEdit(machine: MachineRecord) {
  editing.value = machine
  Object.assign(form, {
    ...blankForm(),
    machineCode: machine.code,
    area: machine.area,
    position: machine.position,
    machineClassRaw: machine.aClassRaw,
    clampingForceTons: machine.clampingForceTons,
    injectionCapacityG: machine.injectionCapacityG,
    tieBarXmm: machine.tieBarXmm,
    tieBarYmm: machine.tieBarYmm,
    machineType: machine.machineType,
    specialMachineType: machine.specialMachineType,
    processTags: machine.processTags.join(', '),
    robotCapabilities: machine.armCapabilities.join(', '),
    fixtureCapabilities: machine.fixtureCapabilities.join(', '),
    processRestrictions: machine.processRestrictions.join(', '),
    status: machine.status,
    remarks: machine.remarks,
    manufacturer: detailText(machine, 'manufacturer'),
    model: detailText(machine, 'model'),
    totalPowerRaw: detailText(machine, 'total_power_raw'),
    injectionSpecRaw: detailText(machine, 'injection_spec_raw'),
    manufactureYear: detailText(machine, 'manufacture_year'),
    machineTypeRaw: detailText(machine, 'machine_type_raw'),
    robotTypeRaw: detailText(machine, 'robot_type_raw'),
    robotModel: detailText(machine, 'robot_model'),
    robotPurchaseYear: detailText(machine, 'robot_purchase_year'),
    chillerModel: detailText(machine, 'chiller_model'),
    chillerPowerRaw: detailText(machine, 'chiller_power_raw'),
    sprueCrusherModel: detailText(machine, 'sprue_crusher_model'),
    sprueCrusherPowerRaw: detailText(machine, 'sprue_crusher_power_raw'),
    loaderModel: detailText(machine, 'loader_model'),
    loaderPowerRaw: detailText(machine, 'loader_power_raw'),
  })
  editorOpen.value = true
}

function payload(): MachineMasterInput {
  const previous = editing.value?.equipmentDetails || {}
  return {
    machineCode: form.machineCode.trim(), area: form.area.trim(), position: form.position.trim(),
    machineClassRaw: form.machineClassRaw.trim(), clampingForceTons: form.clampingForceTons || null,
    injectionCapacityG: form.injectionCapacityG || null, tieBarXmm: form.tieBarXmm || null,
    tieBarYmm: form.tieBarYmm || null, machineType: form.machineType,
    processTags: csv(form.processTags), robotCapabilities: csv(form.robotCapabilities),
    fixtureCapabilities: csv(form.fixtureCapabilities), processRestrictions: csv(form.processRestrictions),
    specialMachineType: form.specialMachineType.trim(), status: form.status, remarks: form.remarks.trim(),
    equipmentDetails: {
      ...previous,
      manufacturer: form.manufacturer.trim(), model: form.model.trim(), total_power_raw: form.totalPowerRaw.trim(),
      injection_spec_raw: form.injectionSpecRaw.trim(), manufacture_year: form.manufactureYear.trim(),
      machine_type_raw: form.machineTypeRaw.trim(), robot_type_raw: form.robotTypeRaw.trim(),
      robot_model: form.robotModel.trim(), robot_purchase_year: form.robotPurchaseYear.trim(),
      chiller_model: form.chillerModel.trim(), chiller_power_raw: form.chillerPowerRaw.trim(),
      sprue_crusher_model: form.sprueCrusherModel.trim(), sprue_crusher_power_raw: form.sprueCrusherPowerRaw.trim(),
      loader_model: form.loaderModel.trim(), loader_power_raw: form.loaderPowerRaw.trim(),
    },
  }
}

async function submit() {
  if (!canManage.value || saving.value) return
  saving.value = true
  try {
    if (editing.value) await updateMachineMaster(factoryId.value, editing.value, payload())
    else await createMachineMaster(factoryId.value, payload())
    editorOpen.value = false
    notify(editing.value ? '机台资料已保存' : '机台已新增')
    await loadMachines()
  } catch (error) {
    notify(errorMessage(error), 'error')
  } finally {
    saving.value = false
  }
}

function changeFactory(value: string) {
  factoryId.value = value
  void router.replace({ query: { ...route.query, factory: value } })
  editorOpen.value = false
  void loadMachines()
}

watch([search, status], () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { void loadMachines() }, 260)
})
onMounted(() => { void loadMachines() })
onBeforeUnmount(() => {
  if (searchTimer) clearTimeout(searchTimer)
  if (feedbackTimer) clearTimeout(feedbackTimer)
})
</script>

<template>
  <div class="injection-scheduling-v2 shared-mold-database machine-database">
    <header class="scheduling-topbar">
      <div class="brand-mark"><Bot :size="22" /></div><div class="brand-copy"><strong>Royal Regent Nexus</strong><span>ROYAL REGENT · PRODUCTION INTELLIGENCE</span></div>
      <button type="button" class="topbar-home-button" @click="router.push({ name: 'dashboard' })"><House :size="15" /><span>返回主页</span></button>
      <div class="topbar-live"><span class="live-dot"></span><span>厂区机台主数据在线</span><b>正式数据</b></div><AccountMenu compact class="scheduling-account-menu" />
    </header>
    <section class="scheduling-commandbar mold-commandbar" aria-label="机台数据库命令栏">
      <div class="page-identity"><span class="eyebrow">生产部 / 注塑排产 / 机台数据库</span><strong>厂区机台数据库</strong><span class="readonly-badge editable">按厂区隔离</span></div>
      <button class="command-button is-secondary" @click="router.push({ name: 'injection-scheduling-v2', query: { factory: factoryId } })"><ArrowLeft :size="15" />返回排产</button>
      <button class="command-button is-secondary" @click="router.push({ name: 'injection-scheduling-mold-database', query: { factory: factoryId } })"><Database :size="15" />共享模具库</button>
      <label class="command-field factory-field"><span>厂区</span><select :value="factoryId" @change="changeFactory(($event.target as HTMLSelectElement).value)"><option v-for="(name, id) in factoryNames" :key="id" :value="id">{{ name }}</option></select></label>
      <label class="command-search"><Search :size="16" /><input v-model="search" placeholder="搜索机号、车间、型号、备注…" /></label>
      <button class="command-button is-secondary" :disabled="loading" @click="loadMachines"><RefreshCw :size="15" :class="{ spinning: loading }" />刷新数据</button>
      <button class="command-button auto" :disabled="!canManage" :title="canManage ? '新增厂区机台' : '缺少机台主数据维护权限'" @click="openCreate"><Plus :size="15" />新增机台</button>
    </section>
    <main>
      <section class="mold-kpi-strip">
        <article class="mold-kpi teal"><div><span>{{ factoryNames[factoryId] }}机台总数</span><strong>{{ machines.length }}</strong><p>仅展示当前厂区主数据</p></div><Server :size="20" /></article>
        <article class="mold-kpi blue"><div><span>当前可用</span><strong>{{ availableCount }}</strong><p>可参与排程候选机台</p></div><CheckCircle2 :size="20" /></article>
        <article class="mold-kpi amber"><div><span>维护 / 停用</span><strong>{{ attentionCount }}</strong><p>不会作为正常排程候选</p></div><Wrench :size="20" /></article>
        <article class="mold-kpi violet"><div><span>核心资格资料完整</span><strong>{{ completeCount }}</strong><p>安数与射胶量可用于资格判断</p></div><Gauge :size="20" /></article>
      </section>
      <section class="mold-catalog-workspace">
        <header class="mold-catalog-header"><div><span class="catalog-icon"><Server :size="18" /></span><div><strong>{{ factoryNames[factoryId] }}机台目录</strong><p>机号在厂区内唯一；型号、机械手、辅机与备注可独立维护</p></div></div><label><span>状态</span><select v-model="status"><option value="">全部</option><option value="available">可用</option><option value="running">生产中</option><option value="maintenance">维护中</option><option value="offline">停用</option></select></label><span class="catalog-count">{{ machines.length }} 台</span></header>
        <div v-if="loadError" class="catalog-error"><AlertTriangle :size="16" /><span>{{ loadError }}</span><button @click="loadMachines">重新加载</button></div>
        <div class="mold-table-scroll"><table class="mold-catalog-table machine-catalog-table"><thead><tr><th>机号 / 位置</th><th>品牌 / 型号</th><th>安数 / 合模力</th><th>射胶量 / 机架</th><th>机器类型</th><th>机械手</th><th>状态</th><th>备注</th><th></th></tr></thead><tbody>
          <tr v-if="loading && !machines.length" v-for="line in 10" :key="line" class="catalog-skeleton"><td colspan="9"><span></span></td></tr>
          <tr v-for="machine in machines" :key="machine.id" tabindex="0" @click="openEdit(machine)" @keydown.enter="openEdit(machine)">
            <td><strong>{{ machine.code }}</strong><span>{{ machine.area }} · {{ machine.position }}号位</span><small>r{{ machine.revision }} · {{ machine.normalizationStatus === 'COMPLETE' ? '已规范' : '待复核' }}</small></td>
            <td><strong>{{ detailText(machine, 'manufacturer') || '—' }}</strong><span>{{ detailText(machine, 'model') || '型号待补' }}</span><small>{{ detailText(machine, 'manufacture_year') || '年份待补' }}</small></td>
            <td><strong>{{ machine.aClass ? `${machine.aClass}A` : machine.aClassRaw || '—' }}</strong><span>{{ machine.clampingForceTons ? `${machine.clampingForceTons}T` : '合模力待补' }}</span></td>
            <td><strong>{{ machine.injectionCapacityG ? `${machine.injectionCapacityG}g` : '—' }}</strong><span>{{ machine.tieBarXmm && machine.tieBarYmm ? `${machine.tieBarXmm} × ${machine.tieBarYmm} mm` : '机架尺寸待补' }}</span></td>
            <td><strong>{{ detailText(machine, 'machine_type_raw') || machineTypeLabel(machine.machineType) }}</strong><span>{{ detailText(machine, 'total_power_raw') || '功率待补' }}</span></td>
            <td><strong>{{ detailText(machine, 'robot_type_raw') || '—' }}</strong><span>{{ detailText(machine, 'robot_model') || '型号待补' }}</span></td>
            <td><span class="machine-status-chip" :class="machine.status">{{ statusLabel(machine.status) }}</span></td><td><span>{{ machine.remarks || '—' }}</span></td>
            <td><button class="row-detail-button" @click.stop="openEdit(machine)">{{ canManage ? '查看 / 编辑' : '查看' }}</button></td>
          </tr>
          <tr v-if="!loading && !machines.length"><td colspan="9" class="catalog-empty"><Server :size="28" /><strong>当前厂区没有符合条件的机台</strong><span>可切换厂区、调整筛选或新增机台</span></td></tr>
        </tbody></table></div>
      </section>
    </main>
    <div v-if="editorOpen" class="mold-drawer-layer" @mousedown.self="editorOpen = false"><aside class="mold-proposal-drawer machine-editor" aria-label="机台资料编辑">
      <header><div><span>{{ editing ? '机台资料详情' : '新增机台' }}</span><strong>{{ editing?.code || '新建厂区机台' }}</strong><p>{{ factoryNames[factoryId] }} · {{ canManage ? '可编辑正式主数据' : '只读查看' }}</p></div><button @click="editorOpen = false"><X :size="18" /></button></header>
      <form class="proposal-form" @submit.prevent="submit"><fieldset :disabled="saving || !canManage"><legend>1. 机台身份与排程资格</legend><div class="proposal-grid machine-form-grid">
        <label><span>机号 *</span><input v-model="form.machineCode" required placeholder="例如 旧1 / 新1" /></label><label><span>运行状态</span><select v-model="form.status"><option value="available">可用</option><option value="running">生产中</option><option value="maintenance">维护中</option><option value="offline">停用</option></select></label>
        <label><span>摆放区域 *</span><input v-model="form.area" required /></label><label><span>机位 *</span><input v-model="form.position" required /></label><label><span>安数 *</span><input v-model="form.machineClassRaw" required placeholder="例如 32A" /></label><label><span>合模力（T）</span><input v-model.number="form.clampingForceTons" type="number" min="0" step="0.001" /></label>
        <label><span>射胶量（g）</span><input v-model.number="form.injectionCapacityG" type="number" min="0" step="0.001" /></label><label><span>机器分类</span><select v-model="form.machineType"><option value="standard">普通</option><option value="high_speed">高速</option><option value="all_electric">全电动机</option><option value="vertical">立式</option><option value="two_color">双色机</option></select></label>
        <label><span>机架 X（mm）</span><input v-model.number="form.tieBarXmm" type="number" min="0" step="0.001" /></label><label><span>机架 Y（mm）</span><input v-model.number="form.tieBarYmm" type="number" min="0" step="0.001" /></label>
        <label><span>机械手能力代码</span><input v-model="form.robotCapabilities" placeholder="single, dual" /></label><label><span>工艺标签</span><input v-model="form.processTags" placeholder="high_speed" /></label><label><span>夹具能力</span><input v-model="form.fixtureCapabilities" /></label><label><span>特殊机型代码</span><input v-model="form.specialMachineType" /></label><label class="wide"><span>工艺限制</span><input v-model="form.processRestrictions" /></label>
      </div></fieldset>
      <fieldset :disabled="saving || !canManage"><legend>2. 设备明细</legend><div class="proposal-grid machine-form-grid"><label><span>品牌 / 名称</span><input v-model="form.manufacturer" /></label><label><span>型号</span><input v-model="form.model" /></label><label><span>总功率原文</span><input v-model="form.totalPowerRaw" /></label><label><span>射胶规格原文</span><input v-model="form.injectionSpecRaw" /></label><label><span>机器年份</span><input v-model="form.manufactureYear" /></label><label><span>机器类型原文</span><input v-model="form.machineTypeRaw" /></label><label><span>机械手类型</span><input v-model="form.robotTypeRaw" /></label><label><span>机械手型号</span><input v-model="form.robotModel" /></label><label><span>机械手购买年份</span><input v-model="form.robotPurchaseYear" /></label><label><span>冷水机型号 / 功率</span><input v-model="form.chillerModel" /><input v-model="form.chillerPowerRaw" /></label><label><span>水口机型号 / 功率</span><input v-model="form.sprueCrusherModel" /><input v-model="form.sprueCrusherPowerRaw" /></label><label><span>吸料机型号 / 功率</span><input v-model="form.loaderModel" /><input v-model="form.loaderPowerRaw" /></label></div></fieldset>
      <fieldset :disabled="saving || !canManage"><legend>3. 文员备注</legend><label class="reason-field"><span>备注</span><textarea v-model="form.remarks" maxlength="4000" placeholder="维修提示、专用螺杆、抽芯限制或其他现场说明"></textarea><small>{{ form.remarks.length }}/4000</small></label></fieldset>
      <footer><button type="button" class="secondary" @click="editorOpen = false">关闭</button><button v-if="canManage" type="submit" class="primary" :disabled="saving"><RefreshCw v-if="saving" :size="15" class="spinning" /><Save v-else :size="15" />{{ saving ? '保存中' : '保存机台资料' }}</button></footer>
      </form>
    </aside></div>
    <div v-if="feedback.message" class="scheduling-feedback-toast" :class="feedback.tone"><CheckCircle2 v-if="feedback.tone === 'success'" :size="17" /><AlertTriangle v-else :size="17" /><span>{{ feedback.message }}</span><button @click="feedback.message = ''"><X :size="15" /></button></div>
  </div>
</template>
