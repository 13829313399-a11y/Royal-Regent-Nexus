<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { cartonMarkApi, type CartonMarkCustomer, type CartonMarkCustomerRecognition, type CartonMarkCustomerInitializationCandidate } from '@/api/cartonMark'
import { getApiErrorMessage } from '@/lib/http'

const props = defineProps<{
  factoryId: string
  factoryName: string
  contractNumber: string
  item: string
  excelAssetId: string
  pdfAssetId: string
  selectedCustomer: string
  customers: CartonMarkCustomer[]
  allowed: boolean
  canManage: boolean
}>()
const emit = defineEmits<{ select: [name: string]; customersChanged: []; busy: [value: boolean] }>()
const result = ref<CartonMarkCustomerRecognition | null>(null)
const error = ref('')
const loading = ref(false)
const selectedOrderId = ref('')
const manualConfirmed = ref(false)
const initializationOpen = ref(false)
const candidates = ref<CartonMarkCustomerInitializationCandidate[]>([])
const selectedNames = ref<string[]>([])
const initializationLoading = ref(false)
const initializationBusy = ref(false)
const initializationError = ref('')
const initializationMessage = ref('')
let generation = 0, previewGeneration = 0
let controller: AbortController | null = null, previewController: AbortController | null = null
let timer: ReturnType<typeof setTimeout> | undefined
let autoName = '', mounted = true
const normalize = (value: string) => value.trim().replace(/\s+/g, ' ').toLocaleLowerCase()
const managedCustomer = computed(() => result.value?.status === 'MATCHED'
  ? props.customers.find(customer => normalize(customer.name) === normalize(result.value!.customer_name)) : undefined)
const missingCustomer = computed(() => result.value?.status === 'MATCHED' && !managedCustomer.value)
const manualConflict = computed(() => result.value?.status === 'MATCHED' && props.selectedCustomer
  && normalize(props.selectedCustomer) !== normalize(result.value.customer_name))
const blocked = computed(() => loading.value || result.value?.status === 'AMBIGUOUS' || result.value?.status === 'CONFLICT'
  || (!!manualConflict.value && !manualConfirmed.value))
watch(blocked, value => emit('busy', value), { immediate: true })
watch(() => props.selectedCustomer, () => { manualConfirmed.value = false })

function applyRecognizedCustomer() {
  if (!props.allowed || !managedCustomer.value || (props.selectedCustomer && props.selectedCustomer !== autoName)) return
  autoName = managedCustomer.value.name
  emit('select', autoName)
}
watch(managedCustomer, applyRecognizedCustomer)

function invalidateRecognition() {
  generation++
  controller?.abort()
  clearTimeout(timer)
  result.value = null
  error.value = ''
  loading.value = false
  manualConfirmed.value = false
  if (autoName && props.selectedCustomer === autoName) emit('select', '')
  autoName = ''
}

async function recognize(orderId = '') {
  if (!props.allowed || !props.contractNumber.trim()) return
  clearTimeout(timer)
  const requestGeneration = ++generation
  controller?.abort()
  const requestController = new AbortController()
  controller = requestController
  loading.value = true; result.value = null; error.value = ''; manualConfirmed.value = false
  const payload = { contract_number: props.contractNumber, item: props.item,
    order_id: orderId || undefined, excel_asset_id: props.excelAssetId || undefined,
    pdf_asset_id: props.pdfAssetId || undefined }
  try {
    const response = await cartonMarkApi.recognizeCustomer(props.factoryId, payload, requestController.signal)
    if (!mounted || requestGeneration !== generation || !props.allowed) return
    result.value = response
    if (response.status !== 'MATCHED' && autoName) {
      if (props.selectedCustomer === autoName) emit('select', '')
      autoName = ''
    }
    applyRecognizedCustomer()
  } catch (exception) {
    if (mounted && requestGeneration === generation && !requestController.signal.aborted) {
      error.value = `客名识别失败：${getApiErrorMessage(exception)}`
      if (autoName && props.selectedCustomer === autoName) emit('select', '')
      autoName = ''
    }
  } finally {
    if (mounted && requestGeneration === generation) loading.value = false
  }
}

watch(() => [props.factoryId, props.contractNumber, props.item, props.excelAssetId, props.pdfAssetId, props.allowed], () => {
  invalidateRecognition()
  selectedOrderId.value = ''
  if (props.allowed && props.contractNumber.trim()) {
    loading.value = true
    timer = setTimeout(() => void recognize(), 250)
  }
}, { immediate: true })

function closeInitialization() {
  if (initializationBusy.value) return
  previewGeneration++
  previewController?.abort()
  initializationOpen.value = false
}

async function openInitialization() {
  if (!props.allowed || !props.canManage || initializationBusy.value) return
  const currentPreview = ++previewGeneration
  previewController?.abort()
  const requestController = new AbortController()
  previewController = requestController
  initializationOpen.value = true; initializationLoading.value = true
  initializationError.value = ''; initializationMessage.value = ''
  candidates.value = []; selectedNames.value = []
  try {
    const response = await cartonMarkApi.customerInitializationCandidates(props.factoryId, requestController.signal)
    if (!mounted || currentPreview !== previewGeneration || !props.canManage || !props.allowed) return
    candidates.value = response
    // Leave the choice explicit. Existing and ambiguous customer names cannot be selected.
  } catch (exception) {
    if (mounted && currentPreview === previewGeneration && !requestController.signal.aborted) initializationError.value = getApiErrorMessage(exception)
  } finally {
    if (mounted && currentPreview === previewGeneration) initializationLoading.value = false
  }
}

async function addCustomers(names: string[], fromRecognition = false) {
  if (!props.allowed || !props.canManage || initializationBusy.value || !names.length) return
  const currentPreview = previewGeneration, currentRecognition = generation
  const factory = props.factoryId
  initializationBusy.value = true; initializationError.value = ''; initializationMessage.value = ''
  try {
    const response = await cartonMarkApi.initializeCustomers(factory, names)
    if (!mounted || factory !== props.factoryId || currentPreview !== previewGeneration || !props.allowed || !props.canManage) return
    emit('customersChanged')
    initializationMessage.value = `已新增 ${response.created_names.length} 个客名，${response.existing_names.length} 个已存在。`
    selectedNames.value = []
    if (fromRecognition && currentRecognition === generation) {
      // The refreshed managed list drives autofill; never select an unregistered name here.
      void recognize(selectedOrderId.value)
    } else if (initializationOpen.value) {
      const response = await cartonMarkApi.customerInitializationCandidates(factory)
      if (mounted && factory === props.factoryId && currentPreview === previewGeneration) candidates.value = response
    }
  } catch (exception) {
    if (mounted && factory === props.factoryId && currentPreview === previewGeneration) initializationError.value = getApiErrorMessage(exception)
  } finally {
    if (mounted && factory === props.factoryId && currentPreview === previewGeneration) initializationBusy.value = false
  }
}

watch(() => [props.factoryId, props.allowed, props.canManage], () => {
  previewGeneration++
  previewController?.abort()
  initializationOpen.value = false; initializationBusy.value = false; initializationLoading.value = false
  candidates.value = []; selectedNames.value = []; initializationError.value = ''; initializationMessage.value = ''
})
onBeforeUnmount(() => {
  mounted = false; generation++; previewGeneration++
  controller?.abort(); previewController?.abort(); clearTimeout(timer)
})
defineExpose({ openInitialization })
</script>

<template>
  <div v-if="allowed" class="space-y-2 text-xs" aria-label="订单客名识别">
    <p v-if="loading" class="text-slate-500">正在从本厂纸箱订单识别客名…</p>
    <template v-else-if="result">
      <p :class="result.status === 'MATCHED' ? 'text-teal-700' : 'text-amber-700'">{{ result.message }}</p>
      <p v-if="result.status === 'MATCHED'" class="break-words text-slate-600">
        识别客名：<strong>{{ result.customer_name }}</strong> · 来源订单：{{ result.orders.map(order => order.order_no).join('、') }}
      </p>
      <p v-if="manualConflict" class="text-amber-700">手选客名与订单客名不同，请确认后再核对。当前保留你的手选客名。</p>
      <button v-if="manualConflict && managedCustomer" type="button" class="font-semibold text-teal-700 underline" @click="autoName = managedCustomer.name; emit('select', managedCustomer.name)">采用订单客名</button>
      <button v-if="manualConflict && !manualConfirmed" type="button" class="ml-3 font-semibold text-amber-700 underline" @click="manualConfirmed = true">确认使用手选客名</button>
      <p v-if="manualConflict && manualConfirmed" class="text-slate-500">已确认使用手选客名。</p>
      <template v-if="missingCustomer">
        <button v-if="canManage" type="button" :disabled="initializationBusy" class="rounded border border-teal-200 bg-teal-50 px-2 py-1 font-semibold text-teal-700 disabled:opacity-50" @click="addCustomers([result.customer_name], true)">将 {{ result.customer_name }} 加入客户库</button>
        <p v-else class="text-amber-700">请主管或管理员将识别客名加入客户库后，点击重新识别。</p>
      </template>
      <label v-if="result.status === 'AMBIGUOUS'" class="block text-slate-600">
        选择对应订单
        <select v-model="selectedOrderId" aria-label="选择识别客名的订单" class="mt-1 h-10 w-full rounded border border-slate-200 bg-white px-2" @change="recognize(selectedOrderId)">
          <option value="">请选择订单</option>
          <option v-for="order in result.orders" :key="order.id" :value="order.id">{{ order.customer_name }} · {{ order.order_no }} · ITEM {{ order.item_no }}</option>
        </select>
      </label>
    </template>
    <p v-if="error" class="text-red-600" role="alert">{{ error }}</p>
    <p v-if="!initializationOpen && initializationError" class="text-red-600" role="alert">{{ initializationError }}</p>
    <p v-if="!initializationOpen && initializationMessage" class="text-teal-700">{{ initializationMessage }}</p>
    <div class="flex flex-wrap gap-3">
      <button v-if="contractNumber.trim()" type="button" :disabled="loading" class="font-semibold text-teal-700 underline disabled:opacity-50" @click="selectedOrderId = ''; recognize()">重新识别客名</button>
      <button v-if="canManage" type="button" class="font-semibold text-teal-700 underline" @click="openInitialization">从本厂订单初始化客名</button>
    </div>
    <Teleport to="body">
      <div v-if="initializationOpen" class="fixed inset-0 z-[100] grid place-items-center bg-slate-900/50 p-4" @mousedown.self="closeInitialization">
        <section role="dialog" aria-modal="true" aria-labelledby="customer-initialization-title" class="flex max-h-[90vh] w-full max-w-xl flex-col rounded-xl bg-white p-5 text-sm shadow-xl">
          <h2 id="customer-initialization-title" class="text-lg font-semibold text-slate-900">从本厂纸箱订单初始化客名</h2>
          <p class="mt-2 text-slate-600">{{ factoryName }} · 勾选核实过的客户，确认后加入箱唛客户库。已有客名和存在身份歧义的客名会跳过，每次最多加入 200 个客名。</p>
          <p v-if="initializationLoading" class="my-4 text-slate-500">正在读取订单客名…</p>
          <div v-else class="my-4 space-y-2 overflow-y-auto">
            <label v-for="candidate in candidates" :key="candidate.name" class="flex gap-3 rounded border border-slate-200 p-3">
              <input v-model="selectedNames" type="checkbox" :value="candidate.name" :disabled="initializationBusy || !!candidate.existing_customer_id || !!candidate.warning || (selectedNames.length >= 200 && !selectedNames.includes(candidate.name))" class="mt-1">
              <span class="min-w-0 break-words"><strong>{{ candidate.name }}</strong><span class="ml-2 text-xs text-slate-500">{{ candidate.order_count }} 张订单</span>
                <span v-if="candidate.existing_customer_id" class="ml-2 text-xs text-teal-700">已在客户库</span>
                <span v-if="candidate.warning" class="mt-1 block text-xs text-amber-700">{{ candidate.warning }}</span>
              </span>
            </label>
            <p v-if="!candidates.length" class="text-slate-500">当前厂区没有可初始化的订单客名，可通过“维护客户”手动新增。</p>
          </div>
          <p v-if="initializationError" class="text-red-600" role="alert">{{ initializationError }}</p>
          <p v-if="initializationMessage" class="text-teal-700">{{ initializationMessage }}</p>
          <footer class="mt-4 flex flex-wrap justify-end gap-2">
            <button type="button" :disabled="initializationBusy" class="rounded border border-slate-200 px-3 py-2" @click="closeInitialization">关闭</button>
            <button type="button" :disabled="initializationLoading || initializationBusy || !selectedNames.length" class="rounded bg-teal-700 px-3 py-2 font-semibold text-white disabled:opacity-50" @click="addCustomers(selectedNames)">确认加入 {{ selectedNames.length }} 个客名</button>
          </footer>
        </section>
      </div>
    </Teleport>
  </div>
</template>
