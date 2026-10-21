<script setup lang="ts">
import { Button } from '@/components/ui/button'
import type { PurchaseMaterialGroup } from '@/api/fabricProcurement'
defineProps<{ groups: PurchaseMaterialGroup[]; busy: boolean }>()
defineEmits<{ open: [group: PurchaseMaterialGroup] }>()
</script>

<template>
  <div class="warehouse-table-scroll" role="region" aria-label="按物料汇总的采购待收料" tabindex="0">
    <table class="fabric-purchase-groups">
      <thead><tr><th>物料 / 采购单</th><th>供应商</th><th class="numeric">剩余待收</th><th class="numeric">本系统已入库</th><th>复期 / 跟进</th><th>操作</th></tr></thead>
      <tbody>
        <tr v-for="group in groups" :key="group.key">
          <td data-label="物料 / 采购单"><strong>{{ group.material_name || '物料名称待补' }}</strong><small>{{ group.material_code || '编码待补' }}</small><small>{{ group.order_count }} 张单 · {{ group.line_count }} 条明细<span v-if="group.production_count"> · {{ group.production_count }} 个生产单</span><span v-if="group.supplement_count"> · 含 {{ group.supplement_count }} 条补数</span></small></td>
          <td data-label="供应商">{{ group.supplier || '供应商待补' }}</td>
          <td class="numeric" data-label="剩余待收"><strong class="quantity">{{ group.remaining_quantity ?? '待核对' }}</strong><span v-if="group.remaining_quantity !== null"> {{ group.unit }}</span><small v-if="group.unknown_quantity_count">已明确 {{ group.known_remaining_quantity }} {{ group.unit }}<br />另有 {{ group.unknown_quantity_count }} 条数量待核对</small></td>
          <td class="numeric" data-label="本系统已入库">{{ group.warehouse_received_quantity ?? '待核对' }}<span v-if="group.warehouse_received_quantity !== null"> {{ group.unit }}</span><small v-if="group.unknown_received_count">已明确 {{ group.known_received_quantity }} {{ group.unit }}<br />另有 {{ group.unknown_received_count }} 条实收身份待核对</small><small v-else>仅本组原单实收</small></td>
          <td data-label="复期 / 跟进"><span v-if="group.earliest_promise">{{ group.earliest_promise }}<small v-if="group.latest_promise !== group.earliest_promise">至 {{ group.latest_promise }}</small></span><span v-else>待供应商复期</span><small v-if="group.overdue_count" class="overdue">{{ group.overdue_count }} 条复期已过</small><small v-if="group.due_today_count" class="due">{{ group.due_today_count }} 条今天到期</small><small v-if="group.awaiting_date_count && group.earliest_promise">{{ group.awaiting_date_count }} 条待复期</small><small v-if="group.changed_count">{{ group.changed_count }} 条有变更未读</small></td>
          <td><Button variant="outline" size="sm" :disabled="busy" :aria-label="`查看采购明细 ${group.supplier} ${group.material_code} ${group.unit}`" @click="$emit('open', group)">查看采购明细</Button></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.fabric-purchase-groups{width:100%;min-width:960px;border-collapse:collapse;text-align:left}
.fabric-purchase-groups th,.fabric-purchase-groups td{padding:16px 24px;border-bottom:1px solid var(--border);vertical-align:top}
.fabric-purchase-groups th{white-space:nowrap}
.fabric-purchase-groups td:first-child{width:29%;min-width:240px;overflow-wrap:anywhere}
.fabric-purchase-groups td:nth-child(2){max-width:240px;overflow-wrap:anywhere}
.fabric-purchase-groups td:last-child{white-space:nowrap}
.fabric-purchase-groups small{display:block;margin-top:5px;color:var(--muted-foreground);font-size:12px;line-height:1.6}
.numeric{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.quantity{color:var(--primary);font-size:18px}
.fabric-purchase-groups .overdue{color:#b91c1c}.fabric-purchase-groups .due{color:#a16207}
@media(max-width:760px){.fabric-purchase-groups th,.fabric-purchase-groups td{padding:14px 16px}}
</style>
