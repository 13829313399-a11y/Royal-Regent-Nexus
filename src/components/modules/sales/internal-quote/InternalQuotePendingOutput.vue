<script setup lang="ts">
import type { ApiInternalQuoteDashboard } from '@/api/internalQuote'
defineProps<{ pending: ApiInternalQuoteDashboard['pending_first_output'] }>()
defineEmits<{ open: [quoteId: string] }>()
function duration(hours: number | null) {
  return hours === null ? '建单时间缺失' : hours < 24 ? `${hours.toFixed(1)} 小时` : `${(hours / 24).toFixed(1)} 天`
}
</script>

<template>
  <article class="pending-output">
    <header><strong>待首次输出</strong><small>当前全部未归档产品 · 不受统计周期限制</small></header>
    <div class="pending-totals"><strong>{{ pending.count }} <small>个产品</small></strong><span>超过 3 天 <b>{{ pending.over_three_days }}</b> 个</span><span v-if="pending.oldest_hours !== null">最长等待 {{ duration(pending.oldest_hours) }}</span></div>
    <ul v-if="pending.items.length">
      <li v-for="item in pending.items" :key="item.quote_id">
        <button type="button" @click="$emit('open', item.quote_id)"><strong>{{ item.product_name }}</strong><small>{{ item.quote_no }} · {{ item.customer }}</small></button>
        <span>{{ duration(item.waiting_hours) }}</span>
      </li>
    </ul>
    <p v-else>当前没有待首次输出的产品</p>
    <footer>按产品合并包装方案与版本；同一产品只计一次。展示等待最久的前 10 个，已输出但时间缺失的产品不列入待办。</footer>
  </article>
</template>

<style scoped>
.pending-output{grid-column:1/-1;border:1px solid #dbe5ee;border-radius:16px;background:white;overflow:hidden}.pending-output header{display:flex;align-items:center;gap:12px;padding:14px 18px;border-bottom:1px solid #eef2f6}.pending-output header strong{color:#0f172a;font-size:13px}.pending-output small,.pending-output footer{color:#64748b;font-size:11px}.pending-totals{display:flex;align-items:center;gap:24px;padding:12px 18px;color:#475569;font-size:12px;flex-wrap:wrap}.pending-totals>strong{font-size:24px;color:#0f766e}.pending-totals b{color:#b45309}.pending-output ul{list-style:none;margin:0;padding:0 18px;max-height:240px;overflow:auto}.pending-output li{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:8px 0;border-top:1px solid #eef2f6;font-size:12px}.pending-output button{display:grid;gap:3px;text-align:left;color:#0f766e}.pending-output p{padding:12px 18px;color:#64748b;font-size:12px}.pending-output footer{padding:10px 18px;background:#f8fafc;line-height:1.5}@media(max-width:700px){.pending-output header{align-items:flex-start;flex-direction:column;gap:5px}}
</style>
