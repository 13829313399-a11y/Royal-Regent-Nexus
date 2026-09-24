<script setup lang="ts">
import RecordImagePicker from "../components/RecordImagePicker.vue";
import QuoteEditor from "../components/QuoteEditor.vue";
import { computed, onMounted, ref } from "vue";
import ProductPicker from "../components/ProductPicker.vue";
import PageControls from "../components/PageControls.vue";
import LegacyPrinterGrid from "../components/LegacyPrinterGrid.vue";
import LegacyDialog from "../components/LegacyDialog.vue";
import TdpButton from '../components/TdpButton.vue';
import { ArrowLeft, CalendarDays, CircleAlert, CircleCheck, Download, Moon, Pencil, Play, Search, Trash2, Plus } from '@lucide/vue';
import { useWorkspaceContext } from "../context";
import type {
  ThreeDDashboard,
  ThreeDProductionRecord,
} from "@/types/threeDPrinting";
const {
  dashboard,
  saving,
  canOperate,
  canUploadImage,
  errorMessage,
  pendingRecordImage,
  recordImageUrl,
  recordProductImageUrl,
  recordImageRetry,
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
const loadingDay = ref(false);
const imagePicker = ref<InstanceType<typeof RecordImagePicker>>();
function closeForm() { if (!saving.value) showForm.value = false; }
function afterFormClose() { if (!showForm.value) pendingRecordImage.value = null; }
const displayedRecordImage = computed(() => recordImageUrl.value || (recordForm.product_id ? recordProductImageUrl.value || dashboard.value?.products.find(p => p.id === recordForm.product_id)?.image_url || "" : ""));
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
  if (loadingDay.value) return;
  loadingDay.value = true;
  recordSearchAllDates.value = false;
  listPages.records!.q = "";
  listPages.records!.page = 1;
  keyword.value = "";
  dateFrom.value = day.value;
  dateTo.value = day.value;
  try { await loadDashboard(); }
  finally { loadingDay.value = false; }
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
const recordStatusIcons = { running: Play, done: CircleCheck, fault: CircleAlert, idle: Moon };
const amount = (r: ThreeDProductionRecord, key: string) =>
  r.frozen_totals[key] == null ? "—" : money(r.frozen_totals[key]);
const image = (r: ThreeDProductionRecord) =>
  r.record_image_url ||
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
    <form class="legacy-toolbar tdp-record-toolbar" @submit.prevent="loadDay">
      <strong>日期：</strong
      ><input v-model="day" type="date" aria-label="生产日期" required /><TdpButton tone="soft" type="submit" :busy="loadingDay">
        <template #icon><CalendarDays :size="16" /></template>{{ loadingDay ? '加载中…' : '加载' }}
      </TdpButton><TdpButton
        v-if="canOperate"
        tone="primary"
        @click="add"
      >
        <template #icon><Plus :size="16" /></template>添加记录</TdpButton><TdpButton
        v-if="canExport"
        tone="secondary"
        :busy="saving"
        @click="exportWorkbook"
      >
        <template #icon><Download :size="16" /></template>{{ searching ? "导出所选日期 Excel" : "导出 Excel" }}</TdpButton><TdpButton
        v-if="canOperate"
        tone="secondary"
        class="ml-auto"
        :busy="saving"
        @click="dayOff"
      >
        <template #icon><Moon :size="16" /></template>
        {{
          dashboard.day_off_dates.includes(day) ? "恢复生产日" : "标记为休息日"
        }}
      </TdpButton>
    </form>
    <form
      class="legacy-toolbar"
      aria-label="打印记录搜索"
      @submit.prevent="searchRecords"
    >
      <div class="tdp-search-field"><Search :size="16" aria-hidden="true" /><input
        v-model="keyword"
        type="search"
        aria-label="打印记录产品关键词"
        placeholder="输入产品关键词，查找打印记录"
        maxlength="200"
        class="min-w-0 flex-1"
      /></div>
      <label class="tdp-search-scope"
        ><input v-model="searchAllDates" type="checkbox" />搜索全部历史</label
      >
      <TdpButton tone="soft" type="submit" :busy="listPages.records!.busy">
        <template #icon><Search :size="16" /></template>{{ listPages.records!.busy ? '查询中…' : '搜索记录' }}
      </TdpButton>
      <TdpButton
        v-if="searching"
        tone="secondary"
        :busy="loadingDay"
        @click="loadDay"
      >
        <template #icon><ArrowLeft :size="16" /></template>返回当日记录
      </TdpButton>
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
                <span class="tag tdp-record-status" :class="`tdp-record-status--${r.status}`">
                  <component :is="recordStatusIcons[r.status as keyof typeof recordStatusIcons] || CircleAlert" :size="13" aria-hidden="true" />{{ statusNames[r.status] || r.status }}
                </span>
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
                  <button type="button" @click="edit(r)"><Pencil :size="13" aria-hidden="true" />编辑</button
                  ><button type="button" class="danger" @click="removeRecord(r)"><Trash2 :size="13" aria-hidden="true" />删除</button>
                </div>
              </td>
            </tr>
            <tr v-if="!dashboard.records.length">
              <td :colspan="canOperate ? 18 : 17" class="p-8 text-center">
                {{
                  searching
                    ? "没有找到匹配记录，请更换关键词或搜索全部历史。"
                    : "暂无记录，点击“添加记录”开始"
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
      class="record-editor-dialog"
      :open="showForm"
      :title="recordForm.id ? '编辑生产记录' : '添加生产记录'"
      @close="closeForm" @after-close="afterFormClose" @paste="imagePicker?.pasteImage($event)"
    >
      <form v-if="canOperate" class="record-editor" @submit.prevent="save">
        <div class="record-editor-content">
          <p class="editor-intro">填写生产信息，粘贴现场图片，报价自动计算。</p>
          <p v-if="errorMessage" class="editor-error" role="alert">{{ errorMessage }}</p>
          <fieldset :disabled="saving" class="record-editor-fields">
            <div class="record-top-grid">
              <div class="record-main-fields">
                <section class="record-form-section" aria-label="生产信息">
                  <h3>生产信息</h3>
                  <div class="record-fields three-columns">
                    <label>日期<input v-model="recordForm.business_date" required type="date" /></label>
                    <label>机号<input v-model.number="recordForm.machine_no" required min="1" max="100" type="number" /></label>
                    <label>状态<select v-model="recordForm.status"><option value="running">生产</option><option value="done">已完成</option><option value="idle">空闲</option><option value="fault">故障</option></select></label>
                  </div>
                </section>
                <section class="record-form-section" aria-label="产品与用料">
                  <h3>产品与用料</h3>
                  <div class="record-fields">
                    <div class="full-width product-picker-field"><span>关联产品</span><ProductPicker v-model="recordForm.product_id" @selected="chooseRecordProduct" /></div>
                    <label>产品名称<input v-model="recordForm.product_name" maxlength="255" placeholder="输入本次打印的产品" /></label>
                    <label>客户<input v-model="recordForm.customer" maxlength="255" placeholder="选填" /></label>
                    <label class="full-width">材料<input v-model="recordForm.material_name" list="record-material-options" maxlength="255" placeholder="选择已登记材料或输入名称" /></label>
                    <datalist id="record-material-options"><option v-for="material in dashboard?.materials || []" :key="material.id" :value="material.name">{{ material.price_per_kg }} 元/kg</option></datalist>
                  </div>
                  <div class="record-fields three-columns measures">
                    <label>单件重量(g)<input v-model.number="recordForm.weight_g" min="0" step="0.01" type="number" /></label>
                    <label>单件时间(h)<input v-model.number="recordForm.duration_hours" min="0" step="0.01" type="number" /></label>
                    <label>数量<input v-model.number="recordForm.quantity" min="0" type="number" /></label>
                  </div>
                </section>
              </div>
              <RecordImagePicker ref="imagePicker" v-model="pendingRecordImage" :existing-url="displayedRecordImage"
                :inherited="!recordImageUrl" :allowed="canUploadImage" :disabled="saving || !!recordImageRetry" />
            </div>
            <section class="record-form-section record-pricing" aria-label="费用与报价">
              <div class="pricing-header"><h3>费用与报价</h3><label>设计费（元）<input v-model.number="recordForm.design_fee" min="0" step="0.01" type="number" /></label></div>
              <QuoteEditor v-model="recordForm.quoted_price" :existing="!!recordForm.id" :settings="dashboard?.settings" :materials="dashboard?.materials || []" :snapshot="recordCostSnapshot"
                :input="{ material: recordForm.material_name, weight: recordForm.weight_g, hours: recordForm.duration_hours, quantity: recordForm.quantity, designFee: recordForm.design_fee }" />
            </section>
            <section class="record-form-section" aria-label="补充信息">
              <h3>补充信息</h3>
              <label>备注<textarea v-model="recordForm.remark" maxlength="4000" rows="2" placeholder="记录工艺要求、异常情况或交接事项（选填）" /></label>
              <details class="record-additional"><summary>修改说明与库存选项</summary>
                <label>备注说明<input v-model="recordForm.reason" :required="recordForm.allow_negative_stock" maxlength="1000" /></label>
                <label v-if="canReadAudit" class="stock-option"><input v-model="recordForm.allow_negative_stock" type="checkbox" />主管明确批准本次负库存</label>
              </details>
            </section>
          </fieldset>
        </div>
        <footer class="record-editor-footer">
          <span>{{ pendingRecordImage ? '1 张图片待上传，保存后生效' : '确认信息后保存本条生产记录' }}</span>
          <TdpButton tone="secondary" :disabled="saving" @click="closeForm">取消</TdpButton>
          <TdpButton tone="primary" type="submit" :busy="saving"><template #icon><Save class="size-4" /></template>{{ saving ? '保存中…' : '保存记录' }}</TdpButton>
        </footer>
      </form>
    </LegacyDialog>
  </section>
</template>
<style>
.record-editor-dialog.legacy-dialog { width:min(1040px,96vw); max-height:92dvh; overflow:hidden; }
.record-editor-dialog.legacy-dialog[open] { display:flex; flex-direction:column; }
.record-editor-dialog > header { flex-shrink:0; padding:18px 24px; background:var(--card); }
.record-editor-dialog .legacy-dialog-body { display:flex; flex-direction:column; min-height:0; padding:0; overflow:hidden; }
.record-editor { display:flex; flex-direction:column; min-height:0; }
.record-editor-content { padding:22px 24px 24px; overflow-y:auto; min-height:0; }
.record-editor .editor-intro { color:var(--muted-foreground); font-size:13px; margin:0 0 20px; }
.record-editor .editor-error { color:var(--destructive); background:color-mix(in oklch,var(--destructive) 7%,var(--card)); border-radius:8px; padding:12px; margin-bottom:16px; font-size:13px; }
.record-editor-fields { min-width:0; border:0; padding:0; margin:0; }
.record-top-grid { display:grid; grid-template-columns:minmax(0,1.7fr) minmax(250px,1fr); gap:24px; align-items:start; }
.record-form-section h3 { font-size:14px; font-weight:650; color:var(--foreground); margin:0 0 14px; }
.record-form-section + .record-form-section { margin-top:22px; }
.record-fields { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }
.record-fields.three-columns { grid-template-columns:repeat(3,minmax(0,1fr)); }
.record-fields .full-width { grid-column:1/-1; }
.record-fields .product-picker-field { font-size:12px; font-weight:600; color:var(--muted-foreground); }
.record-fields .product-picker { margin-top:6px; }
.record-fields label { min-width:0; }
.record-editor input, .record-editor select { min-width:0; height:40px; }
.record-fields.measures { margin-top:14px; }
.record-pricing { border-top:1px solid var(--border); margin-top:24px; padding-top:20px; }
.pricing-header { display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:12px; }
.pricing-header h3 { margin:0; }
.pricing-header label { display:flex; align-items:center; gap:10px; }
.pricing-header input { width:112px; margin:0; }
.record-editor textarea { display:block; width:100%; margin-top:6px; padding:10px 12px; border:1px solid var(--input); background:var(--card); border-radius:8px; color:var(--foreground); font-family:inherit; font-size:13px; font-weight:400; line-height:1.6; resize:vertical; }
.record-editor textarea:focus { outline:2px solid var(--ring); outline-offset:1px; }
.record-additional { margin-top:14px; font-size:12px; color:var(--muted-foreground); }
.record-additional summary { cursor:pointer; margin-bottom:10px; }
.record-editor .stock-option { display:flex; align-items:center; gap:8px; margin-top:10px; }
.record-editor input[type=checkbox] { height:16px; width:16px; margin:0; }
.record-editor-footer { display:flex; flex-shrink:0; align-items:center; justify-content:flex-end; gap:10px; border-top:1px solid var(--border); padding:14px 24px; background:var(--card); }
.record-editor-footer > span { margin-right:auto; font-size:12px; color:var(--muted-foreground); }
@media(max-width:700px) {
  .record-editor-dialog.legacy-dialog { width:calc(100vw - 16px); max-height:96dvh; }
  .record-editor-content { padding:16px; }
  .record-top-grid { grid-template-columns:minmax(0,1fr); gap:18px; }
  .record-main-fields > .record-form-section:first-child .three-columns { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .record-main-fields > .record-form-section:first-child .three-columns > label:first-child { grid-column:1/-1; }
  .record-top-grid .photo-zone { min-height:150px; aspect-ratio:2; }
  .record-editor-footer { padding:12px 16px; flex-wrap:wrap; }
  .record-editor-footer > span { flex-basis:100%; }
  .record-fields.three-columns { gap:10px; }
}
</style>
