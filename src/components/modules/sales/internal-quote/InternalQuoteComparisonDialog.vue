<script setup lang="ts">
import { BarChart3, X } from '@lucide/vue'
import { computed } from 'vue'
import { buildInternalQuoteComparison, type InternalQuoteComparisonState } from '@/lib/internalQuoteComparison'
import type { InternalQuote } from '@/types/internalQuoteDesk'

const props = defineProps<{
  open: boolean
  quotes: InternalQuote[]
  factoryName: string
}>()

const emit = defineEmits<{ close: [] }>()
const comparison = computed(() => buildInternalQuoteComparison(props.quotes))

const stateLabels: Record<InternalQuoteComparisonState, string> = {
  valid: '',
  not_applicable: '不适用',
  not_participating: '未参与',
  invalid: '暂无有效计算',
}

function money(value: number | null) {
  return value == null ? '—' : value.toFixed(4)
}

function signedMoney(value: number | null) {
  if (value == null) return '不可比较'
  if (Math.abs(value) < .00005) return '与基准相同'
  return `较基准 ${value > 0 ? '+' : ''}${value.toFixed(4)}`
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="quote-comparison-backdrop" @click.self="emit('close')" @keydown.esc="emit('close')">
      <section class="quote-comparison-dialog" role="dialog" aria-modal="true" aria-labelledby="quote-comparison-title" tabindex="-1">
        <header>
          <div class="quote-comparison-title-icon"><BarChart3 aria-hidden="true" /></div>
          <div class="quote-comparison-title-copy">
            <span>{{ factoryName }} · 已选 {{ quotes.length }} 张</span>
            <h2 id="quote-comparison-title">报价分段金额对比</h2>
            <p>第一张为比较基准；金额单位为 HKD / PCS，差距范围为该分段最高金额减最低金额。</p>
          </div>
          <button type="button" class="quote-comparison-close" aria-label="关闭报价对比" @click="emit('close')"><X aria-hidden="true" /></button>
        </header>

        <div class="quote-comparison-quotes">
          <article v-for="(quote, index) in quotes" :key="quote.id" :class="{ baseline: index === 0 }">
            <span>{{ index === 0 ? '基准报价' : `对比 ${index}` }}</span>
            <strong>{{ quote.quoteNo }} · {{ quote.versionLabel }}</strong>
            <small>{{ quote.productName }} / {{ quote.customer }} · 数量 {{ quote.quantity.toLocaleString() }}</small>
          </article>
        </div>

        <div class="quote-comparison-table-scroll">
          <table class="quote-comparison-table">
            <thead>
              <tr>
                <th>分段</th>
                <th v-for="(quote, index) in quotes" :key="quote.id">
                  <span>{{ quote.quoteNo }}</span><small>{{ index === 0 ? '基准' : quote.versionLabel }}</small>
                </th>
                <th><span>差距范围</span><small>最高 − 最低</small></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in comparison.rows" :key="row.code">
                <th><strong>{{ row.label }}</strong><small>分段计算金额</small></th>
                <td v-for="(value, index) in row.values" :key="value.quoteId" :class="[`state-${value.state}`, { baseline: index === 0 }]">
                  <strong v-if="value.amountHkd != null">{{ money(value.amountHkd) }}</strong>
                  <strong v-else>—</strong>
                  <small v-if="index === 0 && value.amountHkd != null">比较基准</small>
                  <small v-else-if="value.deltaFromBaselineHkd != null" :class="{ increase: value.deltaFromBaselineHkd > 0, decrease: value.deltaFromBaselineHkd < 0 }">{{ signedMoney(value.deltaFromBaselineHkd) }}</small>
                  <small v-else>{{ stateLabels[value.state] || '不可比较' }}</small>
                  <em v-if="value.state !== 'valid'">{{ stateLabels[value.state] }}</em>
                </td>
                <td class="gap"><strong>{{ money(row.gapHkd) }}</strong><small v-if="row.gapHkd != null">{{ money(row.minimumHkd) }} → {{ money(row.maximumHkd) }}</small><small v-else>有效金额不足 2 张</small></td>
              </tr>
            </tbody>
          </table>
        </div>

        <footer>
          <p><i class="valid" />有效计算　<i class="na" />不适用（按 0）　<i class="missing" />未参与或暂无有效计算不计入差距</p>
          <button type="button" @click="emit('close')">关闭</button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.quote-comparison-backdrop{position:fixed;z-index:1300;inset:0;display:grid;place-items:center;background:rgb(15 23 42/.5);padding:24px;backdrop-filter:blur(4px)}
.quote-comparison-dialog{display:grid;width:min(1380px,96vw);max-height:92vh;overflow:hidden;border:1px solid #cbd5e1;border-radius:18px;background:#fff;box-shadow:0 28px 90px rgb(15 23 42/.3)}
.quote-comparison-dialog>header{display:grid;grid-template-columns:auto 1fr auto;align-items:start;gap:13px;border-bottom:1px solid #dbe5ea;background:linear-gradient(135deg,#f0fdfa,#f8fafc 58%,#eff6ff);padding:18px 20px}.quote-comparison-title-icon{display:grid;width:42px;height:42px;place-items:center;border-radius:12px;background:#0f766e;color:#fff;box-shadow:0 8px 20px rgb(15 118 110/.22)}.quote-comparison-title-icon svg{width:22px}.quote-comparison-title-copy{display:grid;gap:4px}.quote-comparison-title-copy>span{color:#0f766e;font-size:10px;font-weight:900;letter-spacing:.06em}.quote-comparison-title-copy h2{margin:0;color:#0f172a;font-size:20px}.quote-comparison-title-copy p{margin:0;color:#64748b;font-size:11px;line-height:1.55}.quote-comparison-close{display:grid;width:34px;height:34px;place-items:center;border:1px solid #dbe5ea;border-radius:9px;background:#fff;color:#64748b}.quote-comparison-close:hover{border-color:#99f6e4;color:#0f766e}.quote-comparison-close svg{width:17px}
.quote-comparison-quotes{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:8px;border-bottom:1px solid #eef2f6;background:#fff;padding:11px 18px}.quote-comparison-quotes article{display:grid;gap:3px;min-width:0;border:1px solid #e2e8f0;border-radius:9px;background:#f8fafc;padding:9px 11px}.quote-comparison-quotes article.baseline{border-color:#5eead4;background:#f0fdfa}.quote-comparison-quotes span{color:#0f766e;font-size:8px;font-weight:900}.quote-comparison-quotes strong{overflow:hidden;color:#334155;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.quote-comparison-quotes small{overflow:hidden;color:#64748b;font-size:9px;text-overflow:ellipsis;white-space:nowrap}
.quote-comparison-table-scroll{overflow:auto}.quote-comparison-table{width:100%;min-width:900px;border-collapse:separate;border-spacing:0}.quote-comparison-table th,.quote-comparison-table td{border-right:1px solid #e2e8f0;border-bottom:1px solid #e2e8f0;padding:10px 11px;text-align:right;vertical-align:middle}.quote-comparison-table thead th{position:sticky;z-index:2;top:0;background:#eef2f6;color:#475569}.quote-comparison-table thead th:first-child,.quote-comparison-table tbody th{position:sticky;z-index:3;left:0;text-align:left}.quote-comparison-table thead th:first-child{z-index:4}.quote-comparison-table thead span{display:block;color:#334155;font-size:10px}.quote-comparison-table thead small{display:block;margin-top:2px;color:#94a3b8;font-size:8px}.quote-comparison-table tbody th{min-width:130px;background:#fafcfd}.quote-comparison-table tbody th strong{display:block;color:#334155;font-size:10px}.quote-comparison-table tbody th small{display:block;margin-top:3px;color:#94a3b8;font-size:8px;font-weight:600}.quote-comparison-table td{min-width:145px;background:#fff}.quote-comparison-table td.baseline{background:#f0fdfa}.quote-comparison-table td>strong{display:block;color:#0f172a;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px}.quote-comparison-table td>small{display:block;margin-top:3px;color:#64748b;font-size:8px}.quote-comparison-table td>small.increase{color:#dc2626}.quote-comparison-table td>small.decrease{color:#059669}.quote-comparison-table td>em{display:inline-block;margin-top:4px;border-radius:999px;background:#f1f5f9;padding:2px 5px;color:#64748b;font-size:7px;font-style:normal}.quote-comparison-table td.state-not_applicable>em{background:#fef3c7;color:#92400e}.quote-comparison-table td.state-invalid,.quote-comparison-table td.state-not_participating{background:#fafafa}.quote-comparison-table td.gap{background:#f8fafc}.quote-comparison-table td.gap>strong{color:#7c3aed}.quote-comparison-table tr.total th,.quote-comparison-table tr.total td{border-top:2px solid #0f766e;background:#ecfdf5}.quote-comparison-table tr.total td.gap>strong{color:#0f766e}
.quote-comparison-dialog>footer{display:flex;align-items:center;justify-content:space-between;gap:14px;border-top:1px solid #dbe5ea;background:#f8fafc;padding:11px 18px}.quote-comparison-dialog>footer p{margin:0;color:#64748b;font-size:9px}.quote-comparison-dialog>footer i{display:inline-block;width:7px;height:7px;border-radius:99px;background:#0f766e}.quote-comparison-dialog>footer i.na{background:#f59e0b}.quote-comparison-dialog>footer i.missing{background:#94a3b8}.quote-comparison-dialog>footer button{border:0;border-radius:8px;background:#0f766e;padding:8px 18px;color:#fff;font-size:10px;font-weight:900}
@media(max-width:720px){.quote-comparison-backdrop{padding:8px}.quote-comparison-dialog{width:100%;max-height:96vh}.quote-comparison-dialog>header{padding:13px}.quote-comparison-quotes{grid-template-columns:1fr 1fr;padding:8px}.quote-comparison-dialog>footer{align-items:flex-start;flex-direction:column}}
</style>
