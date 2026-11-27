<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'

const props = defineProps<{ id: string }>()
const shortId = computed(() => props.id.length > 16 ? `${props.id.slice(0, 8)}…${props.id.slice(-4)}` : props.id)
const copying = ref(false), message = ref(''), manualCopy = ref(false)
let generation = 0
let timer: ReturnType<typeof setTimeout> | undefined
function reset() {
  generation++
  clearTimeout(timer)
  copying.value = false
  message.value = ''
  manualCopy.value = false
}
watch(() => props.id, reset, { flush: 'sync' })
onBeforeUnmount(reset)

async function copy() {
  if (!props.id || copying.value) return
  const value = props.id, ticket = ++generation
  copying.value = true
  message.value = '正在复制完整编号，请稍候…'
  timer = setTimeout(() => {
    if (ticket !== generation) return
    reset()
    manualCopy.value = true
    message.value = '复制等待超时，请选中完整编号手动复制。'
  }, 10000)
  try {
    if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable')
    await navigator.clipboard.writeText(value)
    if (ticket === generation) message.value = '完整编号已复制。'
  } catch {
    if (ticket === generation) {
      manualCopy.value = true
      message.value = '无法自动复制，请选中完整编号手动复制。'
    }
  } finally {
    if (ticket === generation) { clearTimeout(timer); copying.value = false }
  }
}
</script>

<template>
  <div class="purchase-read-target" role="group" aria-label="原采购明细读取目标">
    <span>原明细编号：<code :title="id">{{ shortId }}</code></span>
    <Button type="button" size="sm" variant="outline" :disabled="copying" :aria-busy="copying" @click="copy">复制完整编号</Button>
    <p v-if="message" role="status">{{ message }}</p>
    <div v-if="manualCopy" class="purchase-read-target-manual">
      <label for="fabric-original-purchase-detail-id">完整原采购明细编号</label>
      <input id="fabric-original-purchase-detail-id" name="original_purchase_detail_id" readonly :value="id" @focus="($event.target as HTMLInputElement).select()" />
    </div>
  </div>
</template>

<style scoped>
.purchase-read-target { display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;margin:8px 0;min-width:0;color:var(--foreground);font-size:13px; }
code { user-select:text;overflow-wrap:anywhere; }
p { flex-basis:100%;margin:0;color:var(--muted-foreground); }
.purchase-read-target-manual { flex-basis:100%;min-width:0; }
label { display:block;margin-bottom:4px; }
input { width:100%;min-width:0;user-select:text; }
</style>
