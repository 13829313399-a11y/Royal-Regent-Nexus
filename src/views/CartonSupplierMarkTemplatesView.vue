<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import { cartonSupplierPortalApi, type SupplierMarkTemplate } from '@/api/cartonSupplierPortal'
import { factoryContexts } from '@/data/enterpriseMock'

const route = useRoute()
const memberships = ref<{ factory_id: string; supplier_name: string }[]>([])
const factory = ref('')
const templates = ref<SupplierMarkTemplate[]>([])
const loading = ref(false)
const discovering = ref(false)
const downloading = ref('')
const error = ref('')
let generation = 0
function factoryDisplayName(id: string) {
  return factoryContexts.find(item => item.id === id)?.shortName ?? id
}

function selectRequestedFactory() {
  const requested = typeof route.query.factory === 'string' ? route.query.factory : ''
  if (!memberships.value.length) {
    factory.value = ''
    templates.value = []
    error.value = '暂无可查看的已下单厂区，请联系内部确认供应商账号已开通且采购单已发行。'
    return
  }
  if (requested && !memberships.value.some(member => member.factory_id === requested)) {
    factory.value = ''
    templates.value = []
    error.value = '所选厂区没有此供应商可查看的已发行订单，请选择其他服务厂区。'
    return
  }
  factory.value = requested || memberships.value[0]?.factory_id || ''
  if (!factory.value) error.value = '暂无可查看的已下单厂区，请联系内部确认供应商账号已开通且采购单已发行。'
}

async function load() {
  const scope = factory.value
  const version = ++generation
  templates.value = []
  if (!scope) return
  loading.value = true
  error.value = ''
  try {
    const records = await cartonSupplierPortalApi.markTemplates(scope)
    if (version === generation && factory.value === scope) templates.value = records
  } catch (reason) {
    if (version === generation) error.value = reason instanceof Error ? reason.message : '箱唛资料读取失败，请重试。'
  } finally {
    if (version === generation) loading.value = false
  }
}
async function refresh() {
  if (discovering.value) return
  discovering.value = true
  error.value = ''
  try {
    const available = await cartonSupplierPortalApi.memberships()
    memberships.value = available
    const scope = available.some(item => item.factory_id === factory.value)
      ? factory.value : available[0]?.factory_id ?? ''
    if (scope !== factory.value) factory.value = scope
    else if (scope) await load()
    else {
      templates.value = []
      error.value = '暂无可查看的已下单厂区，请联系内部确认供应商账号已开通且采购单已发行。'
    }
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '服务厂区读取失败，请重试。'
  } finally { discovering.value = false }
}

async function download(template: SupplierMarkTemplate, kind: 'source_excel' | 'print_pdf') {
  if (downloading.value) return
  const scope = factory.value
  downloading.value = `${template.id}:${kind}`
  error.value = ''
  try {
    await cartonSupplierPortalApi.downloadMarkDocument(template.id, kind, scope,
      kind === 'source_excel' ? template.excel_file_name : template.pdf_file_name)
  } catch (reason) {
    if (scope === factory.value) error.value = reason instanceof Error ? reason.message : '箱唛文档下载失败，请重试。'
  } finally {
    downloading.value = ''
  }
}

watch(factory, scope => {
  if (scope) void load()
  else {
    ++generation
    templates.value = []
    error.value = '暂无可查看的已下单厂区，请联系内部确认供应商账号已开通且采购单已发行。'
  }
})
watch(() => route.query.factory, () => selectRequestedFactory())
onMounted(async () => {
  try {
    memberships.value = await cartonSupplierPortalApi.memberships()
    selectRequestedFactory()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '供应商绑定读取失败，请重试。'
  }
})
</script>

<template>
  <main class="min-h-screen bg-slate-50 p-4 text-slate-800 md:p-8">
    <header class="mx-auto mb-6 flex max-w-6xl flex-wrap items-center justify-between gap-4">
      <div>
        <RouterLink :to="{ path: '/carton-supplier', query: { factory } }" class="text-sm font-semibold text-teal-700">← 返回供应商协同</RouterLink>
        <h1 class="mt-2 text-2xl font-bold">箱唛资料模板</h1>
        <p class="mt-1 text-sm text-slate-500">仅显示所选送货厂区已发行采购单关联、已核对可用的最新版箱唛资料；供应商可查看和下载。</p>
      </div>
      <div class="flex items-center gap-3">
        <select v-model="factory" aria-label="箱唛资料厂区" :disabled="loading" class="rounded-lg border bg-white p-2">
          <option v-for="member in memberships" :key="member.factory_id" :value="member.factory_id">{{ factoryDisplayName(member.factory_id) }} · {{ member.supplier_name }}</option>
        </select>
        <button type="button" :disabled="loading || discovering" class="rounded-lg border bg-white px-3 py-2 disabled:opacity-50" @click="refresh">{{ discovering ? '更新中…' : '刷新' }}</button>
        <AccountMenu />
      </div>
    </header>
    <section class="mx-auto max-w-6xl space-y-3">
      <p v-if="error" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
      <p v-if="loading" role="status" class="rounded-lg border bg-white p-5 text-sm text-slate-500">正在读取箱唛资料…</p>
      <p v-else-if="factory && !templates.length && !error" class="rounded-lg border bg-white p-6 text-sm text-slate-500">暂无与已发行采购单关联且核对可用的箱唛资料。</p>
      <article v-for="template in templates" :key="template.id" :data-template-id="template.id" class="rounded-xl border bg-white p-5 shadow-sm">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 class="font-bold">{{ template.customer_name }} · {{ template.item }} · 第 {{ template.version }} 版</h2>
            <p class="mt-1 text-sm text-slate-600">合同 {{ template.contract_number }} · 客户 PO {{ template.po }}</p>
          </div>
          <span class="rounded-full bg-teal-50 px-3 py-1 text-xs font-semibold text-teal-800">{{ template.manual_released ? '人工放行' : '核对通过' }}</span>
        </div>
        <div class="mt-4 flex flex-wrap gap-2">
          <a :href="cartonSupplierPortalApi.previewMarkPdfUrl(template.id, factory)" target="_blank" rel="noopener noreferrer" :aria-label="`查看 ${template.id} 印刷 PDF`" class="rounded-lg border border-teal-200 px-3 py-2 text-sm text-teal-800">查看印刷 PDF</a>
          <button type="button" :disabled="Boolean(downloading)" :aria-label="`下载 ${template.id} 客人 Excel`" class="rounded-lg border border-teal-200 px-3 py-2 text-sm text-teal-800 disabled:opacity-50" @click="download(template, 'source_excel')">下载客人 Excel</button>
          <button type="button" :disabled="Boolean(downloading)" :aria-label="`下载 ${template.id} 印刷 PDF`" class="rounded-lg border border-teal-200 px-3 py-2 text-sm text-teal-800 disabled:opacity-50" @click="download(template, 'print_pdf')">下载印刷 PDF</button>
        </div>
      </article>
    </section>
  </main>
</template>
