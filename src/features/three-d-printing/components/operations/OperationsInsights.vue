<script setup lang="ts">
import { useOperationsContext } from "../../operationsContext";

const {
  canOperate,
  advice,
  adviceMessage,
  metrics,
  percent,
  analyze,
  analyzing,
  prepare,
  applyAdvice,
  loading,
} = useOperationsContext();
</script>
<template>
  <div class="panel-card p-5">
    <div class="section-heading">
      <h2>排程建议与运行统计</h2>
      <button class="action-button secondary" :disabled="analyzing" :aria-busy="analyzing" @click="analyze">{{ analyzing ? '正在计算…' : '重新计算' }}</button>
    </div>
    <p v-if="analyzing" role="status">正在汇总设备历史，记录较多时需要稍候。</p>
    <p>{{ adviceMessage }}</p>
    <article
      v-for="item in advice"
      :key="item.schedule_id"
      class="border-b py-3"
    >
      <strong
        >{{ item.product_name }} · {{ item.quantity }}件 →
        {{ item.machine_no ? `${item.machine_no}号机` : "暂不推荐" }}</strong
      >
      <p>
        交期 {{ item.due_date }} · {{ item.reason }}
        <span v-if="item.eta">
          · 预计完成 {{ new Date(item.eta).toLocaleString("zh-CN") }}</span
        >
        <b v-if="item.late" class="text-rose-700">预计超期</b>
      </p>
      <p
        v-for="warning in item.warnings"
        :key="warning"
        class="text-sm text-amber-800"
      >
        {{ warning }}
      </p>
      <button
        v-if="item.machine_no && canOperate && !item.assigned"
        class="action-button mt-2 mr-2"
        :disabled="loading"
        @click="applyAdvice(item)"
      >
        采用机台
      </button>
      <span v-if="item.assigned" class="mr-2 text-sm text-teal-700"
        >已分配</span
      >
      <button
        v-if="item.machine_no && canOperate"
        class="action-button secondary"
        @click="prepare(item)"
      >
        调整计划
      </button>
    </article>
    <p class="my-4 text-sm text-slate-500">
      近30日估算：可用率按24小时日历窗口内任务经过时间计算（含暂停），性能采用已记录工时，质量按成功任务数计算；缺少时间或费率的数据不推测。保养小时统计上次维护日期之后的完整任务；缺失时间不补造，观测间隔超过120秒不推测暂停或等待。
    </p>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>机台</th>
            <th>可用率</th>
            <th>性能</th>
            <th>质量</th>
            <th>估算 OEE</th>
            <th>已观测暂停 / 等待</th>
            <th>异常事件</th>
            <th>保养累计</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in metrics" :key="m.machine_no">
            <td>{{ m.machine_no }}号</td>
            <td>{{ percent(m.availability) }}</td>
            <td>{{ percent(m.performance) }}</td>
            <td>{{ percent(m.quality) }}</td>
            <td>{{ percent(m.oee) }}</td>
            <td>{{ m.pause_hours }}h / {{ m.waiting_hours }}h</td>
            <td>
              {{ m.error_events }} · {{ m.maintenance_reasons.join(", ") }}
            </td>
            <td :class="{ 'text-rose-700': m.maintenance_due }">
              {{ m.lifetime_hours_since_service }}h
              {{ m.maintenance_due ? "到期提醒" : "" }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
