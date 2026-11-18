<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/auth'
import { errorMessage } from './api'
import { orderHistoryTime } from './orderDisplay'
import { ordersApi, type PurchaseProgress } from './ordersApi'

const props = defineProps<{ orderId: string }>()
const auth = useAuthStore()
const value = ref<PurchaseProgress>()
const loading = ref(false)
const error = ref('')
const retryOrder = ref('')
let generation = 0

function reset() {
  generation++
  value.value = undefined
  loading.value = false
  error.value = ''
  retryOrder.value = ''
}
watch([() => props.orderId, () => auth.currentUser?.id, () => auth.authorizationVersion], reset, { flush: 'sync' })
onBeforeUnmount(reset)

async function load() {
  if (loading.value) return
  const orderId = retryOrder.value || props.orderId
  const request = ++generation
  loading.value = true
  try {
    const result = await ordersApi.purchaseProgress(orderId)
    if (generation !== request) return
    value.value = result
    error.value = ''
    retryOrder.value = ''
  } catch (failure) {
    if (generation !== request) return
    const status = (failure as { response?: { status?: number } }).response?.status
    const transient = !status || status === 408 || status === 429 || status >= 500
    if (!transient) value.value = undefined
    retryOrder.value = orderId
    error.value = value.value ? '刷新失败，仍显示上次结果，请检查连接后重试。' : errorMessage(failure)
  } finally {
    if (generation === request) loading.value = false
  }
}
</script>

<template>
  <div class="purchase-progress">
    <Button type="button" variant="outline" :aria-disabled="loading" @click="load">
      {{ loading ? '正在读取进度…' : retryOrder ? '按原订单重试进度' : value ? '刷新到货与签收进度' : '查看到货与签收进度' }}
    </Button>
    <p v-if="error" role="alert">{{ error }}</p>
    <div v-if="value" aria-live="polite">
      <p>取数时间 <time :datetime="value.read_at">{{ orderHistoryTime(value.read_at) }}</time></p>
      <p>布料仓数据按采购明细统计，可能同时供给多张订单。裁床数据按本订单需求行统计，包含从现有库存领取的物料。</p>
      <ul>
        <li v-for="item in value.sources" :key="`${item.row}-${item.id}`">
          需求行 {{ item.row + 1 }} · {{ item.order_no }} · 采购明细 {{ item.detail_no || item.id }}
          <template v-if="item.status === 'active'">
            · 布料仓实收 {{ item.received_quantity }} {{ item.unit }} · 待收 {{ item.outstanding_quantity == null ? '待核对' : `${item.outstanding_quantity} ${item.unit}` }}
            <span v-if="item.current_revision !== item.linked_revision"> · 关联时 V{{ item.linked_revision }}，当前 V{{ item.current_revision }}，请核对</span>
          </template>
          <template v-else> · {{ item.status === 'identity_changed' ? '采购明细已变更，请重新核对关联' : '采购明细已失效' }}</template>
        </li>
      </ul>
      <ul>
        <li v-for="item in value.cutting" :key="item.row">需求行 {{ item.row + 1 }} · 本订单裁床已签收 {{ item.signed_quantity }} {{ item.unit }} · 已退仓 {{ item.returned_quantity }} {{ item.unit }}</li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.purchase-progress { display: grid; justify-items: start; gap: .625rem; min-width: 0; overflow-wrap: anywhere; }
.purchase-progress ul { list-style: disc; padding-inline-start: 1.25rem; }
</style>
