<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from 'vue';
import { X, Maximize2, Minimize2 } from '@lucide/vue';
import InjSegmentedControl from './components/ui/InjSegmentedControl.vue';
import InjLoadingState from './components/ui/InjLoadingState.vue';
import InjButton from './components/ui/InjButton.vue';
import { useInjectionViewState } from './composables/useInjectionViewState';
import { useInjectionStore } from '@/stores/injectionScheduling';
import { injectionApi as api } from '@/api/injectionScheduling';
import {
  dateText,
  displayValue,
  numberText,
  parseValue,
  statusText,
  type DataRow,
} from './types';
const props = defineProps<{
  creating?: boolean;
  docked?: boolean;
  canPlan: boolean;
  canReport: boolean;
}>();
const emit = defineEmits<{
  close: [];
  action: [DataRow, string];
  report: [DataRow];
}>();
const store = useInjectionStore(),
  tab = ref(props.creating ? '参数' : '概览'),
  form = ref<Record<string, string>>({}),
  changed = ref<string[]>([]),
  panel = ref<HTMLElement>(),
  expanded = ref(false);
const view = useInjectionViewState(),
  saving = ref(false);
const ready = computed(
  () => props.creating || store.detail?.demand.id === store.selectedId,
);
const tabOptions = computed(() =>
  (props.creating ? ['参数'] : ['概览', '参数', '排程', '报工', '记录']).map(
    (value) => ({ value, label: value }),
  ),
);
const chooseTab = (value: string) => {
  if (store.busy || changed.value.length) {
    store.error = '请先保存或取消本次修改';
    return;
  }
  tab.value = value;
};
watch(expanded, (value) => (view.inspectorExpanded = value));
const demand = computed(() =>
    props.creating || !ready.value ? {} : store.detail?.demand || {},
  ),
  run = computed(() =>
    props.creating || !ready.value ? null : store.detail?.run,
  );
const liveRun = computed(() => store.runs.find((r) => r.id === run.value?.id));
const forecastUnknown = computed(
  () =>
    liveRun.value?.forecast_unknown || run.value?.explanation?.forecast_unknown,
);
const batchOrders = ref<DataRow[]>([]),
  batchError = ref('');
let batchGeneration = 0;
watch(
  () => [run.value?.id, store.factory],
  async () => {
    const generation = ++batchGeneration,
      factory = store.factory;
    batchOrders.value = [];
    batchError.value = '';
    const ids: string[] =
      liveRun.value?.demand_ids || run.value?.snapshot?.demand_ids || [];
    if (ids.length < 2) return;
    try {
      const details = await Promise.all(
        ids.map((id) => api.get('/demands/' + id, { factory_id: factory })),
      );
      if (generation === batchGeneration)
        batchOrders.value = details.map((detail) => detail.demand);
    } catch {
      if (generation === batchGeneration)
        batchError.value = '批次订单读取未完成，请重新打开详情。';
    }
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  batchGeneration++;
});
const editable = computed(() => store.fields.filter((f) => f.editable));
const sourceNames: Record<string, string> = {
  ORDER_OVERRIDE: '本单覆盖',
  MASTER: '公共模具',
  LEGACY: '原表',
  DEFAULT: '默认建议',
  IMPORT: '导入值',
  LEGACY_CACHE: '原表',
};
function sourceLabel(source: unknown) {
  const value: Record<string, any> =
    typeof source === 'object' && source
      ? (source as DataRow)
      : { kind: String(source) };
  return (
    (sourceNames[value.kind] || '已记录来源') +
    (value.source_row ? ' · 原行 ' + value.source_row : '')
  );
}
let previousFocus: HTMLElement | null = null;
function reset() {
  form.value = Object.fromEntries(
    editable.value.map((f) => [
      f.key,
      demand.value[f.key] == null
        ? ''
        : typeof demand.value[f.key] === 'object'
          ? JSON.stringify(demand.value[f.key])
          : String(demand.value[f.key]),
    ]),
  );
  changed.value = [];
}
watch(
  () => store.selectedId,
  () => {
    tab.value = '概览';
    reset();
  },
);
watch(
  () => store.detail,
  () => {
    if (!changed.value.length) reset();
  },
  { immediate: true },
);
function edit(key: string) {
  if (!changed.value.includes(key)) changed.value.push(key);
  store.dirty = true;
}
async function save() {
  saving.value = true;
  try {
    const keys = props.creating
      ? editable.value.filter((f) => form.value[f.key] !== '').map((f) => f.key)
      : changed.value;
    const data = Object.fromEntries(
      keys.map((key) => [
        key,
        parseValue(form.value[key] || '', store.fieldMap[key]!),
      ]),
    );
    const result = await store.mutate(
      props.creating ? '/demands' : '/demands/' + demand.value.id,
      {
        data,
        ...(!props.creating ? { record_revision: demand.value.revision } : {}),
      },
      props.creating ? 'post' : 'patch',
    );
    if (result) {
      changed.value = [];
      if (props.creating) {
        void store.select(result.demand.id, true);
        emit('close');
      } else reset();
    }
  } catch (e) {
    store.showError(e);
  } finally {
    saving.value = false;
  }
}
function close() {
  if (changed.value.length || store.busy) {
    store.error = '参数尚未保存，请先保存或取消本次修改';
    return;
  }
  emit('close');
}
function keydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && !event.isComposing) {
    event.stopPropagation();
    close();
  }
  if (event.key === 'Tab' && !props.docked) {
    const nodes = panel.value?.querySelectorAll<HTMLElement>(
      'button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]',
    );
    if (!nodes?.length) return;
    const first = nodes[0],
      last = nodes[nodes.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last?.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first?.focus();
    }
  }
}
onMounted(() => {
  previousFocus = document.activeElement as HTMLElement;
  reset();
  nextTick(() => panel.value?.focus());
});
onBeforeUnmount(() => previousFocus?.focus());

const templateLabels0: Record<string, string> = {
  mold_change_minutes: '换模分钟',
  color_change_minutes: '清洗分钟',
  changeover_minutes: '总转换分钟',
  machine_a: '机台 A',
  required_machine_a: '模具 A',
  reason: '选择依据',
  estimated: '估算',
  allocation_mode: '分配口径',
};
</script>
<template>
  <div
    class="inj-drawer-backdrop"
    :class="{ 'inj-inspector-dock': docked }"
    @click.self="close"
  >
    <aside
      ref="panel"
      class="inj-drawer"
      :class="{ expanded: expanded }"
      :role="docked ? 'region' : 'dialog'"
      :aria-modal="docked ? undefined : true"
      :aria-label="creating ? '新增需求' : '需求详情'"
      tabindex="-1"
      @keydown="keydown"
    >
      <header>
        <div>
          <small>{{
            creating ? '本厂新需求' : demand.order_no || '需求详情'
          }}</small>
          <h2>
            {{ creating ? '新增需求' : demand.mold_code || '未识别模号' }}
          </h2>
        </div>
        <span class="inj-spacer" /><button
          v-if="!docked"
          :aria-label="expanded ? '收窄详情' : '展开详情'"
          @click="expanded = !expanded"
        >
          <Minimize2 v-if="expanded" /><Maximize2 v-else /></button
        ><button aria-label="关闭详情" @click="close"><X /></button>
      </header>
      <InjSegmentedControl
        class="inj-detail-tabs"
        :model-value="tab"
        :options="tabOptions"
        label="详情页签"
        @update:model-value="chooseTab"
      />
      <InjLoadingState v-if="!ready" label="正在读取所选需求…" />
      <div v-if="ready" class="inj-drawer-content">
        <p v-if="store.error" role="alert" class="inj-error-text">
          {{ store.error }}
        </p>
        <template v-if="tab === '概览'"
          ><div class="inj-inline">
            <span class="inj-badge">{{
              run ? statusText[run.status] : '未排 / 未开工'
            }}</span
            ><strong>{{ demand.machine_code || '待安排机台' }}</strong>
          </div>
          <h3>{{ demand.part_name || demand.item_no || '名称待补' }}</h3>
          <p>{{ demand.color_name }} · {{ demand.material_raw }}</p>
          <div class="inj-metrics">
            <div>
              <small>计划啤数</small
              ><strong>{{ numberText(demand.planned_shots) }}</strong>
            </div>
            <div>
              <small>实际已啤</small
              ><strong>{{ numberText(demand.completed_shots) }}</strong>
            </div>
            <div>
              <small>欠数</small
              ><strong>{{ numberText(demand.remaining_shots) }}</strong>
            </div>
          </div>
          <dl class="inj-key-values">
            <dt>单号 / 货号</dt>
            <dd>{{ demand.order_no }} / {{ demand.item_no }}</dd>
            <dt>计划日目标</dt>
            <dd>{{ numberText(demand.target_shots_per_day) }}</dd>
            <dt>预计完成</dt>
            <dd>
              {{
                forecastUnknown
                  ? '等待恢复，预计结束未知'
                  : dateText(demand.planned_end_at)
              }}
            </dd>
            <dt>交货完成期</dt>
            <dd>{{ dateText(demand.delivery_due_at) }}</dd>
            <dt>交期余量</dt>
            <dd>{{ numberText(demand.delivery_slack_hours) }} 小时</dd>
            <dt>剩余料重</dt>
            <dd>{{ numberText(demand.remaining_material_kg) }} kg</dd>
            <dt>未排原因</dt>
            <dd>{{ demand.unplaced_reason || '—' }}</dd>
          </dl>
          <section
            v-if="batchOrders.length > 1"
            class="inj-batch-orders"
            aria-label="批次订单"
          >
            <h3>同批次订单 · {{ batchOrders.length }} 单</h3>
            <button
              v-for="order in batchOrders"
              :key="order.id"
              :disabled="store.dirty || store.busy"
              :aria-current="order.id === demand.id ? 'true' : undefined"
              @click="store.select(order.id, true)"
            >
              <strong class="inj-mono">{{ order.order_no || '无单号' }}</strong
              ><span>{{
                order.item_no || order.part_name || order.mold_code
              }}</span
              ><small>本单欠 {{ numberText(order.remaining_shots) }} 啤</small>
            </button>
          </section>
          <p v-if="batchError" role="alert" class="inj-error-text">
            {{ batchError }}
          </p>
          <p class="inj-help">
            预计时间由排程计算；实际进度只来自开工和报数。
          </p></template
        >
        <template v-if="tab === '参数'"
          ><p class="inj-help">
            本单修改优先于公共模具资料。留空不填默认产能；缺少价格或重量可继续排产。
          </p>
          <div class="inj-form-grid">
            <label v-for="field in editable" :key="field.key"
              ><span
                >{{ field.label }}
                <small v-if="demand.field_sources?.[field.key]">{{
                  sourceLabel(demand.field_sources[field.key])
                }}</small></span
              ><textarea
                v-if="
                  field.value_type === 'json' || field.key.endsWith('_note')
                "
                v-model="form[field.key]"
                :disabled="!canPlan || store.busy"
                rows="2"
                @input="edit(field.key)" /><input
                v-else
                v-model="form[field.key]"
                :disabled="!canPlan || store.busy"
                :inputmode="
                  ['number', 'integer'].includes(field.value_type)
                    ? 'decimal'
                    : 'text'
                "
                :placeholder="
                  field.value_type === 'datetime' ? 'YYYY-MM-DD HH:mm' : ''
                "
                @input="edit(field.key)"
            /></label></div
        ></template>
        <template v-if="tab === '排程'"
          ><p v-if="!run">
            未排产：{{ demand.unplaced_reason || '可自动排产或拖入机台' }}
          </p>
          <template v-else
            ><dl class="inj-key-values">
              <dt>实物模具</dt>
              <dd>{{ run.mold_asset_id }}</dd>
              <dt>转换开始</dt>
              <dd>{{ dateText(run.setup_start_at) }}</dd>
              <dt>生产开始</dt>
              <dd>{{ dateText(run.planned_start_at) }}</dd>
              <dt>预计结束</dt>
              <dd>
                {{
                  forecastUnknown
                    ? '等待恢复，预计结束未知'
                    : dateText(run.planned_end_at)
                }}
              </dd>
              <dt>批次位置</dt>
              <dd>
                {{ run.sequence + 1 }} ·
                {{ run.pinned ? '固定机台和顺序' : '自动调整' }}
              </dd>
            </dl>
            <h3>排程依据</h3>
            <dl class="inj-key-values">
              <template v-for="(value, key) in run.explanation" :key="key"
                ><dt>{{ templateLabels0[key] || key }}</dt>
                <dd>{{ displayValue(value) }}</dd></template
              >
            </dl>
            <button
              v-if="canPlan && run.status === 'PLANNED'"
              @click="
                store.mutate('/schedule/move', {
                  run_id: run.id,
                  machine_id: run.machine_id,
                  pinned: !run.pinned,
                })
              "
            >
              {{ run.pinned ? '取消固定' : '固定机台与顺序' }}
            </button></template
          ></template
        >
        <template v-if="tab === '报工'"
          ><div v-if="run && canReport" class="inj-inline">
            <button
              v-if="run.status === 'PLANNED'"
              class="inj-primary"
              @click="emit('action', run, 'start')"
            >
              实际开工</button
            ><template v-else
              ><button class="inj-primary" @click="emit('report', run)">
                填写本班报数</button
              ><button
                @click="
                  emit(
                    'action',
                    run,
                    run.status === 'PAUSED' ? 'resume' : 'pause',
                  )
                "
              >
                {{ run.status === 'PAUSED' ? '恢复' : '暂停' }}</button
              ><button @click="emit('action', run, 'transfer')">转机</button
              ><button @click="emit('action', run, 'finish')">
                结束批次
              </button></template
            >
          </div>
          <h3>系统班次报数</h3>
          <table class="inj-small-table">
            <thead>
              <tr>
                <th>生产日 / 班</th>
                <th>物理啤数</th>
                <th>版本</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in store.detail?.reports" :key="r.id">
                <td>
                  {{ r.production_date }} /
                  {{ r.shift_code === 'DAY' ? '白' : '夜' }}
                </td>
                <td>{{ numberText(r.physical_shots) }}</td>
                <td>{{ r.revision }}</td>
              </tr>
            </tbody>
          </table>
          <h3>原表历史班次</h3>
          <p class="inj-muted">
            原始订单历史独立保留，不直接认定为机台物理啤数。
          </p>
          <table class="inj-small-table">
            <tbody>
              <tr v-for="h in store.detail?.history" :key="h.id">
                <td>
                  {{ h.production_date }} /
                  {{ h.shift_code === 'DAY' ? '白' : '夜' }}
                </td>
                <td>{{ numberText(h.quantity) }}</td>
                <td>
                  {{ h.counts_toward_demand ? '已纳入累计' : '仅留证据' }}
                </td>
              </tr>
            </tbody>
          </table></template
        >
        <template v-if="tab === '记录'"
          ><h3>来源与版本</h3>
          <p>
            {{ demand.source_document }} · 原行 {{ demand.source_row }} ·
            当前版本 {{ demand.revision }}
          </p>
          <p>
            更新人 {{ demand.updated_by }} · {{ dateText(demand.updated_at) }}
          </p>
          <details v-for="row in store.detail?.source_rows" :key="row.id">
            <summary>来源行 {{ row.source_row }} · {{ row.row_role }}</summary>
            <pre>{{ JSON.stringify(row.evidence, null, 2) }}</pre>
            <p>{{ row.issues }}</p>
          </details>
          <h3>执行记录</h3>
          <ol>
            <li v-for="(item, index) in run?.execution_events" :key="index">
              {{ dateText(item.at) }} · {{ item.action }} · {{ item.reason }}
            </li>
          </ol></template
        >
      </div>
      <footer v-if="ready && tab === '参数' && canPlan" class="inj-actions">
        <span>{{ changed.length ? '有未保存修改' : '' }}</span
        ><button
          @click="
            reset();
            store.dirty = false;
          "
        >
          取消本次修改</button
        ><InjButton
          primary
          :pending="saving"
          :disabled="store.busy"
          @click="save"
        >
          {{ creating ? '新增并计算' : '保存参数并重算' }}
        </InjButton>
      </footer>
    </aside>
  </div>
</template>
