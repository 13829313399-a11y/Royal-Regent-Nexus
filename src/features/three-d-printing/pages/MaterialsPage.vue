<script setup lang="ts">
import { computed, ref, onMounted } from "vue";
import { threeDPrintingApi } from "@/api/threeDPrinting";
import type { ThreeDMaterial } from "@/types/threeDPrinting";
import LegacyDialog from "../components/LegacyDialog.vue";
import PageControls from "../components/PageControls.vue";
import { useWorkspaceContext } from "../context";
const props = withDefaults(
  defineProps<{ mode?: "materials" | "warehouse" }>(),
  { mode: "materials" },
);
const {
  dashboard,
  canOperate,
  saving,
  materialForm,
  stockInForm,
  submitMaterial,
  submitStockIn,
  archiveMaterial,
  adjustStock,
  money,
  mutate,
  errorMessage,
  listPages,
  loadPage,
} = useWorkspaceContext();
const query = ref(""),
  dialog = ref(""),
  editId = ref(""),
  revision = ref(1);
const items = computed(
  () =>
    dashboard.value?.materials.filter((m) =>
      (m.name + " " + m.material_type)
        .toLowerCase()
        .includes(query.value.toLowerCase()),
    ) || [],
);
const inventory = computed(
  () =>
    dashboard.value?.inventory.filter((m) =>
      m.material_name.toLowerCase().includes(query.value.toLowerCase()),
    ) || [],
);
const total = computed(
  () => inventory.value.reduce((n, m) => n + m.stock_g, 0) / 1000,
);
onMounted(() => {
  if (props.mode === "warehouse") void loadPage("movements");
});
const movementNames: Record<string, string> = {
  migration_opening: "期初库存",
  legacy_history_only: "历史入库",
  stock_in: "入库",
  manual_adjustment: "盘点调整",
  adjustment: "盘点调整",
  record_consumption: "生产扣料",
  record_reversal: "退回",
  migration_adjustment: "迁移调整",
};
function add() {
  editId.value = "";
  Object.assign(materialForm, { name: "", material_type: "", price_per_kg: 0 });
  dialog.value = "material";
}
function edit(m: ThreeDMaterial) {
  editId.value = m.id;
  revision.value = m.revision;
  Object.assign(materialForm, {
    name: m.name,
    material_type: m.material_type,
    price_per_kg: m.price_per_kg,
  });
  dialog.value = "material";
}
async function saveMaterial() {
  if (editId.value)
    await mutate(
      () =>
        threeDPrintingApi.updateMaterial(editId.value, {
          factory_id: "huakang-a",
          ...materialForm,
          revision: revision.value,
        }),
      "材料已更新",
    );
  else await submitMaterial();
  if (!errorMessage.value) dialog.value = "";
}
async function saveStock() {
  await submitStockIn();
  if (!errorMessage.value) dialog.value = "";
}
</script>
<template>
  <section v-if="dashboard" class="space-y-5">
    <div class="legacy-toolbar">
      <input
        v-model="query"
        :placeholder="
          mode === 'materials' ? '搜索材料名称 / 类型' : '搜索库存材料'
        "
      /><button
        v-if="canOperate && mode === 'materials'"
        class="action-button"
        @click="add"
      >
        + 添加材料</button
      ><button
        v-if="canOperate && mode === 'warehouse'"
        class="action-button green"
        @click="dialog = 'stock'"
      >
        + 登记入库</button
      ><span v-if="mode === 'warehouse'"
        >库存合计 {{ total.toFixed(2) }} kg</span
      >
    </div>
    <div v-if="mode === 'materials'" class="panel-card">
      <div class="legacy-panel-head">
        <h2>材料价格表</h2>
        <span>{{ items.length }} 种材料</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>名称</th>
              <th>类型</th>
              <th>单价（元/kg）</th>
              <th v-if="canOperate">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in items" :key="m.id">
              <td>{{ m.name }}</td>
              <td>{{ m.material_type }}</td>
              <td>{{ money(m.price_per_kg) }}</td>
              <td v-if="canOperate">
                <div class="row-actions">
                  <button @click="edit(m)">编辑</button
                  ><button class="danger" @click="archiveMaterial(m)">
                    删除
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    <template v-else
      ><div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <article v-for="m in inventory" :key="m.id" class="panel-card p-5">
          <div class="flex justify-between">
            <h2 class="font-bold">{{ m.material_name }}</h2>
            <span v-if="m.is_low" class="tag">库存不足</span>
          </div>
          <p class="text-2xl font-bold my-4">
            {{ (m.stock_g / 1000).toFixed(2) }} kg
          </p>
          <p class="text-xs text-slate-500">
            预警线 {{ (m.min_stock_g / 1000).toFixed(2) }} kg
          </p>
          <button
            v-if="canOperate"
            class="action-button secondary mt-4"
            @click="adjustStock(m.material_name, m.stock_g, m.min_stock_g)"
          >
            盘点调整
          </button>
        </article>
      </div>
      <div class="panel-card">
        <div class="legacy-panel-head"><h2>出入库记录</h2></div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>日期</th>
                <th>材料</th>
                <th>类型</th>
                <th>数量(g)</th>
                <th>结存(g)</th>
                <th>供应商</th>
                <th>费用</th>
                <th>备注</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in dashboard.inventory_movements" :key="m.id">
                <td>{{ m.business_date }}</td>
                <td>{{ m.material_name }}</td>
                <td>{{ movementNames[m.movement_type] || m.movement_type }}</td>
                <td>{{ m.delta_g }}</td>
                <td>{{ m.balance_after_g }}</td>
                <td>{{ m.vendor }}</td>
                <td>{{ money(m.cost) }}</td>
                <td>{{ m.remark }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <PageControls
          :page="listPages.movements!.page"
          :total="listPages.movements!.total"
          :busy="listPages.movements!.busy"
          @change="loadPage('movements', $event)"
        /></div
    ></template>
    <LegacyDialog
      v-if="dialog === 'material'"
      :title="editId ? '编辑材料' : '添加材料'"
      @close="dialog = ''"
      ><form class="p-4 space-y-4" @submit.prevent="saveMaterial">
        <label>名称<input v-model="materialForm.name" required /></label
        ><label>类型<input v-model="materialForm.material_type" /></label
        ><label
          >单价（元/kg）<input
            v-model.number="materialForm.price_per_kg"
            type="number"
            min="0"
            step="0.01"
            required /></label
        ><button class="action-button" :disabled="saving">保存</button>
      </form></LegacyDialog
    >
    <LegacyDialog
      v-if="dialog === 'stock'"
      title="登记入库"
      @close="dialog = ''"
      ><form class="p-4" @submit.prevent="saveStock">
        <div class="form-grid">
          <label
            >日期<input
              v-model="stockInForm.business_date"
              type="date"
              required /></label
          ><label
            >材料<select v-model="stockInForm.material_name" required>
              <option value="">请选择</option>
              <option
                v-for="m in dashboard.materials"
                :key="m.id"
                :value="m.name"
              >
                {{ m.name }}
              </option>
            </select></label
          ><label
            >数量(g)<input
              v-model.number="stockInForm.amount_g"
              type="number"
              min="0.01"
              step="0.01"
              required /></label
          ><label>供应商<input v-model="stockInForm.vendor" /></label
          ><label
            >费用<input
              v-model.number="stockInForm.cost"
              type="number"
              min="0"
              step="0.01" /></label
          ><label>备注<input v-model="stockInForm.remark" /></label>
        </div>
        <button class="action-button mt-4" :disabled="saving">保存入库</button>
      </form></LegacyDialog
    >
  </section>
</template>
