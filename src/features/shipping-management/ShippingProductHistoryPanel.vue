<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Plus, RefreshCw, UploadCloud } from '@lucide/vue'
import { getApiErrorMessage } from '@/lib/http'
import {
  importProductHistory,
  listProductHistory,
  type ProductHistoryRecord,
} from '@/api/shippingMail'

const props = defineProps<{ factoryId: string }>()
const emit = defineEmits<{ notify: [message: string] }>()

const customers = ['ZURU', 'MOOSE', 'TIG', 'TOMY', 'CEPIA', 'AZAD', 'ZANZOON', 'JOHN ADAMS']
const customer = ref('ZURU')
const files = ref<File[]>([])
const input = ref<HTMLInputElement | null>(null)
const records = ref<ProductHistoryRecord[]>([])
const importing = ref(false)
const loading = ref(false)
const message = ref('')

const fileLabel = computed(() => `${files.value.length} 个文件`)

function choose() {
  input.value?.click()
}

function setFiles(next: File[]) {
  files.value = next.filter((file) => /\.(xls|xlsx)$/i.test(file.name))
  if (files.value.length !== next.length) message.value = '仅支持 .xls / .xlsx 柜单文件'
}

function onFileChange(event: Event) {
  setFiles([...((event.target as HTMLInputElement).files ?? [])])
}

function onDrop(event: DragEvent) {
  setFiles([...(event.dataTransfer?.files ?? [])])
}

async function loadRecords() {
  loading.value = true
  try {
    records.value = await listProductHistory(props.factoryId, customer.value)
  } catch (error) {
    message.value = `读取导入记录失败：${getApiErrorMessage(error)}`
  } finally {
    loading.value = false
  }
}

async function doImport() {
  if (!files.value.length) {
    message.value = '请先选择柜单 Excel 文件'
    return
  }
  importing.value = true
  message.value = ''
  try {
    const result = await importProductHistory(props.factoryId, customer.value, files.value)
    records.value = result.records
    message.value = `导入完成：新增 ${result.created} 条，更新 ${result.updated} 条`
    emit('notify', message.value)
    files.value = []
    if (input.value) input.value.value = ''
  } catch (error) {
    message.value = `导入失败：${getApiErrorMessage(error)}`
  } finally {
    importing.value = false
  }
}

function sendRecords() {
  if (!records.value.length) {
    message.value = '暂无可发送的出货资料，请先导入柜单'
    return
  }
  message.value = `界面预览：一键发送 ${records.value.length} 条资料（邮箱 / 企业微信）尚未接入后端接口。`
  emit('notify', message.value)
}

onMounted(loadRecords)
</script>

<template>
  <section class="space-y-4" aria-label="一键出货">
    <div class="rounded-xl border border-emerald-100/80 bg-white p-4">
      <div class="flex items-center gap-2">
        <Plus class="size-5 text-emerald-600" aria-hidden="true" />
        <h2 class="text-[16px] font-bold text-emerald-950">每日新增出货资料</h2>
      </div>

      <div
        class="mt-3 flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-emerald-200 bg-emerald-50/30 px-4 py-10 text-center transition hover:border-emerald-400 hover:bg-emerald-50/60"
        role="button"
        tabindex="0"
        aria-label="上传柜单 Excel 文件"
        @click="choose"
        @keydown.enter.prevent="choose"
        @dragover.prevent
        @drop.prevent="onDrop"
      >
        <UploadCloud class="size-10 text-emerald-500" aria-hidden="true" />
        <p class="mt-3 text-[13px] text-slate-700">将柜单 Excel 文件拖到此处，或 <span class="font-semibold text-emerald-700">点击上传</span>（支持多个 .xls/.xlsx）</p>
        <p class="mt-1 text-[11px] text-slate-400">系统将自动提取货号、货名、玩具类别、每箱毛重、每箱净重</p>
        <input ref="input" type="file" accept=".xls,.xlsx" multiple class="hidden" @change="onFileChange">
      </div>

      <div class="mt-3 flex flex-wrap items-center gap-3">
        <label class="flex items-center gap-2 text-[12px] text-slate-600">
          归属客户：
          <select v-model="customer" class="h-8 rounded-lg border border-slate-200 bg-white px-2 text-[12px]" @change="loadRecords">
            <option v-for="name in customers" :key="name" :value="name">{{ name }}</option>
          </select>
        </label>
        <button
          type="button"
          class="inline-flex h-8 items-center gap-1.5 rounded-lg bg-emerald-500 px-4 text-[12px] font-semibold text-white transition hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="!files.length || importing"
          @click="doImport"
        >
          {{ importing ? '导入中…' : `导入 (${fileLabel})` }}
        </button>
        <button
          type="button"
          class="inline-flex h-8 items-center gap-1.5 rounded-lg bg-sky-600 px-4 text-[12px] font-semibold text-white transition hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="!records.length"
          @click="sendRecords"
        >
          一键发送
        </button>
        <span v-if="files.length" class="text-[11px] text-slate-500">{{ files.map((file) => file.name).join('、') }}</span>
      </div>
      <p v-if="message" class="mt-2 text-[11px]" :class="message.includes('失败') ? 'text-rose-600' : 'text-emerald-700'">{{ message }}</p>
    </div>

    <div class="rounded-xl border border-emerald-100/80 bg-white p-4">
      <div class="flex items-center justify-between">
        <h3 class="text-[14px] font-bold text-slate-800">最近导入记录</h3>
        <button type="button" class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 px-3 text-[12px] text-slate-600" :disabled="loading" @click="loadRecords">
          <RefreshCw class="size-3.5" :class="loading ? 'animate-spin' : ''" />刷新
        </button>
      </div>
      <div class="mt-3 overflow-x-auto">
        <table class="w-full min-w-[860px] text-left text-[11px]">
          <thead class="bg-slate-50 text-slate-500">
            <tr>
              <th class="px-2 py-2">货号</th><th class="px-2 py-2">货名</th><th class="px-2 py-2">玩具类别</th>
              <th class="px-2 py-2 text-right">每箱毛重</th><th class="px-2 py-2 text-right">每箱净重</th>
              <th class="px-2 py-2">客户</th><th class="px-2 py-2">来源</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="record in records" :key="record.id">
              <td class="px-2 py-1.5 font-semibold text-sky-700">{{ record.product_code }}</td>
              <td class="max-w-[360px] truncate px-2 py-1.5 text-slate-700">{{ record.product_name }}</td>
              <td class="px-2 py-1.5 text-slate-600">{{ record.category || '-' }}</td>
              <td class="px-2 py-1.5 text-right tabular-nums">{{ record.gross_per_carton || '-' }}</td>
              <td class="px-2 py-1.5 text-right tabular-nums">{{ record.net_per_carton || '-' }}</td>
              <td class="px-2 py-1.5">
                <span class="rounded-full bg-sky-50 px-2 py-0.5 text-[10px] font-semibold text-sky-700">{{ record.customer }}</span>
              </td>
              <td class="px-2 py-1.5 text-slate-500">{{ record.source }}</td>
            </tr>
            <tr v-if="!records.length">
              <td colspan="7" class="px-2 py-8 text-center text-slate-400">还没有导入记录</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>
