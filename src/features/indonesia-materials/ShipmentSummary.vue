<script setup lang="ts">
import { computed } from 'vue'
import { Calculator, Package } from '@lucide/vue'
import type { Data } from '@/api/indonesiaMaterials'
import { confirmedShipmentSummary, fixedText } from './presentation'
const props = defineProps<{ shipment: Data }>()
const summary = computed(() => {
  try { return confirmedShipmentSummary(props.shipment) } catch { return null }
})
</script>
<template>
  <section v-if="summary" class="im-shipment-summary">
    <div class="im-summary-strip">
      <div><span>接收方</span><strong>{{ shipment.recipient }}</strong></div>
      <div><span>装箱总数</span><strong>{{ summary.cartons }} <small>箱</small></strong></div>
      <div><span>总净重（含备品）</span><strong>{{ fixedText(summary.net) }} <small>kg</small></strong></div>
      <div><span>总毛重</span><strong>{{ fixedText(summary.gross) }} <small>kg</small></strong></div>
      <div><span>总体积</span><strong>{{ fixedText(summary.cbm, 3) }} <small>m³</small></strong></div>
    </div>
    <div class="im-section-label"><h3><Package :size="16" />出货物料明细</h3><span class="im-note">已确认快照 · 一个物料一行</span></div>
    <div class="im-scroll"><table><thead><tr><th>物料 / 货号</th><th class="im-number">正常数量</th><th class="im-number">免费备品</th><th class="im-number">净重 kg</th><th class="im-number">分摊纸箱 kg</th><th class="im-number">毛重 kg</th><th>包装组</th><th class="im-number">箱数</th><th class="im-number">体积 m³</th></tr></thead>
      <tbody><tr v-for="row in summary.rows" :key="row.code"><td><strong>{{ row.name }}</strong><small>{{ row.code }} · {{ row.items.join(' / ') }}</small><small>{{ row.contracts.join(' / ') }}</small></td><td class="im-number">{{ row.normal }}<small>{{ row.unit }}</small></td><td class="im-number">{{ row.spare }}</td><td class="im-number">{{ fixedText(row.net) }}</td><td class="im-number">{{ fixedText(row.carton) }}</td><td class="im-number"><details class="im-weight-detail"><summary :aria-label="`查看 ${row.code} 毛重计算`">{{ fixedText(row.gross) }}</summary><p>净重 {{ fixedText(row.net) }} + 纸箱 {{ fixedText(row.carton) }} kg</p></details></td><td v-if="row.span" :rowspan="row.span" class="im-merged">{{ row.groupLabels.join(' / ') }}</td><td v-if="row.span" :rowspan="row.span" class="im-merged im-number">{{ row.cartons }}</td><td v-if="row.span" :rowspan="row.span" class="im-merged im-number">{{ fixedText(row.cbm, 3) }}</td></tr></tbody>
      <tfoot><tr><th>本单合计</th><td colspan="2">{{ summary.rows.length }} 款物料</td><td class="im-number">{{ fixedText(summary.net) }}</td><td class="im-number">{{ fixedText(summary.carton) }}</td><td class="im-number">{{ fixedText(summary.gross) }}</td><td>{{ shipment.packages.length }} 组</td><td class="im-number">{{ summary.cartons }}</td><td class="im-number">{{ fixedText(summary.cbm, 3) }}</td></tr></tfoot>
    </table></div>
    <p class="im-table-note"><Calculator :size="15" />毛重含免费备品及分摊纸箱重量；共用混箱的箱数与方数只计一次。</p>
    <div class="im-section-label"><h3>供应商金额汇总</h3><span class="im-note">备品免费，不计采购金额</span></div>
    <div v-if="summary.suppliers" class="im-scroll"><table><thead><tr><th>供应商</th><th>采购币种</th><th>物料款数</th><th class="im-number">采购金额</th></tr></thead><tbody><tr v-for="supplier in summary.suppliers" :key="JSON.stringify([supplier.name, supplier.currency])"><td>{{ supplier.name }}</td><td>{{ supplier.currency }}</td><td>{{ supplier.materials }} 款</td><td class="im-number"><strong>{{ supplier.amount }}</strong></td></tr></tbody></table></div>
    <p v-else class="im-message">此旧版记录未保存供应商金额汇总，请以原版 Excel 为准。</p>
  </section>
  <p v-else class="im-message">此记录未包含完整汇总快照，请查看下方来源明细或下载原版出货文件。</p>
</template>
