<script setup lang="ts">
import { isYinhuiCustomer } from '@/lib/customerPriceConverters/yinhui'
import {
  CheckCircle2,
  CircleAlert,
  CloudDownload,
  Inbox,
  LoaderCircle,
  RefreshCw,
  Search,
  ShieldCheck,
} from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import {
  customerPriceArtifactApi,
  type CustomerPriceArtifactStatus,
  type CustomerPriceArtifactStatusFilter,
  type CustomerPriceInternalQuoteArtifact,
} from '@/api/customerPriceArtifact'
import { getApiErrorMessage } from '@/lib/http'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

interface CustomerChoice {
  id: string
  name: string
}

const props = defineProps<{
  customers: CustomerChoice[]
  selectedCustomerId: string
  prepareArtifact?: (artifact: CustomerPriceInternalQuoteArtifact, blob: Blob) => Promise<void>
}>()

const emit = defineEmits<{
  selectCustomer: [customerId: string]
  artifactConsumed: [handoffId: string]
}>()

const authStore = useAuthStore()
const appStore = useAppStore()
const statusFilter = ref<CustomerPriceArtifactStatusFilter>('available')
const customerFilter = ref('')
const keyword = ref('')
const artifacts = ref<CustomerPriceInternalQuoteArtifact[]>([])
const loading = ref(false)
const actingId = ref('')
const errorMessage = ref('')
const successMessage = ref('')
let artifactRequestSequence = 0
let factoryGeneration = 0

const activeFactoryId = computed(() => appStore.activeProductionFactory?.id ?? 'huaxing')
const hasConfiguredCustomers = computed(() => props.customers.length > 0)
const canImportArtifact = computed(() => authStore.can(
  'customer_price:import_internal_quote',
  activeFactoryId.value,
  'sales-business',
) && hasConfiguredCustomers.value)

function isCurrentFactory(factoryId: string, generation: number) {
  return factoryId === activeFactoryId.value && generation === factoryGeneration
}

const statusOptions: Array<{ value: CustomerPriceArtifactStatusFilter; label: string }> = [
  { value: 'available', label: '待接收' },
  { value: 'consumed', label: '已接收' },
  { value: 'revoked', label: '已撤销' },
  { value: 'all', label: '全部' },
]

function statusLabel(status: CustomerPriceArtifactStatus) {
  if (status === 'available') return '待接收'
  if (status === 'consumed') return '已接收'
  return '已撤销'
}

function statusClass(status: CustomerPriceArtifactStatus) {
  if (status === 'available') return 'bg-amber-50 text-amber-700 ring-amber-200'
  if (status === 'consumed') return 'bg-emerald-50 text-emerald-700 ring-emerald-200'
  return 'bg-slate-100 text-slate-600 ring-slate-200'
}

function formatDate(value: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString('zh-CN', { hour12: false })
}

function formatFileSize(size: number) {
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function manifestText(artifact: CustomerPriceInternalQuoteArtifact, key: string) {
  const value = artifact.artifact_manifest[key]
  return typeof value === 'string' || typeof value === 'number' ? String(value) : ''
}

function normalizeCustomerName(value: string) {
  return value.trim().toLowerCase().replace(/[\s_-]+/g, '')
}

function matchConfiguredCustomer(artifact: CustomerPriceInternalQuoteArtifact) {
  const target = normalizeCustomerName(artifact.customer)
  return props.customers.find((customer) => normalizeCustomerName(customer.name) === target || (customer.id === 'yinhui' && isYinhuiCustomer(artifact.customer)) || (customer.id === 'dicky' && ['dickie', 'dicky'].includes(target)))
}

async function loadArtifacts() {
  const requestId = ++artifactRequestSequence
  const requestedFactoryId = activeFactoryId.value
  const requestedFactoryGeneration = factoryGeneration

  if (!canImportArtifact.value) {
    artifacts.value = []
    loading.value = false
    return
  }

  loading.value = true
  errorMessage.value = ''
  try {
    const nextArtifacts = await customerPriceArtifactApi.list({
      factoryId: requestedFactoryId,
      status: statusFilter.value,
      customer: customerFilter.value,
      keyword: keyword.value.trim(),
    })

    if (
      requestId !== artifactRequestSequence
      || !isCurrentFactory(requestedFactoryId, requestedFactoryGeneration)
    ) return

    artifacts.value = nextArtifacts.filter((artifact) => artifact.factory_id === requestedFactoryId)
  } catch (error) {
    if (
      requestId !== artifactRequestSequence
      || !isCurrentFactory(requestedFactoryId, requestedFactoryGeneration)
    ) return

    artifacts.value = []
    errorMessage.value = `读取交接文件失败：${getApiErrorMessage(error)}`
  } finally {
    if (
      requestId === artifactRequestSequence
      && isCurrentFactory(requestedFactoryId, requestedFactoryGeneration)
    ) loading.value = false
  }
}

async function selectStatus(status: CustomerPriceArtifactStatusFilter) {
  statusFilter.value = status
  successMessage.value = ''
  await loadArtifacts()
}

async function sha256(blob: Blob) {
  if (!globalThis.crypto?.subtle) return ''
  const digest = await globalThis.crypto.subtle.digest('SHA-256', await blob.arrayBuffer())
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('')
}

function downloadBlob(blob: Blob, fileName: string) {
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  anchor.style.display = 'none'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => window.URL.revokeObjectURL(url), 1000)
}

async function fetchVerifiedArtifact(artifact: CustomerPriceInternalQuoteArtifact) {
  const file = await customerPriceArtifactApi.download(artifact.id)
  if (file.releaseStage && file.releaseStage !== 'p4_final_approved') {
    throw new Error(`服务端返回了非 P4 放行文件：${file.releaseStage}`)
  }
  if (file.sha256 && file.sha256.toLowerCase() !== artifact.sha256.toLowerCase()) {
    throw new Error('下载响应的 SHA-256 与交接记录不一致')
  }
  const actualSha = await sha256(file.blob)
  if (actualSha && actualSha.toLowerCase() !== artifact.sha256.toLowerCase()) {
    throw new Error('下载文件的 SHA-256 校验失败')
  }
  return file.blob
}

async function downloadArtifact(artifact: CustomerPriceInternalQuoteArtifact) {
  if (
    !canImportArtifact.value
    || artifact.factory_id !== activeFactoryId.value
    || artifact.status === 'revoked'
    || actingId.value
  ) return
  const requestedFactoryId = activeFactoryId.value
  const requestedFactoryGeneration = factoryGeneration
  actingId.value = artifact.id
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const blob = await fetchVerifiedArtifact(artifact)
    if (!isCurrentFactory(requestedFactoryId, requestedFactoryGeneration)) return
    downloadBlob(blob, artifact.file_name)
    successMessage.value = `${artifact.quote_no} 受控文件已通过 SHA-256 校验并开始下载。`
  } catch (error) {
    if (!isCurrentFactory(requestedFactoryId, requestedFactoryGeneration)) return
    errorMessage.value = `下载失败：${getApiErrorMessage(error)}`
  } finally {
    if (isCurrentFactory(requestedFactoryId, requestedFactoryGeneration)) actingId.value = ''
  }
}

async function consumeArtifact(artifact: CustomerPriceInternalQuoteArtifact) {
  if (
    !canImportArtifact.value
    || artifact.factory_id !== activeFactoryId.value
    || artifact.status !== 'available'
    || actingId.value
  ) return
  const requestedFactoryId = activeFactoryId.value
  const requestedFactoryGeneration = factoryGeneration
  actingId.value = artifact.id
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const blob = await fetchVerifiedArtifact(artifact)
    if (!isCurrentFactory(requestedFactoryId, requestedFactoryGeneration)) return
    const matchedCustomer = matchConfiguredCustomer(artifact)
    if (props.prepareArtifact && !matchedCustomer) {
      throw new Error(`尚未配置“${artifact.customer}”的客户转换模板，文件保持待接收`)
    }
    if (matchedCustomer && props.prepareArtifact) {
      await props.prepareArtifact(artifact, blob)
      if (!isCurrentFactory(requestedFactoryId, requestedFactoryGeneration)) return
    }
    await customerPriceArtifactApi.consume(artifact.id, `customer-price-ui:${artifact.id}`)
    if (!isCurrentFactory(requestedFactoryId, requestedFactoryGeneration)) return
    if (matchedCustomer && matchedCustomer.id !== props.selectedCustomerId) {
      emit('selectCustomer', matchedCustomer.id)
    }
    emit('artifactConsumed', artifact.id)
    downloadBlob(blob, artifact.file_name)
    successMessage.value = matchedCustomer
      ? `${artifact.quote_no} 已一次性接收，${matchedCustomer.name} 转换预览已生成，并已下载受控源文件。`
      : `${artifact.quote_no} 已一次性接收并下载；当前尚无“${artifact.customer}”客户模板，请保留受控文件等待模板配置。`
    await loadArtifacts()
  } catch (error) {
    if (!isCurrentFactory(requestedFactoryId, requestedFactoryGeneration)) return
    const message = getApiErrorMessage(error)
    await loadArtifacts()
    if (!isCurrentFactory(requestedFactoryId, requestedFactoryGeneration)) return
    errorMessage.value = `接收或转换预检失败：${message}`
  } finally {
    if (isCurrentFactory(requestedFactoryId, requestedFactoryGeneration)) actingId.value = ''
  }
}

async function restoreConsumedArtifact(artifact: CustomerPriceInternalQuoteArtifact) {
  if (
    !canImportArtifact.value
    || artifact.factory_id !== activeFactoryId.value
    || artifact.status !== 'consumed'
    || actingId.value
  ) return
  const requestedFactoryId = activeFactoryId.value
  const requestedFactoryGeneration = factoryGeneration
  actingId.value = artifact.id
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const blob = await fetchVerifiedArtifact(artifact)
    if (!isCurrentFactory(requestedFactoryId, requestedFactoryGeneration)) return
    const matchedCustomer = matchConfiguredCustomer(artifact)
    if (!matchedCustomer || !props.prepareArtifact) {
      throw new Error(`尚未配置“${artifact.customer}”的客户转换模板，无法恢复转换预览`)
    }
    await props.prepareArtifact(artifact, blob)
    if (!isCurrentFactory(requestedFactoryId, requestedFactoryGeneration)) return
    if (matchedCustomer.id !== props.selectedCustomerId) emit('selectCustomer', matchedCustomer.id)
    emit('artifactConsumed', artifact.id)
    successMessage.value = `${artifact.quote_no} 已从受控源文件恢复 ${matchedCustomer.name} 转换预览；后端接收记录未重复生成。`
  } catch (error) {
    if (!isCurrentFactory(requestedFactoryId, requestedFactoryGeneration)) return
    errorMessage.value = `恢复转换预览失败：${getApiErrorMessage(error)}`
  } finally {
    if (isCurrentFactory(requestedFactoryId, requestedFactoryGeneration)) actingId.value = ''
  }
}

watch(activeFactoryId, () => {
  factoryGeneration += 1
  artifactRequestSequence += 1
  artifacts.value = []
  loading.value = false
  actingId.value = ''
  errorMessage.value = ''
  successMessage.value = ''
  void loadArtifacts()
})
onMounted(() => { void loadArtifacts() })
onBeforeUnmount(() => {
  factoryGeneration += 1
  artifactRequestSequence += 1
})
</script>

<template>
  <SectionPanel
    title="内部报价交接池"
    subtitle="P4 v2 会先校验客户映射再一次性接收并生成转换预览；字段不完整时保持待接收，领取状态、撤销状态和厂区权限均由服务端控制"
  >
    <template #action>
      <button
        type="button"
        class="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700 transition hover:border-teal-300 hover:text-teal-800 disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="loading || !canImportArtifact"
        @click="loadArtifacts"
      >
        <RefreshCw class="size-4" :class="loading ? 'animate-spin' : ''" aria-hidden="true" />
        刷新交接池
      </button>
    </template>

    <div v-if="!hasConfiguredCustomers" class="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-4 text-sm text-amber-800">
      <CircleAlert class="mt-0.5 size-5 shrink-0" aria-hidden="true" />
      <div><strong class="block">当前厂区尚未配置报客映射</strong><span class="mt-1 block">请先为本厂区建立独立客户映射链路，再接收 P4 交接文件。</span></div>
    </div>

    <div v-else-if="!canImportArtifact" class="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-4 text-sm text-amber-800">
      <CircleAlert class="mt-0.5 size-5 shrink-0" aria-hidden="true" />
      <div><strong class="block">当前账号不可接收内部报价</strong><span class="mt-1 block">需要当前厂区的 `customer_price:import_internal_quote` 权限。</span></div>
    </div>

    <template v-else>
      <div class="grid gap-3 lg:grid-cols-[auto_180px_minmax(220px,1fr)_auto] lg:items-end">
        <div>
          <span class="mb-2 block text-xs font-semibold text-slate-600">交接状态</span>
          <div class="inline-flex flex-wrap rounded-lg border border-slate-200 bg-slate-50 p-1">
            <button
              v-for="option in statusOptions"
              :key="option.value"
              type="button"
              :data-testid="`artifact-status-${option.value}`"
              :data-active="statusFilter === option.value"
              class="h-8 rounded-md px-3 text-xs font-semibold transition"
              :class="statusFilter === option.value ? 'bg-white text-teal-800 shadow-sm' : 'text-slate-500 hover:text-slate-900'"
              @click="selectStatus(option.value)"
            >
              {{ option.label }}
            </button>
          </div>
        </div>

        <label>
          <span class="mb-2 block text-xs font-semibold text-slate-600">客户</span>
          <select v-model="customerFilter" class="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-800 outline-none transition focus:border-teal-400" @change="loadArtifacts">
            <option value="">全部客户</option>
            <option v-for="customer in customers" :key="customer.id" :value="customer.name">{{ customer.name }}</option>
          </select>
        </label>

        <label class="relative">
          <span class="mb-2 block text-xs font-semibold text-slate-600">搜索</span>
          <Search class="pointer-events-none absolute bottom-3 left-3 size-4 text-slate-400" aria-hidden="true" />
          <input v-model="keyword" type="search" class="h-10 w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 text-sm text-slate-800 outline-none transition focus:border-teal-400" placeholder="报价号、客户或版本" @keyup.enter="loadArtifacts">
        </label>

        <button type="button" class="h-10 rounded-lg bg-slate-950 px-4 text-xs font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50" :disabled="loading" @click="loadArtifacts">查询</button>
      </div>

      <p v-if="successMessage" class="mt-4 flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
        <CheckCircle2 class="mt-0.5 size-4 shrink-0" aria-hidden="true" />{{ successMessage }}
      </p>
      <p v-if="errorMessage" class="mt-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
        <CircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />{{ errorMessage }}
      </p>

      <div v-if="loading" class="mt-4 flex min-h-32 items-center justify-center gap-3 rounded-lg border border-slate-200 bg-slate-50 text-sm text-slate-600">
        <LoaderCircle class="size-5 animate-spin" aria-hidden="true" />正在读取最终放行交接文件…
      </div>

      <div v-else-if="artifacts.length === 0" class="mt-4 flex min-h-32 flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 text-center">
        <Inbox class="size-7 text-slate-400" aria-hidden="true" />
        <strong class="mt-3 text-sm text-slate-800">{{ hasConfiguredCustomers ? '当前筛选下没有交接文件' : '当前厂区尚未配置报客映射' }}</strong>
        <span class="mt-1 text-xs text-slate-500">{{ hasConfiguredCustomers ? '只有已由本单负责跟客最终放行且未被后续 revision 撤销的文件会进入待接收列表。' : '请先为本厂区建立独立客户映射链路，再接收 P4 交接文件。' }}</span>
      </div>

      <div v-else class="mt-4 grid gap-3 xl:grid-cols-2">
        <article v-for="artifact in artifacts" :key="artifact.id" class="rounded-xl border border-slate-200 bg-white p-4 shadow-[0_10px_24px_rgba(15,23,42,0.05)] transition hover:-translate-y-0.5 hover:border-teal-200 hover:shadow-[0_14px_30px_rgba(15,23,42,0.08)]">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <strong class="text-base text-slate-950">{{ artifact.quote_no }}</strong>
                <span class="rounded-full px-2.5 py-1 text-xs font-semibold ring-1" :class="statusClass(artifact.status)">{{ statusLabel(artifact.status) }}</span>
                <span class="rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700 ring-1 ring-indigo-200">P4 · R{{ artifact.release_revision }}</span>
              </div>
              <p class="mt-2 truncate text-sm text-slate-600">{{ artifact.customer }} · {{ manifestText(artifact, 'product_name') || '未填写产品名称' }} · {{ artifact.version_label }}</p>
            </div>
            <ShieldCheck class="size-6 shrink-0 text-teal-700" aria-label="P4 受控文件" />
          </div>

          <dl class="mt-4 grid gap-3 rounded-lg bg-slate-50 p-3 text-xs sm:grid-cols-2">
            <div><dt class="text-slate-500">受控文件</dt><dd class="mt-1 truncate font-semibold text-slate-800" :title="artifact.file_name">{{ artifact.file_name }}</dd></div>
            <div><dt class="text-slate-500">文件大小</dt><dd class="mt-1 font-semibold text-slate-800">{{ formatFileSize(artifact.size_bytes) }}</dd></div>
            <div><dt class="text-slate-500">SHA-256</dt><dd class="mt-1 truncate font-mono text-slate-700" :title="artifact.sha256">{{ artifact.sha256 }}</dd></div>
            <div><dt class="text-slate-500">放行时间</dt><dd class="mt-1 font-medium text-slate-700">{{ formatDate(artifact.created_at) }}</dd></div>
          </dl>

          <p v-if="artifact.status === 'consumed'" class="mt-3 rounded-lg border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">{{ artifact.consumed_by_name || '已授权用户' }} 于 {{ formatDate(artifact.consumed_at) }} 接收 · {{ artifact.consumer_reference }}</p>
          <p v-if="artifact.status === 'revoked'" class="mt-3 rounded-lg border border-slate-200 bg-slate-100 px-3 py-2 text-xs text-slate-700">撤销原因：{{ artifact.revoke_reason || '最终放行已失效或被后续版本取代' }}</p>

          <div class="mt-4 flex flex-wrap justify-end gap-2">
            <button v-if="artifact.status !== 'revoked'" type="button" class="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700 transition hover:border-teal-300 hover:text-teal-800 disabled:cursor-wait disabled:opacity-50" :disabled="Boolean(actingId)" @click="downloadArtifact(artifact)">
              <CloudDownload class="size-4" aria-hidden="true" />{{ artifact.status === 'consumed' ? '重新下载' : '下载核对' }}
            </button>
            <button v-if="artifact.status === 'available'" type="button" :data-testid="`consume-artifact-${artifact.id}`" class="inline-flex h-9 items-center gap-2 rounded-lg bg-teal-700 px-3 text-xs font-semibold text-white transition hover:bg-teal-600 disabled:cursor-wait disabled:bg-slate-400" :disabled="Boolean(actingId)" @click="consumeArtifact(artifact)">
              <LoaderCircle v-if="actingId === artifact.id" class="size-4 animate-spin" aria-hidden="true" />
              <CheckCircle2 v-else class="size-4" aria-hidden="true" />
              {{ actingId === artifact.id ? '正在预检…' : '接收并转换' }}
            </button>
            <button v-if="artifact.status === 'consumed'" type="button" :data-testid="`restore-artifact-${artifact.id}`" class="inline-flex h-9 items-center gap-2 rounded-lg bg-teal-700 px-3 text-xs font-semibold text-white transition hover:bg-teal-600 disabled:cursor-wait disabled:bg-slate-400" :disabled="Boolean(actingId)" @click="restoreConsumedArtifact(artifact)">
              <LoaderCircle v-if="actingId === artifact.id" class="size-4 animate-spin" aria-hidden="true" />
              <RefreshCw v-else class="size-4" aria-hidden="true" />
              {{ actingId === artifact.id ? '正在恢复…' : '恢复转换预览' }}
            </button>
          </div>
        </article>
      </div>
    </template>
  </SectionPanel>
</template>
