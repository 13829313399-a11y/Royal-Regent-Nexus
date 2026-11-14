<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Download, RefreshCw } from '@lucide/vue'
import { getApiErrorMessage } from '@/lib/http'
import {
  downloadCustomsDoc,
  listCustomsDocs,
  markCustomsDocsRead,
  type CustomsDoc,
} from '@/api/shippingMail'

const props = defineProps<{ factoryId: string }>()
const emit = defineEmits<{ notify: [message: string]; back: [] }>()

const docs = ref<CustomsDoc[]>([])
const unread = ref(0)
const incoming = ref(0)
const loading = ref(false)
const message = ref('')

function sizeLabel(size: number) {
  if (size > 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`
  return `${Math.max(1, Math.round(size / 1024))} KB`
}

async function load(markRead = false) {
  loading.value = true
  try {
    const result = await listCustomsDocs(props.factoryId)
    docs.value = result.docs
    unread.value = result.unread
    incoming.value = result.unread
    message.value = ''
    if (result.unread) {
      emit('notify', `有 ${result.unread} 份通关一体化资料到，请查看。`)
    }
    if (result.unread && markRead) await markCustomsDocsRead(props.factoryId)
  } catch (error) {
    message.value = `读取通关一体化资料失败：${getApiErrorMessage(error)}`
  } finally {
    loading.value = false
  }
}

async function download(doc: CustomsDoc) {
  try {
    const blob = await downloadCustomsDoc(props.factoryId, doc.id)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = doc.filename
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    message.value = `下载失败：${getApiErrorMessage(error)}`
  }
}

onMounted(() => load(true))
</script>

<template>
  <section class="space-y-4" aria-label="通关一体化资料">
    <div class="rounded-xl border border-emerald-100/80 bg-gradient-to-b from-white to-emerald-50/50 p-4">
      <div class="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 class="text-[16px] font-bold text-emerald-950">通关一体化资料</h2>
          <p class="mt-0.5 text-[11px] text-slate-500">自动识别邮件中的「出货资料 / 通关一体化资料」，保存柜装箱单附件。</p>
        </div>
        <div class="flex items-center gap-2">
          <button type="button" class="text-[11px] font-semibold text-emerald-800 hover:underline" @click="emit('back')">← 返回工厂排期单</button>
          <button type="button" class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 px-3 text-[12px] text-slate-600" @click="load(false)">
            <RefreshCw class="size-3.5" :class="loading ? 'animate-spin' : ''" />刷新
          </button>
        </div>
      </div>
      <p v-if="message" class="mt-2 text-[11px] text-rose-600">{{ message }}</p>
      <p v-if="incoming" class="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] font-semibold text-amber-800" role="status">
        有 {{ incoming }} 份通关一体化资料到，请查看下方列表。
      </p>
    </div>

    <div class="rounded-xl border border-emerald-100/80 bg-white p-4">
      <h3 class="text-[13px] font-bold text-slate-800">资料列表</h3>
      <div class="mt-2 overflow-x-auto">
        <table class="w-full min-w-[760px] text-left text-[11px]">
          <thead class="bg-slate-50 text-slate-500">
            <tr><th class="px-2 py-2">文件名</th><th class="px-2 py-2">邮件主题</th><th class="px-2 py-2 text-right">大小</th><th class="px-2 py-2">到达时间</th><th class="px-2 py-2 text-right">操作</th></tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="doc in docs" :key="doc.id">
              <td class="px-2 py-2 font-semibold text-slate-800">{{ doc.filename }}</td>
              <td class="max-w-[420px] truncate px-2 py-2 text-slate-600">{{ doc.subject }}</td>
              <td class="px-2 py-2 text-right tabular-nums text-slate-500">{{ sizeLabel(doc.size) }}</td>
              <td class="px-2 py-2 tabular-nums text-slate-500">{{ doc.created_at.replace('T', ' ') }}</td>
              <td class="px-2 py-2 text-right">
                <button type="button" class="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700" @click="download(doc)">
                  <Download class="size-3.5" />下载
                </button>
              </td>
            </tr>
            <tr v-if="!docs.length">
              <td colspan="5" class="px-2 py-8 text-center text-slate-400">暂无通关一体化资料</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>
