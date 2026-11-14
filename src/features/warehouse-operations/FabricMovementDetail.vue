<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { ArrowLeftRight, ArrowUpRight } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type { FabricIssueGroup, WarehouseDocument } from '@/api/warehouseOperations'
import { formatBusinessDateTime } from '@/lib/dateTime'
import FabricDetailDialog from './FabricDetailDialog.vue'
import { documentProgress, fabricOperationLabel, operationLabels, remaining } from './operations'

const props = defineProps<{ record: WarehouseDocument; issueGroup?: FabricIssueGroup; printError?: string }>()
const emit = defineEmits<{ close: []; print: [] }>()

const entry = computed(() => props.record.data)
const batch = computed(() => props.record.batch_snapshot)
const kind = computed(() => props.record.kind)
const unit = computed(() => entry.value.unit || batch.value?.unit)
const isRequest = computed(() => kind.value === 'REQUEST')
const isTransfer = computed(() => kind.value === 'TRANSFER')
const isLocation = computed(() => kind.value === 'LOCATION_BIND')
const quantityLabel = computed(() => {
  if (isLocation.value) return '核实时结余'
  if (isRequest.value) return '申请数量'
  switch (kind.value) {
    case 'RECEIPT': return '本笔入库'
    case 'ISSUE': return '本笔出库'
    case 'RETURN': return '本笔退料'
    case 'TRANSFER': return '本笔调仓'
    case 'CORRECTION': return '冲销数量'
    case 'OPENING': return '期初数量'
    case 'STOCKTAKE': return '盘点差额'
    default: return '本笔数量'
  }
})
const place = computed(() => entry.value.location || batch.value?.location_label || batch.value?.location)
const lot = computed(() => entry.value.lot || batch.value?.lot)
const roll = computed(() => entry.value.roll_no || batch.value?.roll_no)
const progress = computed(() => documentProgress(props.record))
const status = computed(() => props.record.reversed ? '已冲销' : isLocation.value ? '数量未变' : props.record.closed ? '已关闭' : isRequest.value ? '' : progress.value === '已登记' ? '已登记' : '')
</script>

<template>
  <FabricDetailDialog :title="`${fabricOperationLabel(kind).replace(/^登记/, '')}详情`" :description="`业务日期 ${record.business_date}`"
    :icon="ArrowLeftRight" close-label="关闭业务单据详情" @close="emit('close')">
    <template v-if="status" #status>
      <span class="fabric-detail-badge" :data-tone="record.reversed ? 'warning' : 'posted'">{{ status }}</span>
    </template>
    <section class="fabric-detail-overview" aria-label="业务概览">
      <div class="fabric-detail-identity">
        <h3>{{ entry.item_name || batch?.item_name || entry.source_no || '物料未记录' }}</h3>
        <p v-if="entry.item_code || batch?.item_code">{{ entry.item_code || batch?.item_code }}</p>
      </div>
      <dl v-if="isLocation ? batch?.quantity : entry.quantity" class="fabric-detail-metrics">
        <div><dt>{{ quantityLabel }}</dt><dd><strong>{{ isLocation ? batch?.quantity : entry.quantity }}</strong> <small>{{ unit }}</small></dd></div>
        <template v-if="isRequest">
          <div><dt>已发数量</dt><dd>{{ record.issued_quantity ?? '0' }} {{ unit }}</dd></div>
          <div v-if="!record.closed"><dt>待发数量</dt><dd>{{ remaining(entry.quantity, record.issued_quantity) }} {{ unit }}</dd></div>
        </template>
      </dl>
    </section>

    <p v-if="printError" role="alert" class="fabric-error">{{ printError }}</p>
    <section v-if="kind === 'CORRECTION' || record.reversed || record.close_reason" class="fabric-detail-section">
      <h3>{{ kind === 'CORRECTION' || record.reversed ? '冲销说明' : '关闭说明' }}</h3>
      <p>{{ progress }}</p>
      <p v-if="kind === 'CORRECTION' && entry.reason">{{ entry.reason }}</p>
    </section>

    <section class="fabric-detail-section">
      <h3>{{ isTransfer || isLocation ? '仓位与批次' : '办理明细' }}</h3>
      <dl class="fabric-detail-fields">
        <template v-if="isTransfer || isLocation">
          <div><dt>{{ isTransfer ? '调出仓位' : '核实前仓位' }}</dt><dd>{{ batch?.location_label || batch?.location || '未记录' }}</dd></div>
          <div><dt>{{ isTransfer ? '调入仓位' : '核实后仓位' }}</dt><dd>{{ entry.location || '未记录' }}</dd></div>
        </template>
        <div v-else-if="place"><dt>仓位</dt><dd>{{ place }}</dd></div>
        <div v-if="lot || ((entry.material_category || batch?.material_category) === 'FABRIC' && place)"><dt>缸号 / 批号</dt><dd>{{ lot || '未记录' }}</dd></div>
        <div v-if="roll"><dt>卷号</dt><dd>{{ roll }}</dd></div>
        <div v-if="entry.counterparty"><dt>{{ kind === 'RECEIPT' ? '来源单位' : ['ISSUE', 'REQUEST', 'RETURN'].includes(kind) ? '领用方' : '往来单位' }}</dt><dd>{{ entry.counterparty }}</dd></div>
        <div v-if="entry.source_no"><dt>来源凭证</dt><dd>{{ entry.source_no }}</dd></div>
        <div v-if="entry.production_no"><dt>生产 / 放产单号</dt><dd>{{ entry.production_no }}</dd></div>
        <div v-if="entry.due_date"><dt>需求日期</dt><dd>{{ entry.due_date }}</dd></div>
        <div v-if="entry.purpose"><dt>用途 / 工序</dt><dd>{{ entry.purpose }}</dd></div>
        <div v-if="entry.process_state || batch?.process_state"><dt>加工状态</dt><dd>{{ entry.process_state || batch?.process_state }}</dd></div>
        <div v-if="entry.responsible_person"><dt>确认人</dt><dd>{{ entry.responsible_person }}</dd></div>
        <div v-if="issueGroup" class="wide"><dt>订单配套组</dt><dd>{{ issueGroup.order_no }} · {{ issueGroup.name }}</dd></div>
        <div v-if="entry.reason && kind !== 'CORRECTION'" class="wide"><dt>办理依据</dt><dd>{{ entry.reason }}</dd></div>
        <div v-if="kind === 'QUALITY'"><dt>质检结论</dt><dd>{{ progress }}</dd></div>
        <div v-if="kind === 'CORRECTION' && entry.reversed_kind"><dt>原业务</dt><dd>{{ operationLabels[entry.reversed_kind] }}</dd></div>
        <div><dt>经办人</dt><dd>{{ record.actor_name || '未记录' }}</dd></div>
      </dl>
    </section>

    <section v-if="entry.allocations.length" class="fabric-detail-section">
      <h3>用料分配</h3>
      <dl class="fabric-detail-fields">
        <div v-for="(allocation, index) in entry.allocations" :key="index"><dt>{{ allocation.production_no }}</dt><dd>{{ allocation.quantity }} {{ unit }}</dd></div>
      </dl>
    </section>

    <details class="fabric-detail-section fabric-detail-disclosure">
      <summary>登记与追溯</summary>
      <dl class="fabric-detail-fields fabric-detail-disclosure-body">
        <div><dt>登记时间</dt><dd>{{ formatBusinessDateTime(record.occurred_at) }}</dd></div>
        <div v-if="entry.source_version"><dt>来源版本</dt><dd>{{ entry.source_version }}</dd></div>
        <div class="wide"><dt>本笔记录编号</dt><dd class="fabric-detail-code">{{ record.id }}</dd></div>
        <div v-if="entry.source_line" class="wide"><dt>来源明细编号</dt><dd class="fabric-detail-code">{{ entry.source_line }}</dd></div>
        <div v-if="entry.original_id" class="wide"><dt>关联原单编号</dt><dd class="fabric-detail-code">{{ entry.original_id }}</dd></div>
        <div v-if="entry.task_id" class="wide"><dt>加工任务编号</dt><dd class="fabric-detail-code">{{ entry.task_id }}</dd></div>
        <div v-if="issueGroup" class="wide"><dt>关联领料单</dt><dd class="fabric-detail-code">{{ issueGroup.request_ids.join('、') }}</dd></div>
      </dl>
    </details>
    <template v-if="kind === 'ISSUE' || kind === 'RECEIPT'" #actions>
      <Button v-if="kind === 'ISSUE'" type="button" variant="outline" @click="emit('print')">打印发料单</Button>
      <Button v-else as-child variant="outline">
        <RouterLink :to="{ path: '/modules/pmc-warehouse/fabric-warehouse/receipts', query: { factory: 'huakang-c', view: 'history', receipt: record.receipt_record_id || record.id } }">
          查看入库单详情<ArrowUpRight :size="15" aria-hidden="true" />
        </RouterLink>
      </Button>
    </template>
  </FabricDetailDialog>
</template>
