<script setup lang="ts">
import PageControls from "../components/PageControls.vue";
import { useWorkspaceContext } from "../context";
const {
  listPages,
  loadPage,
  dashboard,
  saving,
  canOperate,
  materialForm,
  stockInForm,
  money,
  submitMaterial,
  archiveMaterial,
  adjustStock,
  submitStockIn,
  PackagePlus,
} = useWorkspaceContext();
</script>
<template>
  <template v-if="dashboard">
    <section class="space-y-5">
      <form
        class="collection-filters flex flex-wrap gap-3 rounded-xl border bg-white p-3"
        @submit.prevent="loadPage('movements')"
      >
        <input
          v-model="listPages.movements!.q"
          placeholder="搜索名称 / 客户 / 材料"
          class="rounded border p-2"
        /><button type="submit" class="rounded border px-4">查询</button>
      </form>
      <PageControls
        :page="listPages.movements!.page"
        :total="listPages.movements!.total"
        :busy="listPages.movements!.busy"
        @change="loadPage('movements', $event)"
      />
      <div v-if="canOperate" class="grid gap-5 xl:grid-cols-2">
        <form class="panel-card p-5" @submit.prevent="submitMaterial">
          <div class="section-heading">
            <div>
              <h2>新增物料</h2>
              <p>物料价格参与旧系统兼容计价。</p>
            </div>
          </div>
          <div class="form-grid">
            <label>名称<input v-model="materialForm.name" required /></label
            ><label>类型<input v-model="materialForm.material_type" /></label
            ><label
              >单价(元/kg)<input
                v-model.number="materialForm.price_per_kg"
                min="0"
                step="0.01"
                type="number"
            /></label>
          </div>
          <button class="action-button mt-4" type="submit" :disabled="saving">
            <PackagePlus class="size-4" />新增物料
          </button>
        </form>
        <form class="panel-card p-5" @submit.prevent="submitStockIn">
          <div class="section-heading">
            <div>
              <h2>登记入库</h2>
              <p>入库同时更新库存并生成不可丢失的流水。</p>
            </div>
          </div>
          <div class="form-grid">
            <label
              >日期<input
                v-model="stockInForm.business_date"
                required
                type="date" /></label
            ><label
              >物料<select v-model="stockInForm.material_name" required>
                <option value="">请选择</option>
                <option
                  v-for="item in dashboard.materials"
                  :key="item.id"
                  :value="item.name"
                >
                  {{ item.name }}
                </option>
              </select></label
            ><label
              >数量(g)<input
                v-model.number="stockInForm.amount_g"
                required
                min="0.01"
                step="0.01"
                type="number" /></label
            ><label>供应商<input v-model="stockInForm.vendor" /></label
            ><label
              >成本<input
                v-model.number="stockInForm.cost"
                min="0"
                step="0.01"
                type="number" /></label
            ><label>备注<input v-model="stockInForm.remark" /></label>
          </div>
          <button class="action-button mt-4" type="submit" :disabled="saving">
            <PackagePlus class="size-4" />确认入库
          </button>
        </form>
      </div>
      <div class="panel-card p-5">
        <div class="section-heading">
          <div>
            <h2>库存</h2>
            <p>库存快照与历史流水分别保存，迁移时不会重复累加入库历史。</p>
          </div>
        </div>
        <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          <article
            v-for="item in dashboard.inventory"
            :key="item.id"
            class="rounded-xl border p-4"
            :class="
              item.is_low
                ? 'border-amber-300 bg-amber-50'
                : 'border-slate-200 bg-white'
            "
          >
            <div class="flex justify-between">
              <strong>{{ item.material_name }}</strong
              ><span v-if="item.is_low" class="tag bg-amber-100 text-amber-700"
                >低库存</span
              >
            </div>
            <p class="mt-3 text-2xl font-bold">
              {{ (item.stock_g / 1000).toFixed(2) }} kg
            </p>
            <p class="text-xs text-slate-500">
              预警线 {{ (item.min_stock_g / 1000).toFixed(2) }} kg
            </p>
            <button
              v-if="canOperate"
              class="action-button secondary mt-3"
              type="button"
              @click="
                adjustStock(item.material_name, item.stock_g, item.min_stock_g)
              "
            >
              盘点调整
            </button>
          </article>
        </div>
      </div>
      <div class="panel-card p-5">
        <div class="section-heading">
          <div>
            <h2>物料主数据</h2>
            <p>{{ dashboard.materials.length }} 项有效物料</p>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>类型</th>
                <th>价格</th>
                <th v-if="canOperate">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in dashboard.materials" :key="item.id">
                <td>
                  <strong>{{ item.name }}</strong>
                </td>
                <td>{{ item.material_type || "—" }}</td>
                <td>{{ money(item.price_per_kg) }}/kg</td>
                <td v-if="canOperate">
                  <button
                    class="text-rose-600"
                    type="button"
                    @click="archiveMaterial(item)"
                  >
                    停用
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div class="panel-card p-5">
        <div class="section-heading">
          <div>
            <h2>最近库存流水</h2>
            <p>显示最近 500 条库存变动。</p>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>日期</th>
                <th>物料</th>
                <th>类型</th>
                <th>变动(g)</th>
                <th>结存(g)</th>
                <th>供应商 / 备注</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in dashboard.inventory_movements" :key="item.id">
                <td>{{ item.business_date }}</td>
                <td>{{ item.material_name }}</td>
                <td>
                  <span class="tag">{{ item.movement_type }}</span>
                </td>
                <td
                  :class="
                    item.delta_g >= 0 ? 'text-emerald-700' : 'text-rose-700'
                  "
                >
                  {{ item.delta_g }}
                </td>
                <td>{{ item.balance_after_g }}</td>
                <td>{{ item.vendor || item.remark || "—" }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  </template>
</template>
