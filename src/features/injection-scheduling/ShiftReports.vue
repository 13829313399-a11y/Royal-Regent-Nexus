<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { injectionApi as api } from '@/api/injectionScheduling';
import { useInjectionStore } from '@/stores/injectionScheduling';
import {
  dateText,
  numberText,
  statusText,
  productionShift,
  type DataRow,
} from './types';
defineProps<{ canReport: boolean; selectedRunId?: string }>();
const store = useInjectionStore(),
  date = ref(productionShift(store.settings).date),
  shift = ref(productionShift(store.settings).shift),
  term = ref(''),
  onlyUnreported = ref(false),
  onlyRunning = ref(false);
const reports = ref<DataRow[]>([]),
  allRuns = ref<DataRow[]>([]),
  drafts = ref<Record<string, string>>({}),
  outcomes = ref<Record<string, string>>({}),
  units = ref<Record<string, string>>({}),
  scraps = ref<Record<string, string>>({}),
  revisionAtEdit = ref<Record<string, number>>({}),
  pasteStart = ref(0),
  pastePreview = ref<string[] | null>(null);
const reportByRun = computed(() =>
  Object.fromEntries(
    reports.value
      .filter(
        (r) => r.shift_code === shift.value && r.segment_key === 'default',
      )
      .map((r) => [r.run_id, r]),
  ),
);
const rows = computed(() =>
  allRuns.value.filter(
    (r) =>
      r.actual_start_at &&
      (!onlyRunning.value || r.status === 'RUNNING') &&
      (!onlyUnreported.value || !reportByRun.value[r.id]) &&
      (!term.value ||
        [r.machine_code, r.mold_code, r.order_no, r.color_name]
          .join(' ')
          .includes(term.value)),
  ),
);
let generation = 0;
async function load() {
  if (!store.factory) return;
  const id = ++generation;
  try {
    const [list, timeline] = await Promise.all([
      api.get('/shift-reports', {
        factory_id: store.factory,
        from_date: date.value,
        to_date: date.value,
      }),
      api.get('/timeline', {
        factory_id: store.factory,
        include_finished: true,
      }),
    ]);
    if (id !== generation) return;
    reports.value = list.rows;
    allRuns.value = timeline.runs;
  } catch (e) {
    store.showError(e);
  }
}
watch(
  () => [store.factory, store.revision, date.value],
  () => {
    void load();
  },
  { immediate: true },
);
watch(
  () => store.factory,
  () => {
    drafts.value = {};
    outcomes.value = {};
    units.value = {};
    scraps.value = {};
    revisionAtEdit.value = {};
  },
);
function draft(id: string, value: string) {
  if (!(id in drafts.value))
    revisionAtEdit.value[id] = reportByRun.value[id]?.revision || 0;
  drafts.value[id] = value;
  outcomes.value[id] = '待保存';
  store.dirty = true;
}
function cancelRun(id: string) {
  delete drafts.value[id];
  delete units.value[id];
  delete scraps.value[id];
  delete revisionAtEdit.value[id];
  delete outcomes.value[id];
  store.dirty = Object.keys(drafts.value).length > 0;
}
function payload(run: DataRow) {
  const raw = drafts.value[run.id];
  if (raw == null) return null;
  if (raw.trim() === '')
    throw new Error('请输入本班累计物理啤数，或取消本次输入；已报零请填写 0');
  const physical = Number(raw);
  if (!Number.isInteger(physical) || physical < 0)
    throw new Error('请输入非负整数；空白表示未填写，0 表示已报零');
  return {
    run_id: run.id,
    production_date: date.value,
    shift_code: shift.value,
    segment_key: 'default',
    physical_shots: physical,
    report_revision: revisionAtEdit.value[run.id] ?? 0,
    good_units: units.value[run.id]
      ? JSON.parse(units.value[run.id]!)
      : reportByRun.value[run.id]?.good_units || {},
    scrap_units: scraps.value[run.id]
      ? JSON.parse(scraps.value[run.id]!)
      : reportByRun.value[run.id]?.scrap_units || {},
  };
}
async function save(list: DataRow[]) {
  const items: any[] = [],
    ids: string[] = [];
  for (const run of list) {
    try {
      const p = payload(run);
      if (p) {
        items.push(p);
        ids.push(run.id);
      }
    } catch (e) {
      outcomes.value[run.id] = String(e);
    }
  }
  if (!items.length) return;
  const response = await store.mutate('/shift-reports/bulk', { rows: items });
  if (response) {
    response.results.forEach((r: any) => {
      const id = ids[r.index]!;
      outcomes.value[id] = r.ok ? '已保存' : String(r.error);
      if (r.ok) {
        delete drafts.value[id];
        delete units.value[id];
        delete scraps.value[id];
        delete revisionAtEdit.value[id];
      }
    });
    store.dirty = Object.keys(drafts.value).length > 0;
    await load();
  }
}
function products(run: DataRow): string[] {
  return [
    ...new Set<string>((run.products || []).map((p: any) => p.product_code)),
  ];
}
function unitValue(run: DataRow, product: string, kind: 'good' | 'scrap') {
  const raw = (kind === 'good' ? units : scraps).value[run.id];
  return (
    (raw
      ? JSON.parse(raw)
      : reportByRun.value[run.id]?.[kind + '_units'] || {})[product] ?? ''
  );
}
function setUnit(
  run: DataRow,
  product: string,
  kind: 'good' | 'scrap',
  value: string,
) {
  const target = kind === 'good' ? units : scraps;
  const values = target.value[run.id]
    ? JSON.parse(target.value[run.id]!)
    : { ...(reportByRun.value[run.id]?.[kind + '_units'] || {}) };
  if (value === '') delete values[product];
  else values[product] = Number(value);
  target.value[run.id] = JSON.stringify(values);
  draft(
    run.id,
    drafts.value[run.id] ??
      String(reportByRun.value[run.id]?.physical_shots ?? ''),
  );
}
function paste(event: ClipboardEvent, run: DataRow) {
  event.preventDefault();
  pasteStart.value = rows.value.findIndex((r) => r.id === run.id);
  pastePreview.value = (event.clipboardData?.getData('text/plain') || '')
    .replace(/\r/g, '')
    .replace(/\n$/, '')
    .split('\n')
    .map((s) => s.split('\t')[0] || '');
}
function applyPaste() {
  pastePreview.value?.forEach((value, i) => {
    if (rows.value[i + pasteStart.value])
      draft(rows.value[i + pasteStart.value]!.id, value);
  });
  pastePreview.value = null;
}
</script>
<template>
  <section class="inj-reports">
    <div class="inj-toolbar">
      <input
        v-model="date"
        type="date"
        aria-label="生产日期"
        :disabled="Object.keys(drafts).length > 0"
      /><select
        v-model="shift"
        aria-label="生产班次"
        :disabled="Object.keys(drafts).length > 0"
      >
        <option value="DAY">白班</option>
        <option value="NIGHT">夜班</option></select
      ><input
        v-model="term"
        placeholder="机号 / 模号 / 单号"
        aria-label="报工查找"
      /><label><input v-model="onlyRunning" type="checkbox" />只看在产</label
      ><label><input v-model="onlyUnreported" type="checkbox" />只看未报</label
      ><span class="inj-spacer" /><button
        v-if="canReport"
        :disabled="store.busy"
        class="inj-primary"
        @click="save(rows)"
      >
        保存已填报数</button
      ><button
        v-if="Object.keys(drafts).length"
        @click="
          drafts = {};
          units = {};
          scraps = {};
          revisionAtEdit = {};
          outcomes = {};
          store.dirty = false;
        "
      >
        取消本次输入
      </button>
    </div>
    <p class="inj-help">
      生产日期以班次开始日归属。白班 {{ store.settings.day_start }}–{{
        store.settings.night_start
      }}；夜班 {{ store.settings.night_start }}–次日
      {{ store.settings.day_start }}。填写本班累计物理啤数，修改后替换原值。
    </p>
    <div class="inj-grid-scroll">
      <table class="inj-report-grid">
        <thead>
          <tr>
            <th>机号 / 状态</th>
            <th>模号 / 订单</th>
            <th>颜色 / 材料</th>
            <th>本班累计啤数</th>
            <th>批次总物理啤数</th>
            <th>保存状态 / 操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="run in rows"
            :key="run.id"
            :class="{ 'inj-selected-row': selectedRunId === run.id }"
          >
            <td>
              <strong>{{
                run.machine_code ||
                store.machines.find((m) => m.id === run.machine_id)?.code
              }}</strong
              ><small>{{ statusText[run.status] || run.status }}</small>
            </td>
            <td>
              <button
                class="inj-link"
                @click="store.select(run.demand_ids[0], true)"
              >
                {{ run.mold_code || run.snapshot?.mold_code }}</button
              ><small
                >{{ run.order_no || run.snapshot?.order_no }}
                <span v-if="run.demand_ids?.length > 1"
                  >等 {{ run.demand_ids.length }} 单</span
                ></small
              >
            </td>
            <td>
              {{ run.color_name || run.snapshot?.color_name
              }}<small>{{
                run.material_raw || run.snapshot?.material_raw
              }}</small>
            </td>
            <td>
              <input
                :value="
                  drafts[run.id] ?? reportByRun[run.id]?.physical_shots ?? ''
                "
                :disabled="!canReport || store.busy"
                inputmode="numeric"
                :aria-label="(run.machine_code || '机台') + '累计啤数'"
                :placeholder="reportByRun[run.id] ? '已报' : '未报'"
                @input="
                  draft(run.id, ($event.target as HTMLInputElement).value)
                "
                @keydown.enter="save([run])"
                @keydown.esc="cancelRun(run.id)"
                @paste="paste($event, run)"
              />
              <details
                v-if="
                  run.allocation_mode === 'CO_OUTPUT_UNITS' ||
                  run.snapshot?.allocation_mode === 'CO_OUTPUT_UNITS'
                "
              >
                <summary>同啤良品分配</summary>
                <p class="inj-muted">
                  各产物的本班累计良品 /
                  废品件数。良品留空按物理啤数和出件率计算；同一产物只填写一次。
                </p>
                <div
                  v-for="product in products(run)"
                  :key="product"
                  class="inj-product-report"
                >
                  <strong>{{ product }}</strong>
                  <label
                    >良品<input
                      type="number"
                      min="0"
                      step="1"
                      :disabled="!canReport || store.busy"
                      :value="unitValue(run, product, 'good')"
                      placeholder="理论产出"
                      @input="
                        setUnit(
                          run,
                          product,
                          'good',
                          ($event.target as HTMLInputElement).value,
                        )
                      "
                  /></label>
                  <label
                    >废品<input
                      type="number"
                      min="0"
                      step="1"
                      :disabled="!canReport || store.busy"
                      :value="unitValue(run, product, 'scrap')"
                      placeholder="0"
                      @input="
                        setUnit(
                          run,
                          product,
                          'scrap',
                          ($event.target as HTMLInputElement).value,
                        )
                      "
                  /></label>
                </div>
              </details>
            </td>
            <td>
              {{ numberText(run.physical_shots)
              }}<small>开工 {{ dateText(run.actual_start_at) }}</small>
            </td>
            <td>
              <span
                :class="{
                  'inj-error-text':
                    outcomes[run.id] &&
                    !['待保存', '已保存'].includes(outcomes[run.id]!),
                }"
                >{{
                  outcomes[run.id] ||
                  (reportByRun[run.id]
                    ? '已报 ' + numberText(reportByRun[run.id]!.physical_shots)
                    : '未报')
                }}</span
              ><button
                v-if="canReport && drafts[run.id] != null"
                :disabled="store.busy"
                @click="save([run])"
              >
                保存
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!rows.length" class="inj-empty">
        没有符合条件的已开工批次。请先在机台看板或详情中开工，再填写报数。
      </div>
    </div>
    <div v-if="pastePreview" class="inj-modal-backdrop">
      <section
        class="inj-modal"
        role="dialog"
        aria-modal="true"
        aria-label="报数粘贴预览"
      >
        <h2>报数粘贴预览</h2>
        <p>
          粘贴 {{ pastePreview.length }} 行第一列，从当前单元格向下对应到
          {{ rows.length }} 个批次。
        </p>
        <p
          v-if="pastePreview.length > rows.length - pasteStart"
          class="inj-error-text"
        >
          行数超过矩阵，无法应用。
        </p>
        <ol>
          <li v-for="(value, i) in pastePreview.slice(0, 12)" :key="i">
            {{ rows[i + pasteStart]?.machine_code }} /
            {{ rows[i + pasteStart]?.mold_code }} →
            {{ value || '空白（不保存）' }}
          </li>
        </ol>
        <div class="inj-actions">
          <button @click="pastePreview = null">取消</button
          ><button
            class="inj-primary"
            :disabled="pastePreview.length > rows.length - pasteStart"
            @click="applyPaste"
          >
            填入并逐行检查
          </button>
        </div>
      </section>
    </div>
  </section>
</template>
