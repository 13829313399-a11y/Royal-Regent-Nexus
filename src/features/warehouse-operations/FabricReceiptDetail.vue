<script setup lang="ts">
import { computed, shallowRef, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { DialogClose, DialogContent, DialogDescription, DialogOverlay, DialogPortal, DialogRoot, DialogTitle } from 'reka-ui'
import { ArrowUpRight, Boxes, Check, CircleAlert, ClipboardList, RotateCcw, X } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { formatBusinessDateTime } from '@/lib/dateTime'
import { fabricReceivingApi, materialCategoryLabels, type FabricReceipt, type HandoverReceiptDetail, type ReceiptLineEvidence } from '@/api/fabricReceiving'
import { getApiErrorMessage } from '@/lib/http'
import { quantityText, receiptQuantity } from './receiptQuantities'
import { purchasePriceText } from './purchasePrice'

const props = defineProps<{ record: FabricReceipt }>()
const emit = defineEmits<{ close: [] }>()

const isFabric = computed(() => props.record.material_category === 'FABRIC')
const isHandover = computed(() => props.record.receipt_origin === 'HANDOVER' || !!props.record.handover_document_id)
const handover = shallowRef<HandoverReceiptDetail>()
const handoverLoading = ref(false)
const handoverError = ref('')
const detailAttempt = ref(0)
watch([() => isHandover.value ? props.record.id : undefined, detailAttempt], async ([id], _, onCleanup) => {
  handover.value = undefined
  handoverError.value = ''
  handoverLoading.value = !!id
  if (!id) return

  const controller = new AbortController()
  onCleanup(() => controller.abort())
  try {
    const detail = await fabricReceivingApi.handoverDetail(id, controller.signal)
    if (!controller.signal.aborted) handover.value = detail
  } catch (error) {
    if (!controller.signal.aborted) handoverError.value = getApiErrorMessage(error)
  } finally {
    if (!controller.signal.aborted) handoverLoading.value = false
  }
}, { immediate: true })

const batches = computed(() => handover.value?.batches ?? props.record.batches)
const observation = computed(() => handover.value?.observation)
const correctedBatches = computed(() => handover.value?.batches.filter(batch => batch.reversal) ?? [])
const allReversed = computed(() => handover.value
  ? batches.value.length > 0 && correctedBatches.value.length === batches.value.length
  : !!props.record.reversed)
const partlyReversed = computed(() => correctedBatches.value.length > 0 && !allReversed.value)
const originalQuantity = computed(() => handover.value?.original_quantity ?? props.record.quantity)
const shownQuantity = computed(() => partlyReversed.value ? handover.value?.effective_quantity : originalQuantity.value)
const zeroReceipt = computed(() => props.record.stock_posted === false && receiptQuantity(props.record.quantity) === 0n)
const status = computed(() => {
  if (allReversed.value) return { label: '已冲销 · 原单保留', tone: 'reversed', icon: RotateCcw }
  if (partlyReversed.value) return { label: '部分批次已冲销', tone: 'warning', icon: RotateCcw }
  if (zeroReceipt.value) return { label: '零入库差异单', tone: 'warning', icon: CircleAlert }
  return { label: '已入库', tone: 'posted', icon: Check }
})

type DifferenceLine = Omit<ReceiptLineEvidence, 'batch_id' | 'shortage_quantity' | 'shortage_scope' | 'returned_to_supplier' | 'disposition'>
  & Partial<Pick<ReceiptLineEvidence, 'returned_to_supplier' | 'disposition'>>
const differenceLines = computed<DifferenceLine[]>(() => observation.value?.parts ?? props.record.receipt_lines ?? [])
const hasDifference = computed(() => !!observation.value || (!!differenceLines.value.length &&
  [props.record.shortage_quantity, props.record.returned_to_supplier].some(value => (receiptQuantity(value ?? '') ?? 0n) > 0n)))
const summary = computed(() => {
  const evidence = observation.value ?? props.record
  return [
    { label: '送货量', value: evidence.delivered_quantity },
    { label: '实点合计', value: evidence.counted_quantity },
    { label: correctedBatches.value.length ? '原入库合计' : '入库合计', value: observation.value ? originalQuantity.value : props.record.accepted_quantity },
    { label: '短少', value: evidence.shortage_quantity, difference: true },
    { label: '破损合计', value: evidence.damaged_quantity, difference: true },
    { label: '拒收合计', value: evidence.rejected_quantity, difference: true },
    { label: '其他不可用合计', value: evidence.other_unusable_quantity, difference: true },
    ...(!isHandover.value ? [{ label: '退供应商合计', value: props.record.returned_to_supplier, difference: true }] : []),
  ]
})
const differenceColumns = [
  { key: 'counted_quantity', label: '实点' },
  { key: 'damaged_quantity', label: '破损' },
  { key: 'rejected_quantity', label: '拒收' },
  { key: 'other_unusable_quantity', label: '其他不可用' },
  { key: 'accepted_quantity', label: '入库' },
] as const

function displayedQuantity(value?: string | null) {
  if (value == null || value === '') return '—'
  const quantity = receiptQuantity(value)
  return quantity === undefined ? value : quantityText(quantity)
}
</script>

<template>
  <DialogRoot :open="true" @update:open="open => { if (!open) emit('close') }">
    <DialogPortal>
      <DialogOverlay class="receipt-detail-overlay" />
      <DialogContent class="receipt-detail-panel" aria-modal="true">
        <header class="receipt-detail-header">
          <span class="receipt-detail-header-icon"><ClipboardList :size="22" aria-hidden="true" /></span>
          <div class="receipt-detail-heading">
            <DialogTitle>入库单详情</DialogTitle>
            <DialogDescription>{{ isHandover ? '送货单 / 扫码入库' : '手动入库' }} · 收货日期 {{ record.receipt_date }}</DialogDescription>
          </div>
          <span class="receipt-detail-status" :data-tone="status.tone">
            <component :is="status.icon" :size="14" aria-hidden="true" />{{ status.label }}
          </span>
          <DialogClose as-child>
            <Button class="receipt-detail-close" type="button" variant="ghost" size="icon" aria-label="关闭入库详情">
              <X :size="20" aria-hidden="true" />
            </Button>
          </DialogClose>
        </header>

        <div class="receipt-detail-body" role="region" aria-label="入库详情正文" tabindex="0">
          <section class="receipt-detail-overview">
            <div class="receipt-detail-material">
              <p>{{ materialCategoryLabels[record.material_category] || '分类未注明' }} · {{ record.facts.material_code || '未填编码' }}</p>
              <h3>{{ record.facts.material_name || '未填物料名称' }}</h3>
            </div>
            <dl class="receipt-detail-metrics">
              <div class="receipt-detail-main-metric">
                <dt>{{ isHandover && !handover?.has_posting ? (allReversed ? '所选批次原入库' : '所选批次入库') : allReversed ? '原入库数量' : partlyReversed ? '未冲销入库量' : '本次入库' }}</dt>
                <dd><strong>{{ displayedQuantity(shownQuantity) }}</strong> <small>{{ record.unit }}</small></dd>
                <p v-if="partlyReversed" class="receipt-detail-hint">原入库 {{ displayedQuantity(originalQuantity) }} {{ record.unit }}</p>
              </div>
              <div>
                <dt>实物明细</dt>
                <dd><strong>{{ isHandover ? batches.length : (record.receipt_lines?.length || batches.length) }}</strong> <small>项</small></dd>
              </div>
            </dl>
          </section>

          <p v-if="zeroReceipt" class="receipt-detail-alert">
            <CircleAlert :size="17" aria-hidden="true" />
            <span>本次入库 0，全部为差异/退供应商。请在差异明细核对本次实点及退回数量。</span>
          </p>
          <p v-if="handoverLoading" class="receipt-detail-hint" role="status">正在核对同次收货的分仓与差异…</p>
          <div v-else-if="handoverError" class="receipt-detail-alert" role="alert">
            <CircleAlert :size="17" aria-hidden="true" />
            <span>本次收货汇总读取失败，以下显示所选批次。{{ handoverError }}</span>
            <Button type="button" size="sm" variant="outline" @click="detailAttempt++">重试</Button>
          </div>
          <p v-else-if="handover && !handover.has_posting" class="receipt-detail-hint">
            这笔记录缺少同次收货凭证，以下显示所选批次。
          </p>

          <section v-if="record.reversal && !handover" class="receipt-detail-card receipt-detail-reversal">
            <h3><RotateCcw :size="17" aria-hidden="true" />{{ isHandover ? '批次冲销记录' : '整单冲销记录' }}</h3>
            <dl class="receipt-detail-fields">
              <div><dt>冲销日期</dt><dd>{{ record.reversal.date }}</dd></div>
              <div><dt>经办人</dt><dd>{{ record.reversal.actor_name || '—' }}</dd></div>
              <div class="wide"><dt>冲销原因</dt><dd>{{ record.reversal.reason || '—' }}</dd></div>
              <div class="wide"><dt>冲销单号</dt><dd class="receipt-detail-code">{{ record.reversal.id }}</dd></div>
            </dl>
          </section>

          <div class="receipt-detail-grid">
            <section v-if="batches.length" class="receipt-detail-card receipt-detail-batches">
              <div class="receipt-detail-section-title">
                <h3><Boxes :size="17" aria-hidden="true" />实物批次明细</h3>
                <span v-if="handover?.has_posting && batches.length > 1">同一次收货 · {{ batches.length }} 个入库批次</span>
                <span v-else>{{ batches.length }} 个入库批次</span>
              </div>
              <table aria-label="入库批次明细" class="receipt-detail-batch-table">
                <thead>
                  <tr>
                    <th scope="col">仓位</th>
                    <th v-if="isFabric" scope="col">缸号 / 卷号</th>
                    <th scope="col" class="numeric">入库数量</th>
                    <th scope="col">入库时质量</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="batch in batches" :key="batch.id">
                    <td>
                      <strong>{{ batch.location || '—' }}</strong>
                      <small v-if="handover && batches.length > 1">
                        <template v-if="batch.id === record.id">当前批次</template>
                        <RouterLink v-else class="receipt-detail-batch-link"
                          :to="{ path: '/modules/pmc-warehouse/fabric-warehouse/receipts', query: { factory: 'huakang-c', view: 'history', receipt: batch.id } }"
                          :aria-label="`查看批次 ${batch.id} 的入库记录`">批次记录</RouterLink>
                      </small>
                    </td>
                    <td v-if="isFabric">{{ batch.dye_lot || '—' }}<small>卷号 {{ batch.roll_no || '—' }}</small></td>
                    <td class="numeric">
                      <strong>{{ displayedQuantity(batch.quantity) }}</strong> {{ record.unit }}
                      <small v-if="batch.reversal">已冲销</small>
                    </td>
                    <td><span class="receipt-detail-quality">待检</span></td>
                  </tr>
                </tbody>
              </table>
              <p v-if="handover?.has_posting && !hasDifference" class="receipt-detail-hint">本次收货未登记实点和差异数据。</p>
              <p v-else class="receipt-detail-hint">这里显示入库时的质量状态。后续质检和结余可到库存台账查看。</p>
            </section>
            <section v-else-if="!zeroReceipt" class="receipt-detail-card">
              <h3><Boxes :size="17" aria-hidden="true" />实物批次明细</h3>
              <p class="receipt-detail-hint">这笔单据没有记录批次明细。</p>
            </section>

            <section class="receipt-detail-card receipt-detail-source">
              <h3>收货与采购来源</h3>
              <dl class="receipt-detail-fields">
                <div class="receipt-detail-supplier"><dt>供应商</dt><dd>{{ record.facts.supplier || '—' }}</dd></div>
                <div><dt>采购单号</dt><dd>{{ record.facts.order_no || '—' }}</dd></div>
                <div><dt>送货依据</dt><dd>{{ record.delivery_reference || '—' }}</dd></div>
                <div v-if="record.purchase_status">
                  <dt>采购归属</dt>
                  <dd><span v-if="record.purchase_status === 'PENDING'" class="receipt-detail-quality">采购待核对</span><template v-else>已补关联采购</template></dd>
                </div>
                <div v-if="record.facts.source_category"><dt>采购类型</dt><dd>{{ record.facts.source_category === 'SUPPLEMENT' ? '补数追货' : '正常采购' }}</dd></div>
                <div v-if="record.procurement_pending_reason" class="wide"><dt>原采购待核对原因</dt><dd>{{ record.procurement_pending_reason }}</dd></div>
                <div v-if="record.delivery_quantity != null && record.delivery_quantity !== ''">
                  <dt>本单该采购明细到货量</dt><dd>{{ displayedQuantity(record.delivery_quantity) }} {{ record.unit }}</dd>
                </div>
                <div><dt>记账月份</dt><dd>{{ record.accounting_month || '—' }}</dd></div>
                <div v-if="record.facts.production_no"><dt>生产 / 放产单号</dt><dd>{{ record.facts.production_no }}</dd></div>
                <div v-if="record.facts.plan_no"><dt>计划跟踪号</dt><dd>{{ record.facts.plan_no }}</dd></div>
                <div v-if="record.facts.contract_no"><dt>合同号</dt><dd>{{ record.facts.contract_no }}</dd></div>
              </dl>
            </section>

            <section v-if="hasDifference" class="receipt-detail-card receipt-detail-wide receipt-differences">
              <h3><CircleAlert :size="17" aria-hidden="true" />本次收货差异</h3>
              <dl class="receipt-detail-difference-summary">
                <div v-for="item in summary" :key="item.label"
                  :class="{ 'is-difference': item.difference && (receiptQuantity(item.value ?? '') ?? 0n) > 0n }">
                  <dt>{{ item.label }}</dt>
                  <dd>{{ item.value == null || item.value === '' ? '—' : `${displayedQuantity(item.value)} ${record.unit}` }}</dd>
                </div>
              </dl>
              <p class="receipt-detail-hint" v-if="observation && !observation.complete">
                部分批次只登记了入库数量。下表显示已记录的实点和差异，未完整登记的合计留空。
              </p>
              <p class="receipt-detail-hint" v-else-if="!isHandover">短少按整单记录。各项不可用量已当场退供应商。</p>
              <div class="receipt-detail-difference-scroll" tabindex="0" role="region" :aria-label="isFabric ? '逐卷差异' : '逐项差异'">
                <table class="receipt-detail-difference-table" :class="{ 'receipt-detail-observed-table': isHandover }">
                  <thead>
                    <tr>
                      <th scope="col">{{ isFabric ? '仓位 / 缸号 / 卷号' : '仓位' }}</th>
                      <th v-for="column in differenceColumns" :key="column.key" scope="col" class="numeric">{{ column.label }}</th>
                      <th v-if="!isHandover" scope="col" class="numeric">退供应商</th>
                      <th v-if="!isHandover" scope="col">去向</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(line, index) in differenceLines" :key="index">
                      <td>{{ line.location || '—' }}<small v-if="isFabric">{{ line.dye_lot || '—' }} / {{ line.roll_no || '—' }}</small></td>
                      <td v-for="column in differenceColumns" :key="column.key" class="numeric">{{ displayedQuantity(line[column.key]) }}</td>
                      <td v-if="!isHandover" class="numeric">{{ displayedQuantity(line.returned_to_supplier) }}</td>
                      <td v-if="!isHandover">{{ line.disposition === 'RETURNED_TO_SUPPLIER' ? '不可用量当场退供应商' : '可用量入库' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>

            <section class="receipt-detail-card">
              <h3>本次单价与金额</h3>
              <dl class="receipt-detail-fields">
                <div><dt>{{ isHandover ? '原送货单价' : '入库单价' }} / 计价单位</dt><dd>{{ record.unit_price || '未记录' }} / {{ record.price_unit || '未注明' }}</dd></div>
                <div><dt>币种</dt><dd>{{ record.currency || '未注明' }}</dd></div>
                <div><dt>本次金额合计</dt><dd>{{ record.amount ? `${record.amount} ${record.currency ?? ''}`.trim() : '未记录' }}</dd></div>
                <div v-if="record.purchase_price">
                  <dt>追货表采购参考单价</dt>
                  <dd>{{ purchasePriceText(record.purchase_price.unit_price, record.purchase_price.price_unit) }}</dd>
                </div>
                <div class="wide"><dt>价格依据</dt><dd>{{ record.price_basis || '本次入库单价未记录' }}</dd></div>
              </dl>
            </section>

            <section class="receipt-detail-card">
              <h3>登记与追溯</h3>
              <dl class="receipt-detail-fields">
                <div><dt>登记人</dt><dd>{{ record.actor_name || '—' }}</dd></div>
                <div><dt>登记时间</dt><dd>{{ formatBusinessDateTime(record.occurred_at) }}</dd></div>
                <div><dt>{{ isHandover ? '所选入库批次编号' : '完整入库单号' }}</dt><dd class="receipt-detail-code">{{ record.id }}</dd></div>
                <div v-if="record.source_revision"><dt>采购来源版本</dt><dd>第 {{ record.source_revision }} 版</dd></div>
                <div v-if="record.operation_id && record.source_version"><dt>原单版本</dt><dd>{{ record.source_version }}</dd></div>
                <div class="wide"><dt>来源明细编号</dt><dd class="receipt-detail-code">{{ record.source_line_id || '—' }}</dd></div>
              </dl>
            </section>
          </div>

          <section v-if="correctedBatches.length" class="receipt-detail-card receipt-detail-reversal">
            <h3><RotateCcw :size="17" aria-hidden="true" />批次冲销记录</h3>
            <dl v-for="batch in correctedBatches" :key="batch.id" class="receipt-detail-fields">
              <div><dt>原批次</dt><dd>{{ batch.location }} · {{ displayedQuantity(batch.quantity) }} {{ record.unit }}</dd></div>
              <div><dt>原批次编号</dt><dd class="receipt-detail-code">{{ batch.id }}</dd></div>
              <div><dt>冲销日期 / 经办人</dt><dd>{{ batch.reversal?.date }} / {{ batch.reversal?.actor_name || '—' }}</dd></div>
              <div><dt>冲销单号</dt><dd class="receipt-detail-code">{{ batch.reversal?.id }}</dd></div>
              <div class="wide"><dt>冲销原因</dt><dd>{{ batch.reversal?.reason || '—' }}</dd></div>
            </dl>
          </section>

          <section v-if="record.difference_reason || record.note" class="receipt-detail-card">
            <h3>补充说明</h3>
            <dl class="receipt-detail-fields">
              <div v-if="record.difference_reason" class="wide"><dt>超收说明</dt><dd>{{ record.difference_reason }}</dd></div>
              <div v-if="record.note" class="wide"><dt>备注</dt><dd>{{ record.note }}</dd></div>
            </dl>
          </section>
        </div>

        <footer class="receipt-detail-footer">
          <div class="receipt-detail-footer-links">
            <Button v-if="record.handover_document_id" as-child variant="soft">
              <RouterLink :to="{ path: '/modules/pmc-warehouse/material-handover', query: { factory: 'huakang-c', tab: 'documents', document: record.handover_document_id } }">
                查看原送货单<ArrowUpRight :size="15" aria-hidden="true" />
              </RouterLink>
            </Button>
            <Button as-child variant="outline">
              <RouterLink :to="{ path: '/modules/pmc-warehouse/fabric-warehouse/inventory', query: { factory: 'huakang-c', view: 'stock' } }">
                查看当前库存<ArrowUpRight :size="15" aria-hidden="true" />
              </RouterLink>
            </Button>
          </div>
          <DialogClose as-child><Button type="button" variant="ghost">关闭详情</Button></DialogClose>
        </footer>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style scoped>
.receipt-detail-overlay {
  position: fixed;
  inset: 0;
  z-index: 140;
  background: rgb(15 23 42 / 43%);
}

.receipt-detail-panel {
  --detail-gutter: 24px;
  --detail-gap: 12px;
  --detail-warning: #92400e;
  --detail-warning-bg: #fffbeb;
  --detail-warning-border: #fde68a;
  position: fixed;
  inset: 0;
  z-index: 150;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  width: min(1120px, calc(100% - 48px));
  height: fit-content;
  max-height: min(840px, calc(100dvh - 48px));
  margin: auto;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 16px;
  outline: none;
  background: var(--card);
  color: var(--card-foreground);
  box-shadow: 0 24px 72px rgb(15 23 42 / 24%);
}

.receipt-detail-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px var(--detail-gutter);
  border-bottom: 1px solid var(--border);
}
.receipt-detail-header-icon {
  display: grid;
  flex: 0 0 42px;
  place-items: center;
  height: 42px;
  border-radius: 10px;
  background: var(--accent);
  color: var(--primary);
}
.receipt-detail-heading { flex: 1; min-width: 0; }
.receipt-detail-heading h2 { font-size: 20px; font-weight: 650; line-height: 1.4; }
.receipt-detail-heading p { margin-top: 3px; color: var(--muted-foreground); font-size: 12px; line-height: 1.5; }
.receipt-detail-status {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 5px;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--muted);
  color: var(--foreground);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.4;
}
.receipt-detail-status[data-tone='posted'] { background: var(--accent); color: var(--primary); }
.receipt-detail-status[data-tone='warning'], .receipt-detail-quality {
  border-color: var(--detail-warning-border);
  background: var(--detail-warning-bg);
  color: var(--detail-warning);
}

.receipt-detail-body {
  display: flex;
  flex-direction: column;
  gap: var(--detail-gap);
  overflow: auto;
  overscroll-behavior: contain;
  padding: var(--detail-gap) var(--detail-gutter);
  background: var(--background);
}
.receipt-detail-overview {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 16px 24px;
  padding: 12px 18px;
  border: 1px solid var(--border);
  border-left: 3px solid var(--primary);
  border-radius: 10px;
  background: var(--card);
}
.receipt-detail-material p { color: var(--muted-foreground); font-size: 12px; overflow-wrap: anywhere; }
.receipt-detail-material h3 { margin-top: 4px; font-size: 19px; font-weight: 650; line-height: 1.5; overflow-wrap: anywhere; }
.receipt-detail-metrics { display: flex; gap: 24px; margin: 0; }
.receipt-detail-metrics > div { min-width: 74px; padding-left: 20px; border-left: 1px solid var(--border); }
.receipt-detail-metrics dt { color: var(--muted-foreground); font-size: 12px; }
.receipt-detail-metrics dd { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 6px; margin: 3px 0 0; }
.receipt-detail-metrics strong { font-size: 26px; font-weight: 650; font-variant-numeric: tabular-nums; line-height: 1.25; overflow-wrap: anywhere; }
.receipt-detail-main-metric strong { color: var(--primary); }
.receipt-detail-metrics small { color: var(--muted-foreground); font-size: 12px; }

.receipt-detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--detail-gap);
}
.receipt-detail-wide, .receipt-detail-source:first-child { grid-column: 1 / -1; }
.receipt-detail-card {
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--card);
}
.receipt-detail-card h3 { display: flex; align-items: center; gap: 7px; font-size: 15px; font-weight: 650; line-height: 1.5; }
.receipt-detail-card h3 svg { flex: none; color: var(--primary); }
.receipt-detail-section-title { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 4px 12px; }
.receipt-detail-section-title > span, .receipt-detail-hint { color: var(--muted-foreground); font-size: 12px; }
.receipt-detail-hint { margin-top: 9px; line-height: 1.55; }
.receipt-detail-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 14px;
  margin: 9px 0 0;
}
.receipt-detail-fields .wide { grid-column: 1 / -1; }
.receipt-detail-fields dt { color: var(--muted-foreground); font-size: 12px; line-height: 1.45; }
.receipt-detail-fields dd {
  margin: 3px 0 0;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.receipt-detail-code { font-family: var(--font-mono, monospace); }

.receipt-detail-batch-table, .receipt-detail-difference-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  text-align: left;
  font-size: 13px;
  line-height: 1.5;
}
.receipt-detail-batch-table { table-layout: fixed; margin-top: 8px; }
.receipt-detail-batch-table th, .receipt-detail-difference-table th {
  padding: 7px 10px;
  background: var(--muted);
  color: var(--muted-foreground);
  font-size: 12px;
  font-weight: 600;
}
.receipt-detail-batch-table th:first-child { border-radius: 6px 0 0 6px; }
.receipt-detail-batch-table th:last-child { border-radius: 0 6px 6px 0; }
.receipt-detail-batch-table td, .receipt-detail-difference-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
  overflow-wrap: anywhere;
}
.receipt-detail-batch-table .numeric, .receipt-detail-difference-table .numeric { text-align: right; font-variant-numeric: tabular-nums; }
.receipt-detail-batch-table small, .receipt-detail-difference-table small { display: block; margin-top: 3px; color: var(--muted-foreground); font-size: 11px; }
.receipt-detail-batch-link { color: var(--primary); text-decoration: underline; text-underline-offset: 2px; }
.receipt-detail-quality { display: inline-block; padding: 1px 6px; border-style: solid; border-width: 1px; border-radius: 4px; font-size: 11px; }

.receipt-detail-alert {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--detail-warning-border);
  border-radius: 8px;
  background: var(--detail-warning-bg);
  color: var(--detail-warning);
  font-size: 13px;
  line-height: 1.6;
}
.receipt-detail-alert svg { flex: none; margin-top: 2px; }
.receipt-detail-reversal { border-left: 3px solid var(--muted-foreground); }
.receipt-detail-reversal h3 svg { color: var(--muted-foreground); }
.receipt-detail-reversal dl + dl { padding-top: 12px; border-top: 1px solid var(--border); }
.receipt-differences h3 svg { color: var(--detail-warning); }
.receipt-detail-difference-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  margin: 12px 0 0;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--border);
}
.receipt-detail-difference-summary > div { min-width: 0; padding: 8px 10px; background: var(--card); }
.receipt-detail-difference-summary > :last-child:nth-child(odd) { grid-column: span 2; }
.receipt-detail-difference-summary dt { color: var(--muted-foreground); font-size: 12px; }
.receipt-detail-difference-summary dd { margin: 3px 0 0; font-size: 14px; font-weight: 600; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.receipt-detail-difference-summary .is-difference { background: var(--detail-warning-bg); }
.receipt-detail-difference-summary .is-difference dd { color: var(--detail-warning); }
.receipt-detail-difference-scroll { margin-top: 10px; overflow-x: auto; border: 1px solid var(--border); border-radius: 8px; }
.receipt-detail-difference-table { min-width: 570px; }
.receipt-detail-observed-table { min-width: 448px; }
.receipt-detail-difference-table .numeric { white-space: nowrap; }
.receipt-detail-difference-table tbody tr:last-child td { border-bottom: 0; }

.receipt-detail-footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 12px;
  padding: 10px var(--detail-gutter);
  border-top: 1px solid var(--border);
  background: var(--card);
}
.receipt-detail-footer-links { display: flex; flex-wrap: wrap; gap: 8px; }
.receipt-detail-panel :is(a, button, [tabindex]):focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
.receipt-detail-panel .receipt-detail-body:focus-visible { outline-offset: -2px; }

@media (min-width: 1280px) {
  .receipt-detail-source .receipt-detail-fields { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .receipt-detail-difference-summary {
    grid-template-columns: none;
    grid-auto-flow: column;
    grid-auto-columns: minmax(0, 1fr);
  }
  .receipt-detail-difference-summary > :last-child:nth-child(odd) { grid-column: auto; }
}

@media (max-width: 940px) {
  .receipt-detail-grid { grid-template-columns: minmax(0, 1fr); }
  .receipt-detail-supplier { grid-column: 1 / -1; }
}

@media (max-width: 700px) {
  .receipt-detail-panel {
    --detail-gutter: 16px;
    width: 100%;
    height: 100dvh;
    max-height: none;
    border: 0;
    border-radius: 0;
  }
  .receipt-detail-header { gap: 8px; padding-top: max(12px, env(safe-area-inset-top)); padding-bottom: 12px; }
  .receipt-detail-header-icon { display: none; }
  .receipt-detail-heading h2 { font-size: 18px; }
  .receipt-detail-close, .receipt-detail-footer :is(a, button) { min-height: 44px; }
  .receipt-detail-close { min-width: 44px; }
  .receipt-detail-overview { grid-template-columns: minmax(0, 1fr); gap: 12px; padding: 14px; }
  .receipt-detail-material h3 { font-size: 17px; }
  .receipt-detail-metrics { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, .55fr); gap: 12px; }
  .receipt-detail-metrics > div { min-width: 0; padding: 0; border: 0; }
  .receipt-detail-card { padding: 12px; }
  .receipt-detail-fields { gap: 10px 12px; }
  .receipt-detail-batch-table th, .receipt-detail-batch-table td { padding: 8px 5px; overflow-wrap: anywhere; }
  .receipt-detail-difference-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .receipt-detail-footer { padding-bottom: max(10px, env(safe-area-inset-bottom)); }
  .receipt-detail-footer-links { flex: 1; }
  .receipt-detail-footer-links a { flex: 1 1 auto; }
}

@media (max-width: 440px) {
  .receipt-detail-header { display: grid; grid-template-columns: minmax(0, 1fr) auto; }
  .receipt-detail-heading { grid-column: 1; grid-row: 1; }
  .receipt-detail-close { grid-column: 2; grid-row: 1 / 3; align-self: start; }
  .receipt-detail-status { grid-column: 1; grid-row: 2; justify-self: start; }
  .receipt-detail-footer-links { flex-basis: 100%; }
  .receipt-detail-footer-links a { padding-inline: 8px; }
  .receipt-detail-footer > button { display: none; }
}
</style>
