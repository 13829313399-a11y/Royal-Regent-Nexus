<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { http, getApiErrorMessage } from "@/lib/http";
import PageControls from "../components/PageControls.vue";
interface Batch {
  id: string;
  status: string;
  source_sha256: string;
  started_at: string;
}
interface Row {
  id: string;
  entity_type: string;
  legacy_id: string;
  target_id: string;
  status: string;
  error_code: string;
  attempt_count: number;
}
interface Reconciliation {
  passed: boolean | null;
  expected_counts: Record<string, number>;
  actual_counts: Record<string, number>;
  issue_count: number;
}
const batches = ref<Batch[]>([]),
  page = ref(1),
  total = ref(0),
  error = ref(""),
  selected = ref(""),
  busy = ref(false);
const batch = ref<unknown>(),
  reconciliation = ref<Reconciliation>(),
  rows = ref<Row[]>([]),
  rowPage = ref(1),
  rowTotal = ref(0),
  status = ref("");
const counts = computed(() =>
  Array.from(
    new Set([
      ...Object.keys(reconciliation.value?.expected_counts ?? {}),
      ...Object.keys(reconciliation.value?.actual_counts ?? {}),
    ]),
  ),
);
const params = { factory_id: "huakang-a" };
async function load(value = 1) {
  try {
    const { data } = await http.get("/three-d-printing/migration-batches", {
      params: { ...params, page: value, page_size: 50 },
    });
    batches.value = data.items;
    total.value = data.total;
    page.value = value;
  } catch (e) {
    error.value = getApiErrorMessage(e);
  }
}
async function loadRows(value = 1) {
  try {
    const { data } = await http.get(
      `/three-d-printing/migration-batches/${selected.value}/rows`,
      {
        params: { ...params, page: value, page_size: 50, status: status.value },
      },
    );
    rows.value = data.items;
    rowTotal.value = data.total;
    rowPage.value = value;
  } catch (e) {
    error.value = getApiErrorMessage(e);
  }
}
async function inspect(id: string) {
  busy.value = true;
  error.value = "";
  try {
    selected.value = id;
    const [a, b] = await Promise.all([
      http.get(`/three-d-printing/migration-batches/${id}`, { params }),
      http.get(`/three-d-printing/migration-batches/${id}/reconciliation`, {
        params,
      }),
    ]);
    batch.value = a.data;
    reconciliation.value = b.data;
    await loadRows();
  } catch (e) {
    error.value = getApiErrorMessage(e);
  } finally {
    busy.value = false;
  }
}
function download(content: string, type: string, extension: string) {
  const url = URL.createObjectURL(new Blob(["\ufeff" + content], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `migration-${selected.value}.${extension}`;
  a.click();
  URL.revokeObjectURL(url);
}
function csv() {
  const cell = (value: unknown) =>
    `"${String(value ?? "")
      .replace(/^[=+@-]/, "'$&")
      .replaceAll('"', '""')}"`;
  download(
    [
      ["项目", "源数量", "目标数量", "结果"],
      ...counts.value.map((k) => [
        k,
        reconciliation.value?.expected_counts[k],
        reconciliation.value?.actual_counts[k],
        reconciliation.value?.expected_counts[k] ===
        reconciliation.value?.actual_counts[k]
          ? "一致"
          : "差异",
      ]),
    ]
      .map((r) => r.map(cell).join(","))
      .join("\r\n"),
    "text/csv",
    "csv",
  );
}
async function report() {
  busy.value = true;
  try {
    const all: Row[] = [];
    let current = 1;
    let count = 0;
    do {
      const { data } = await http.get(
        `/three-d-printing/migration-batches/${selected.value}/rows`,
        { params: { ...params, page: current, page_size: 100 } },
      );
      if (!data.items.length && all.length < data.total)
        throw new Error("批次正在变化，请稍后重新下载");
      all.push(...data.items);
      count = data.total;
      current++;
    } while (all.length < count);
    download(
      JSON.stringify(
        { batch: batch.value, reconciliation: reconciliation.value, rows: all },
        null,
        2,
      ),
      "application/json",
      "json",
    );
  } catch (e) {
    error.value = getApiErrorMessage(e);
  } finally {
    busy.value = false;
  }
}
onMounted(() => load());
</script>
<template>
  <section class="panel-card p-5">
    <h2 class="text-xl font-bold">历史数据迁移</h2>
    <p class="my-3 text-sm text-slate-500">
      管理员只读查看批次、对账及行级结果。此页面不会触发迁移。
    </p>
    <p role="alert" class="text-rose-700">{{ error }}</p>
    <PageControls :page="page" :total="total" @change="load" /><button
      v-for="item in batches"
      :key="item.id"
      class="block w-full border-b p-3 text-left"
      :disabled="busy"
      @click="inspect(item.id)"
    >
      {{ item.started_at }} · {{ item.status
      }}<small class="block break-all">{{ item.source_sha256 }}</small>
    </button>
    <p v-if="!batches.length" class="p-4 text-slate-500">暂无迁移批次</p>
    <div v-if="reconciliation" class="mt-6 space-y-4">
      <p
        class="rounded-lg p-3"
        :class="
          reconciliation.passed === true
            ? 'bg-emerald-50 text-emerald-800'
            : 'bg-amber-50 text-amber-900'
        "
      >
        {{
          reconciliation.passed === true
            ? "对账通过"
            : reconciliation.passed === false
              ? "对账有差异"
              : "尚未对账"
        }}
        · {{ reconciliation.issue_count }}项问题
      </p>
      <div class="flex gap-2">
        <button
          class="action-button secondary"
          :disabled="busy"
          @click="report"
        >
          下载完整报告 JSON</button
        ><button class="action-button secondary" @click="csv">
          下载数量对账 CSV
        </button>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>项目</th>
              <th>源数量</th>
              <th>目标数量</th>
              <th>结果</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="key in counts" :key="key">
              <td>{{ key }}</td>
              <td>{{ reconciliation.expected_counts[key] ?? "缺失" }}</td>
              <td>{{ reconciliation.actual_counts[key] ?? "缺失" }}</td>
              <td
                :class="
                  reconciliation.expected_counts[key] ===
                  reconciliation.actual_counts[key]
                    ? 'text-emerald-700'
                    : 'text-rose-700'
                "
              >
                {{
                  reconciliation.expected_counts[key] ===
                  reconciliation.actual_counts[key]
                    ? "一致"
                    : "差异"
                }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="flex gap-3">
        <h3 class="font-bold">行级结果与错误</h3>
        <select v-model="status" aria-label="迁移行状态" @change="loadRows()">
          <option value="">全部</option>
          <option value="failed">失败</option>
          <option value="conflict">冲突</option>
          <option value="reconciled">已对账</option>
        </select>
      </div>
      <PageControls :page="rowPage" :total="rowTotal" @change="loadRows" />
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>类型</th>
              <th>旧ID</th>
              <th>新ID</th>
              <th>状态</th>
              <th>错误</th>
              <th>尝试次数</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.id">
              <td>{{ row.entity_type }}</td>
              <td>{{ row.legacy_id }}</td>
              <td>{{ row.target_id }}</td>
              <td>{{ row.status }}</td>
              <td class="text-rose-700">{{ row.error_code }}</td>
              <td>{{ row.attempt_count }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>
