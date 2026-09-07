<script setup lang="ts">
import { vInjDialog } from '@/features/injection-scheduling/composables/injDialog';
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAppStore } from '@/stores/app';
import { useAuthStore } from '@/stores/auth';
import { useInjectionStore } from '@/stores/injectionScheduling';
import { injectionApi as api } from '@/api/injectionScheduling';
import {
  dateText,
  factories,
  numberText,
  type DataRow,
  type FactoryId,
  type FilterNode,
} from '@/features/injection-scheduling/types';
import FilterGroup from '@/features/injection-scheduling/FilterGroup.vue';
import PlanTable from '@/features/injection-scheduling/PlanTable.vue';
import ScheduleBoard from '@/features/injection-scheduling/ScheduleBoard.vue';
import ShiftReports from '@/features/injection-scheduling/ShiftReports.vue';
import MasterData from '@/features/injection-scheduling/MasterData.vue';
import DemandDrawer from '@/features/injection-scheduling/DemandDrawer.vue';
import {
  ArrowLeft,
  ArrowRight,
  ChevronDown,
  ArrowUp,
  ArrowDown,
  Search,
  Plus,
  Filter,
  Upload,
  Download,
  Ellipsis,
  RefreshCw,
  CircleHelp,
  WandSparkles,
  Undo2,
  Focus,
  X,
  Factory,
  ChartGantt,
  LayoutGrid,
  Table2,
  ClipboardList,
  Database,
} from '@lucide/vue';
import InjSegmentedControl from '@/features/injection-scheduling/components/ui/InjSegmentedControl.vue';
import InjButton from '@/features/injection-scheduling/components/ui/InjButton.vue';
import InjLoadingState from '@/features/injection-scheduling/components/ui/InjLoadingState.vue';
import { provideInjectionViewState } from '@/features/injection-scheduling/composables/useInjectionViewState';
import { useInjMotionPreference } from '@/features/injection-scheduling/composables/useInjMotionPreference';
import '@/features/injection-scheduling/injection.css';

const route = useRoute(),
  router = useRouter(),
  app = useAppStore(),
  auth = useAuthStore(),
  store = useInjectionStore();
const view = provideInjectionViewState();
const { motionAllowed } = useInjMotionPreference();
const tab = ref(view.planningView),
  runningOnly = ref(false),
  newDemand = ref(false),
  filterOpen = ref(false),
  filterDraft = ref<FilterNode>({
    op: 'and',
    children: [{ field: 'remaining_shots', op: 'gt', value: 0 }],
  }),
  fileInput = ref<HTMLInputElement>();
const importPreview = ref<any>(null),
  importMatches = ref<Record<string, string>>({}),
  skipRows = ref<number[]>([]),
  exportOpen = ref(false),
  exportStart = ref(new Date().toLocaleDateString('en-CA')),
  exportDays = ref(14),
  exportFormulas = ref(false);
const autoOptions = ref(false),
  autoMode = ref('UNSCHEDULED'),
  autoMachines = ref<string[]>([]),
  action = ref<{ run: DataRow; verb: string } | null>(null),
  reason = ref(''),
  targetMachine = ref(''),
  selectedReport = ref(''),
  findIndex = ref(0),
  findCount = ref(0),
  help = ref(false);
const section = computed(() =>
  ['timeline', 'machines', 'table'].includes(tab.value)
    ? 'planning'
    : tab.value,
);
const sectionOptions = [
  { value: 'planning', label: '排产工作台', icon: ChartGantt },
  { value: 'reports', label: '白夜班报工', icon: ClipboardList },
  { value: 'master', label: '基础资料', icon: Database },
];
const planningOptions = [
  { value: 'timeline', label: '甘特', icon: ChartGantt },
  { value: 'machines', label: '看板', icon: LayoutGrid },
  { value: 'table', label: '计划表', icon: Table2 },
];
const pendingActionKey = ref(''),
  moreOpen = ref(false),
  riskOpen = ref(false),
  viewportWidth = ref(window.innerWidth);
const docked = computed(() => viewportWidth.value >= 1280 && !newDemand.value);
const resize = () => {
  viewportWidth.value = window.innerWidth;
};
async function pending(key: string, action: () => Promise<unknown>) {
  if (pendingActionKey.value) return;
  pendingActionKey.value = key;
  try {
    return await action();
  } finally {
    pendingActionKey.value = '';
  }
}
watch(tab, (key) => {
  if (['timeline', 'machines', 'table'].includes(key)) view.planningView = key;
});
watch([() => store.factory, () => auth.currentUser?.id], () => {
  view.contextGeneration++;
  store.selectedId = null;
  store.detail = null;
  store.drawer = false;
  selectedReport.value = '';
  newDemand.value = false;
  view.scroll = {};
  view.table = null;
  view.workshop = '';
  view.machineSearch = '';
  findIndex.value = 0;
  findCount.value = 0;
});
const allowed = (action: string) =>
  !!store.factory &&
  ['production', 'molding', 'management'].some((dept) =>
    auth.can('injection_scheduling:' + action, store.factory!, dept),
  );
const canPlan = computed(() => allowed('plan')),
  canReport = computed(() => allowed('report')),
  canMaster = computed(() => allowed('master_write'));
const factoryContext = computed(() => {
  const query = route.query.factory;
  const id = typeof query === 'string' ? query : app.activeFactoryId;
  return id in factories ? (id as FactoryId) : null;
});
const factoryLoading = ref(false);
let factoryLoadGeneration = 0;
watch(
  factoryContext,
  async (id) => {
    const generation = ++factoryLoadGeneration;
    factoryLoading.value = true;
    try {
      await store.setFactory(id);
    } finally {
      if (generation === factoryLoadGeneration) factoryLoading.value = false;
    }
  },
  { immediate: true },
);
async function changeFactory(event: Event) {
  const id = (event.target as HTMLSelectElement).value as FactoryId;
  if (!id) return;
  app.setActiveFactory(id);
  await router.replace({ query: { ...route.query, factory: id } });
}
function switchTab(key: string) {
  if (store.dirty || store.busy) {
    store.error = '当前有未保存输入，请先保存或取消本次修改';
    return;
  }
  tab.value = key === 'planning' ? view.planningView : key;
  store.error = '';
}
async function search() {
  store.cursor = 0;
  findIndex.value = 0;
  await store.loadTable();
  findCount.value = store.total;
}
async function find(step: number) {
  if (!store.search.text || store.dirty || store.busy) return;
  switchTab('table');
  try {
    const r = await api.post('/demands/locate', {
      ...store.query,
      cursor: Math.max(0, findIndex.value + step),
    });
    findCount.value = r.total_count;
    findIndex.value = r.position;
    if (r.demand_id) {
      store.cursor = r.page_cursor;
      await store.loadTable();
      await store.select(r.demand_id, true);
    }
  } catch (e) {
    store.showError(e);
  }
}
function filterLabel(node: FilterNode): string {
  if (node.children)
    return (
      '(' +
      node.children.map(filterLabel).join(node.op === 'or' ? ' 或 ' : ' 且 ') +
      ')'
    );
  return (
    (store.fieldMap[node.field || '']?.label || node.field) +
    ' ' +
    (
      {
        eq: '=',
        gt: '>',
        gte: '≥',
        lt: '<',
        lte: '≤',
        ne: '≠',
        is_empty: '为空',
        not_empty: '非空',
        in: '属于',
        next_days: '未来天数',
        contains: '包含',
        prefix: '开头',
        not_in: '排除',
        between: '区间',
        today: '今天',
        overdue: '逾期',
        on_day: '某天',
      } as Record<string, string>
    )[node.op || ''] +
    ' ' +
    (Array.isArray(node.value) ? node.value.join('、') : (node.value ?? ''))
  );
}
async function applyFilter() {
  store.filter = filterDraft.value.children?.length
    ? JSON.parse(JSON.stringify(filterDraft.value))
    : null;
  store.cursor = 0;
  await store.loadTable();
  filterOpen.value = false;
}
async function schedule(save = true) {
  const result = await store.mutate('/schedule/auto', {
    scope: {
      mode: autoMode.value,
      ...(autoMode.value === 'SELECTED'
        ? {
            machine_ids: autoMachines.value,
            demand_ids: store.selectedId ? [store.selectedId] : [],
          }
        : {}),
    },
    save,
  });
  if (result && save) autoOptions.value = false;
  return result;
}
async function upload(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file || !store.factory) return;
  store.busy = true;
  store.error = '';
  try {
    const result = await api.upload(store.factory, file, store.revision);
    store.revision = result.revision;
    importPreview.value = result;
    skipRows.value = [];
    importMatches.value = {};
  } catch (e) {
    store.showError(e);
  } finally {
    store.busy = false;
    (event.target as HTMLInputElement).value = '';
    await store.refresh();
  }
}
async function applyImport() {
  const result = await store.mutate(
    '/imports/' + importPreview.value.batch_id + '/apply',
    {
      matches: importMatches.value,
      skip_rows: skipRows.value,
    },
  );
  if (result?.summary?.conflicts?.length) {
    importPreview.value = { ...importPreview.value, summary: result.summary };
    store.error = result.summary.conflicts
      .map(
        (c: any) =>
          `原行 ${c.source_row ?? c.row ?? ''}：${c.message || c.reason || c.code || JSON.stringify(c)}`,
      )
      .join('；');
  } else if (result) {
    importPreview.value = null;
    tab.value = 'table';
  }
}
async function download() {
  try {
    store.busy = true;
    await api.export({
      ...store.query,
      cursor: null,
      window_start: exportStart.value,
      window_days: exportDays.value,
      editable_formulas: exportFormulas.value,
    });
    exportOpen.value = false;
  } catch (e) {
    store.showError(e);
  } finally {
    store.busy = false;
  }
}
function beginAction(run: DataRow, verb: string) {
  reason.value = '';
  targetMachine.value = '';
  action.value = { run, verb };
  store.error = '';
}
async function applyAction() {
  if (!action.value) return;
  const result = await store.mutate(
    '/runs/' + action.value.run.id + '/' + action.value.verb,
    { reason: reason.value, target_machine_id: targetMachine.value || null },
  );
  if (result) action.value = null;
}
function openReport(run: DataRow) {
  if (store.dirty || store.busy) {
    store.error = '请先保存或取消当前输入';
    return;
  }
  store.drawer = false;
  selectedReport.value = run.id;
  tab.value = 'reports';
}
const statLabels = [
  ['pending_count', '待排需求'],
  ['running_count', '实际在产'],
  ['late_count', '交期风险'],
  ['unresolved_count', '待处理资料'],
];
let timer: ReturnType<typeof setInterval> | undefined;
onMounted(() => {
  window.addEventListener('resize', resize);
  timer = setInterval(() => void store.poll(), 5000);
});
onBeforeUnmount(() => {
  factoryLoadGeneration++;
  clearInterval(timer);
  window.removeEventListener('resize', resize);
});

const templateLabels0: Record<string, string> = {
  machine_count: '机台',
  candidate_count: '候选需求',
  demand_count: '需求',
  new_count: '新增',
  update_count: '更新',
  ambiguous_count: '需匹配',
  historical_cell_count: '历史数量格',
  formula_count: '公式格',
  task_candidate_count: '候选需求',
  old_machine_count: '旧车间机台',
  new_machine_count: '新车间机台',
  machine_area_task_count: '机台区需求',
  tail_task_count: '尾部需求',
  numeric_order_quantity_rows: '有计划数的行',
  cached_remaining_quantity_rows: '有原表欠数的行',
  order_quantity_sum: '原表计划合计',
  cached_produced_quantity_sum: '原表已啤合计',
  cached_remaining_quantity_sum: '原表欠数合计',
  standard_remaining_sum: '按计划减已啤计算欠数',
  quantity_sum_gap: '欠数口径差异',
  numeric_shift_cell_count: '历史报数格',
  numeric_shift_quantity_sum: '历史逐班合计',
  shift_sum_minus_cached_M: '逐班与已啤差异',
  formula_cell_count: '原表公式格',
  cached_na_cells: '原表错误值',
  dated_shift_column_count: '日期班次列',
  creates: '新增需求',
  updates: '更新需求',
  conflicts: '待解决冲突',
};
const issueNames: Record<string, string> = {
  MISSING_QUANTITY: '数量待补',
  WRONG_AS_REFERENCE: '原表异常值仅留作参考',
  SOURCE_CELL_ERROR: '原表单元格错误',
  INVALID_LEGACY_DATE: '原表日期无法识别',
  MISSING_REMAINING_FORMULA: '原表欠数公式缺失',
  AMBIGUOUS_DEMAND: '存在多个同编码需求，请明确匹配',
  UNKNOWN_SCOPED_DEMAND: '未找到当前厂区的需求',
};
function issueText(issue: any) {
  return typeof issue === 'string'
    ? issue
    : issue.message || issueNames[issue.code] || '原表资料需核对';
}
const importSummary = computed(() =>
  Object.entries(importPreview.value?.summary || {})
    .filter(([k]) => templateLabels0[k])
    .map(([k, value]) => ({
      label: templateLabels0[k],
      value: Array.isArray(value) ? value.length : value,
    })),
);
const templateLabels1: Record<string, string> = {
  start: '实际开工',
  pause: '暂停批次',
  resume: '恢复生产',
  transfer: '转机',
  finish: '结束批次',
};
</script>
<template>
  <main
    class="inj-workspace"
    :class="{
      'inj-focus-mode': view.focusMode,
      'inj-no-motion': !motionAllowed,
    }"
    :data-density="view.density"
    :aria-busy="factoryLoading || store.loading || store.busy"
  >
    <header class="inj-header">
      <RouterLink
        class="inj-back"
        :to="{
          path: '/modules/production',
          query: store.factory ? { factory: store.factory } : {},
        }"
        aria-label="返回生产模块"
        ><ArrowLeft
      /></RouterLink>
      <h1>注塑排产中枢</h1>
      <select
        :value="store.factory || ''"
        aria-label="当前厂区"
        :disabled="store.busy || store.dirty"
        @change="changeFactory"
      >
        <option value="" disabled>选择厂区</option>
        <option v-for="(label, key) in factories" :key="key" :value="key">
          {{ label }}
        </option>
      </select>
      <InjSegmentedControl
        v-if="store.factory"
        class="inj-workspaces"
        :model-value="section"
        :options="sectionOptions"
        label="工作区"
        :disabled="store.busy || store.dirty"
        @update:model-value="switchTab"
      />
      <span class="inj-spacer" />
      <span
        class="inj-sync"
        :class="{ stale: store.stale }"
        :title="'每 5 秒检查资料更新 · ' + store.syncedAt"
        ><i :key="store.syncedAt" />{{
          store.stale
            ? '有更新待刷新'
            : store.syncedAt
              ? '定时同步 ' + store.syncedAt
              : '正在连接'
        }}</span
      >
      <InjButton
        aria-label="刷新工作台"
        :disabled="store.busy || store.dirty"
        :pending="pendingActionKey === 'refresh'"
        @click="pending('refresh', store.refresh)"
        ><template #icon><RefreshCw /></template
      ></InjButton>
      <button
        aria-label="操作说明"
        class="inj-help-button"
        @click="help = !help"
      >
        <CircleHelp />
      </button>
      <div id="inj-primary-slot">
        <InjButton
          v-if="canPlan && section === 'planning'"
          primary
          :disabled="store.busy || store.dirty"
          :pending="pendingActionKey === 'auto'"
          @click="
            autoMode = 'UNSCHEDULED';
            pending('auto', () => schedule());
          "
          ><template #icon><WandSparkles /></template>自动排产</InjButton
        >
      </div>
    </header>
    <div v-if="!store.factory" class="inj-factory-empty">
      <Factory class="inj-empty-symbol" />
      <h2>选择要排产的厂区</h2>
      <p>各厂独立维护机台、需求和报数，公共模具资料由四厂共享。</p>
      <div class="inj-inline">
        <button
          v-for="(label, key) in factories"
          :key="key"
          @click="
            app.setActiveFactory(key);
            router.replace({ query: { factory: key } });
          "
        >
          {{ label }}
        </button>
      </div>
    </div>
    <template v-else>
      <div
        v-if="['timeline', 'table', 'machines'].includes(tab)"
        class="inj-global-toolbar"
        :inert="store.dirty || store.busy"
      >
        <InjSegmentedControl
          :model-value="tab"
          :options="planningOptions"
          label="排产视图"
          @update:model-value="switchTab"
        />
        <div class="inj-search">
          <Search aria-hidden="true" />
          <select v-model="store.search.field" aria-label="查找字段">
            <option value="mold_code">模号</option>
            <option value="order_no">单号</option>
            <option value="item_no">货号</option>
            <option value="machine_code">机号</option>
            <option value="order_note">备注</option>
            <option value="all">全部文本</option></select
          ><select v-model="store.search.mode" aria-label="查找模式">
            <option value="exact">精确</option>
            <option value="contains">包含</option>
            <option value="prefix">前缀</option>
            <option value="in">批量列表</option></select
          ><textarea
            v-if="store.search.mode === 'in'"
            v-model="store.search.text"
            rows="4"
            placeholder="粘贴一列完整编码"
            aria-label="查找内容"
          /><input
            v-else
            v-model="store.search.text"
            placeholder="输入编码，Enter 查找"
            aria-label="查找内容"
            @keydown.enter="
              search();
              tab = 'table';
            "
          /><button
            @click="
              search();
              tab = 'table';
            "
          >
            查找
          </button>
        </div>
        <span v-if="store.search.text" class="inj-muted"
          >{{ findCount }} 处 · 当前 {{ findCount ? findIndex + 1 : 0 }}</span
        ><button v-if="store.search.text" title="上一处" @click="find(-1)">
          <ArrowUp /></button
        ><button v-if="store.search.text" title="下一处" @click="find(1)">
          <ArrowDown /></button
        ><button
          @click="
            filterDraft = store.filter
              ? JSON.parse(JSON.stringify(store.filter))
              : filterDraft;
            filterOpen = !filterOpen;
          "
        >
          <Filter /> 筛选{{ store.filter ? ' · 已应用' : '' }}</button
        ><button
          v-if="store.filter || store.search.text"
          @click="
            store.filter = null;
            store.search.text = '';
            store.cursor = 0;
            store.loadTable();
          "
        >
          清除</button
        ><span class="inj-spacer" /><button
          v-if="canPlan"
          :disabled="store.busy || store.dirty"
          @click="newDemand = true"
        >
          <Plus /> 新增需求</button
        ><button
          v-if="canPlan"
          :disabled="store.busy || store.dirty"
          @click="fileInput?.click()"
        >
          <Upload /> 导入 Excel</button
        ><button @click="exportOpen = true">导出</button>
        <details
          class="inj-more"
          :open="moreOpen"
          @toggle="moreOpen = ($event.target as HTMLDetailsElement).open"
        >
          <summary><Ellipsis />更多</summary>
          <div class="inj-menu">
            <button
              v-if="canPlan"
              @click="
                autoOptions = true;
                moreOpen = false;
              "
            >
              <WandSparkles />排产范围与预览
            </button>
            <button
              v-if="canPlan"
              :disabled="store.busy || store.dirty"
              @click="
                pending('undo', () => store.mutate('/schedule/undo'));
                moreOpen = false;
              "
            >
              <Undo2 />撤销排产
            </button>
            <button
              @click="
                view.focusMode = !view.focusMode;
                moreOpen = false;
              "
            >
              <Focus />{{ view.focusMode ? '退出' : '进入' }}焦点模式
            </button>
            <label
              >行密度<select v-model="view.density" aria-label="行密度">
                <option value="compact">紧凑</option>
                <option value="comfortable">舒适</option>
              </select></label
            >
            <button
              @click="
                help = true;
                moreOpen = false;
              "
            >
              <CircleHelp />操作说明
            </button>
          </div>
        </details>
        <input
          ref="fileInput"
          hidden
          type="file"
          accept=".xlsx"
          @change="upload"
        />
      </div>
      <div class="inj-signal-bar">
        <button
          class="inj-risk-toggle"
          :aria-expanded="riskOpen"
          @click="riskOpen = !riskOpen"
        >
          生产摘要 · 风险 {{ numberText(store.summary.late_count)
          }}<ChevronDown />
        </button>
        <div class="inj-stats" :class="{ open: riskOpen }">
          <button
            v-for="item in statLabels"
            :key="item[0]"
            :disabled="store.busy || store.dirty"
            @click="
              runningOnly = item[0] === 'running_count';
              tab = runningOnly ? 'machines' : 'table';
              store.filter =
                item[0] === 'late_count'
                  ? { field: 'delivery_slack_hours', op: 'lt', value: 0 }
                  : item[0] === 'unresolved_count'
                    ? { field: 'unplaced_reason', op: 'not_empty' }
                    : item[0] === 'pending_count'
                      ? {
                          op: 'and',
                          children: [
                            { field: 'planned_start_at', op: 'is_empty' },
                            { field: 'remaining_shots', op: 'gt', value: 0 },
                          ],
                        }
                      : null;
              store.cursor = 0;
              store.loadTable();
            "
          >
            <span>{{ item[1] }}</span
            ><strong
              :key="String(store.summary[item[0]!])"
              class="inj-metric-value"
              >{{ numberText(store.summary[item[0]!])
              }}<small v-if="item[0] === 'running_count'">
                / {{ store.summary.machine_count ?? 0 }}</small
              ></strong
            >
          </button>
        </div>
        <span class="inj-spacer" /><span
          v-if="section !== 'planning'"
          class="inj-inline"
          ><button
            v-if="canPlan"
            :disabled="store.dirty || store.busy"
            @click="autoOptions = true"
          >
            排产范围</button
          ><button @click="exportOpen = true">导出</button></span
        >
        <span v-else class="inj-scope-note"
          >需求查找结果在计划表 · 数量单位：物理啤数</span
        >
      </div>
      <div v-if="store.filter && tab === 'table'" class="inj-condition-strip">
        {{ factories[store.factory] }} · {{ filterLabel(store.filter) }}
      </div>
      <div v-if="store.error" class="inj-alert" role="alert">
        <strong>操作未完成</strong><span>{{ store.error }}</span
        ><button @click="store.error = ''" aria-label="关闭错误提示">
          <X />
        </button>
      </div>
      <div v-else-if="store.notice" class="inj-notice" role="status">
        {{ store.notice
        }}<button @click="store.notice = ''" aria-label="关闭保存提示">
          <X />
        </button>
      </div>
      <div
        class="inj-content"
        :class="{ 'inj-has-inspector': (store.drawer || newDemand) && docked }"
      >
        <InjLoadingState
          v-if="factoryLoading || (store.loading && !store.syncedAt)"
        />
        <ScheduleBoard
          :key="view.contextGeneration"
          v-else-if="tab === 'timeline' || tab === 'machines'"
          v-model:running-only="runningOnly"
          :mode="tab"
          :collapse-pool="store.drawer && docked && viewportWidth < 1600"
          :can-plan="canPlan"
          :can-report="canReport"
          @report="openReport"
          @action="beginAction"
        /><PlanTable
          :key="view.contextGeneration"
          v-else-if="tab === 'table'"
          :can-edit="canPlan"
        /><ShiftReports
          :key="view.contextGeneration"
          v-else-if="tab === 'reports'"
          :can-report="canReport"
          :selected-run-id="selectedReport"
        /><MasterData
          :key="view.contextGeneration"
          v-else
          :can-write="canMaster"
        />
        <DemandDrawer
          v-if="store.drawer || newDemand"
          :docked="docked"
          :creating="newDemand"
          :can-plan="canPlan"
          :can-report="canReport"
          @close="
            newDemand = false;
            store.drawer = false;
          "
          @action="beginAction"
          @report="openReport"
        />
      </div>
      <footer class="inj-statusbar">
        <span>{{ factories[store.factory] }} · {{ store.total }} 条需求</span
        ><template v-if="store.detail?.demand.id === store.selectedId"
          ><span class="inj-mono">{{ store.detail.demand.mold_code }}</span
          ><span
            >欠数 {{ numberText(store.detail.demand.remaining_shots) }}</span
          ><button
            :disabled="store.dirty || store.busy"
            @click="store.drawer = true"
          >
            打开详情<ArrowRight /></button></template
        ><span class="inj-spacer" /><span>{{
          store.dirty ? '有未保存输入' : '物理啤数 · 计划与实际分别记录'
        }}</span>
      </footer>
    </template>
    <div v-if="filterOpen" class="inj-modal-backdrop">
      <section
        class="inj-modal inj-filter-modal"
        role="dialog"
        aria-modal="true"
        aria-label="自定义筛选"
        v-inj-dialog="{
          close: () => {
            filterOpen = false;
          },
          busy: store.busy,
        }"
      >
        <h2>自定义筛选</h2>
        <p>条件作用于本厂全部需求，统计和导出共用同一条件。</p>
        <FilterGroup v-model="filterDraft" :fields="store.fields" />
        <div class="inj-actions">
          <button @click="filterOpen = false">取消</button
          ><button
            class="inj-primary"
            @click="
              applyFilter();
              tab = 'table';
            "
          >
            应用筛选
          </button>
        </div>
      </section>
    </div>
    <div v-if="autoOptions" class="inj-modal-backdrop">
      <section
        class="inj-modal"
        role="dialog"
        aria-modal="true"
        aria-label="自动排产范围"
        v-inj-dialog="{
          close: () => {
            autoOptions = false;
          },
          busy: store.busy,
        }"
      >
        <h2>自动排产范围</h2>
        <select v-model="autoMode">
          <option value="UNSCHEDULED">仅未排需求</option>
          <option value="ALL_UNSTARTED">全部未开工需求</option>
          <option value="SELECTED">指定机台 / 当前选中需求</option>
        </select>
        <div v-if="autoMode === 'SELECTED'" class="inj-column-list">
          <label v-for="m in store.machines" :key="m.id"
            ><input v-model="autoMachines" type="checkbox" :value="m.id" />{{
              m.code
            }}</label
          >
        </div>
        <p class="inj-help">
          已经开工、暂停的批次保留实际事实；固定任务保留机台和队列位置。
        </p>
        <details v-if="store.lastResult">
          <summary>最近计算结果</summary>
          <p>待处理 {{ store.lastResult.unplaced?.length || 0 }} 条</p>
          <ul>
            <li
              v-for="r in store.lastResult.unplaced?.slice(0, 30)"
              :key="r.demand_id"
            >
              {{ r.reason_text || r.reason }} · {{ r.demand_id }}
            </li>
          </ul>
        </details>
        <div class="inj-actions">
          <button @click="autoOptions = false">关闭</button
          ><button :disabled="store.busy" @click="schedule(false)">
            仅预览</button
          ><button
            class="inj-primary"
            :disabled="store.busy"
            @click="schedule()"
          >
            计算并保存
          </button>
        </div>
      </section>
    </div>
    <div v-if="importPreview" class="inj-modal-backdrop">
      <section
        class="inj-modal inj-import-modal"
        role="dialog"
        aria-modal="true"
        aria-label="导入预览"
        v-inj-dialog="{
          close: () => {
            importPreview = null;
          },
          busy: store.busy,
        }"
      >
        <h2>计划表导入预览 · {{ factories[store.factory!] }}</h2>
        <p>只读取“计划表”。检查候选需求、原表问题和更新差异后应用。</p>
        <div class="inj-import-summary">
          <span v-for="item in importSummary" :key="item.label"
            ><strong>{{ item.label }}</strong> {{ item.value }}</span
          >
        </div>
        <div class="inj-preview-scroll">
          <table class="inj-small-table">
            <thead>
              <tr>
                <th>跳过</th>
                <th>原行</th>
                <th>模号 / 单号</th>
                <th>计划 / 已啤 / 欠数</th>
                <th>待处理问题</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in importPreview.rows" :key="row.source_row">
                <td>
                  <input
                    v-model="skipRows"
                    type="checkbox"
                    :value="row.source_row"
                    :aria-label="'跳过原行 ' + row.source_row"
                  />
                </td>
                <td>{{ row.source_row }}</td>
                <td>
                  {{ row.fields.mold_code
                  }}<small>{{ row.fields.order_no }}</small>
                </td>
                <td>
                  {{ numberText(row.fields.planned_shots) }} /
                  {{ numberText(row.fields.completed_shots) }} /
                  {{ numberText(row.fields.remaining_shots) }}
                </td>
                <td>
                  {{ row.issues?.map(issueText).join('；') }}
                  <select
                    v-if="row.match_candidates?.length > 1"
                    v-model="importMatches[String(row.source_row)]"
                    :aria-label="'匹配原行 ' + row.source_row"
                  >
                    <option value="">请选择现有需求</option>
                    <option
                      v-for="candidate in row.match_candidates"
                      :key="candidate.id"
                      :value="candidate.id"
                    >
                      原行 {{ candidate.source_row ?? '手工新增' }} · 版本
                      {{ candidate.revision }} · {{ candidate.id.slice(-6) }}
                    </option>
                  </select>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="inj-error-text">{{ store.error }}</p>
        <div class="inj-actions">
          <button @click="importPreview = null">暂不应用</button
          ><button
            class="inj-primary"
            :disabled="store.busy"
            @click="pending('import', applyImport)"
          >
            <RefreshCw
              v-if="pendingActionKey === 'import'"
              class="inj-spin"
            />应用所选需求
          </button>
        </div>
      </section>
    </div>
    <div v-if="exportOpen" class="inj-modal-backdrop">
      <section
        class="inj-modal"
        role="dialog"
        aria-modal="true"
        aria-label="导出计划"
        v-inj-dialog="{
          close: () => {
            exportOpen = false;
          },
          busy: store.busy,
        }"
      >
        <h2>导出当前筛选范围</h2>
        <p>包含全部匹配需求、标准交换表、机台分组计划表和口径说明。</p>
        <div class="inj-form-grid">
          <label>历史窗口开始<input v-model="exportStart" type="date" /></label
          ><label
            >窗口天数<input
              v-model.number="exportDays"
              type="number"
              min="1"
              max="366" /></label
          ><label
            ><input
              v-model="exportFormulas"
              type="checkbox"
            />附可编辑数量公式</label
          >
        </div>
        <p class="inj-error-text">{{ store.error }}</p>
        <div class="inj-actions">
          <button @click="exportOpen = false">取消</button
          ><button
            class="inj-primary"
            :disabled="store.busy"
            @click="pending('export', download)"
          >
            <RefreshCw
              v-if="pendingActionKey === 'export'"
              class="inj-spin"
            />导出 Excel
          </button>
        </div>
      </section>
    </div>
    <div v-if="action" class="inj-modal-backdrop inj-action-modal">
      <section
        class="inj-modal"
        role="dialog"
        aria-modal="true"
        aria-label="生产操作"
        v-inj-dialog="{
          close: () => {
            action = null;
          },
          busy: store.busy,
        }"
      >
        <h2>{{ templateLabels1[action.verb] }}</h2>
        <p>
          {{ action.run.mold_code || action.run.snapshot?.mold_code }} ·
          {{
            store.machines.find((m) => m.id === action!.run.machine_id)?.code
          }}
        </p>
        <p class="inj-help">记录实际操作时刻，并据此更新机台占用和后续计划。</p>
        <label v-if="action.verb === 'transfer'"
          >目标机台<select v-model="targetMachine">
            <option value="">请选择</option>
            <option
              v-for="m in store.machines"
              :key="m.id"
              :value="m.id"
              :disabled="m.id === action.run.machine_id"
            >
              {{ m.code }} · {{ m.machine_a }}A
            </option>
          </select></label
        ><label
          >说明<textarea v-model="reason" placeholder="填写现场情况" />
        </label>
        <p class="inj-error-text">{{ store.error }}</p>
        <div class="inj-actions">
          <button @click="action = null">取消</button
          ><button
            class="inj-primary"
            :disabled="
              store.busy || (action.verb === 'transfer' && !targetMachine)
            "
            @click="pending('execution', applyAction)"
          >
            <RefreshCw
              v-if="pendingActionKey === 'execution'"
              class="inj-spin"
            />记录并更新
          </button>
        </div>
      </section>
    </div>
    <div v-if="help" class="inj-modal-backdrop">
      <section
        class="inj-modal"
        role="dialog"
        aria-modal="true"
        aria-label="操作说明"
        v-inj-dialog="{
          close: () => {
            help = false;
          },
          busy: store.busy,
        }"
      >
        <h2>日常使用</h2>
        <ol>
          <li>选择厂区，导入计划表或新增需求。</li>
          <li>在待处理需求中补齐模具 A、可用资产和日目标。</li>
          <li>点击自动排产直接保存；拖动批次可调整机台和顺序。</li>
          <li>现场开工后，在白夜班报工输入本班累计数。</li>
          <li>通过全字段表精确查找、批量维护并导出。</li>
        </ol>
        <p>
          修改 200 为 250 仅增加 50，随后改为 230 会回减
          20。价格和重量缺失不阻止排产。
        </p>
        <button class="inj-primary" @click="help = false">知道了</button>
      </section>
    </div>
  </main>
</template>
