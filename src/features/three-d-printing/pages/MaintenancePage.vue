<script setup lang="ts">
import PageControls from "../components/PageControls.vue";
import { useWorkspaceContext } from "../context";
const {
  listPages,
  loadPage,
  dashboard,
  saving,
  canOperate,
  maintenanceForm,
  money,
  submitMaintenance,
  removeMaintenance,
  Wrench,
} = useWorkspaceContext();
</script>
<template>
  <template v-if="dashboard">
    <section class="space-y-5">
      <form
        class="collection-filters flex flex-wrap gap-3 rounded-xl border bg-white p-3"
        @submit.prevent="loadPage('maintenance')"
      >
        <input
          v-model="listPages.maintenance!.q"
          placeholder="搜索名称 / 客户 / 材料"
          class="rounded border p-2"
        /><button type="submit" class="rounded border px-4">查询</button>
      </form>
      <PageControls
        :page="listPages.maintenance!.page"
        :total="listPages.maintenance!.total"
        :busy="listPages.maintenance!.busy"
        @change="loadPage('maintenance', $event)"
      />
      <form
        v-if="canOperate"
        class="panel-card p-5"
        @submit.prevent="submitMaintenance"
      >
        <div class="section-heading">
          <div>
            <h2>新增维护记录</h2>
            <p>保养、维修和耗材更换统一纳入成本。</p>
          </div>
        </div>
        <div class="form-grid">
          <label
            >日期<input
              v-model="maintenanceForm.business_date"
              required
              type="date" /></label
          ><label
            >机号(0=公共)<input
              v-model.number="maintenanceForm.machine_no"
              min="0"
              max="100"
              type="number" /></label
          ><label
            >类型<input
              v-model="maintenanceForm.maintenance_type"
              required /></label
          ><label
            >费用<input
              v-model.number="maintenanceForm.cost"
              min="0"
              step="0.01"
              type="number" /></label
          ><label>供应商<input v-model="maintenanceForm.vendor" /></label
          ><label class="md:col-span-2"
            >维护内容<input
              v-model="maintenanceForm.description"
              required /></label
          ><label class="md:col-span-2"
            >备注<input v-model="maintenanceForm.remark"
          /></label>
        </div>
        <button class="action-button mt-4" type="submit" :disabled="saving">
          <Wrench class="size-4" />保存维护记录
        </button>
      </form>
      <div class="panel-card p-5">
        <div class="section-heading">
          <div>
            <h2>维护历史</h2>
            <p>共 {{ dashboard.maintenance.length }} 条</p>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>日期</th>
                <th>机台</th>
                <th>类型</th>
                <th>内容</th>
                <th>供应商</th>
                <th>费用</th>
                <th v-if="canOperate">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in dashboard.maintenance" :key="item.id">
                <td>{{ item.business_date }}</td>
                <td>{{ item.machine_no ? `${item.machine_no}号` : "公共" }}</td>
                <td>{{ item.maintenance_type }}</td>
                <td>
                  {{ item.description }}<small>{{ item.remark }}</small>
                </td>
                <td>{{ item.vendor || "—" }}</td>
                <td>{{ money(item.cost) }}</td>
                <td v-if="canOperate">
                  <button
                    class="text-rose-600"
                    type="button"
                    @click="removeMaintenance(item)"
                  >
                    删除
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  </template>
</template>
