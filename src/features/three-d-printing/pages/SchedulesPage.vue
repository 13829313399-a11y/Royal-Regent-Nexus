<script setup lang="ts">
import { ref, watch } from "vue";
import LegacyDialog from "../components/LegacyDialog.vue";
import ProductPicker from "../components/ProductPicker.vue";
import PageControls from "../components/PageControls.vue";
import { useWorkspaceContext } from "../context";
const {
  scheduleEditId,
  editSchedule,
  listPages,
  loadPage,
  dashboard,
  saving,
  errorMessage,
  canOperate,
  scheduleForm,
  chooseScheduleProduct,
  submitSchedule,
  changeScheduleStatus,
  removeSchedule,
  CalendarDays,
  Trash2,
  todayText,
} = useWorkspaceContext();
const showForm = ref(false);
function openAdd() {
  scheduleEditId.value = "";
  Object.assign(scheduleForm, {
    business_date: todayText(),
    product_id: "",
    product_name: "",
    customer: "",
    material_name: "",
    weight_g: 1,
    quantity: 1,
    machine_no: 0,
    priority: "normal",
    status: "pending",
    remark: "",
  });
  showForm.value = true;
}
watch(
  () => scheduleEditId.value,
  (value) => {
    if (value) showForm.value = true;
  },
);
async function saveForm() {
  await submitSchedule();
  if (!errorMessage.value) showForm.value = false;
}
</script>
<template>
  <template v-if="dashboard">
    <section class="space-y-5">
      <div class="legacy-toolbar">
        <button v-if="canOperate" class="action-button" @click="openAdd">
          + 添加排期
        </button>
      </div>
      <form
        class="collection-filters flex flex-wrap gap-3 rounded-xl border bg-white p-3"
        @submit.prevent="loadPage('schedules')"
      >
        <input
          v-model="listPages.schedules!.q"
          placeholder="搜索名称 / 客户 / 材料"
          class="rounded border p-2"
        /><button type="submit" class="rounded border px-4">查询</button>
      </form>
      <PageControls
        :page="listPages.schedules!.page"
        :total="listPages.schedules!.total"
        :busy="listPages.schedules!.busy"
        @change="loadPage('schedules', $event)"
      />
      <LegacyDialog v-if="showForm" title="排期" @close="showForm = false">
        <form
          v-if="canOperate"
          class="panel-card p-5"
          @submit.prevent="saveForm"
        >
          <div class="section-heading">
            <div>
              <h2>
                {{ scheduleEditId ? "编辑计划（确认后保存）" : "新增生产计划" }}
              </h2>
              <p>计划可分配机台并按待排、打印、完成、取消流转。</p>
            </div>
          </div>
          <div class="form-grid">
            <label
              >日期<input
                v-model="scheduleForm.business_date"
                required
                type="date" /></label
            ><label
              >产品<ProductPicker
                v-model="scheduleForm.product_id"
                @selected="chooseScheduleProduct" /></label
            ><label
              >产品名称<input
                v-model="scheduleForm.product_name"
                required /></label
            ><label>客户<input v-model="scheduleForm.customer" /></label
            ><label
              >材料<input
                v-model="scheduleForm.material_name"
                required /></label
            ><label
              >单件重量(g)<input
                v-model.number="scheduleForm.weight_g"
                min="0.01"
                step="0.01"
                type="number" /></label
            ><label
              >数量<input
                v-model.number="scheduleForm.quantity"
                min="1"
                type="number" /></label
            ><label
              >机号(0=待分配)<input
                v-model.number="scheduleForm.machine_no"
                min="0"
                max="100"
                type="number" /></label
            ><label
              >优先级<select v-model="scheduleForm.priority">
                <option value="high">高</option>
                <option value="normal">普通</option>
                <option value="low">低</option>
              </select></label
            ><label class="md:col-span-2"
              >备注<input v-model="scheduleForm.remark"
            /></label>
          </div>
          <button class="action-button mt-4" type="submit" :disabled="saving">
            <CalendarDays class="size-4" />保存计划
          </button>
        </form>
      </LegacyDialog>
      <div class="panel-card p-5">
        <div class="section-heading">
          <div>
            <h2>计划队列</h2>
            <p>按日期与优先级排列。</p>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>日期</th>
                <th>产品</th>
                <th>材料 / 数量</th>
                <th>机台</th>
                <th>优先级</th>
                <th>状态</th>
                <th v-if="canOperate">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in dashboard.schedules" :key="item.id">
                <td>{{ item.business_date }}</td>
                <td>
                  <strong>{{ item.product_name }}</strong
                  ><small>{{ item.customer }}</small>
                </td>
                <td>{{ item.material_name }} · {{ item.quantity }}</td>
                <td>
                  {{ item.machine_no ? `${item.machine_no}号` : "待分配" }}
                </td>
                <td>{{ item.priority }}</td>
                <td>
                  <span class="tag">{{ item.status }}</span>
                </td>
                <td v-if="canOperate">
                  <div class="row-actions">
                    <button
                      type="button"
                      @click="
                        showForm = true;
                        editSchedule(item);
                      "
                    >
                      编辑</button
                    ><button
                      v-if="item.status === 'pending'"
                      type="button"
                      @click="changeScheduleStatus(item, 'printing')"
                    >
                      开始</button
                    ><button
                      v-if="item.status === 'printing'"
                      type="button"
                      @click="changeScheduleStatus(item, 'done')"
                    >
                      完成</button
                    ><button
                      v-if="!['done', 'cancelled'].includes(item.status)"
                      class="danger"
                      type="button"
                      @click="changeScheduleStatus(item, 'cancelled')"
                    >
                      取消</button
                    ><button
                      class="danger"
                      type="button"
                      @click="removeSchedule(item)"
                    >
                      <Trash2 class="size-3" />
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  </template>
</template>
