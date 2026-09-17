<script setup lang="ts">
import QuoteEditor from "../components/QuoteEditor.vue";
import { computed, onMounted, ref } from "vue";
import ProductPicker from "../components/ProductPicker.vue";
import PageControls from "../components/PageControls.vue";
import LegacyPrinterGrid from "../components/LegacyPrinterGrid.vue";
import LegacyDialog from "../components/LegacyDialog.vue";
import { useWorkspaceContext } from "../context";
import type {
  ThreeDDashboard,
  ThreeDProductionRecord,
} from "@/types/threeDPrinting";
const {
  dashboard,
  saving,
  canOperate,
  canReadAudit,
  canExport,
  recordForm,
  recordCostSnapshot,
  listPages,
  recordSearchAllDates,
  loadPage,
  dateFrom,
  dateTo,
  loadDashboard,
  todayText,
  chooseRecordProduct,
  resetRecordForm,
  editRecord,
  submitRecord,
  removeRecord,
  toggleDayOff,
  exportWorkbook,
  money,
  Save,
} = useWorkspaceContext();
const day = ref(todayText()),
  showForm = ref(false);
const keyword = ref(listPages.records!.q);
const searchAllDates = ref(true);
const searching = computed(
  () => recordSearchAllDates.value || !!listPages.records!.q,
);
const stats = computed(
  () =>
    (dashboard.value?.summary.legacyDisplay ||
      dashboard.value?.summary ||
      {}) as ThreeDDashboard["summary"],
);
async function loadDay() {
  recordSearchAllDates.value = false;
  listPages.records!.q = "";
  listPages.records!.page = 1;
  keyword.value = "";
  dateFrom.value = day.value;
  dateTo.value = day.value;
  await loadDashboard();
}
async function searchRecords() {
  listPages.records!.q = keyword.value.trim();
  recordSearchAllDates.value = searchAllDates.value;
  dateFrom.value = day.value;
  dateTo.value = day.value;
  await loadPage("records", 1);
}
onMounted(() =>
  recordSearchAllDates.value ? loadPage("records", 1) : loadDay(),
);
function add() {
  resetRecordForm();
  recordForm.business_date = day.value;
  showForm.value = true;
}
function edit(r: ThreeDProductionRecord) {
  editRecord(r);
  recordForm.history_only_correction = !!r.legacy_id;
  showForm.value = true;
}
async function save() {
  recordForm.reason ||= recordForm.id ? "编辑生产记录" : "新增生产记录";
  if (await submitRecord()) showForm.value = false;
}
async function dayOff() {
  recordForm.business_date = day.value;
  await toggleDayOff();
}
const statusNames: Record<string, string> = {
  running: "生产",
  done: "完成",
  fault: "故障",
  idle: "空闲",
};
const amount = (r: ThreeDProductionRecord, key: string) =>
  r.frozen_totals[key] == null ? "—" : money(r.frozen_totals[key]);
const image = (r: ThreeDProductionRecord) =>
  r.product_image_url ||
  dashboard.value?.products.find((p) => p.id === r.product_id)?.image_url;
const time = (s: string) =>
  s
    ? new Date(s).toLocaleTimeString("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
</script>
<template>
  <section v-if="dashboard" class="space-y-5">
    <form class="legacy-toolbar" @submit.prevent="loadDay">
      <strong>日期：</strong
      ><input v-model="day" type="date" aria-label="生产日期" required /><button
        class="action-button"
      >
        加载</button
      ><button
        v-if="canOperate"
        type="button"
        class="action-button green"
        @click="add"
      >
        + 添加记录</button
      ><button
        v-if="canExport"
        type="button"
        class="action-button secondary"
        @click="exportWorkbook"
      >
        {{ searching ? "导出所选日期 Excel" : "导出 Excel" }}</button
      ><button
        v-if="canOperate"
        type="button"
        class="action-button secondary ml-auto"
        @click="dayOff"
      >
        {{
          dashboard.day_off_dates.includes(day) ? "恢复生产日" : "标记为休息日"
        }}
      </button>
    </form>
    <form
      class="legacy-toolbar"
      aria-label="打印记录搜索"
      @submit.prevent="searchRecords"
    >
      <input
        v-model="keyword"
        type="search"
        aria-label="打印记录产品关键词"
        placeholder="输入产品关键词，查找打印记录"
        maxlength="200"
        class="min-w-0 flex-1"
      />
      <label class="flex items-center gap-2"
        ><input v-model="searchAllDates" type="checkbox" />搜索全部历史</label
      >
      <button class="action-button" :disabled="listPages.records!.busy">
        搜索记录
      </button>
      <button
        v-if="searching"
        type="button"
        class="action-button secondary"
        @click="loadDay"
      >
        返回当日记录
      </button>
      <span class="basis-full text-sm text-muted-foreground"
        >支持产品名称、打印文件名关键词；取消“搜索全部历史”可限定上方所选日期。</span
      >
    </form>
    <LegacyPrinterGrid v-if="!searching" />
    <div class="panel-card">
      <div class="legacy-panel-head">
        <h2>
          <template v-if="searching"
            >{{ recordSearchAllDates ? "全部历史" : day }} · 打印记录<span
              v-if="listPages.records!.q"
            >
              · {{ listPages.records!.q }}</span
            ></template
          >
          <template v-else
            >{{ day
            }}{{
              dashboard.day_off_dates.includes(day) ? "（休息日）" : ""
            }}</template
          >
        </h2>
        <span v-if="!searching"
          >产值：{{ money(stats.revenue) }} | 支出：{{
            money(stats.totalCost)
          }}
          | 结余：{{ money(stats.balance) }}</span
        >
        <span v-else>找到 {{ listPages.records!.total }} 条记录</span>
      </div>
      <PageControls
        v-if="listPages.records!.total > 50"
        :page="listPages.records!.page"
        :total="listPages.records!.total"
        :busy="listPages.records!.busy"
        @change="loadPage('records', $event)"
      />
      <div class="table-wrap">
        <table class="legacy-record-table">
          <thead>
            <tr>
              <th>#</th>
              <th>生产日期</th>
              <th>机台</th>
              <th>机型</th>
              <th>状态</th>
              <th>产品</th>
              <th>图片</th>
              <th>客户</th>
              <th>材料</th>
              <th>料重(g)</th>
              <th>数量</th>
              <th>耗时(h)</th>
              <th>材料成本</th>
              <th>设计费</th>
              <th>报价</th>
              <th>备注</th>
              <th>入库时间</th>
              <th v-if="canOperate">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(r, index) in dashboard.records" :key="r.id">
              <td>{{ (listPages.records!.page - 1) * 50 + index + 1 }}</td>
              <td class="whitespace-nowrap">{{ r.business_date }}</td>
              <td>#{{ r.machine_no }}</td>
              <td>
                {{
                  dashboard.printers.find((p) => p.machine_no === r.machine_no)
                    ?.model || "Bambu"
                }}
              </td>
              <td>
                <span class="tag">{{ statusNames[r.status] || r.status }}</span>
              </td>
              <td class="record-product">
                <span v-if="r.auto_record" class="tag auto">自动</span
                >{{ r.product_name || "—" }}
              </td>
              <td>
                <a
                  v-if="image(r)"
                  :href="image(r)"
                  target="_blank"
                  rel="noopener"
                  ><img
                    :src="image(r)"
                    :alt="r.product_name"
                    loading="lazy"
                    class="record-image"
                /></a>
              </td>
              <td>{{ r.customer || "—" }}</td>
              <td>{{ r.material_name || "—" }}</td>
              <td>{{ r.weight_g || "—" }}</td>
              <td>{{ r.quantity }}</td>
              <td>{{ r.duration_hours || "—" }}</td>
              <td>{{ amount(r, "materialCost") }}</td>
              <td>{{ money(r.design_fee) }}</td>
              <td>{{ amount(r, "revenue") }}</td>
              <td class="record-remark">{{ r.remark }}</td>
              <td>{{ time(r.created_at || r.print_start_at) }}</td>
              <td v-if="canOperate">
                <div class="row-actions">
                  <button @click="edit(r)">编辑</button
                  ><button class="danger" @click="removeRecord(r)">删除</button>
                </div>
              </td>
            </tr>
            <tr v-if="!dashboard.records.length">
              <td colspan="18" class="p-8 text-center">
                {{
                  searching
                    ? "没有找到匹配记录，请更换关键词或搜索全部历史。"
                    : "暂无记录，点击“+ 添加记录”开始"
                }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <PageControls
        :page="listPages.records!.page"
        :total="listPages.records!.total"
        :busy="listPages.records!.busy"
        @change="loadPage('records', $event)"
      />
    </div>
    <LegacyDialog
      v-if="showForm"
      :title="recordForm.id ? '编辑生产记录' : '添加生产记录'"
      @close="showForm = false"
    >
      <form v-if="canOperate" class="panel-card p-5" @submit.prevent="save">
        <div class="section-heading">
          <div>
            <h2>{{ recordForm.id ? "编辑生产记录" : "新增生产记录" }}</h2>
            <p>选择产品后自动带出材料、重量、时间与报价，可继续调整。</p>
          </div>
          <button
            v-if="recordForm.id"
            class="action-button secondary"
            type="button"
            @click="showForm = false"
          >
            取消编辑
          </button>
        </div>
        <div class="form-grid">
          <label
            >日期<input v-model="recordForm.business_date" required type="date"
          /></label>
          <label
            >机号<input
              v-model.number="recordForm.machine_no"
              required
              min="1"
              max="100"
              type="number"
          /></label>
          <label
            >状态<select v-model="recordForm.status">
              <option value="running">生产</option>
              <option value="done">已完成</option>
              <option value="idle">空闲</option>
              <option value="fault">故障</option>
            </select></label
          >
          <label
            >产品<ProductPicker
              v-model="recordForm.product_id"
              @selected="chooseRecordProduct"
          /></label>
          <label
            >产品名称<input v-model="recordForm.product_name" maxlength="255"
          /></label>
          <label
            >材料<input v-model="recordForm.material_name" maxlength="255"
          /></label>
          <label
            >单件重量(g)<input
              v-model.number="recordForm.weight_g"
              min="0"
              step="0.01"
              type="number"
          /></label>
          <label
            >数量<input
              v-model.number="recordForm.quantity"
              min="0"
              type="number"
          /></label>
          <label
            >单件时间(h)<input
              v-model.number="recordForm.duration_hours"
              min="0"
              step="0.01"
              type="number"
          /></label>
          <label
            >设计费<input
              v-model.number="recordForm.design_fee"
              min="0"
              step="0.01"
              type="number"
          /></label>
          <label
            >客户<input v-model="recordForm.customer" maxlength="255"
          /></label>
          <QuoteEditor
            v-model="recordForm.quoted_price"
            :existing="!!recordForm.id"
            :settings="dashboard?.settings"
            :materials="dashboard?.materials || []"
            :snapshot="recordCostSnapshot"
            :input="{
              material: recordForm.material_name,
              weight: recordForm.weight_g,
              hours: recordForm.duration_hours,
              quantity: recordForm.quantity,
              designFee: recordForm.design_fee,
            }"
          />
          <label class="md:col-span-2 xl:col-span-4"
            >备注<input v-model="recordForm.remark" maxlength="4000"
          /></label>
          <label class="md:col-span-2"
            >备注说明<input
              v-model="recordForm.reason"
              :required="recordForm.allow_negative_stock"
              maxlength="1000"
          /></label>
          <label v-if="canReadAudit"
            ><input
              v-model="recordForm.allow_negative_stock"
              type="checkbox"
            />主管明确批准本次负库存</label
          >
        </div>
        <button class="action-button mt-4" type="submit" :disabled="saving">
          <Save class="size-4" />{{ saving ? "保存中…" : "保存记录" }}</button
        ><button
          class="action-button secondary mt-4 ml-2"
          type="button"
          :disabled="saving"
          @click="toggleDayOff"
        >
          设置/恢复当日休息日
        </button>
      </form>
    </LegacyDialog>
  </section>
</template>
