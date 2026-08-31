<script setup lang="ts">
import type { InjectionScheduleLine, InjectionScheduleOrder } from '@/types/injectionScheduling'

defineProps<{
  lines: InjectionScheduleLine[]
  orders: InjectionScheduleOrder[]
}>()

function numberText(value: number | string | null | undefined) {
  if (value === null || value === undefined || value === '') return '—'
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(Number(value))
}
</script>

<template>
  <div class="overflow-hidden rounded-xl border border-slate-200 bg-white">
    <div class="overflow-x-auto">
      <table class="min-w-[1360px] w-full border-collapse text-left text-sm">
        <thead class="bg-slate-50 text-xs font-semibold text-slate-600">
          <tr>
            <th class="px-4 py-3">机号</th>
            <th class="px-4 py-3">顺序</th>
            <th class="px-4 py-3">状态</th>
            <th class="px-4 py-3">优先级</th>
            <th class="px-4 py-3">工模</th>
            <th class="px-4 py-3">单号</th>
            <th class="px-4 py-3">货号</th>
            <th class="px-4 py-3">名称</th>
            <th class="px-4 py-3">颜色 / 用料</th>
            <th class="px-4 py-3 text-right">已啤数</th>
            <th class="px-4 py-3 text-right">欠数</th>
            <th class="px-4 py-3">计划区间</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-for="line in lines" :key="line.id" class="hover:bg-teal-50/30">
            <td class="px-4 py-3 font-semibold text-slate-900">{{ line.machine_code }}</td>
            <td class="px-4 py-3 tabular-nums">{{ numberText(line.sequence_no) }}</td>
            <td class="px-4 py-3">{{ line.status }}</td>
            <td class="px-4 py-3">{{ line.priority }}</td>
            <td class="px-4 py-3">{{ line.mold_code || '—' }}</td>
            <td class="px-4 py-3">{{ line.order_no }}</td>
            <td class="px-4 py-3">{{ line.product_code }}</td>
            <td class="max-w-56 truncate px-4 py-3" :title="line.product_name">{{ line.product_name || '—' }}</td>
            <td class="px-4 py-3">{{ [line.color, line.material_name].filter(Boolean).join(' · ') || '—' }}</td>
            <td class="px-4 py-3 text-right tabular-nums">{{ numberText(line.qualified_shots) }}</td>
            <td class="px-4 py-3 text-right font-semibold tabular-nums">{{ numberText(line.remaining_shots) }}</td>
            <td class="px-4 py-3 text-xs text-slate-500">
              {{ line.planned_start_at || '未定' }}<br>{{ line.planned_finish_at || '未定' }}
            </td>
          </tr>
          <tr v-for="order in orders.filter((item) => !lines.some((line) => line.order_demand_id === item.id))" :key="`order-${order.id}`" class="bg-amber-50/30">
            <td class="px-4 py-3 font-semibold text-amber-700">未排机台</td>
            <td class="px-4 py-3">—</td>
            <td class="px-4 py-3">{{ order.status }}</td>
            <td class="px-4 py-3">{{ order.priority }}</td>
            <td class="px-4 py-3">{{ order.mold_code }}</td>
            <td class="px-4 py-3">{{ order.order_no }}</td>
            <td class="px-4 py-3">{{ order.product_code }}</td>
            <td class="max-w-56 truncate px-4 py-3" :title="order.product_name">{{ order.product_name || '—' }}</td>
            <td class="px-4 py-3">{{ [order.color, order.material_name].filter(Boolean).join(' · ') || '—' }}</td>
            <td class="px-4 py-3 text-right tabular-nums">{{ numberText(order.qualified_shots) }}</td>
            <td class="px-4 py-3 text-right font-semibold tabular-nums">{{ numberText(order.remaining_shots) }}</td>
            <td class="px-4 py-3 text-xs text-slate-500">交期 {{ order.delivery_due_date || '未维护' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
