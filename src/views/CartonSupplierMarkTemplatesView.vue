<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import CartonMarkAssetLibrary from '@/components/CartonMarkAssetLibrary.vue'
import CartonSupplierMarkCheck from '@/components/CartonSupplierMarkCheck.vue'
import CartonSupplierMarkUpload from '@/components/CartonSupplierMarkUpload.vue'
import CartonSupplierMarkPdf from '@/components/CartonSupplierMarkPdf.vue'
import CartonMarkManualReview, { type ManualReviewAsset } from '@/components/CartonMarkManualReview.vue'
import { cartonSupplierPortalApi, type SupplierMarkAsset } from '@/api/cartonSupplierPortal'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { factoryContexts } from '@/data/enterpriseMock'

const route = useRoute()
const auth = useAuthStore()
const tab = ref<'library' | 'check' | 'review' | 'pdf'>('library')
const generationSource = ref<(SupplierMarkAsset & { factory_id: string }) | null>(null)
function chooseGeneration(asset: SupplierMarkAsset & { factory_id: string }) { generationSource.value = asset; tab.value = 'pdf' }
const reviewSources = ref<ManualReviewAsset[]>([])
const reviewMessage = ref('')
function chooseReview(assets: ManualReviewAsset[]) { reviewSources.value = assets; reviewMessage.value = ''; tab.value = 'review' }
function reviewSaved() { reviewSources.value = []; reviewMessage.value = '已提交内部审核。内部审核人确认原稿并放行后，QC 才能选用此版本。'; load(); tab.value = 'check' }
const source = ref<(SupplierMarkAsset & { factory_id: string }) | null>(null)
const pdfSource = ref<(SupplierMarkAsset & { factory_id: string }) | null>(null)
function clearSource() { source.value = null; pdfSource.value = null; reviewSources.value = []; generationSource.value = null }
function chooseExcel(asset: SupplierMarkAsset & { factory_id: string }) { pdfSource.value = null; source.value = asset; tab.value = 'check' }
function chooseSources(assets: (SupplierMarkAsset & { factory_id: string })[]) { source.value = assets[0] ?? null; pdfSource.value = assets[1] ?? null; tab.value = 'check' }
const ALL_FACTORIES = 'ALL'
const memberships = ref<{ factory_id: string; supplier_name: string }[]>([])
const factory = ref(ALL_FACTORIES)
const memberFactoryIds = computed(() => memberships.value.map(member => member.factory_id))
const refreshKey = ref(0)
const discovering = ref(false)
const error = ref('')
let generation = 0
function factoryDisplayName(id: string) {
  return factoryContexts.find(item => item.id === id)?.shortName ?? id
}

function selectRequestedFactory() {
  const requested = typeof route.query.factory === 'string' ? route.query.factory : ''
  if (!memberships.value.length) {
    factory.value = ''
    error.value = '暂无可查看的已下单厂区，请联系内部确认供应商账号已开通且采购单已生成。'
    return
  }
  if (requested && requested !== ALL_FACTORIES && !memberships.value.some(member => member.factory_id === requested)) {
    factory.value = ''
    error.value = '所选厂区没有此供应商可查看的已生成订单，请选择其他服务厂区。'
    return
  }
  factory.value = requested || ALL_FACTORIES
  error.value = ''
}

function load() { refreshKey.value++ }

async function refresh(restart = false) {
  if (discovering.value && !restart) return
  const token = ++generation
  discovering.value = true
  error.value = ''
  try {
    const available = await cartonSupplierPortalApi.memberships()
    if (token !== generation) return
    memberships.value = available
    if (!available.length) {
      factory.value = ''
      error.value = '暂无可查看的已下单厂区，请联系内部确认供应商账号已开通且采购单已生成。'
      return
    }
    const scope = factory.value === ALL_FACTORIES || available.some(item => item.factory_id === factory.value)
      ? factory.value : ALL_FACTORIES
    if (scope !== factory.value) factory.value = scope
    else load()
  } catch (reason) {
    if (token === generation) { memberships.value = []; clearSource(); error.value = getApiErrorMessage(reason) }
  } finally { if (token === generation) discovering.value = false }
}

watch(factory, scope => {
  clearSource()
  if ((scope === ALL_FACTORIES && memberships.value.length) || memberships.value.some(member => member.factory_id === scope)) {
    error.value = ''; load()
  }
})
watch(() => route.query.factory, () => selectRequestedFactory())
watch([() => auth.currentUser?.id, () => auth.authorizationVersion,
  () => auth.can('carton_supplier:read', '*', '*')], () => {
  clearSource(); memberships.value = []; void refresh(true)
})
onBeforeUnmount(() => { generation++ })
onMounted(async () => {
  const token = ++generation
  discovering.value = true
  try {
    const available = await cartonSupplierPortalApi.memberships()
    if (token !== generation) return
    memberships.value = available
    selectRequestedFactory()
  } catch (reason) {
    if (token === generation) error.value = getApiErrorMessage(reason)
  } finally { if (token === generation) discovering.value = false }
})
</script>

<template>
  <main class="min-h-screen bg-slate-50 p-4 text-slate-800 md:p-8" data-yl-help="carton-supplier.overview">
    <header class="mx-auto mb-6 flex max-w-[1500px] flex-wrap items-center justify-between gap-4">
      <div>
        <RouterLink :to="{ path: '/carton-supplier', query: factory === ALL_FACTORIES ? {} : { factory } }" class="text-sm font-semibold text-teal-700">← 返回供应商协同</RouterLink>
        <h1 class="mt-2 text-2xl font-bold">箱唛资料库</h1>
        <p class="mt-1 text-sm text-slate-500">Excel / PDF 可一起核对；只有 PDF 或图片时，提交内部人工审核后供 QC 使用。</p>
      </div>
      <div class="flex w-full flex-wrap items-center gap-3 sm:w-auto">
        <select v-model="factory" aria-label="箱唛资料厂区" :disabled="discovering" class="min-w-0 max-w-full rounded-lg border bg-white p-2">
          <option :value="ALL_FACTORIES">全部厂区</option>
          <option v-for="member in memberships" :key="member.factory_id" :value="member.factory_id">{{ factoryDisplayName(member.factory_id) }} · {{ member.supplier_name }}</option>
        </select>
        <button type="button" :disabled="discovering" class="rounded-lg border bg-white px-3 py-2 disabled:opacity-50" @click="refresh()">{{ discovering ? '更新中…' : '刷新' }}</button>
        <AccountMenu />
      </div>
    </header>
    <section class="mx-auto max-w-[1500px]">
      <p v-if="error" role="alert" class="mb-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{{ error }}</p>
      <p v-if="discovering" role="status" class="p-4 text-sm text-slate-500">正在查询服务厂区…</p>
      <template v-if="memberships.length && factory && !error && !discovering">
        <nav class="mb-4 flex flex-wrap gap-2" aria-label="供应商箱唛工作区"><button type="button" class="rounded-lg border px-4 py-2" :class="tab === 'library' ? 'bg-teal-700 text-white' : 'bg-white'" @click="tab = 'library'">资料库</button><button type="button" class="rounded-lg border px-4 py-2" :class="tab === 'pdf' ? 'bg-teal-700 text-white' : 'bg-white'" @click="tab = 'pdf'">文档生成 PDF</button><button type="button" class="rounded-lg border px-4 py-2" :class="tab === 'check' ? 'bg-teal-700 text-white' : 'bg-white'" @click="tab = 'check'">核对 / 审核记录</button><button type="button" class="rounded-lg border px-4 py-2" :class="tab === 'review' ? 'bg-amber-700 text-white' : 'bg-white'" @click="tab = 'review'">单 PDF / 图片审核</button></nav>
        <CartonSupplierMarkUpload v-show="tab === 'library'" :factory-ids="factory === ALL_FACTORIES ? memberFactoryIds : [factory]" @uploaded="load" />
        <p v-if="reviewMessage" role="status" class="mb-4 rounded-lg bg-teal-50 p-3 text-sm text-teal-800">{{ reviewMessage }}</p>
        <CartonMarkAssetLibrary v-show="tab === 'library'" :key="`${factory}:${refreshKey}`" :factory-id="factory === ALL_FACTORIES ? '' : factory" :supplier-factories="factory === ALL_FACTORIES ? memberFactoryIds : undefined" supplier read-only supplier-check-enabled @supplier-excel="chooseExcel" @supplier-sources="chooseSources" @supplier-review="chooseReview" @supplier-generate-pdf="chooseGeneration" />
        <CartonSupplierMarkPdf v-show="tab === 'pdf'" :factory-ids="factory === ALL_FACTORIES ? memberFactoryIds : [factory]" :source="generationSource" @choose="tab = 'library'" @saved="load" @check="chooseSources" />
        <CartonMarkManualReview v-show="tab === 'review'" :sources="reviewSources" supplier @choose="tab = 'library'" @saved="reviewSaved" />
        <CartonSupplierMarkCheck v-show="tab === 'check'" :factory-ids="factory === ALL_FACTORIES ? memberFactoryIds : [factory]" :source="source" :pdf-source="pdfSource" :refresh-key="refreshKey" @choose-source="tab = 'library'" @clear-source="clearSource" @clear-pdf-source="pdfSource = null" />
      </template>
    </section>
  </main>
</template>
