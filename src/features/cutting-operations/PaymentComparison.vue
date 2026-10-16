<script setup lang="ts">
import { computed } from 'vue'
import type { PaymentSave, PaymentSnapshot } from './paymentApi'

const props = defineProps<{ before: PaymentSnapshot; after: PaymentSave | PaymentSnapshot }>()
const fields = [
  ['day', '实际付款日期'], ['voucher_no', '付款凭证号'], ['method', '付款方式'],
  ['evidence', '付款凭据'], ['currency', '币种'], ['amount', '付款金额'],
] as const
const methods = { bank: '银行转账', cash: '现金', cheque: '支票', other: '其他' }
function display(key: typeof fields[number][0], value: PaymentSave | PaymentSnapshot) {
  return key === 'method' ? methods[value.method] : value[key]
}
function difference(after: string, before: string) {
  if (props.before.currency !== props.after.currency) return '币种变化，不计算差额'
  const cents = (value: string) => {
    if (!/^\d{1,16}(\.\d{1,2})?$/.test(value)) return null
    const [whole, fraction = ''] = value.split('.')
    return BigInt(whole!) * 100n + BigInt(fraction.padEnd(2, '0'))
  }
  const a = cents(after), b = cents(before)
  if (a === null || b === null) return '金额待核对'
  const delta = a - b, absolute = delta < 0n ? -delta : delta
  return `${delta < 0n ? '-' : '+'}${absolute / 100n}.${String(absolute % 100n).padStart(2, '0')}`
}
const rows = computed(() => {
  const ids = new Set([...props.before.allocations, ...props.after.allocations].map(row => row.settlement_id))
  return [...ids].map(id => {
    const before = props.before.allocations.find(row => row.settlement_id === id)
    const after = props.after.allocations.find(row => row.settlement_id === id)
    return { id, before, after, status: !before ? '新增分配' : !after ? '取消分配' :
      props.before.currency !== props.after.currency || difference(after.amount, before.amount) !== '+0.00' ? '调整分配' : '分配未变' }
  })
})
</script>

<template>
  <div class="cutting-table-scroll">
    <table aria-label="付款内容差异"><thead><tr><th>字段</th><th>对照版本</th><th>本次内容</th><th>变化</th></tr></thead>
      <tbody><tr v-for="[key, label] in fields" :key="key"><td>{{ label }}</td><td>{{ display(key, before) }}</td><td>{{ display(key, after) }}</td><td>{{ key === 'amount' ? difference(after.amount, before.amount) : before[key] === after[key] ? '未变' : '已修改' }}</td></tr></tbody>
    </table>
    <table aria-label="付款分配差异"><thead><tr><th>结算单</th><th>变化</th><th>对照分配</th><th>本次分配</th><th>差额</th></tr></thead>
      <tbody><tr v-for="row in rows" :key="row.id"><td>{{ row.id }}</td><td>{{ row.status }}</td><td>{{ row.before?.amount ?? '0.00' }} {{ before.currency }}</td><td>{{ row.after?.amount ?? '0.00' }} {{ after.currency }}</td><td>{{ difference(row.after?.amount ?? '0.00', row.before?.amount ?? '0.00') }}</td></tr></tbody>
    </table>
  </div>
</template>
