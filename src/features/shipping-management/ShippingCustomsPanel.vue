<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ChevronDown, ChevronLeft, ChevronRight, Download, ExternalLink, RefreshCw, Search, Trash2 } from '@lucide/vue'
import { getApiErrorMessage } from '@/lib/http'
import {
  deleteCustomsDoc,
  listCustomsDocs,
  markCustomsDocsRead,
  openCustomsDoc,
  type CustomsDoc,
} from '@/api/shippingMail'

const props = defineProps<{ factoryId: string }>()
const emit = defineEmits<{ notify: [message: string]; back: [] }>()

const PAGE_SIZE = 10

const docs = ref<CustomsDoc[]>([])
const incoming = ref(0)
const loading = ref(false)
const message = ref('')
const searchInput = ref('')
const appliedQuery = ref('')
const portFilter = ref('')
const typeFilter = ref('')
const page = ref(1)
const pendingId = ref('')
const busyId = ref('')

const ports = computed(() => [...new Set(docs.value.map((doc) => doc.port).filter(Boolean))])
const containerTypes = computed(() => [...new Set(docs.value.map((doc) => doc.container_type).filter(Boolean))])

const filtered = computed(() => {
  const keyword = appliedQuery.value.trim().toLowerCase()
  return docs.value.filter((doc) => {
    if (portFilter.value && doc.port !== portFilter.value) return false
    if (typeFilter.value && doc.container_type !== typeFilter.value) return false
    if (!keyword) return true
    return doc.filename.toLowerCase().includes(keyword) || doc.subject.toLowerCase().includes(keyword)
  })
})
const total = computed(() => filtered.value.length)
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
const pagedDocs = computed(() => filtered.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE))

watch(filtered, () => { page.value = 1 })
watch(pageCount, (count) => { if (page.value > count) page.value = count })

function applySearch() {
  appliedQuery.value = searchInput.value.trim()
  page.value = 1
}

function resetSearch() {
  searchInput.value = ''
  appliedQuery.value = ''
  portFilter.value = ''
  typeFilter.value = ''
  page.value = 1
}

function formatMonthDayTime(value: string) {
  if (!value) return '—'
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/)
  if (!match) return value
  const [, , month, day, hour, minute] = match
  return hour ? `${Number(month)}/${Number(day)} ${hour}:${minute}` : `${Number(month)}/${Number(day)}`
}

function sizeLabel(size: number) {
  if (size > 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`
  return `${Math.max(1, Math.round(size / 1024))} KB`
}

async function load(markRead = false) {
  loading.value = true
  try {
    const result = await listCustomsDocs(props.factoryId)
    docs.value = result.docs
    incoming.value = result.unread
    message.value = ''
    if (result.unread) emit('notify', `有 ${result.unread} 份通关一体化资料到，请查看。`)
    if (result.unread && markRead) await markCustomsDocsRead(props.factoryId)
  } catch (error) {
    message.value = `读取通关一体化资料失败：${getApiErrorMessage(error)}`
  } finally {
    loading.value = false
  }
}

function downloadUrl(doc: CustomsDoc) {
  return `/api/shipping/customs-docs/${doc.id}/download?factory_id=${encodeURIComponent(props.factoryId)}`
}

function askDelete(doc: CustomsDoc) {
  pendingId.value = doc.id
  window.setTimeout(() => {
    if (pendingId.value === doc.id) pendingId.value = ''
  }, 5000)
}

async function confirmDelete(doc: CustomsDoc) {
  busyId.value = doc.id
  try {
    await deleteCustomsDoc(props.factoryId, doc.id)
    pendingId.value = ''
    await load(false)
  } catch (error) {
    message.value = `删除失败：${getApiErrorMessage(error)}`
  } finally {
    busyId.value = ''
  }
}

async function openFile(doc: CustomsDoc) {
  try {
    await openCustomsDoc(props.factoryId, doc.id)
  } catch (error) {
    message.value = `打开失败：${getApiErrorMessage(error)}`
  }
}

onMounted(() => load(true))
</script>

<template>
  <section class="enterprise-panel overflow-hidden rounded-xl" aria-label="通关一体化资料">
    <header class="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-4 py-4 sm:px-5">
      <div class="min-w-0">
        <div class="flex items-center gap-2">
          <h2 class="text-[17px] font-semibold tracking-[-0.02em] text-slate-950">通关一体化资料</h2>
          <span v-if="total" class="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold tabular-nums text-emerald-800">{{ total }}</span>
        </div>
        <p class="mt-1 text-[11px] text-slate-500">自动识别邮件中的「出货资料 / 通关一体化资料」，保存柜装箱单附件。</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <button type="button" class="text-[13px] font-semibold text-emerald-800 hover:underline" @click="emit('back')">← 返回工厂排期单</button>
        <button type="button" class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 text-[12px] font-semibold text-slate-600" @click="load(false)">
          <RefreshCw class="size-3.5" :class="loading ? 'animate-spin' : ''" />刷新
        </button>
      </div>
    </header>

    <p v-if="incoming" class="border-b border-amber-100 bg-amber-50 px-4 py-2 text-[12px] font-semibold text-amber-800" role="status">
      有 {{ incoming }} 份通关一体化资料到，请查看下方列表。
    </p>
    <p v-if="message" class="border-b border-rose-100 bg-rose-50 px-4 py-2 text-[11px] text-rose-600">{{ message }}</p>

    <div class="border-b border-slate-100 px-4 py-3 sm:px-5">
      <div class="flex flex-wrap items-center gap-2">
        <label class="relative min-w-[220px] flex-1">
          <span class="sr-only">搜索文件名或邮件主题</span>
          <Search class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
          <input
            v-model="searchInput"
            type="search"
            aria-label="搜索文件名或邮件主题"
            placeholder="搜索文件名或邮件主题"
            class="h-9 w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 text-[13px] text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-3 focus:ring-emerald-500/15"
            @keydown.enter="applySearch"
          >
        </label>
        <button type="button" class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-emerald-700 px-4 text-[12px] font-semibold text-white" @click="applySearch">
          <Search class="size-4" aria-hidden="true" />搜索
        </button>
        <label class="relative">
          <span class="sr-only">全部港口</span>
          <select v-model="portFilter" aria-label="全部港口" class="h-9 appearance-none rounded-lg border border-slate-200 bg-white pl-3 pr-8 text-[12px] font-medium text-slate-700 outline-none focus:border-emerald-500">
            <option value="">全部港口</option>
            <option v-for="name in ports" :key="name" :value="name">{{ name }}</option>
          </select>
          <ChevronDown class="pointer-events-none absolute right-2.5 top-1/2 size-3.5 -translate-y-1/2 text-slate-400" aria-hidden="true" />
        </label>
        <label class="relative">
          <span class="sr-only">全部柜型</span>
          <select v-model="typeFilter" aria-label="全部柜型" class="h-9 appearance-none rounded-lg border border-slate-200 bg-white pl-3 pr-8 text-[12px] font-medium text-slate-700 outline-none focus:border-emerald-500">
            <option value="">全部柜型</option>
            <option v-for="name in containerTypes" :key="name" :value="name">{{ name }}</option>
          </select>
          <ChevronDown class="pointer-events-none absolute right-2.5 top-1/2 size-3.5 -translate-y-1/2 text-slate-400" aria-hidden="true" />
        </label>
        <button type="button" class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-600" @click="resetSearch">重置</button>
      </div>
    </div>

    <div class="overflow-x-auto">
      <table class="w-full min-w-[1080px] text-left text-[12px]">
        <thead class="bg-slate-50 text-[11px] font-semibold text-slate-500">
          <tr>
            <th class="px-3 py-2">文件名</th>
            <th class="px-3 py-2">邮件主题</th>
            <th class="px-3 py-2">港口</th>
            <th class="px-3 py-2">柜型</th>
            <th class="px-3 py-2">SI截止 / 截关期</th>
            <th class="px-3 py-2">特殊要求</th>
            <th class="px-3 py-2 text-right">大小</th>
            <th class="px-3 py-2">到达时间</th>
            <th class="px-3 py-2 text-right">操作</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-for="doc in pagedDocs" :key="doc.id" class="bg-white hover:bg-slate-50/60">
            <td class="px-3 py-2 font-semibold text-slate-800">{{ doc.filename }}</td>
            <td class="max-w-[340px] truncate px-3 py-2 text-slate-600">{{ doc.subject }}</td>
            <td class="px-3 py-2 text-slate-600">{{ doc.port || '—' }}</td>
            <td class="px-3 py-2 text-slate-600">{{ doc.container_type || '—' }}</td>
            <td class="px-3 py-2 tabular-nums text-slate-600">{{ formatMonthDayTime(doc.si_cutoff) }}</td>
            <td class="max-w-[180px] truncate px-3 py-2 text-[11px] text-slate-500" :title="doc.special_note || '—'">{{ doc.special_note || '—' }}</td>
            <td class="px-3 py-2 text-right tabular-nums text-slate-500">{{ sizeLabel(doc.size) }}</td>
            <td class="px-3 py-2 tabular-nums text-slate-500">{{ formatMonthDayTime(doc.created_at) }}</td>
            <td class="px-3 py-2 text-right">
              <div class="flex items-center justify-end gap-3">
                <button type="button" class="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700" @click="openFile(doc)">
                  <ExternalLink class="size-3.5" />打开
                </button>
                <a :href="downloadUrl(doc)" :download="doc.filename" target="_blank" rel="noopener" class="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700">
                  <Download class="size-3.5" />下载
                </a>
                <button
                  v-if="pendingId === doc.id"
                  type="button"
                  class="inline-flex items-center gap-1 text-[11px] font-semibold text-rose-700 disabled:opacity-50"
                  :disabled="busyId === doc.id"
                  @click="confirmDelete(doc)"
                >
                  <Trash2 class="size-3.5" />确认删除
                </button>
                <button v-else type="button" class="inline-flex items-center gap-1 text-[11px] font-semibold text-rose-600" @click="askDelete(doc)">
                  <Trash2 class="size-3.5" />删除
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="!pagedDocs.length">
            <td colspan="9" class="px-3 py-12 text-center text-slate-400">{{ docs.length ? '没有匹配的资料' : '暂无通关一体化资料' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <footer class="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 px-4 py-2.5 sm:px-5">
      <span class="text-[11px] text-slate-500">第 {{ page }} / {{ pageCount }} 页 · 本页 {{ pagedDocs.length }} 条</span>
      <div class="flex items-center gap-2">
        <button type="button" class="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 text-[11px] font-semibold text-slate-600 disabled:opacity-40" :disabled="page <= 1" @click="page -= 1">
          <ChevronLeft class="size-3.5" />上一页
        </button>
        <button type="button" class="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 text-[11px] font-semibold text-slate-600 disabled:opacity-40" :disabled="page >= pageCount" @click="page += 1">
          下一页<ChevronRight class="size-3.5" />
        </button>
      </div>
    </footer>
  </section>
</template>
