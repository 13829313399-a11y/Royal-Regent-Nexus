<script setup lang="ts">
import { ref } from 'vue'
import { Button } from '@/components/ui/button'
import { errorMessage } from './api'
import { ordersApi, type PurchaseProgress } from './ordersApi'

const props = defineProps<{ orderId: string }>()
const value = ref<PurchaseProgress>()
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  value.value = undefined
  try { value.value = await ordersApi.purchaseProgress(props.orderId) }
  catch (failure) { error.value = errorMessage(failure) }
  finally { loading.value = false }
}
</script>

<template>
  <div class="purchase-progress">
    <Button type="button" variant="outline" :disabled="loading" @click="load">
      {{ loading ? '正在读取进度…' : value ? '刷新到货与签收进度' : '查看到货与签收进度' }}
    </Button>
    <p v-if="error" role="alert">{{ error }}</p>
    <div v-if="value" aria-live="polite">
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
