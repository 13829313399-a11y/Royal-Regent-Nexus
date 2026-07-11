<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { AlertTriangle, BookOpenCheck, LoaderCircle, Search } from '@lucide/vue'
import { iamApi, type PermissionCatalogItem, type PermissionRiskLevel } from '@/api/iam'
import IamNavigation from '@/components/iam/IamNavigation.vue'
import { permissionActionLabel, permissionDisplayLabel, permissionScopeLabel } from '@/components/iam/permissionCatalogLabels'
import { getApiErrorMessage } from '@/lib/http'

const permissions = ref<PermissionCatalogItem[]>([])
const search = ref('')
const moduleFilter = ref('')
const riskFilter = ref<'' | PermissionRiskLevel>('')
const isLoading = ref(false)
const errorMessage = ref('')

const modules = computed(() => [...new Map(permissions.value.map((permission) => [permission.module_code, permission.module_name])).entries()])
const filteredPermissions = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  return permissions.value.filter((permission) =>
    (!keyword || `${permissionDisplayLabel(permission)} ${permission.name} ${permission.code} ${permission.module_name} ${permissionActionLabel(permission.action)}`.toLowerCase().includes(keyword))
    && (!moduleFilter.value || permission.module_code === moduleFilter.value)
    && (!riskFilter.value || permission.risk_level === riskFilter.value),
  )
})

async function loadData() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    permissions.value = await iamApi.listPermissions('active')
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
    <IamNavigation title="权限目录" subtitle="权限由开发迁移登记；新增模块上线后会在这里自动出现，默认不授予普通用户。" />
    <div class="mx-auto grid min-w-0 max-w-[1480px] gap-5 px-4 py-6 sm:px-5 xl:px-8">
      <section class="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm" aria-labelledby="permission-filter-title">
        <h2 id="permission-filter-title" class="sr-only">筛选权限目录</h2>
        <div class="grid gap-3 md:grid-cols-[minmax(240px,1fr)_240px_180px]">
          <label class="grid min-w-0 gap-1.5 text-xs font-semibold text-slate-600"><span>搜索权限</span><span class="flex h-11 min-w-0 items-center gap-2 rounded-xl border border-slate-200 px-3 focus-within:border-emerald-500 focus-within:ring-2 focus-within:ring-emerald-100"><Search class="size-4 shrink-0 text-slate-400" aria-hidden="true" /><input v-model="search" type="search" aria-label="搜索权限目录" class="min-w-0 flex-1 outline-none" placeholder="模块、名称或权限代码"></span></label>
          <label class="grid min-w-0 gap-1.5 text-xs font-semibold text-slate-600"><span>模块</span><select v-model="moduleFilter" aria-label="按模块筛选权限" class="h-11 min-w-0 rounded-xl border border-slate-200 px-3 outline-none focus:border-emerald-500"><option value="">全部模块</option><option v-for="[code, name] in modules" :key="code" :value="code">{{ name }}</option></select></label>
          <label class="grid min-w-0 gap-1.5 text-xs font-semibold text-slate-600"><span>风险级别</span><select v-model="riskFilter" aria-label="按风险级别筛选权限" class="h-11 min-w-0 rounded-xl border border-slate-200 px-3 outline-none focus:border-emerald-500"><option value="">全部风险</option><option value="normal">普通</option><option value="high">高风险</option></select></label>
        </div>
      </section>

      <div v-if="errorMessage" role="alert" class="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{{ errorMessage }}</div>
      <section class="min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div class="flex items-center justify-between gap-3 border-b border-slate-200 px-5 py-4"><h2 class="flex items-center gap-2 font-bold"><BookOpenCheck class="size-5 shrink-0 text-emerald-700" aria-hidden="true" />已登记权限</h2><span class="shrink-0 text-sm text-slate-500" aria-live="polite">{{ filteredPermissions.length }} / {{ permissions.length }}</span></div>
        <div v-if="isLoading" class="grid min-h-56 place-items-center" role="status" aria-label="正在加载权限目录"><LoaderCircle class="size-7 animate-spin text-emerald-700" /></div>
        <div v-else class="max-w-full overflow-x-auto overscroll-x-contain">
          <table class="w-full min-w-[900px] text-left text-sm">
            <caption class="sr-only">已登记权限及其模块、业务动作、适用范围、风险级别与状态</caption>
            <thead class="bg-slate-50 text-xs uppercase tracking-wide text-slate-500"><tr><th class="px-5 py-3">模块</th><th class="px-5 py-3">权限</th><th class="px-5 py-3">动作</th><th class="px-5 py-3">范围</th><th class="px-5 py-3">风险</th><th class="px-5 py-3">状态</th></tr></thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-for="permission in filteredPermissions" :key="permission.code" class="hover:bg-slate-50"><td class="px-5 py-3"><b>{{ permission.module_name }}</b><code class="block text-xs text-slate-400">{{ permission.module_code }}</code></td><td class="px-5 py-3"><b>{{ permissionDisplayLabel(permission) }}</b><code class="block text-xs text-slate-400">{{ permission.code }}</code></td><td class="px-5 py-3"><b class="block font-semibold text-slate-700">{{ permissionActionLabel(permission.action) }}</b><code class="block text-xs text-slate-400">{{ permission.action }}</code></td><td class="px-5 py-3"><b class="block font-semibold text-slate-700">{{ permissionScopeLabel(permission.scope_type) }}</b><code class="block text-xs text-slate-400">{{ permission.scope_type }}</code></td><td class="px-5 py-3"><span v-if="permission.risk_level === 'high'" class="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-1 text-xs font-bold text-amber-700"><AlertTriangle class="size-3" aria-hidden="true" />高风险</span><span v-else class="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-500">普通</span></td><td class="px-5 py-3"><span class="rounded-full bg-emerald-50 px-2 py-1 text-xs font-bold text-emerald-700">启用</span></td></tr>
              <tr v-if="!filteredPermissions.length"><td colspan="6" class="p-8 text-center text-slate-500">当前搜索和筛选条件下没有匹配的权限。</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </main>
</template>
