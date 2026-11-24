<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ClipboardList } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import WarehouseDetailDialog from '@/features/warehouse-foundation/WarehouseDetailDialog.vue'
import { documentProgress, operationLabels, pendingHandoffQuantity } from './operations'
import type { SemiOrderProgress, WarehouseDocument, WarehouseOperationKind } from '@/api/warehouseOperations'

const props = defineProps<{
  order: SemiOrderProgress
  release: WarehouseDocument
  documents: WarehouseDocument[]
  canOperate: boolean
  canCorrect: boolean
  hasStock: boolean
  hasTask: boolean
}>()
defineEmits<{
  close: []
  closeAutoFocus: [event: Event]
  detail: [row: WarehouseDocument]
  action: [kind: WarehouseOperationKind, original?: WarehouseDocument]
}>()

const page = ref(0)
const pageSize = 20
const visible = computed(() => props.documents.slice(page.value * pageSize, (page.value + 1) * pageSize))
const taskUnits = computed(() => new Map(props.documents.filter(row => row.kind === 'TASK').map(row => [row.id, row.data.unit])))
watch(() => props.documents.length, length => { page.value = Math.min(page.value, Math.max(0, Math.ceil(length / pageSize) - 1)) })

function canCorrectTask(row: WarehouseDocument) {
  return props.canCorrect && row.kind === 'TASK' && !!row.data.release_id && !row.reversed
    && !props.documents.some(document => document.kind === 'PROCESS_SEND' && !document.reversed && document.data.task_id === row.id)
}
</script>

<template>
  <WarehouseDetailDialog :title="`订单进度 · ${release.data.production_no}`" :description="`${release.data.part}${release.data.label_code ? ` · 布标 ${release.data.label_code}` : ''}`"
    :icon="ClipboardList" close-label="关闭订单进度" wide @close="$emit('close')" @close-auto-focus="$emit('closeAutoFocus', $event)">
    <div class="fabric-detail-overview">
      <div class="fabric-detail-identity">
        <h3>{{ release.data.item_name }}</h3>
        <p>{{ release.data.item_code }} · {{ release.data.process_state }}</p>
        <p>放产 {{ release.data.source_no }} / {{ release.data.source_line }} · {{ release.business_date }}</p>
        <p v-if="release.data.due_date">应收日期 {{ release.data.due_date }}</p>
      </div>
      <dl class="fabric-detail-metrics">
        <div><dt>累计实收</dt><dd><strong>{{ order.received }}</strong> {{ release.data.unit }}</dd></div>
        <div><dt>放产计划</dt><dd><strong>{{ release.data.quantity }}</strong> {{ release.data.unit }}</dd></div>
      </dl>
    </div>
    <div class="semi-trace-actions">
      <Button variant="outline" size="sm" @click="$emit('detail', release)">查看放产明细</Button>
      <Button v-if="canOperate" size="sm" @click="$emit('action', 'RECEIPT')">登记实收</Button>
      <Button v-if="canOperate" variant="outline" size="sm" @click="$emit('action', 'TASK')">登记加工任务</Button>
      <Button v-if="canOperate && hasStock && hasTask" variant="outline" size="sm" @click="$emit('action', 'PROCESS_SEND')">登记加工发出</Button>
      <Button v-if="canOperate && hasStock" variant="outline" size="sm" @click="$emit('action', 'PACK_SEND')">登记包装发出</Button>
      <Button v-if="canCorrect && !documents.some(row => row.kind !== 'CORRECTION' && !row.reversed)" variant="outline" size="sm" @click="$emit('action', 'CORRECTION', release)">冲销放产明细</Button>
    </div>
    <section class="fabric-detail-section semi-trace-records">
      <h3>关联单据</h3>
      <p v-if="!documents.length" class="text-muted-foreground">登记实收或加工任务后，可从这里查看关联记录。</p>
      <div v-else class="overflow-x-auto" role="region" aria-label="关联单据" tabindex="0">
        <table>
          <thead><tr><th scope="col">业务 / 日期</th><th scope="col">产品 / 数量</th><th scope="col">来源凭证 / 原单</th><th scope="col">操作</th></tr></thead>
          <tbody>
            <tr v-for="row in visible" :key="row.id">
              <td><strong>{{ operationLabels[row.kind] }}</strong><small>{{ row.business_date }} · {{ row.actor_name }}</small></td>
              <td>
                <strong>{{ row.data.quantity }} {{ row.data.unit }}</strong>
                <small>{{ row.data.item_code }} · {{ row.data.process_state }}</small>
                <small v-if="row.kind === 'PROCESS_RETURN'">核销 {{ row.data.consumed_quantity }} {{ row.data.consumed_unit }}</small>
                <small>{{ documentProgress(row, taskUnits.get(row.data.task_id)) }}</small>
              </td>
              <td>
                <strong>{{ row.data.source_no || row.id }}</strong><small v-if="row.data.source_no">{{ row.id }}</small>
                <small v-if="row.data.original_id">原单 {{ row.data.original_id }}</small>
              </td>
              <td>
                <div class="semi-trace-actions">
                  <Button variant="outline" size="sm" @click="$emit('detail', row)">详情</Button>
                  <Button v-if="canCorrectTask(row)" variant="outline" size="sm" @click="$emit('action', 'CORRECTION', row)">冲销任务</Button>
                  <template v-if="canOperate && !row.reversed">
                    <Button v-if="row.kind === 'PROCESS_SEND' && pendingHandoffQuantity(row)" size="sm" @click="$emit('action', 'PROCESS_RETURN', row)">登记回货</Button>
                    <template v-if="row.kind === 'PACK_SEND' && pendingHandoffQuantity(row)">
                      <Button size="sm" @click="$emit('action', 'PACK_RECEIVE', row)">代录签收</Button>
                      <Button variant="outline" size="sm" @click="$emit('action', 'RETURN', row)">登记退回</Button>
                    </template>
                  </template>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="documents.length > pageSize" class="semi-trace-pagination">
        <span>共 {{ documents.length }} 条</span>
        <Button variant="outline" size="sm" :disabled="page === 0" @click="page--">上一页</Button>
        <Button variant="outline" size="sm" :disabled="(page + 1) * pageSize >= documents.length" @click="page++">下一页</Button>
      </div>
    </section>
  </WarehouseDetailDialog>
</template>

<style scoped>
.semi-trace-actions { display: flex; flex-wrap: wrap; gap: 6px; align-items: start; }
.semi-trace-records table { width: 100%; min-width: 550px; text-align: left; font-size: 12px; }
.semi-trace-records th { padding: 8px 10px; font-weight: 600; background: var(--muted); }
.semi-trace-records td { padding: 10px; vertical-align: top; overflow-wrap: anywhere; }
.semi-trace-records tr + tr > td { border-top: 1px solid var(--border); }
.semi-trace-records td small { display: block; margin-top: 3px; font-size: 11px; color: var(--muted-foreground); }
.semi-trace-records td:nth-child(2) { font-variant-numeric: tabular-nums; }
.semi-trace-pagination { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-top: 8px; }
</style>
