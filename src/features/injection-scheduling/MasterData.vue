<script setup lang="ts">
import { vInjDialog } from '@/features/injection-scheduling/composables/injDialog';
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue';
import {
  Plus,
  Save,
  Boxes,
  Cpu,
  CalendarDays,
  SlidersHorizontal,
  Library,
} from '@lucide/vue';
import MasterParameterEditor from './components/MasterParameterEditor.vue';
import InjButton from './components/ui/InjButton.vue';
import InjLoadingState from './components/ui/InjLoadingState.vue';
import { parseParameter } from './parameterAdapter';
import { injectionApi as api } from '@/api/injectionScheduling';
import { useInjectionStore } from '@/stores/injectionScheduling';
import {
  dateText,
  displayValue,
  factories,
  statusText,
  type DataRow,
} from './types';
defineProps<{ canWrite: boolean }>();
const headerReady = ref(false);
onMounted(() => {
  headerReady.value = !!document.getElementById('inj-primary-slot');
});
const originalSettings = ref<Record<string, unknown>>({}),
  originalSettingsText = ref<Record<string, string>>({});
const savingSettings = ref(false);
const masterSections = [
  { value: 'molds', label: '公共模具库', icon: Library },
  { value: 'machines', label: '本厂设备', icon: Cpu },
  { value: 'mold-assets', label: '实物模具', icon: Boxes },
  { value: 'calendar-events', label: '班制日历', icon: CalendarDays },
  { value: 'settings', label: '排产参数', icon: SlidersHorizontal },
];
const originalForm = ref<Record<string, string>>({});
const enumOptions: Record<string, Record<string, string>> = {
  machine_family: {
    HORIZONTAL: '卧式',
    VERTICAL: '立式',
    TWO_COLOR: '双色专用',
  },
  speed_class: { NORMAL: '普通', HIGH_SPEED: '高速', ELECTRIC: '全电' },
  status: { AVAILABLE: '可用', MAINTENANCE: '检修', UNAVAILABLE: '暂不可用' },
  kind: { MAINTENANCE: '检修', HOLIDAY: '停工假期', BREAK: '休息' },
};
const store = useInjectionStore(),
  section = ref('molds'),
  rows = ref<DataRow[]>([]),
  molds = ref<DataRow[]>([]),
  assets = ref<DataRow[]>([]),
  term = ref(''),
  edit = ref<DataRow | null>(null),
  creating = ref(false),
  form = ref<Record<string, string>>({}),
  advanced = ref(false),
  settingsDraft = ref<Record<string, string>>({});
const statusMachine = ref<DataRow | null>(null),
  statusForm = ref({
    operating_status: 'MAINTENANCE',
    recovery_at: '',
    notes: '',
  }),
  relocation = ref<DataRow | null>(null),
  destination = ref(''),
  availableAt = ref('');
type InputField = {
  key: string;
  label: string;
  type?: string;
  required?: boolean;
  hint?: string;
};
const specs: Record<string, InputField[]> = {
  molds: [
    { key: 'mold_code', label: '模号', required: true },
    { key: 'required_machine_a', label: '模具 A', type: 'number' },
    { key: 'part_name', label: '名称' },
    {
      key: 'requirement_raw',
      label: '专用机型 / 原始要求',
      hint: '如：14A高速、立式、双色、不上新15/16',
    },
    { key: 'target_shots_per_day', label: '公共日目标', type: 'number' },
    { key: 'alias_codes', label: '明确别名（每行一个）', type: 'list' },
    {
      key: 'defaults',
      label: '其余公共工艺参数',
      type: 'json',
      hint: '如 {"gross_weight_g": 100, "price_per_shot": 0.25}',
    },
    { key: 'requirements', label: '结构化设备要求', type: 'json' },
    { key: 'notes', label: '资料备注' },
  ],
  machines: [
    { key: 'code', label: '机号', required: true },
    { key: 'workshop', label: '车间' },
    { key: 'machine_a', label: '机台 A', type: 'number' },
    { key: 'clamp_ton', label: '锁模力 T', type: 'number' },
    {
      key: 'machine_family',
      label: '机型',
      hint: 'HORIZONTAL / VERTICAL / TWO_COLOR',
    },
    { key: 'speed_class', label: '速度等级', hint: 'NORMAL / HIGH_SPEED' },
    { key: 'manipulator', label: '机械手' },
    {
      key: 'capabilities',
      label: '设备能力',
      type: 'json',
      hint: '记录夹具、电热等能力',
    },
    {
      key: 'restrictions',
      label: '禁排要求',
      type: 'json',
      hint: '如 {"forbidden_resins": ["PVC"]}',
    },
    { key: 'current_setup', label: '当前装模和材料', type: 'json' },
    { key: 'notes', label: '设备备注' },
  ],
  'mold-assets': [
    { key: 'master_id', label: '所属公共模具', type: 'mold', required: true },
    { key: 'asset_code', label: '实物模具编号', required: true },
    {
      key: 'status',
      label: '资产状态',
      hint: 'AVAILABLE / MAINTENANCE / UNAVAILABLE',
    },
    { key: 'available_at', label: '可用时间', type: 'date' },
    { key: 'notes', label: '位置和可用性说明' },
  ],
  'calendar-events': [
    {
      key: 'resource_type',
      label: '影响范围',
      type: 'resource',
      required: true,
    },
    {
      key: 'resource_id',
      label: '机台 / 实物模具',
      type: 'resourceId',
    },
    { key: 'start_at', label: '开始', type: 'date', required: true },
    { key: 'end_at', label: '恢复时间', type: 'date', hint: '未知时可留空' },
    { key: 'kind', label: '事件类型', hint: 'MAINTENANCE / HOLIDAY / BREAK' },
    { key: 'notes', label: '停工原因' },
  ],
};
const filtered = computed(() =>
  rows.value.filter(
    (r) =>
      !term.value ||
      JSON.stringify(r).toLowerCase().includes(term.value.toLowerCase()),
  ),
);
const headings = computed(() =>
  section.value === 'molds'
    ? ['mold_code', 'part_name', 'required_machine_a', 'requirement_raw']
    : section.value === 'machines'
      ? ['code', 'workshop', 'machine_a', 'machine_family', 'operating_status']
      : section.value === 'mold-assets'
        ? ['asset_code', 'master_id', 'current_factory_id', 'status']
        : ['resource_type', 'resource_id', 'start_at', 'end_at', 'notes'],
);
const labels: Record<string, string> = {
  mold_code: '模号',
  part_name: '名称',
  required_machine_a: '模具 A',
  requirement_raw: '要求原文',
  code: '机号',
  workshop: '车间',
  machine_a: '机台 A',
  machine_family: '机型',
  operating_status: '状态',
  asset_code: '实物模具编号',
  master_id: '公共模具',
  current_factory_id: '所在厂',
  status: '状态',
  resource_type: '影响范围',
  resource_id: '资源',
  start_at: '开始时间',
  end_at: '恢复时间',
  notes: '说明',
};
const parameterLabels: Record<string, string> = {
  day_start: '白班开始',
  night_start: '夜班开始',
  target_basis_hours: '日目标基准小时',
  downstream_lead_days: '后工序准备天数',
  allowance_rate: '材料附加比例',
  material_change_minutes: '换材料清洗分钟',
  working_days: '工作日（周一为 0）',
  daily_breaks: '每日休息时段',
  allowed_upsize: '允许上放 A 等级',
  changeover_reference: '换模 / 换色分钟表',
  cleaning_matrix: '材料清洗矩阵',
  color_ranks: '颜色深浅排序',
  defaults_note: '参数口径说明',
  business_timezone: '业务时区',
  setup_interruptible: '换模是否允许切分',
};
let generation = 0;
const loading = ref(false),
  loadedSection = ref(''),
  loadFailed = ref(false);
const sectionReady = computed(
  () => loadedSection.value === `${store.factory}/${section.value}`,
);
onBeforeUnmount(() => {
  generation++;
});
async function load() {
  if (!store.factory) return;
  const id = ++generation;
  const requestedSection = section.value;
  const sectionKey = `${store.factory}/${requestedSection}`;
  loading.value = true;
  loadFailed.value = false;
  try {
    if (requestedSection === 'settings') {
      const r = await api.get('/settings', { factory_id: store.factory });
      if (id === generation) {
        originalSettings.value = r.parameters;
        settingsDraft.value = Object.fromEntries(
          Object.entries(r.parameters).map(([k, v]) => [
            k,
            typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v),
          ]),
        );
        originalSettingsText.value = { ...settingsDraft.value };
        loadedSection.value = sectionKey;
      }
      return;
    }
    const r = await api.get('/' + requestedSection, {
      factory_id: store.factory,
    });
    if (id !== generation) return;
    rows.value = r.rows;
    if (requestedSection === 'calendar-events') {
      const result = await api.get('/mold-assets', {
        factory_id: store.factory,
      });
      if (id === generation) assets.value = result.rows;
    }
    if (requestedSection === 'mold-assets') {
      const result = await api.get('/molds', { factory_id: store.factory });
      if (id === generation) molds.value = result.rows;
    }
    if (id === generation) loadedSection.value = sectionKey;
  } catch (e) {
    if (id === generation) {
      loadFailed.value = true;
      store.showError(e);
    }
  } finally {
    if (id === generation) loading.value = false;
  }
}
watch(
  () => [store.factory, section.value, store.revision],
  () => {
    if (!store.dirty) void load();
  },
  { immediate: true },
);
function open(row?: DataRow) {
  edit.value = row || null;
  creating.value = !row;
  advanced.value = false;
  form.value = Object.fromEntries(
    (specs[section.value] || []).map((s) => {
      const value =
        s.key === 'target_shots_per_day'
          ? row?.defaults?.target_shots_per_day
          : row?.[s.key];
      return [
        s.key,
        value == null
          ? ''
          : s.type === 'list'
            ? value.join('\n')
            : typeof value === 'object'
              ? JSON.stringify(value, null, 2)
              : String(value),
      ];
    }),
  );
  if (!row && section.value === 'calendar-events')
    form.value.resource_type = 'FACTORY';
  originalForm.value = { ...form.value };
}
function close() {
  edit.value = null;
  creating.value = false;
  store.dirty = false;
}
async function save() {
  try {
    const data: Record<string, unknown> = {};
    for (const s of specs[section.value] || []) {
      const raw = form.value[s.key] || '';
      if (!raw && !edit.value) continue;
      if (edit.value && raw === originalForm.value[s.key]) continue;
      data[s.key] = !raw
        ? s.type === 'json'
          ? {}
          : s.type === 'list'
            ? []
            : ['number', 'date'].includes(s.type || '')
              ? null
              : ''
        : s.type === 'number'
          ? Number(raw)
          : s.type === 'json'
            ? JSON.parse(raw)
            : s.type === 'list'
              ? raw.split('\n').filter(Boolean)
              : s.type === 'date'
                ? new Date(raw).toISOString()
                : raw;
    }
    if (section.value === 'molds' && 'target_shots_per_day' in data) {
      const target = data.target_shots_per_day;
      delete data.target_shots_per_day;
      data.defaults = {
        ...((data.defaults || edit.value?.defaults || {}) as object),
        target_shots_per_day: target,
      };
    }
    const result = await store.mutate(
      '/' + section.value + (edit.value ? '/' + edit.value.id : ''),
      { data, ...(edit.value ? { record_revision: edit.value.revision } : {}) },
      edit.value ? 'patch' : 'post',
    );
    if (result) {
      close();
      await load();
    }
  } catch (e) {
    store.showError(e);
  }
}
async function saveSettings() {
  savingSettings.value = true;
  try {
    const data: Record<string, unknown> = {};
    for (const [key, raw] of Object.entries(settingsDraft.value)) {
      data[key] =
        raw === originalSettingsText.value[key]
          ? originalSettings.value[key]
          : parseParameter(raw, originalSettings.value[key]);
    }
    const result = await store.mutate('/settings', { data }, 'patch');
    if (result) {
      store.settings = result.parameters;
      store.dirty = false;
      await load();
    }
  } catch (e) {
    store.showError(e);
  } finally {
    savingSettings.value = false;
  }
}
async function saveStatus() {
  if (!statusMachine.value) return;
  const result = await store.mutate(
    '/machines/' + statusMachine.value.id + '/status',
    {
      data: {
        ...statusForm.value,
        recovery_at: statusForm.value.recovery_at
          ? new Date(statusForm.value.recovery_at).toISOString()
          : null,
      },
    },
  );
  if (result) {
    statusMachine.value = null;
    await load();
  }
}
async function relocate() {
  if (!relocation.value) return;
  const result = await store.mutate(
    '/mold-assets/' + relocation.value.id + '/relocate',
    {
      destination_factory_id: destination.value,
      available_at: availableAt.value
        ? new Date(availableAt.value).toISOString()
        : null,
      record_revision: relocation.value.revision,
    },
  );
  if (result) {
    relocation.value = null;
    await load();
  }
}

const templateLabels0: Record<string, string> = {
  molds: '公共模具',
  machines: '本厂设备',
  'mold-assets': '实物模具',
  'calendar-events': '日历事件',
};
</script>
<template>
  <section class="inj-master">
    <nav class="inj-master-nav" aria-label="基础资料分类">
      <strong>资源与排产配置</strong
      ><button
        v-for="item in masterSections"
        :key="item.value"
        :aria-current="section === item.value ? 'page' : undefined"
        :disabled="store.dirty || store.busy"
        @click="
          section = item.value;
          term = '';
        "
      >
        <component :is="item.icon" />{{ item.label }}
      </button>
    </nav>
    <Teleport v-if="headerReady && canWrite" to="#inj-primary-slot"
      ><InjButton
        v-if="section === 'settings'"
        primary
        :disabled="store.busy || !sectionReady"
        :pending="savingSettings"
        @click="saveSettings"
        ><template #icon><Save /></template>保存参数并重算</InjButton
      ><InjButton
        v-else
        primary
        :disabled="store.dirty || store.busy || !sectionReady"
        @click="open()"
        ><template #icon><Plus /></template>新增资料</InjButton
      ></Teleport
    >
    <div class="inj-toolbar">
      <span class="inj-spacer" /><span class="inj-badge">{{
        section === 'molds' ? '四厂共享' : factories[store.factory!]
      }}</span
      ><input
        v-if="section !== 'settings'"
        v-model="term"
        placeholder="查找资料"
        aria-label="基础资料查找"
      /><button
        v-if="canWrite && section !== 'settings' && !headerReady"
        class="inj-primary"
        @click="open()"
      >
        <Plus /> 新增
      </button>
    </div>
    <InjLoadingState v-if="loading && !sectionReady" label="正在读取基础资料" />
    <div
      v-else-if="!sectionReady && loadFailed"
      class="inj-empty"
      role="status"
    >
      资料读取失败，请重试。
      <button @click="load">重新读取</button>
    </div>
    <div v-else-if="section === 'settings'" class="inj-settings">
      <p class="inj-help">
        班制、允许上放和休息时间为可调整配置，保存后重新计算本厂未来排程。
      </p>
      <div class="inj-parameter-groups">
        <template v-for="(_, key) in settingsDraft" :key="key">
          <MasterParameterEditor
            v-if="typeof originalSettings[key] === 'object'"
            v-model="settingsDraft[key]!"
            :kind="String(key)"
            :label="parameterLabels[key] || String(key)"
            :disabled="!canWrite || store.busy"
            @update:model-value="store.dirty = true"
          />
          <section v-else class="inj-parameter">
            <label
              ><span>{{ parameterLabels[key] || key }}</span
              ><select
                v-if="typeof originalSettings[key] === 'boolean'"
                v-model="settingsDraft[key]"
                :disabled="!canWrite || store.busy"
                @change="store.dirty = true"
              >
                <option value="true">是</option>
                <option value="false">否</option></select
              ><input
                v-else
                v-model="settingsDraft[key]"
                :type="
                  ['day_start', 'night_start'].includes(String(key))
                    ? 'time'
                    : typeof originalSettings[key] === 'number'
                      ? 'number'
                      : 'text'
                "
                step="any"
                :disabled="
                  !canWrite || store.busy || key === 'business_timezone'
                "
                @input="store.dirty = true"
            /></label>
          </section>
        </template>
      </div>
      <div v-if="canWrite" class="inj-actions">
        <button
          @click="
            store.dirty = false;
            load();
          "
        >
          放弃修改</button
        ><button
          v-if="!headerReady"
          class="inj-primary"
          :disabled="store.busy"
          @click="saveSettings"
        >
          保存参数并重算
        </button>
      </div>
    </div>
    <div v-else class="inj-grid-scroll">
      <table class="inj-master-grid">
        <thead>
          <tr>
            <th v-for="key in headings" :key="key">{{ labels[key] }}</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in filtered" :key="row.id">
            <td
              v-for="key in headings"
              :key="key"
              :title="String(row[key] ?? '')"
            >
              {{
                key === 'master_id'
                  ? molds.find((m) => m.id === row[key])?.mold_code || row[key]
                  : key.endsWith('_at')
                    ? dateText(row[key])
                    : enumOptions[key]?.[row[key]] ||
                      statusText[row[key]] ||
                      factories[row[key] as keyof typeof factories] ||
                      displayValue(row[key])
              }}
            </td>
            <td>
              <button @click="open(row)">
                {{ canWrite ? '编辑' : '查看' }}</button
              ><button
                v-if="section === 'machines' && canWrite"
                @click="
                  statusMachine = row;
                  statusForm = {
                    operating_status: 'MAINTENANCE',
                    recovery_at: '',
                    notes: row.notes || '',
                  };
                "
              >
                设备状态</button
              ><button
                v-if="section === 'mold-assets' && canWrite"
                @click="relocation = row"
              >
                调厂
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!filtered.length" class="inj-empty">
        暂无资料。{{
          canWrite ? '点击新增，或通过计划表导入建立初始资料。' : ''
        }}
      </div>
    </div>
    <div v-if="creating || edit" class="inj-modal-backdrop">
      <section
        class="inj-modal inj-wide-modal"
        role="dialog"
        aria-modal="true"
        aria-label="基础资料编辑"
        v-inj-dialog="{
          close: () => {
            close();
          },
          busy: store.busy,
        }"
      >
        <h2>{{ creating ? '新增' : '编辑' }}{{ templateLabels0[section] }}</h2>
        <p v-if="edit" class="inj-muted">当前版本 {{ edit.revision }}</p>
        <p v-if="store.error" class="inj-error-text">{{ store.error }}</p>
        <form @submit.prevent="save">
          <div class="inj-form-grid">
            <label
              v-for="s in specs[section]?.filter((s) => s.type !== 'json')"
              :key="s.key"
              ><span>{{ s.label }}{{ s.required ? ' *' : '' }}</span
              ><select
                v-if="enumOptions[s.key]"
                v-model="form[s.key]"
                :disabled="!canWrite || store.busy"
                @change="store.dirty = true"
              >
                <option value="">请选择</option>
                <option
                  v-for="(label, value) in enumOptions[s.key]"
                  :key="value"
                  :value="value"
                >
                  {{ label }}
                </option></select
              ><select
                v-else-if="s.type === 'mold'"
                v-model="form[s.key]"
                :disabled="!canWrite || store.busy"
                @change="store.dirty = true"
              >
                <option value="">请选择公共模具</option>
                <option v-for="m in molds" :key="m.id" :value="m.id">
                  {{ m.mold_code }} · {{ m.part_name }}
                </option></select
              ><select
                v-else-if="s.type === 'resource'"
                v-model="form[s.key]"
                :disabled="!canWrite || store.busy"
                @change="
                  store.dirty = true;
                  form.resource_id = '';
                "
              >
                <option value="FACTORY">全厂</option>
                <option value="MACHINE">机台</option>
                <option value="MOLD">实物模具</option></select
              ><select
                v-else-if="s.type === 'resourceId'"
                v-model="form[s.key]"
                :disabled="
                  !canWrite || store.busy || form.resource_type === 'FACTORY'
                "
                :required="form.resource_type !== 'FACTORY'"
                @change="store.dirty = true"
              >
                <option value="">
                  {{
                    form.resource_type === 'FACTORY'
                      ? '全厂所有资源'
                      : '请选择资源'
                  }}
                </option>
                <option
                  v-for="resource in form.resource_type === 'MACHINE'
                    ? store.machines
                    : assets"
                  :key="resource.id"
                  :value="resource.id"
                >
                  {{ resource.code || resource.asset_code }}
                </option></select
              ><textarea
                v-else-if="['json', 'list'].includes(s.type || '')"
                v-model="form[s.key]"
                :disabled="!canWrite || store.busy"
                rows="4"
                :placeholder="s.hint"
                @input="store.dirty = true" /><input
                v-else
                v-model="form[s.key]"
                :required="s.required"
                :disabled="!canWrite || store.busy"
                :type="s.type === 'number' ? 'number' : 'text'"
                step="any"
                :placeholder="s.type === 'date' ? 'YYYY-MM-DD HH:mm' : s.hint"
                @input="store.dirty = true"
            /></label>
          </div>
          <div class="inj-parameter-groups">
            <MasterParameterEditor
              v-for="field in specs[section]?.filter((f) => f.type === 'json')"
              :key="field.key"
              v-model="form[field.key]!"
              :kind="field.key"
              :label="field.label"
              :disabled="!canWrite || store.busy"
              @update:model-value="store.dirty = true"
            />
          </div>
          <div class="inj-actions">
            <button type="button" @click="close">取消</button
            ><button v-if="canWrite" class="inj-primary" :disabled="store.busy">
              保存
            </button>
          </div>
        </form>
      </section>
    </div>
    <div v-if="statusMachine" class="inj-modal-backdrop">
      <section
        class="inj-modal"
        role="dialog"
        aria-modal="true"
        aria-label="设备状态"
        v-inj-dialog="{
          close: () => {
            statusMachine = null;
          },
          busy: store.busy,
        }"
      >
        <h2>{{ statusMachine.code }} · 设备状态</h2>
        <p>停工会暂停正在执行的批次并重新计算后续计划。</p>
        <div class="inj-form-grid">
          <label
            >状态<select v-model="statusForm.operating_status">
              <option value="MAINTENANCE">检修</option>
              <option value="FAULT">故障</option>
              <option value="DISABLED">停用</option>
              <option value="IDLE">恢复可用</option>
            </select></label
          ><label
            >预计恢复<input
              v-model="statusForm.recovery_at"
              type="datetime-local" /></label
          ><label>原因<textarea v-model="statusForm.notes" /></label>
        </div>
        <p class="inj-error-text">{{ store.error }}</p>
        <div class="inj-actions">
          <button @click="statusMachine = null">取消</button
          ><button
            class="inj-primary"
            :disabled="store.busy"
            @click="saveStatus"
          >
            保存状态
          </button>
        </div>
      </section>
    </div>
    <div v-if="relocation" class="inj-modal-backdrop">
      <section
        class="inj-modal"
        role="dialog"
        aria-modal="true"
        aria-label="实物模具调厂"
        v-inj-dialog="{
          close: () => {
            relocation = null;
          },
          busy: store.busy,
        }"
      >
        <h2>{{ relocation.asset_code }} · 调厂</h2>
        <p>将重新计算源厂和目标厂的可用性。需要两厂的基础资料权限。</p>
        <label
          >目标厂<select v-model="destination">
            <option value="">选择目标厂</option>
            <option
              v-for="(label, key) in factories"
              :key="key"
              :value="key"
              :disabled="key === store.factory"
            >
              {{ label }}
            </option>
          </select></label
        ><label
          >预计可用<input v-model="availableAt" type="datetime-local"
        /></label>
        <p class="inj-error-text">{{ store.error }}</p>
        <div class="inj-actions">
          <button @click="relocation = null">取消</button
          ><button
            class="inj-primary"
            :disabled="!destination || store.busy"
            @click="relocate"
          >
            确认调厂
          </button>
        </div>
      </section>
    </div>
  </section>
</template>
