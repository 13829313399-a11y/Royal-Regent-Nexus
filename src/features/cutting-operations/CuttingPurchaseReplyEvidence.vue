<script setup lang="ts">
import { computed } from 'vue'
import type { PendingPurchase } from './ordersApi'

const props = defineProps<{ purchase: PendingPurchase }>()
const prior = computed(() => props.purchase.batches.length ? null : props.purchase.prior_purchase_reply)
const batches = computed(() => prior.value?.batches ?? props.purchase.batches)
const unit = (row: number) => props.purchase.requisition?.lines.find(line => line.row === row)?.unit ?? ''
</script>

<template>
  <div class="purchase-reply-evidence">
    <p v-if="prior">最新交期回复已移除批次。以下凭据来自裁床记录 V{{ prior.revision }}。</p>
    <ul v-if="batches.length">
      <li v-for="(batch, index) in batches" :key="index">
        需求行 {{ batch.row + 1 }} · {{ batch.expected_date }} · {{ batch.quantity }} {{ unit(batch.row) }} · {{ batch.supplier }} · {{ batch.purchase_reference }}
      </li>
    </ul>
    <p v-else-if="purchase.has_purchase_evidence">原需求有历史交期记录，当前版本暂未提供批次明细。</p>
    <p v-else>原需求暂无采购交期记录。</p>
  </div>
</template>

<style scoped>
.purchase-reply-evidence { min-width: 0; overflow-wrap: anywhere; }
</style>
