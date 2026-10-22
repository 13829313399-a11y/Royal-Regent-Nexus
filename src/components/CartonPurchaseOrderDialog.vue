<script setup lang="ts">
import { X } from '@lucide/vue'
import type { CartonPurchaseOrderContextResponse, CartonPurchaseOrderIssueResponse } from '@/api/cartonProcurement'
defineProps<{ orderNo: string; context?: CartonPurchaseOrderContextResponse | null; loading?: boolean; generating?: boolean; downloadingId?: string; exporting?: boolean; canGenerate?: boolean; referenceEnabled?: boolean; error?: string }>()
const emit = defineEmits<{ close: []; generate: []; download: [issue: CartonPurchaseOrderIssueResponse]; batch: [issue: CartonPurchaseOrderIssueResponse]; reference: [] }>()
const purchaseOrderTypeLabel = (kind: string) => ({ INITIAL: '首次采购单', APPEND: '追加采购单', REDUCE: '减单通知', ADJUSTMENT: '采购变更单', NONE: '没有待生成采购单' }[kind] || kind)
const signedQuantity = (value: string | null) => value == null ? '—' : `${Number(value) > 0 ? '+' : ''}${Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 4 })}`
</script>
<template>
    <div class="fixed inset-0 z-[65] flex items-center justify-center bg-slate-950/45 p-4" @click.self="emit('close')">
      <div class="max-h-[88vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="purchase-order-dialog-title">
        <div class="flex items-start justify-between border-b border-slate-200 px-5 py-4">
          <div><h2 id="purchase-order-dialog-title" class="text-[16px] font-bold text-slate-950">供应商采购单 · {{ orderNo }}</h2><p class="mt-1 text-[11px] text-slate-500">订单保留累计数量；供应商执行只认每张采购单的“本次变化”列。</p></div>
          <button type="button" aria-label="关闭采购单记录" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100" @click="emit('close')"><X class="size-4" /></button>
        </div>
        <p v-if="error" role="alert" class="p-5 text-sm text-red-700">{{ error }}</p>
        <div v-if="loading" class="p-8 text-center text-[12px] font-semibold text-slate-500">正在读取采购单生成记录…</div>
        <div v-else-if="context" class="space-y-4 p-5">
          <div v-if="context.historical_baseline" class="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-[11px] leading-5 text-blue-800">历史已下单数量已登记为历史基线；后续追加或减单只导出相对该基线的净变化，避免重复下单。</div>
          <section class="rounded-xl border p-4" :class="context.can_generate ? 'border-amber-200 bg-amber-50/60' : 'border-slate-200 bg-slate-50'">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div class="text-[10px] font-bold uppercase tracking-wide text-slate-500">当前待处理</div>
                <div class="mt-1 text-[15px] font-bold text-slate-950">{{ purchaseOrderTypeLabel(context.pending_type) }}</div>
                <p v-if="context.pending_type !== 'NONE'" class="mt-1 text-[11px] text-slate-600">产品数量变化 {{ signedQuantity(context.pending_product_quantity) }}；{{ context.pending_line_count }} 条纸品产生箱数变化。</p>
                <p v-else class="mt-1 text-[11px] text-slate-500">{{ context.empty_reason || '当前累计数量与最近一次采购单快照一致，无需再次向供应商下单。' }}</p>
              </div>
              <button v-if="context.can_generate && canGenerate" type="button" :disabled="generating" class="h-9 rounded-lg bg-amber-600 px-4 text-[11px] font-bold text-white disabled:opacity-50" @click="emit('generate')">{{ generating ? '正在固定生成…' : `生成并下载${purchaseOrderTypeLabel(context.pending_type)}` }}</button>
            </div>
            <p v-if="context.pending_type !== 'NONE' && !context.can_generate" class="mt-3 rounded-lg bg-white px-3 py-2 text-[11px] font-semibold text-amber-800">请先确认订单并锁定，再生成正式供应商采购单。</p>
            <p v-else-if="context.can_generate && (!canGenerate)" class="mt-3 rounded-lg bg-white px-3 py-2 text-[11px] font-semibold text-red-700">当前账号可查看记录，生成采购单需要岗位权限和该客户的操作授权。</p>
          </section>

          <section class="overflow-hidden rounded-xl border border-slate-200">
            <div class="flex items-center justify-between bg-slate-50 px-4 py-3"><div><h3 class="text-[12px] font-bold text-slate-900">不可变采购单历史</h3><p class="mt-0.5 text-[10px] text-slate-500">重新下载始终使用当时快照，不会套用订单后续数量。</p></div><span class="rounded-full bg-white px-2.5 py-1 text-[10px] font-bold text-slate-600">{{ context.issues.length }} 份</span></div>
            <div v-if="context.issues.length" class="divide-y divide-slate-100">
              <div v-for="issue in context.issues" :key="issue.id" class="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <div><div class="flex items-center gap-2"><b class="font-mono text-[12px] text-slate-900">{{ issue.document_no }}</b><span class="rounded-full bg-teal-50 px-2 py-0.5 text-[9px] font-bold text-teal-700">{{ issue.is_cancellation ? '取消通知单' : issue.is_replenishment ? '补单采购单' : purchaseOrderTypeLabel(issue.document_type) }}</span></div><p class="mt-1 text-[10px] text-slate-500">产品变化 {{ signedQuantity(issue.product_quantity_delta) }} · {{ issue.generated_by_name || '—' }} · {{ issue.generated_at.slice(0, 16).replace('T', ' ') }}</p></div>
                <button type="button" :disabled="Boolean(downloadingId)" class="h-8 rounded-lg border border-teal-200 bg-white px-3 text-[10px] font-bold text-teal-700 disabled:opacity-40" @click="emit('download', issue)">{{ downloadingId === issue.id ? '下载中…' : '重新下载原版本' }}</button>
                <button v-if="issue.purchase_order_batch" type="button" :disabled="Boolean(downloadingId)" class="h-8 rounded-lg bg-teal-700 px-3 text-[10px] font-bold text-white disabled:opacity-40" @click="emit('batch', issue)">下载合并采购单（{{ issue.purchase_order_batch.order_count }} 张订单）</button>
              </div>
            </div>
            <div v-else class="px-4 py-6 text-center text-[11px] text-slate-400">{{ context.empty_reason || '还没有正式生成过供应商采购单' }}</div>
          </section>

          <div v-if="referenceEnabled" class="rounded-xl border border-slate-200 bg-white p-4"><div class="flex flex-wrap items-center justify-between gap-3"><div><div class="text-[11px] font-bold text-slate-800">当前累计对账表</div><p class="mt-1 text-[10px] text-slate-500">仅供内部核对当前总量，不代表向供应商追加下单。</p></div><button type="button" :disabled="Boolean(exporting)" class="h-8 rounded-lg border border-slate-200 px-3 text-[10px] font-bold text-slate-600 disabled:opacity-40" @click="emit('reference')">{{ exporting ? '生成中…' : '导出累计参考' }}</button></div></div>
        </div>
        <div class="flex justify-end border-t border-slate-200 bg-slate-50 px-5 py-4"><button type="button" class="h-9 rounded-lg border border-slate-200 bg-white px-4 text-[12px] font-bold text-slate-600" @click="emit('close')">关闭</button></div>
      </div>
    </div>

</template>
