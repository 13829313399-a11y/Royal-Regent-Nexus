<script setup lang="ts">
import { computed } from 'vue'
import type { HandoverDocument } from '@/api/materialHandover'

const props = defineProps<{ document: HandoverDocument; qrUrl: string }>()
const data = computed(() => props.document.data)
const delivery = computed(() => data.value.kind === 'DELIVERY')
const status = { DRAFT: '草稿 · 仅供校对', CONFIRMED: '已确认', VOID: '已作废 · 仅供查阅' }
</script>

<template>
  <section class="handover-summary-print">
    <table class="summary-table" aria-label="交接明细">
      <colgroup>
        <col style="width: 15%" />
        <col style="width: 26%" />
        <col style="width: 13%" />
        <col style="width: 16%" />
        <col style="width: 12%" />
        <col style="width: 18%" />
      </colgroup>
      <thead>
        <tr>
          <td class="summary-heading-cell" colspan="6">
            <header class="summary-heading">
              <div class="summary-identity">
                <img v-if="qrUrl && document.status === 'CONFIRMED'" :src="qrUrl" alt="交接单二维码" class="print-qr" />
                <div>
                  <p class="summary-kicker">统一明细（备用） · {{ status[document.status] }}</p>
                  <h2>{{ delivery ? '供应商送货交接单' : '领料交接单' }}</h2>
                  <p><span class="summary-label">{{ delivery ? '供应商' : '领用方' }}</span> {{ data.counterparty }}</p>
                </div>
              </div>
              <div class="summary-meta">
                <p class="summary-label">原单号</p>
                <p class="summary-number">{{ data.source_no || '待补' }}</p>
                <p><span class="summary-label">{{ delivery ? '送货日期' : '单据日期' }}</span> {{ data.document_date || '待补' }}</p>
                <p v-if="document.code" class="summary-code">交接码 {{ document.code }}</p>
              </div>
            </header>
            <div v-if="data.purchase_order_no || data.contract_no || data.production_no || data.product_no" class="summary-references">
              <span v-if="data.purchase_order_no">采购订单号 {{ data.purchase_order_no }}</span>
              <span v-if="data.contract_no">合同 {{ data.contract_no }}</span>
              <span v-if="data.production_no">生产单 {{ data.production_no }}</span>
              <span v-if="data.product_no">货号 {{ data.product_no }}</span>
            </div>
          </td>
        </tr>
        <tr class="summary-columns">
          <th scope="col">物料编码</th>
          <th scope="col">物料名称 / 规格</th>
          <th scope="col" class="summary-quantity">{{ document.status === 'CONFIRMED' ? '确认数量' : '单据数量' }}</th>
          <th scope="col">缸号 / 卷号</th>
          <th scope="col">参考单价</th>
          <th scope="col">原单依据 / 生产关联</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="line in data.lines" :key="line.id">
          <td>{{ line.item_code }}</td>
          <td>
            <strong class="summary-material">{{ line.item_name }}</strong>
            <span v-if="line.specification || line.color" class="summary-secondary">{{ [line.specification, line.color].filter(Boolean).join(' · ') }}</span>
          </td>
          <td class="summary-quantity"><strong>{{ line.quantity }}</strong> <span>{{ line.unit }}</span></td>
          <td>
            <span v-if="line.lot">缸 {{ line.lot }}</span>
            <span v-if="line.roll_no" class="summary-secondary">卷 {{ line.roll_no }}</span>
            <span v-if="line.roll_quantities" class="summary-secondary">{{ line.roll_quantities }}</span>
            <span v-if="!line.lot && !line.roll_no && !line.roll_quantities">-</span>
          </td>
          <td>
            <span>{{ line.unit_price || '未记录' }}</span>
            <span v-if="line.currency || line.price_unit" class="summary-secondary">{{ [line.currency, line.price_unit].filter(Boolean).join(' / ') }}</span>
          </td>
          <td>
            <span v-if="line.purchase_order_no" class="summary-secondary">采购单 {{ line.purchase_order_no }}</span>
            <span v-if="line.ordered_quantity" class="summary-secondary">下单 {{ line.ordered_quantity }} {{ line.unit }}</span>
            <span v-if="line.production_no" class="summary-secondary">生产单 {{ line.production_no }}</span>
            <span v-if="line.price_note" class="summary-secondary">{{ line.price_note }}</span>
            <span v-if="line.note" class="summary-secondary">{{ line.note }}</span>
          </td>
        </tr>
      </tbody>
    </table>
    <footer class="summary-footer">
      <section v-if="delivery && document.status === 'CONFIRMED'" class="summary-signoff" aria-label="现场签收">
        <div class="summary-signoff-heading">
          <h3>现场签收</h3>
          <span v-if="data.source_no">原单号 {{ data.source_no }}</span>
        </div>
        <div class="summary-signatures">
          <div>送货人签字</div>
          <div>收货人签字</div>
          <div>签收日期</div>
        </div>
        <p class="summary-signoff-note">签收备注</p>
      </section>
      <p class="summary-disclaimer">数量以仓库实际点收 / 实发记录为准。参考单价是原单依据，付款金额需另行核对。</p>
    </footer>
  </section>
</template>

<style scoped>
.handover-summary-print { display: none; }

@media print {
  .handover-summary-print {
    display: block;
    background: #fff;
    color: #172320;
    font: 10.5pt/1.35 "Microsoft YaHei", "Noto Sans CJK SC", "PingFang SC", Arial, sans-serif;
    overflow-wrap: anywhere;
  }

  .handover-summary-print :is(p, h2, h3) { margin: 0; }
  .summary-table { width: 100%; table-layout: fixed; border-collapse: collapse; text-align: left; }
  .summary-table thead { display: table-header-group; }
  .summary-table tr { break-inside: avoid; }
  .summary-heading-cell { padding: 0 0 4mm; }

  .summary-heading {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 35%);
    align-items: center;
    gap: 6mm;
    padding-bottom: 3mm;
    border-bottom: 0.8pt solid #253732;
  }

  .summary-identity { display: flex; align-items: center; gap: 3mm; }
  .summary-identity > div { min-width: 0; }
  .print-qr { display: block; flex: none; width: 22mm; height: 22mm; }
  .summary-heading h2 { margin: 0.5mm 0 1mm; font-size: 19pt; line-height: 1.18; font-weight: 700; }
  .summary-kicker, .summary-label, .summary-references { color: #364640; font-size: 9.5pt; }
  .summary-meta { text-align: right; }
  .summary-number { font-size: 12.5pt; font-weight: 700; font-variant-numeric: tabular-nums; }
  .summary-code { color: #364640; font-size: 8pt; }
  .summary-references { display: flex; flex-wrap: wrap; gap: 1mm 5mm; margin-top: 2mm; }

  .summary-columns th {
    padding: 2.2mm;
    background: #edf1ef;
    border-top: 0.75pt solid #586862;
    border-bottom: 0.75pt solid #586862;
    font-size: 10pt;
    font-weight: 700;
    print-color-adjust: exact;
  }

  .summary-table tbody td { padding: 2.8mm 2.2mm; vertical-align: top; border-bottom: 0.5pt solid #a8b4af; }
  .summary-material { font-size: 11.5pt; }
  .summary-secondary { display: block; color: #364640; font-size: 9pt; white-space: pre-line; }
  .summary-quantity { text-align: right; font-variant-numeric: tabular-nums; }
  .summary-quantity strong { font-size: 12.5pt; }

  .summary-footer { margin-top: 5mm; break-inside: avoid; break-before: avoid; }
  .summary-signoff { padding: 3mm; border: 0.75pt solid #71817b; }
  .summary-signoff-heading { display: flex; justify-content: space-between; gap: 4mm; }
  .summary-signoff-heading h3 { flex: none; font-size: 11pt; }
  .summary-signoff-heading span { color: #364640; font-size: 9pt; text-align: right; }
  .summary-signatures { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 5mm; margin: 2mm 0 3mm; }
  .summary-signatures div, .summary-signoff-note { min-height: 11mm; border-bottom: 0.5pt solid #71817b; }
  .summary-disclaimer { margin-top: 2mm !important; color: #364640; font-size: 9pt; }
}
</style>
