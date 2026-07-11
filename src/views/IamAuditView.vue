<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { FileClock, LoaderCircle, Search } from '@lucide/vue'
import { iamApi, type AuthorizationAuditEvent } from '@/api/iam'
import IamNavigation from '@/components/iam/IamNavigation.vue'
import { permissionDisplayLabel } from '@/components/iam/permissionCatalogLabels'
import { getApiErrorMessage } from '@/lib/http'

const events = ref<AuthorizationAuditEvent[]>([])
const filters = ref({ target_user_id: '', module_code: '', factory_id: '', from: '', to: '' })
const isLoading = ref(false)
const errorMessage = ref('')

function formatDate(value: string) {
  return new Date(value).toLocaleString('zh-CN')
}

function compactValue(value: unknown) {
  if (value === undefined || value === null) return '-'
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}

function permissionLabel(permissionCode: string) {
  return permissionDisplayLabel({ code: permissionCode, name: permissionCode })
}

async function loadData() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    events.value = await iamApi.listAuditEvents({
      target_user_id: filters.value.target_user_id || undefined,
      module_code: filters.value.module_code || undefined,
      factory_id: filters.value.factory_id || undefined,
      from: filters.value.from || undefined,
      to: filters.value.to || undefined,
    })
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isLoading.value = false
  }
}

onMounted(() => void loadData())
</script>

<template>
  <main class="min-h-screen overflow-x-hidden bg-slate-100 text-slate-950">
    <IamNavigation title="权限操作记录" subtitle="授权、禁止、撤销、模板调整和审批事件均为只追加审计记录。" />
    <div class="mx-auto grid min-w-0 max-w-[1480px] gap-5 px-4 py-6 sm:px-5 xl:px-8">
      <section class="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <form class="grid min-w-0 gap-3 sm:grid-cols-2 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_180px_180px_auto] xl:items-end" aria-label="筛选权限操作记录" @submit.prevent="loadData">
          <label class="grid min-w-0 gap-1.5 text-xs font-semibold text-slate-600"><span>目标用户 ID</span><input v-model="filters.target_user_id" aria-label="按目标用户 ID 筛选" class="h-10 min-w-0 rounded-xl border border-slate-200 px-3 text-sm font-normal text-slate-900" placeholder="例如 user-001"></label>
          <label class="grid min-w-0 gap-1.5 text-xs font-semibold text-slate-600"><span>模块代码</span><input v-model="filters.module_code" aria-label="按模块代码筛选" class="h-10 min-w-0 rounded-xl border border-slate-200 px-3 text-sm font-normal text-slate-900" placeholder="例如 molding_sample"></label>
          <label class="grid min-w-0 gap-1.5 text-xs font-semibold text-slate-600"><span>厂区代码</span><input v-model="filters.factory_id" aria-label="按厂区代码筛选" class="h-10 min-w-0 rounded-xl border border-slate-200 px-3 text-sm font-normal text-slate-900" placeholder="例如 huaxing"></label>
          <label class="grid min-w-0 gap-1.5 text-xs font-semibold text-slate-600"><span>开始日期</span><input v-model="filters.from" type="date" aria-label="筛选开始日期" class="h-10 min-w-0 rounded-xl border border-slate-200 px-3 text-sm font-normal text-slate-900"></label>
          <label class="grid min-w-0 gap-1.5 text-xs font-semibold text-slate-600"><span>结束日期</span><input v-model="filters.to" type="date" aria-label="筛选结束日期" class="h-10 min-w-0 rounded-xl border border-slate-200 px-3 text-sm font-normal text-slate-900"></label>
          <button type="submit" class="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-emerald-700 px-4 text-sm font-bold text-white sm:col-span-2 xl:col-span-1"><Search class="size-4" aria-hidden="true" />筛选</button>
        </form>
      </section>
      <div v-if="errorMessage" role="alert" class="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{{ errorMessage }}</div>
      <section class="min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div class="flex items-center justify-between border-b border-slate-200 px-5 py-4"><h2 class="flex items-center gap-2 font-bold"><FileClock class="size-5 text-emerald-700" />审计事件</h2><span class="text-sm text-slate-500">{{ events.length }} 条</span></div>
        <div v-if="isLoading" class="grid min-h-56 place-items-center" role="status" aria-label="正在加载权限操作记录"><LoaderCircle class="size-7 animate-spin text-emerald-700" /></div>
        <div v-else class="divide-y divide-slate-100">
          <article v-for="event in events" :key="event.id" class="grid min-w-0 gap-3 px-4 py-4 sm:px-5 lg:grid-cols-[200px_220px_minmax(0,1fr)] lg:items-start 2xl:grid-cols-[200px_220px_minmax(0,1fr)_220px]">
            <div><b class="text-sm text-slate-900">{{ event.event_type }}</b><time class="mt-1 block text-xs text-slate-400">{{ formatDate(event.created_at) }}</time></div>
            <div class="text-sm"><p><span class="text-slate-400">操作者：</span>{{ event.actor_name || event.actor_user_id }}</p><p v-if="event.target_user_id" class="mt-1"><span class="text-slate-400">目标：</span>{{ event.target_user_name || event.target_user_id }}</p></div>
            <div class="min-w-0 text-sm"><p class="break-words font-semibold text-slate-800">{{ event.reason }}</p><template v-if="event.permission_code"><b class="mt-1 block text-sm text-slate-700">{{ permissionLabel(event.permission_code) }}</b><code class="block break-all text-xs text-slate-500">{{ event.permission_code }} @ {{ event.factory_id || '*' }} / {{ event.department || '*' }}</code></template><p v-if="event.before_value !== undefined || event.after_value !== undefined" class="mt-2 truncate text-xs text-slate-400" :title="`${compactValue(event.before_value)} → ${compactValue(event.after_value)}`">{{ compactValue(event.before_value) }} → {{ compactValue(event.after_value) }}</p></div>
            <div class="min-w-0 break-all text-xs text-slate-400 lg:col-span-3 2xl:col-span-1"><p>事件 ID：{{ event.id }}</p><p v-if="event.request_id" class="mt-1">申请 ID：{{ event.request_id }}</p><p v-if="event.ip_address" class="mt-1">IP：{{ event.ip_address }}</p></div>
          </article>
          <p v-if="!events.length" class="p-10 text-center text-sm text-slate-500">没有匹配的权限审计事件。</p>
        </div>
      </section>
    </div>
  </main>
</template>
