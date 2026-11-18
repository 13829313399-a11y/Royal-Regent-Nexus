<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { errorMessage } from './api'
import { ordersApi, type EtaPurchaseSource, type PurchaseCandidate } from './ordersApi'

const props = defineProps<{ orderId: string; row: number; reference: string; supplier: string; fieldId: string; fieldName: string; canSearch: boolean }>()
const source = defineModel<EtaPurchaseSource | undefined>('source')
const choices = ref<PurchaseCandidate[]>([])
const loading = ref(false)
const message = ref('')
const availableUpdate = computed(() => choices.value.find(item => item.id === source.value?.id && item.revision !== source.value?.revision))
let generation = 0

watch(() => [props.orderId, props.row, props.reference.trim(), props.supplier.trim()] as const, (next, prior) => {
  if (next.every((value, index) => value === prior[index])) return
  generation++
  choices.value = []
  loading.value = false
  message.value = source.value ? '匹配条件已改变，请重新选择采购明细。' : ''
  source.value = undefined
}, { flush: 'sync' })

async function search() {
  const request = ++generation
  loading.value = true
  choices.value = []
  message.value = ''
  try {
    const result = await ordersApi.purchaseCandidates(props.orderId, props.row, props.reference.trim(), props.supplier.trim())
    if (request !== generation) return
    choices.value = result.items
    if (!result.items.length) message.value = '没有匹配的采购明细。请核对单号、供应商、物料编码和单位。'
  } catch (error) {
    if (request === generation) message.value = errorMessage(error)
  } finally {
    if (request === generation) loading.value = false
  }
}

function choose(event: Event) {
  const select = event.target as HTMLSelectElement
  const choice = choices.value.find(item => item.id === select.value)
  if (choice) applyChoice(choice)
  else if (!select.value) source.value = undefined
}

function applyChoice(choice: PurchaseCandidate) { source.value = { id: choice.id, revision: choice.revision } }
</script>

<template>
  <div class="purchase-source-picker">
    <Button v-if="canSearch" type="button" variant="outline" :disabled="loading || !reference.trim() || !supplier.trim()" @click="search">
      {{ loading ? '正在查找…' : '查找采购明细' }}
    </Button>
    <label v-if="choices.length" :for="fieldId">关联采购明细（选填）
      <select :id="fieldId" :name="fieldName" :value="source?.id ?? ''" @change="choose">
        <option value="">暂不关联</option>
        <option v-if="source && !choices.some(item => item.id === source?.id)" :value="source.id">保留现有关联</option>
        <option v-for="item in choices" :key="item.id" :value="item.id">
          {{ item.detail_no || item.id }} · {{ item.production_no || '无生产单号' }} · {{ item.quantity ?? '数量待核对' }} {{ item.unit }} · V{{ item.revision }}
        </option>
      </select>
    </label>
    <p v-if="source" class="purchase-source-id">
      已选采购明细 {{ source.id }} · V{{ source.revision }}
      <Button v-if="availableUpdate" type="button" variant="outline" @click="applyChoice(availableUpdate)">确认当前明细版本</Button>
      <Button type="button" variant="outline" @click="source = undefined">移除关联</Button>
    </p>
    <p v-if="message" role="status">{{ message }}</p>
  </div>
</template>

<style scoped>
.purchase-source-picker { display: flex; flex-wrap: wrap; align-items: end; gap: .625rem; width: 100%; min-width: 0; }
.purchase-source-picker label { display: grid; gap: .375rem; min-width: 0; }
.purchase-source-picker select { max-width: 100%; }
.purchase-source-picker p { width: 100%; margin: 0; }
.purchase-source-id { overflow-wrap: anywhere; }
</style>
