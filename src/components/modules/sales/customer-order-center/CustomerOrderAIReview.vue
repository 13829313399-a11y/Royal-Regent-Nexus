<script setup lang="ts">
import { computed, ref } from 'vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import type { CustomerOrderImportPreview } from '@/types/customerOrder'

const props = defineProps<{ preview: CustomerOrderImportPreview }>()
const expanded = ref(false)
const limit = ref(20)
const ai = computed(() => props.preview.ai_recognition)
const labels: Record<string, string> = {
  order_no: '客 PO', contract_no: '合同号', reference_no: 'SO / Reference', source_line_no: '原单行号',
  product_no: '完整货号', quantity: '数量', quantity_unit: '数量单位', units_per_carton: '装箱数',
  unit_price: '原币单价', unit_price_usd: '美元单价', unit_price_hkd: '港币单价', currency: '币种', amount: '原币金额',
  price_unit: '计价单位', price_per_qty: '计价基数',
  delivery_date: '客户交期', requested_ship_date: '客户交期', description: '品名', description_zh: '中文品名',
  product_name_en: '英文品名', product_name_zh: '中文品名', customer_name: '客名', barcode: '条码', packaging: '包装',
}
const entries = computed(() => {
  const differences = props.preview.rows.flatMap(row => (row.ai_candidates || []).filter(value => value.message).map(value => ({
    title: `${row.po_no || row.contract_no} · ${row.product_no}`,
    note: value.message!, fields: [{ name: value.field, ...value }],
  })))
  const matched = (ai.value?.matched || []).map(line => ({
    title: `${line.file} · ${line.fields.order_no || line.fields.contract_no || ''} · ${line.fields.product_no || ''}`,
    note: '已对应原单明细；以下为原文，数量单位和计价口径以原单为准。原识别值保留。',
    fields: Object.entries(line.fields).map(([name, value]) => ({ name, value, ...line.evidence[name] })),
  }))
  const unmatched = (ai.value?.unmatched || []).map(line => ({
    title: `${line.file} · ${line.fields.order_no || line.fields.contract_no || ''} · ${line.fields.product_no || '未明确货号'}`,
    note: '未能唯一对应现有明细，未自动加单、合并或取消订单。',
    fields: Object.entries(line.fields).map(([name, value]) => ({ name, value, ...line.evidence[name] })),
  }))
  return [...differences, ...matched, ...unmatched]
})
</script>

<template>
  <SectionPanel v-if="ai" title="AI 识别核对" subtitle="保留原识别值。AI 发现的差异和漏项仅作提醒，可以直接保存和生成。" data-testid="ai-review">
    <div class="flex flex-wrap items-center justify-between gap-3" role="status">
      <p class="text-sm text-muted-foreground">已完成 {{ ai.completed }} / {{ ai.files }} 份文件；识别完成不代表所有字段均正确。</p>
      <StatusPill :label="ai.state === 'complete' ? '识别完成' : ai.state === 'partial' ? '部分完成' : '沿用原识别'" :tone="ai.state === 'complete' ? 'blue' : 'amber'" />
    </div>
    <ul class="mt-3 space-y-2 break-words text-sm text-muted-foreground">
      <li v-for="(document, index) in ai.documents" :key="index">
        <span class="font-medium text-foreground">{{ document.file }}</span>：{{ document.message || (document.state === 'complete' ? '已提取并核对' : '沿用原识别') }}
        <p v-for="(note, noteIndex) in document.notes" :key="noteIndex">{{ note }}</p>
      </li>
    </ul>
    <Collapsible v-if="entries.length" v-model:open="expanded" class="mt-4">
      <CollapsibleTrigger as-child>
        <Button variant="outline">{{ expanded ? '收起' : '查看' }} {{ entries.length }} 项候选与原文依据</Button>
      </CollapsibleTrigger>
      <CollapsibleContent class="mt-4 space-y-4">
        <article v-for="(entry, index) in entries.slice(0, limit)" :key="index" class="rounded-lg border border-border p-4">
          <h3 class="break-words text-sm font-semibold text-foreground">{{ entry.title }}</h3>
          <p class="mt-1 text-sm text-muted-foreground">{{ entry.note }}</p>
          <dl class="mt-3 space-y-3">
            <div v-for="field in entry.fields" :key="field.name" class="break-words text-sm">
              <dt class="font-medium text-foreground">{{ labels[field.name] || field.name }}：{{ field.value }}</dt>
              <dd class="mt-1 whitespace-pre-wrap text-muted-foreground">{{ field.source }} · {{ field.quote }}</dd>
              <dd class="text-muted-foreground">{{ field.text_verified ? '引用文字与原单一致；字段归属仍以原单为准。' : 'AI 图像候选，尚未独立验证。' }}</dd>
            </div>
          </dl>
        </article>
        <Button v-if="entries.length > limit" variant="outline" @click="limit += 20">继续查看（剩余 {{ entries.length - limit }} 项）</Button>
      </CollapsibleContent>
    </Collapsible>
  </SectionPanel>
</template>
