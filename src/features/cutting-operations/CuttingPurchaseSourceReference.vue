<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { Button } from '@/components/ui/button'
import type { EtaPurchaseSource } from './ordersApi'

const props = defineProps<{ source: EtaPurchaseSource; canOpen?: boolean }>()
const message = ref('')
const copying = ref(false)
let token = 0
let timer: ReturnType<typeof setTimeout> | undefined
function reset() {
  token++
  clearTimeout(timer)
  copying.value = false
  message.value = ''
}
watch(() => props.source.id, reset)
onBeforeUnmount(reset)

async function copy() {
  const attempt = ++token
  copying.value = true
  message.value = '正在复制内部编号…'
  timer = setTimeout(() => {
    if (token !== attempt) return
    reset()
    message.value = '复制等待超时，请选中编号手动复制。'
  }, 10000)
  try {
    if (!navigator.clipboard?.writeText) throw new Error()
    await navigator.clipboard.writeText(props.source.id)
    if (token === attempt) message.value = '内部编号已复制。'
  } catch {
    if (token === attempt) message.value = '无法自动复制，请选中编号手动复制。'
  } finally {
    if (token === attempt) { clearTimeout(timer); copying.value = false }
  }
}
</script>

<template>
  <div class="purchase-reference">
    <span>采购明细 {{ source.detail_no || '明细号未记录' }} · V{{ source.revision }}</span>
    <RouterLink v-if="canOpen" :to="{ path: '/modules/pmc-warehouse/fabric-warehouse/receipts',
      query: { factory: 'huakang-c', view: 'pending', purchase_id: source.id } }"
      target="_blank" rel="noopener" class="purchase-link">打开布料仓原明细</RouterLink>
    <details class="purchase-id">
      <summary>内部编号</summary>
      <code>{{ source.id }}</code>
      <Button type="button" size="sm" variant="outline" :disabled="copying" @click="copy">复制内部编号</Button>
      <span v-if="message" role="status">{{ message }}</span>
    </details>
  </div>
</template>

<style scoped>
.purchase-reference { display: inline-flex; flex-wrap: wrap; align-items: baseline; gap: .25rem .75rem; min-width: 0; overflow-wrap: anywhere; }
.purchase-id code { user-select: text; margin-inline-end: .5rem; }
.purchase-link { text-decoration: underline; }
</style>
