<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { Download, Trash2 } from '@lucide/vue'
import { getApiErrorMessage } from '@/lib/http'
import {
  deleteGeneratedDoc,
  downloadGeneratedDoc,
  listGeneratedDocs,
  openGeneratedDoc,
  type GeneratedDoc,
} from '@/api/shippingMail'

const props = defineProps<{ factoryId: string; refreshKey?: number }>()
const emit = defineEmits<{ notify: [message: string] }>()

const docs = ref<GeneratedDoc[]>([])
const loading = ref(false)
const busy = ref(false)
const message = ref('')
const selected = ref<string[]>([])
const viewedDocs = ref<Record<string, string>>({})

function viewedKey(id: string) {
  return `shipping-truck-export-viewed:${props.factoryId}:${id}`
}

function knownKey() {
  return `shipping-truck-export-known:${props.factoryId}`
}

function isNewDoc(doc: GeneratedDoc) {
  return viewedDocs.value[doc.id] !== doc.created_at
}

function markViewed(doc: GeneratedDoc) {
  window.localStorage.setItem(viewedKey(doc.id), doc.created_at)
  viewedDocs.value = { ...viewedDocs.value, [doc.id]: doc.created_at }
}

async function load() {
  loading.value = true
  try {
    docs.value = await listGeneratedDocs(props.factoryId, 'truck_export')
    selected.value = selected.value.filter((id) => docs.value.some((doc) => doc.id === id))
    const firstVisit = window.localStorage.getItem(knownKey()) === null
    if (firstVisit) {
      const recentCutoff = Date.now() - 30 * 60 * 1000
      for (const doc of docs.value) {
        const created = Date.parse(doc.created_at)
        if (Number.isFinite(created) && created < recentCutoff) {
          window.localStorage.setItem(viewedKey(doc.id), doc.created_at)
        }
      }
      viewedDocs.value = Object.fromEntries(docs.value.map((doc) => {
        const stored = window.localStorage.getItem(viewedKey(doc.id))
        return [doc.id, stored || '']
      }))
      window.localStorage.setItem(knownKey(), '1')
    } else {
      viewedDocs.value = Object.fromEntries(docs.value.map((doc) => {
        const stored = window.localStorage.getItem(viewedKey(doc.id))
        if (!stored || stored === '1') {
          window.localStorage.setItem(viewedKey(doc.id), doc.created_at)
          return [doc.id, doc.created_at]
        }
        return [doc.id, stored]
      }))
    }
  } catch (error) {
    message.value = getApiErrorMessage(error)
  } finally {
    loading.value = false
  }
}

async function download(doc: GeneratedDoc) {
  busy.value = true
  try {
    const blob = await downloadGeneratedDoc(props.factoryId, doc.id)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = doc.filename
    link.click()
    URL.revokeObjectURL(url)
    emit('notify', `已下载 ${doc.filename}`)
  } catch (error) {
    message.value = getApiErrorMessage(error)
  } finally {
    busy.value = false
  }
}

async function open(doc: GeneratedDoc) {
  markViewed(doc)
  busy.value = true
  try {
    const result = await openGeneratedDoc(props.factoryId, doc.id)
    emit('notify', result.opened ? `已打开 ${doc.filename}` : `已保存 ${result.path}`)
  } catch (error) {
    message.value = getApiErrorMessage(error)
  } finally {
    busy.value = false
  }
}

async function remove(doc: GeneratedDoc) {
  busy.value = true
  try {
    await deleteGeneratedDoc(props.factoryId, doc.id)
    await load()
    emit('notify', `已删除 ${doc.filename}`)
  } catch (error) {
    message.value = getApiErrorMessage(error)
  } finally {
    busy.value = false
  }
}

async function removeSelected() {
  if (!selected.value.length) return
  busy.value = true
  try {
    for (const id of [...selected.value]) {
      try { await deleteGeneratedDoc(props.factoryId, id) } catch { /* keep deleting */ }
    }
    selected.value = []
    await load()
    emit('notify', '已批量删除生成的车货表。')
  } finally {
    busy.value = false
  }
}

function toggleAll(event: Event) {
  selected.value = (event.target as HTMLInputElement).checked ? docs.value.map((doc) => doc.id) : []
}

watch(() => props.refreshKey, () => { void load() })
onMounted(load)
defineExpose({ refresh: load })
</script>

<template>
  <section class="rounded-xl border border-emerald-100/80 bg-white" aria-label="已生成车的出货单">
    <header class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-2.5">
      <div class="flex items-center gap-2">
        <h3 class="text-[13px] font-bold text-slate-800">已生成车的出货单</h3>
        <span class="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">{{ docs.length }}</span>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <label v-if="docs.length" class="inline-flex items-center gap-1 text-[10px] text-slate-500">
          <input type="checkbox" aria-label="全选已生成车表" :checked="docs.length > 0 && selected.length === docs.length" @change="toggleAll">
          全选
        </label>
        <button type="button" class="h-7 rounded border border-rose-200 px-2 text-[11px] text-rose-600 disabled:opacity-40" :disabled="!selected.length || busy" @click="removeSelected">批量删除</button>
        <button type="button" class="h-7 rounded border border-slate-200 px-2 text-[11px] text-slate-600" :disabled="loading" @click="load">刷新</button>
      </div>
    </header>
    <p v-if="message" class="px-4 pt-2 text-[11px] text-rose-600">{{ message }}</p>
    <div v-if="docs.length" class="divide-y divide-slate-100">
      <div v-for="doc in docs" :key="doc.id" class="flex flex-wrap items-center justify-between gap-2 px-4 py-2 text-[11px]">
        <label class="flex min-w-0 flex-1 items-center gap-2">
          <input type="checkbox" :aria-label="`选择 ${doc.filename}`" :checked="selected.includes(doc.id)" @change="selected.includes(doc.id) ? selected = selected.filter((id) => id !== doc.id) : selected = [...selected, doc.id]">
          <span v-if="isNewDoc(doc)" class="size-2 shrink-0 rounded-full bg-rose-500" :data-doc-id="doc.id" aria-label="新文件"></span>
          <span class="truncate font-semibold text-slate-700">{{ doc.filename }}</span>
        </label>
        <span class="tabular-nums text-slate-400">{{ doc.created_at.replace('T', ' ').slice(0, 16) }}</span>
        <div class="flex items-center gap-3">
          <button type="button" class="inline-flex items-center gap-1 text-emerald-700 disabled:opacity-40" :disabled="busy" @click="download(doc)"><Download class="size-3" />下载</button>
          <button type="button" class="text-emerald-700 disabled:opacity-40" :disabled="busy" @click="open(doc)">打开</button>
          <button type="button" class="inline-flex items-center gap-1 text-rose-600 disabled:opacity-40" :disabled="busy" @click="remove(doc)"><Trash2 class="size-3" />删除</button>
        </div>
      </div>
    </div>
    <p v-else class="px-4 py-3 text-[11px] text-slate-400">暂无生成记录；导出一份车货表后会出现在这里。</p>
  </section>
</template>
