<script setup lang="ts">
import { vInjDialog } from '@/features/injection-scheduling/composables/injDialog';
import {
  computed,
  nextTick,
  ref,
  watch,
  onMounted,
  onBeforeUnmount,
} from 'vue';
import {
  getCoreRowModel,
  useVueTable,
  type ColumnDef,
  type ColumnSizingState,
  type VisibilityState,
} from '@tanstack/vue-table';
import { useVirtualizer } from '@tanstack/vue-virtual';
import { useInjectionStore } from '@/stores/injectionScheduling';
import { injectionApi as api } from '@/api/injectionScheduling';
import {
  displayValue,
  numberText,
  parseValue,
  type DataRow,
  type FilterNode,
} from './types';
import {
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  ArrowDown,
  Filter,
  X,
  GripVertical,
} from '@lucide/vue';
import {
  useInjectionViewState,
  rowHeight,
} from './composables/useInjectionViewState';
import PlanCell from './components/PlanCell.vue';
import FilterGroup from './FilterGroup.vue';

const props = defineProps<{ canEdit: boolean }>();
const store = useInjectionStore(),
  view = useInjectionViewState();
const viewContext = view.contextGeneration;
const tableRowHeight = computed(() => rowHeight(view.density, 'table'));
const columnSearch = ref(''),
  draggedColumn = ref('');
const columnFilter = ref<FilterNode | null>(null);
async function applyColumnFilter() {
  store.filter = columnFilter.value;
  store.cursor = 0;
  await store.loadTable();
  columnFilter.value = null;
}
watch(
  () => store.cursor,
  () => {
    selected.value = [];
  },
);
const scroll = ref<HTMLElement>(),
  columnPanel = ref(false),
  preset = ref(view.table?.preset || '常用'),
  sizing = ref<ColumnSizingState>(view.table?.sizing || {}),
  visibility = ref<VisibilityState>(view.table?.visibility || {}),
  order = ref<string[]>(view.table?.order || []),
  freeze = ref(view.table?.freeze ?? 2);
const selected = ref<string[]>([]),
  active = ref({ row: 0, column: 0 }),
  anchor = ref({ row: 0, column: 0 });
const editing = ref<{
    id: string;
    revision: number;
    field: string;
    value: string;
  } | null>(null),
  editError = ref(''),
  pendingPaste = ref<{
    rows: any[];
    errors: string[];
    columns: string[];
    count: number;
  } | null>(null);
const bulkValue = ref(''),
  viewName = ref(''),
  groupMachine = ref(''),
  pageSize = 100;
const common = [
  'machine_code',
  'mold_code',
  'order_no',
  'item_no',
  'part_name',
  'required_machine_a',
  'planned_shots',
  'completed_shots',
  'remaining_shots',
  'target_shots_per_day',
  'color_name',
  'material_raw',
  'planned_start_at',
  'planned_end_at',
  'delivery_due_at',
  'delivery_slack_hours',
  'unplaced_reason',
];
const columns = computed<ColumnDef<DataRow>[]>(() =>
  store.fields.map((f) => ({
    id: f.key,
    accessorKey: f.key,
    header: f.label,
    size: ['mold_code', 'order_no', 'item_no'].includes(f.key)
      ? 178
      : f.value_type === 'datetime'
        ? 160
        : 125,
    minSize: 78,
    maxSize: 450,
  })),
);
const table = useVueTable({
  get data() {
    return store.rows;
  },
  get columns() {
    return columns.value;
  },
  getCoreRowModel: getCoreRowModel(),
  getRowId: (row) => row.id,
  columnResizeMode: 'onChange',
  state: {
    get columnSizing() {
      return sizing.value;
    },
    get columnVisibility() {
      return visibility.value;
    },
    get columnOrder() {
      return order.value;
    },
  },
  onColumnSizingChange: (v) =>
    (sizing.value = typeof v === 'function' ? v(sizing.value) : v),
  onColumnVisibilityChange: (v) =>
    (visibility.value = typeof v === 'function' ? v(visibility.value) : v),
  onColumnOrderChange: (v) =>
    (order.value = typeof v === 'function' ? v(order.value) : v),
});
const visible = computed(() => table.getVisibleLeafColumns()),
  model = computed(() => table.getRowModel().rows);
const virtual = useVirtualizer(
  computed(() => ({
    count: model.value.length,
    getScrollElement: () => scroll.value ?? null,
    estimateSize: () => tableRowHeight.value,
    getItemKey: (index: number) => model.value[index]!.id,
    overscan: 8,
  })),
);
const virtualRows = computed(() => virtual.value.getVirtualItems());
watch(tableRowHeight, () => nextTick(() => virtual.value.measure()));
const columnGroups: Record<string, string> = {
  identity: '订单识别',
  schedule: '排程',
  process: '工艺参数',
  quantity: '数量',
  delivery: '交期',
  source: '原表来源',
  status: '状态',
  machine: '机台',
  requirements: '设备要求',
  audit: '记录',
  material: '材料',
};
const columnGroupLabel = (group?: string) =>
  group ? columnGroups[group] || group : '';
const filteredColumns = computed(() =>
  table
    .getAllLeafColumns()
    .filter(
      (c) =>
        !columnSearch.value ||
        [
          c.id,
          store.fieldMap[c.id]?.label,
          columnGroupLabel(store.fieldMap[c.id]?.group),
        ]
          .join(' ')
          .includes(columnSearch.value),
    ),
);
function dropColumn(id: string) {
  const keys = table
    .getAllLeafColumns()
    .map((c) => c.id)
    .filter((key) => key !== draggedColumn.value);
  const i = keys.indexOf(id);
  if (i >= 0 && draggedColumn.value) {
    keys.splice(i, 0, draggedColumn.value);
    order.value = keys;
  }
  draggedColumn.value = '';
}
function rememberScroll() {
  if (viewContext !== view.contextGeneration) return;
  if (scroll.value)
    view.scroll.table = {
      top: scroll.value.scrollTop,
      left: scroll.value.scrollLeft,
    };
}
onMounted(() =>
  nextTick(() => {
    const position = view.scroll.table;
    if (scroll.value && position) {
      scroll.value.scrollTop = position.top;
      scroll.value.scrollLeft = position.left;
    }
  }),
);
onBeforeUnmount(() => {
  if (viewContext !== view.contextGeneration) return;
  rememberScroll();
  view.table = {
    preset: preset.value,
    sizing: { ...sizing.value },
    visibility: { ...visibility.value },
    order: [...order.value],
    freeze: freeze.value,
  };
});
const selectedSummary = computed(() =>
  store.rows
    .filter((r) => selected.value.includes(r.id))
    .reduce(
      (s, r) => ({
        count: s.count + 1,
        planned: s.planned + Number(r.planned_shots || 0),
        remaining: s.remaining + Number(r.remaining_shots || 0),
      }),
      { count: 0, planned: 0, remaining: 0 },
    ),
);
function applyPreset() {
  visibility.value = Object.fromEntries(
    store.fields.map((f) => [
      f.key,
      preset.value === '全字段' ||
        (preset.value === '常用'
          ? common.includes(f.key)
          : [
              'identity',
              preset.value === '工艺' ? 'process' : 'delivery',
              'quantity',
            ].includes(f.group)),
    ]),
  );
  if (!order.value.length)
    order.value = [
      ...common,
      ...store.fields.map((f) => f.key).filter((k) => !common.includes(k)),
    ];
}
watch(
  () => store.fields,
  () => {
    if (!view.table) applyPreset();
  },
  { immediate: true },
);
watch(
  () => store.factory,
  () => {
    editing.value = null;
    pendingPaste.value = null;
    selected.value = [];
  },
);
function cellStyle(index: number) {
  const c = visible.value[index]!,
    fixed = index < freeze.value;
  return {
    width: c.getSize() + 'px',
    minWidth: c.getSize() + 'px',
    left: fixed
      ? 38 +
        visible.value.slice(0, index).reduce((n, c) => n + c.getSize(), 0) +
        'px'
      : undefined,
    position: fixed ? ('sticky' as const) : undefined,
    zIndex: fixed ? 2 : undefined,
  };
}
function focusCell(row: number, column: number, extend = false) {
  active.value = {
    row: Math.max(0, Math.min(model.value.length - 1, row)),
    column: Math.max(0, Math.min(visible.value.length - 1, column)),
  };
  if (!extend) anchor.value = { ...active.value };
  virtual.value.scrollToIndex(active.value.row);
  nextTick(() =>
    scroll.value
      ?.querySelector<HTMLElement>(
        `[data-cell="${active.value.row}:${active.value.column}"]`,
      )
      ?.focus(),
  );
}
function inRange(r: number, c: number) {
  return (
    r >= Math.min(active.value.row, anchor.value.row) &&
    r <= Math.max(active.value.row, anchor.value.row) &&
    c >= Math.min(active.value.column, anchor.value.column) &&
    c <= Math.max(active.value.column, anchor.value.column)
  );
}
function beginEdit(row: DataRow, key: string) {
  if (!props.canEdit || store.busy || !store.fieldMap[key]?.editable) return;
  editing.value = {
    id: row.id,
    revision: row.revision,
    field: key,
    value:
      row[key] == null
        ? ''
        : typeof row[key] === 'object'
          ? JSON.stringify(row[key])
          : String(row[key]),
  };
  editError.value = '';
  store.dirty = true;
  nextTick(() =>
    scroll.value?.querySelector<HTMLInputElement>('.inj-cell-editor')?.focus(),
  );
}
function cancel() {
  editing.value = null;
  editError.value = '';
  store.dirty = !!pendingPaste.value;
}
async function commit() {
  if (!editing.value) return;
  const edit = editing.value,
    row = { id: edit.id };
  try {
    const value = parseValue(edit.value, store.fieldMap[edit.field]!);
    const result = await store.mutate(
      '/demands/' + row.id,
      { data: { [edit.field]: value }, record_revision: edit.revision },
      'patch',
    );
    if (result) cancel();
    else editError.value = store.error;
  } catch (e) {
    editError.value = String(e);
  }
}
function keydown(event: KeyboardEvent, row: DataRow, key: string) {
  if (event.isComposing) return;
  if (editing.value) {
    if (event.key === 'Escape') {
      event.preventDefault();
      cancel();
    } else if (event.key === 'Enter') {
      event.preventDefault();
      void commit();
    }
    return;
  }
  const moves: Record<string, [number, number]> = {
    ArrowUp: [-1, 0],
    ArrowDown: [1, 0],
    ArrowLeft: [0, -1],
    ArrowRight: [0, 1],
    Tab: [0, event.shiftKey ? -1 : 1],
  };
  if (moves[event.key]) {
    event.preventDefault();
    const [r, c] = moves[event.key]!;
    focusCell(
      active.value.row + r,
      active.value.column + c,
      event.shiftKey && event.key !== 'Tab',
    );
  } else if (event.key === 'Enter' || event.key === 'F2') {
    event.preventDefault();
    beginEdit(row, key);
  }
}
function copy(event: ClipboardEvent) {
  if (editing.value) return;
  const lines: string[] = [];
  for (
    let r = Math.min(anchor.value.row, active.value.row);
    r <= Math.max(anchor.value.row, active.value.row);
    r++
  )
    lines.push(
      visible.value
        .slice(
          Math.min(anchor.value.column, active.value.column),
          Math.max(anchor.value.column, active.value.column) + 1,
        )
        .map((c) => String(store.rows[r]?.[c.id] ?? ''))
        .join('\t'),
    );
  event.clipboardData?.setData('text/plain', lines.join('\n'));
  event.preventDefault();
}
function paste(event: ClipboardEvent) {
  if (editing.value || !props.canEdit) return;
  event.preventDefault();
  const lines = (event.clipboardData?.getData('text/plain') || '')
    .replace(/\r/g, '')
    .replace(/\n$/, '')
    .split('\n')
    .map((s) => s.split('\t'));
  const errors: string[] = [],
    rows: any[] = [],
    names = new Set<string>();
  lines.forEach((cells, i) => {
    const row = store.rows[active.value.row + i];
    if (!row) {
      errors.push(`第 ${i + 1} 行超出当前页，请分段粘贴`);
      return;
    }
    const data: Record<string, unknown> = {};
    cells.forEach((raw, j) => {
      const column = visible.value[active.value.column + j],
        field = column && store.fieldMap[column.id];
      if (!field?.editable) {
        errors.push(`第 ${i + 1} 行第 ${j + 1} 列为只读或超出范围`);
        return;
      }
      names.add(field.label);
      try {
        data[field.key] = parseValue(raw, field);
      } catch (e) {
        errors.push(`第 ${i + 1} 行：${String(e)}`);
      }
    });
    rows.push({ id: row.id, revision: row.revision, data });
  });
  pendingPaste.value = {
    rows,
    errors,
    columns: [...names],
    count: lines.length,
  };
  store.dirty = true;
}
async function applyPaste() {
  if (
    pendingPaste.value &&
    !pendingPaste.value.errors.length &&
    (await store.mutate('/demands/bulk-update', {
      rows: pendingPaste.value.rows,
    }))
  )
    pendingPaste.value = null;
}
async function fill() {
  const column = visible.value[active.value.column],
    field = column && store.fieldMap[column.id];
  if (!field?.editable || !selected.value.length) return;
  try {
    const value = parseValue(bulkValue.value, field);
    await store.mutate('/demands/bulk-update', {
      rows: store.rows
        .filter((r) => selected.value.includes(r.id))
        .map((r) => ({
          id: r.id,
          revision: r.revision,
          data: { [field.key]: value },
        })),
    });
  } catch (e) {
    store.showError(e);
  }
}
function sortBy(key: string, multi: boolean) {
  if (store.dirty) {
    store.error = '请先保存或取消当前单元格编辑';
    return;
  }
  const old = store.sort.find((s) => s.field === key);
  const next = old?.direction === 'asc' ? 'desc' : old ? '' : 'asc';
  store.sort = [
    ...(multi ? store.sort.filter((s) => s.field !== key) : []),
    ...(next ? [{ field: key, direction: next }] : []),
  ];
  store.cursor = 0;
  void store.loadTable();
}
function reorder(key: string, offset: number) {
  const list = [...order.value],
    i = list.indexOf(key);
  if (i + offset < 0 || i + offset >= list.length) return;
  [list[i], list[i + offset]] = [list[i + offset]!, list[i]!];
  order.value = list;
}
async function saveView() {
  if (!viewName.value.trim()) return;
  const result = await store.mutate('/views', {
    data: {
      name: viewName.value,
      view_type: 'table',
      config: {
        visibility: visibility.value,
        order: order.value,
        sizing: sizing.value,
        freeze: freeze.value,
        filter: store.filter,
        sort: store.sort,
        search: store.search,
      },
    },
  });
  if (result) {
    store.views = await api.get('/views', { factory_id: store.factory });
    viewName.value = '';
  }
}
function restoreView(id: string) {
  const config = store.views.find((v) => v.id === id)?.config;
  if (!config) return;
  visibility.value = config.visibility || {};
  order.value = config.order || [];
  sizing.value = config.sizing || {};
  freeze.value = config.freeze ?? 2;
  store.filter = config.filter;
  store.sort = config.sort || [];
  store.search = config.search || store.search;
  store.cursor = 0;
  void store.loadTable();
}
</script>
<template>
  <section
    class="inj-table-area"
    :style="{ '--inj-table-row': tableRowHeight + 'px' }"
  >
    <div class="inj-toolbar" :inert="store.dirty || store.busy">
      <select v-model="preset" aria-label="列视图" @change="applyPreset">
        <option>常用</option>
        <option>工艺</option>
        <option>交付</option>
        <option>全字段</option></select
      ><button @click="columnPanel = !columnPanel">
        列设置 · {{ visible.length }}</button
      ><select
        aria-label="已保存视图"
        @change="restoreView(($event.target as HTMLSelectElement).value)"
      >
        <option value="">已保存视图</option>
        <option v-for="v in store.views" :key="v.id" :value="v.id">
          {{ v.name }}
        </option></select
      ><span class="inj-muted"
        >Shift 点击列头可多列排序 · Enter 编辑 · Ctrl+C/V 复制粘贴</span
      ><span class="inj-spacer" /><strong
        >{{ numberText(store.total) }} 条</strong
      >
    </div>
    <aside
      v-if="columnPanel"
      :inert="store.dirty || store.busy"
      class="inj-columns-panel"
      aria-label="计划表列管理"
    >
      <header>
        <h3>列管理</h3>
        <button aria-label="关闭列管理" @click="columnPanel = false">
          <X />
        </button>
      </header>
      <input
        v-model="columnSearch"
        aria-label="查找列"
        placeholder="搜索字段名称或分组"
      />
      <div class="inj-inline">
        <label
          >冻结左列
          <input v-model.number="freeze" type="number" min="0" max="5" /></label
        ><input v-model="viewName" placeholder="视图名称" /><button
          @click="saveView"
        >
          保存视图</button
        ><button @click="columnPanel = false">完成</button>
      </div>
      <div class="inj-column-list">
        <label
          v-for="column in filteredColumns"
          :key="column.id"
          :draggable="!store.dirty && !store.busy"
          @dragstart="draggedColumn = column.id"
          @dragover.prevent
          @drop.prevent="dropColumn(column.id)"
          ><input
            type="checkbox"
            :checked="column.getIsVisible()"
            @change="column.toggleVisibility()"
          /><GripVertical class="inj-column-grip" /><span
            >{{ store.fieldMap[column.id]?.label
            }}<small>{{
              columnGroupLabel(store.fieldMap[column.id]?.group)
            }}</small></span
          ><button title="向前移动" @click="reorder(column.id, -1)">←</button
          ><button title="向后移动" @click="reorder(column.id, 1)">
            →
          </button></label
        >
      </div>
    </aside>
    <div
      ref="scroll"
      class="inj-grid-scroll"
      @scroll="rememberScroll"
      @copy="copy"
      @paste="paste"
    >
      <table
        class="inj-grid"
        :style="{ width: table.getTotalSize() + 38 + 'px' }"
      >
        <thead>
          <tr>
            <th class="inj-check-column">
              <input
                type="checkbox"
                aria-label="选择当前页"
                :checked="
                  selected.length === store.rows.length && !!store.rows.length
                "
                @change="
                  selected =
                    selected.length === store.rows.length
                      ? []
                      : store.rows.map((r) => r.id)
                "
              />
            </th>
            <th
              v-for="(column, index) in visible"
              :key="column.id"
              :style="cellStyle(index)"
            >
              <button
                class="inj-column-title"
                @click="sortBy(column.id, $event.shiftKey)"
              >
                {{ store.fieldMap[column.id]?.label }}
                <component
                  :is="
                    store.sort.find((s) => s.field === column.id)?.direction ===
                    'asc'
                      ? ArrowUp
                      : ArrowDown
                  "
                  v-if="store.sort.some((s) => s.field === column.id)"
                /></button
              ><button
                class="inj-column-filter"
                :title="'筛选' + store.fieldMap[column.id]?.label"
                :disabled="store.dirty || store.busy"
                @click="
                  columnFilter = {
                    op: 'and',
                    children: [{ field: column.id, op: 'eq', value: '' }],
                  }
                "
              >
                <Filter />
              </button>
              <div
                class="inj-resizer"
                @mousedown="
                  table
                    .getHeaderGroups()[0]
                    ?.headers.find((h) => h.id === column.id)
                    ?.getResizeHandler()($event)
                "
                @touchstart="
                  table
                    .getHeaderGroups()[0]
                    ?.headers.find((h) => h.id === column.id)
                    ?.getResizeHandler()($event)
                "
              />
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-if="virtualRows[0]?.start"
            :style="{ height: virtualRows[0]?.start + 'px' }"
          >
            <td :colspan="visible.length + 1" />
          </tr>
          <tr
            v-for="vr in virtualRows"
            :key="model[vr.index]!.id"
            :class="{
              'inj-selected-row':
                store.selectedId === model[vr.index]!.original.id,
            }"
          >
            <td class="inj-check-column">
              <input
                v-model="selected"
                type="checkbox"
                :value="model[vr.index]!.original.id"
                :aria-label="'选择第 ' + (vr.index + 1) + ' 行'"
              />
            </td>
            <td
              v-for="(column, ci) in visible"
              :key="column.id"
              :style="cellStyle(ci)"
              :data-cell="`${vr.index}:${ci}`"
              :tabindex="
                active.row === vr.index && active.column === ci ? 0 : -1
              "
              :class="{
                'inj-cell-range': inRange(vr.index, ci),
                'inj-cell-active':
                  active.row === vr.index && active.column === ci,
                'inj-cell-number': ['number', 'integer'].includes(
                  store.fieldMap[column.id]?.value_type || '',
                ),
                'inj-derived': !store.fieldMap[column.id]?.editable,
                'inj-negative':
                  column.id === 'delivery_slack_hours' &&
                  model[vr.index]!.original[column.id] < 0,
              }"
              :title="
                displayValue(
                  model[vr.index]!.original[column.id],
                  store.fieldMap[column.id],
                )
              "
              @click="focusCell(vr.index, ci, $event.shiftKey)"
              @keydown="keydown($event, model[vr.index]!.original, column.id)"
              @dblclick="
                ['mold_code', 'order_no'].includes(column.id)
                  ? store.select(model[vr.index]!.original.id, true)
                  : beginEdit(model[vr.index]!.original, column.id)
              "
            >
              <input
                v-if="
                  editing?.id === model[vr.index]!.original.id &&
                  editing?.field === column.id
                "
                v-model="editing.value"
                :disabled="store.busy"
                class="inj-cell-editor"
                :aria-label="store.fieldMap[column.id]?.label"
                @click.stop
              /><PlanCell
                v-else
                :value="model[vr.index]!.original[column.id]"
                :field="store.fieldMap[column.id]"
              />
            </td>
          </tr>
          <tr
            :style="{
              height:
                Math.max(
                  0,
                  virtual.getTotalSize() - (virtualRows.at(-1)?.end || 0),
                ) + 'px',
            }"
          >
            <td :colspan="visible.length + 1" />
          </tr>
        </tbody>
      </table>
      <div v-if="!store.rows.length" class="inj-empty">
        {{
          store.loading
            ? '正在读取计划…'
            : '当前条件没有需求。可清除筛选、导入计划或新增需求。'
        }}
      </div>
    </div>
    <div v-if="editing" class="inj-toolbar">
      <span>编辑 {{ store.fieldMap[editing.field]?.label }}</span
      ><button class="inj-primary" :disabled="store.busy" @click="commit">
        保存 Enter</button
      ><button @click="cancel">取消 Esc</button
      ><span class="inj-error-text">{{ editError }}</span>
    </div>
    <div class="inj-table-footer">
      <span
        >筛选合计：计划 {{ numberText(store.filteredSummary.planned_shots) }} ·
        已啤 {{ numberText(store.filteredSummary.completed_shots) }} · 欠数
        {{ numberText(store.filteredSummary.remaining_shots) }}</span
      ><span class="inj-spacer" /><button
        :disabled="store.cursor === 0 || store.dirty || store.busy"
        @click="
          store.cursor = Math.max(0, store.cursor - pageSize);
          store.loadTable();
        "
      >
        上一页</button
      ><span
        >{{ store.rows.length ? store.cursor + 1 : 0 }}–{{
          store.cursor + store.rows.length
        }}</span
      ><button
        :disabled="store.nextCursor === null || store.dirty || store.busy"
        @click="
          store.cursor = store.nextCursor!;
          store.loadTable();
        "
      >
        下一页
      </button>
    </div>
    <div v-if="columnFilter" class="inj-modal-backdrop">
      <section
        class="inj-modal inj-wide-modal"
        role="dialog"
        aria-modal="true"
        aria-label="列筛选"
        v-inj-dialog="{
          close: () => {
            columnFilter = null;
          },
          busy: store.busy,
        }"
      >
        <h2>列筛选</h2>
        <FilterGroup v-model="columnFilter" :fields="store.fields" />
        <div class="inj-actions">
          <button @click="columnFilter = null">取消</button
          ><button class="inj-primary" @click="applyColumnFilter">
            应用筛选
          </button>
        </div>
      </section>
    </div>
    <div
      v-if="selected.length"
      class="inj-toolbar"
      :inert="store.dirty || store.busy"
    >
      <strong>本页已选 {{ selectedSummary.count }} 条</strong
      ><span
        >计划 {{ numberText(selectedSummary.planned) }} / 欠数
        {{ numberText(selectedSummary.remaining) }}</span
      ><input
        v-if="canEdit"
        v-model="bulkValue"
        :placeholder="
          '统一填写：' +
          (store.fieldMap[visible[active.column]?.id || '']?.label || '选中列')
        "
      /><button v-if="canEdit" @click="fill">批量填入</button
      ><button
        v-if="canEdit"
        @click="
          store.mutate('/demands/enrich', {
            rows: selected.map((id) => ({ id })),
          })
        "
      >
        应用最新公共资料
      </button>
      <template v-if="canEdit && selected.length > 1"
        ><select v-model="groupMachine" aria-label="组批机台">
          <option value="">选择组批机台</option>
          <option v-for="m in store.machines" :key="m.id" :value="m.id">
            {{ m.code }} · {{ m.machine_a }}A
          </option></select
        ><button
          :disabled="!groupMachine || store.busy || store.dirty"
          @click="
            store.mutate('/schedule/group', {
              demand_ids: selected,
              machine_id: groupMachine,
            })
          "
        >
          合并为生产批次
        </button></template
      >
    </div>
    <div v-if="pendingPaste" class="inj-modal-backdrop">
      <section
        class="inj-modal"
        role="dialog"
        aria-modal="true"
        aria-label="粘贴预览"
        v-inj-dialog="{
          close: () => {
            pendingPaste = null;
            store.dirty = false;
          },
          busy: store.busy,
        }"
      >
        <h2>粘贴预览</h2>
        <p>
          {{ pendingPaste.count }} 行 → {{ pendingPaste.columns.join('、') }}
        </p>
        <p
          v-for="message in pendingPaste.errors.slice(0, 20)"
          :key="message"
          class="inj-error-text"
        >
          {{ message }}
        </p>
        <p v-if="!pendingPaste.errors.length">
          类型检查通过，将更新当前所示需求并重算排程。
        </p>
        <div class="inj-actions">
          <button
            @click="
              pendingPaste = null;
              store.dirty = false;
            "
          >
            取消</button
          ><button
            class="inj-primary"
            :disabled="!!pendingPaste.errors.length || store.busy"
            @click="applyPaste"
          >
            应用 {{ pendingPaste.count }} 行
          </button>
        </div>
      </section>
    </div>
  </section>
</template>
