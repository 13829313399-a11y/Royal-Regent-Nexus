<script setup lang="ts">
import { useWorkspaceContext } from "../context";
const {
  auditEvents,
  deletedRecords,
  saving,
  canOperate,
  canReadAudit,
  settingsForm,
  saveSettings,
  restoreRecord,
  History,
  Save,
  Settings2,
} = useWorkspaceContext();
</script>
<template>
  <section class="grid gap-5 xl:grid-cols-[420px_1fr]">
    <form class="panel-card p-5" @submit.prevent="saveSettings">
      <div class="section-heading">
        <div>
          <h2>计费设置</h2>
          <p>继续使用旧系统的机器、电费、人工、损耗和利润参数。</p>
        </div>
        <Settings2 class="size-5 text-slate-400" />
      </div>
      <div class="space-y-3">
        <label
          >机器数量<input
            v-model.number="settingsForm.machine_count"
            :disabled="!canOperate"
            min="1"
            max="100"
            type="number" /></label
        ><label
          >单机每日电费<input
            v-model.number="settingsForm.electricity_per_machine_day"
            :disabled="!canOperate"
            min="0"
            step="0.01"
            type="number" /></label
        ><label
          >每日人工<input
            v-model.number="settingsForm.labor_per_day"
            :disabled="!canOperate"
            min="0"
            step="0.01"
            type="number" /></label
        ><label
          >材料损耗系数<input
            v-model.number="settingsForm.material_loss_rate"
            :disabled="!canOperate"
            min="0.01"
            step="0.01"
            type="number" /></label
        ><label
          >利润率(%)<input
            v-model.number="settingsForm.profit_rate_percent"
            :disabled="!canOperate"
            min="0"
            step="0.1"
            type="number"
        /></label>
      </div>
      <button
        v-if="canOperate"
        class="action-button mt-4"
        type="submit"
        :disabled="saving"
      >
        <Save class="size-4" />保存设置
      </button>
    </form>
    <div v-if="canReadAudit" class="panel-card p-5">
      <h2>已撤销记录（最近500条）</h2>
      <p class="text-sm text-slate-500">
        恢复后重新检查库存；缺料记录需补料后编辑重试。迁移历史凭证不重放期初库存。
      </p>
      <div
        v-for="record in deletedRecords"
        :key="record.id"
        class="flex items-center justify-between gap-3 border-b py-3"
      >
        <span
          >{{ record.business_date }} · {{ record.product_name }} ·
          {{ record.machine_no }}号机</span
        ><button
          v-if="canOperate"
          class="action-button secondary"
          :disabled="saving"
          @click="restoreRecord(record)"
        >
          恢复记录
        </button>
      </div>
    </div>
    <div class="panel-card p-5">
      <div class="section-heading">
        <div>
          <h2>审计记录</h2>
          <p>远程控制、图片、库存和业务变更均保留操作人及时间。</p>
        </div>
        <History class="size-5 text-slate-400" />
      </div>
      <div
        v-if="!canReadAudit"
        class="rounded-xl bg-slate-50 p-6 text-sm text-slate-500"
      >
        当前岗位无审计查看权限。
      </div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>时间</th>
              <th>操作人</th>
              <th>对象</th>
              <th>动作</th>
              <th>详情</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="event in auditEvents" :key="event.id">
              <td>{{ event.created_at }}</td>
              <td>{{ event.actor_name || event.actor_type }}</td>
              <td>
                {{ event.entity_type }}<small>{{ event.entity_id }}</small>
              </td>
              <td>
                <span class="tag">{{ event.action }}</span>
              </td>
              <td class="max-w-md">
                <pre class="whitespace-pre-wrap text-xs">{{
                  JSON.stringify(event.detail, null, 2)
                }}</pre>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>
