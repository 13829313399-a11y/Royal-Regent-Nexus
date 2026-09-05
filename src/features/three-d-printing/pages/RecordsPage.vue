<script setup lang="ts">
import ProductPicker from "../components/ProductPicker.vue";
import { computed, ref, watch, nextTick } from "vue";
import PageControls from "../components/PageControls.vue";
import DataQualityBadge from "../components/DataQualityBadge.vue";
import { useWorkspaceContext } from "../context";
const {
  listPages,
  loadPage,
  dashboard,
  saving,
  dateFrom,
  dateTo,
  canOperate,
  canReadAudit,
  recordForm,
  loadDashboard,
  chooseRecordProduct,
  resetRecordForm,
  editRecord,
  submitRecord,
  removeRecord,
  toggleDayOff,
  Save,
} = useWorkspaceContext();
const runLabels: Record<string, string> = {
  pending: "待处理",
  running: "打印中",
  paused: "暂停",
  succeeded: "完成",
  failed: "失败",
  cancelled: "取消",
  unknown: "待核对",
};
const reconciliationLabels: Record<string, string> = {
  none: "无需对账",
  pending: "待对账",
  resolved: "已对账",
};
const scrollTop = ref(0);
const scroller = ref<HTMLElement | null>(null);
const rowHeight = 120;
const start = computed(() =>
  Math.max(0, Math.floor(scrollTop.value / rowHeight) - 3),
);
const windowedRecords = computed(
  () => dashboard.value?.records.slice(start.value, start.value + 12) ?? [],
);
watch(
  () => dashboard.value?.records.map((r) => r.id).join(","),
  () => {
    scrollTop.value = 0;
    nextTick(() => {
      if (scroller.value) scroller.value.scrollTop = 0;
    });
  },
);
</script>
<template>
  <template v-if="dashboard">
    <section class="space-y-5">
      <form
        class="collection-filters flex flex-wrap gap-3 rounded-xl border bg-white p-3"
        @submit.prevent="loadPage('records')"
      >
        <input
          v-model="listPages.records!.q"
          placeholder="搜索名称 / 客户 / 材料"
          class="rounded border p-2"
        /><input
          v-model.number="listPages.records!.machine_no"
          type="number"
          min="0"
          max="11"
          aria-label="机号（0为全部）"
          class="w-20 rounded border"
        /><select v-model="listPages.records!.state">
          <option value="">全部运行状态</option>
          <option value="running">运行</option>
          <option value="paused">暂停</option>
          <option value="succeeded">完成</option>
          <option value="failed">失败</option>
          <option value="unknown">未知</option></select
        ><select v-model="listPages.records!.quality">
          <option value="">全部质量</option>
          <option value="pending">待对账</option>
          <option value="flags">有质量标记</option></select
        ><input
          v-model="listPages.records!.customer"
          placeholder="筛选客户"
          aria-label="筛选客户"
        /><input
          v-model="listPages.records!.material"
          placeholder="筛选材料"
          aria-label="筛选材料"
        /><select v-model="listPages.records!.source" aria-label="筛选来源">
          <option value="">全部来源</option>
          <option value="legacy">旧系统</option>
          <option value="cloud-connector">云端连接器</option>
          <option value="nexus">云端手工</option></select
        ><button type="submit" class="rounded border px-4">查询</button>
      </form>
      <PageControls
        :page="listPages.records!.page"
        :total="listPages.records!.total"
        :busy="listPages.records!.busy"
        @change="loadPage('records', $event)"
      />
      <form
        v-if="canOperate"
        class="panel-card p-5"
        @submit.prevent="submitRecord"
      >
        <div class="section-heading">
          <div>
            <h2>{{ recordForm.id ? "编辑生产记录" : "新增生产记录" }}</h2>
            <p>选择产品后自动带出材料、重量、时间与报价，可继续调整。</p>
          </div>
          <button
            v-if="recordForm.id"
            class="action-button secondary"
            type="button"
            @click="resetRecordForm"
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
            >报价<input
              v-model.number="recordForm.quoted_price"
              min="0"
              step="0.01"
              type="number"
          /></label>
          <label
            >客户<input v-model="recordForm.customer" maxlength="255"
          /></label>
          <label class="md:col-span-2 xl:col-span-4"
            >备注<input v-model="recordForm.remark" maxlength="4000"
          /></label>
          <label class="md:col-span-2"
            >修改/批准原因<input
              v-model="recordForm.reason"
              :required="!!recordForm.id || recordForm.allow_negative_stock"
              maxlength="1000"
          /></label>
          <label v-if="canReadAudit"
            ><input
              v-model="recordForm.allow_negative_stock"
              type="checkbox"
            />主管明确批准本次负库存</label
          >
          <label v-if="recordForm.id && canReadAudit"
            ><input
              v-model="recordForm.history_only_correction"
              type="checkbox"
            />迁移记录仅修正历史，不重放期初库存</label
          >
          <p v-if="recordForm.id" class="md:col-span-2 text-sm text-amber-800">
            原扣料按流水冲销，新耗料
            {{
              recordForm.weight_g * recordForm.quantity
            }}g；缺料时不扣减。迁移历史仅纠错，不重放库存。成本纠错沿用原费率，换材料后成本待核实。
          </p>
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
      <div class="panel-card p-5">
        <div class="section-heading">
          <div>
            <h2>历史生产记录</h2>
            <p>旧系统记录、自动记录与云端新增记录统一保留。</p>
          </div>
          <div class="flex gap-2">
            <input v-model="dateFrom" class="compact-input" type="date" /><input
              v-model="dateTo"
              class="compact-input"
              type="date"
            /><button
              class="action-button secondary"
              type="button"
              @click="loadDashboard()"
            >
              筛选
            </button>
          </div>
        </div>
        <div
          ref="scroller"
          class="table-wrap max-h-[600px]"
          @scroll="scrollTop = ($event.target as HTMLElement).scrollTop"
        >
          <table>
            <thead>
              <tr>
                <th>日期</th>
                <th>机台</th>
                <th>产品</th>
                <th>客户</th>
                <th>材料</th>
                <th>数量</th>
                <th>时间</th>
                <th>来源</th>
                <th v-if="canOperate">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="start" aria-hidden="true">
                <td
                  :colspan="9"
                  :style="{ height: `${start * rowHeight}px`, padding: 0 }"
                ></td>
              </tr>
              <tr
                style="height: 120px"
                v-for="record in windowedRecords"
                :key="record.id"
              >
                <td>
                  <div class="record-cell">{{ record.business_date }}</div>
                </td>
                <td>
                  <div class="record-cell">{{ record.machine_no }}号</div>
                </td>
                <td>
                  <div class="record-cell">
                    <strong>{{
                      record.product_name || record.gcode_file || "—"
                    }}</strong
                    ><small>{{ record.remark }}</small
                    ><DataQualityBadge
                      :flags="record.data_quality_flags"
                    /><small
                      >{{ runLabels[record.run_status || "unknown"] }} ·
                      {{
                        reconciliationLabels[
                          record.reconciliation_status || "pending"
                        ] || "待核对"
                      }}</small
                    >
                  </div>
                </td>
                <td>
                  <div class="record-cell">{{ record.customer || "—" }}</div>
                </td>
                <td>
                  <div class="record-cell">
                    {{ record.material_name || "—"
                    }}<small
                      :class="
                        record.material_status === 'material_shortage'
                          ? 'text-rose-700'
                          : ''
                      "
                      >{{
                        record.material_status === "material_shortage"
                          ? "缺料 · 未扣库存"
                          : record.inventory_consumed
                            ? "已扣料"
                            : "未扣料 / 历史凭证"
                      }}</small
                    ><small
                      v-if="
                        record.data_quality_flags.includes(
                          'negative_inventory_approved',
                        )
                      "
                      class="text-rose-700"
                      >主管批准负库存 · 请补料</small
                    >
                  </div>
                </td>
                <td>
                  <div class="record-cell">{{ record.quantity }}</div>
                </td>
                <td>
                  <div class="record-cell">{{ record.duration_hours }}h</div>
                </td>
                <td>
                  <div class="record-cell">
                    <span class="tag">{{
                      record.auto_record
                        ? "设备自动"
                        : record.legacy_id
                          ? "旧系统"
                          : "云端手工"
                    }}</span>
                  </div>
                </td>
                <td v-if="canOperate">
                  <div class="record-cell">
                    <div class="row-actions">
                      <button type="button" @click="editRecord(record)">
                        编辑</button
                      ><button
                        class="danger"
                        type="button"
                        @click="removeRecord(record)"
                      >
                        撤销
                      </button>
                    </div>
                  </div>
                </td>
              </tr>
              <tr
                v-if="dashboard.records.length > start + 12"
                aria-hidden="true"
              >
                <td
                  :colspan="9"
                  :style="{
                    height: `${(dashboard.records.length - start - 12) * rowHeight}px`,
                    padding: 0,
                  }"
                ></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  </template>
</template>

<style scoped>
.record-cell {
  max-height: 96px;
  overflow: auto;
}
</style>
