<script setup lang="ts">
import { ArrowLeft, ArrowUpRight, ChevronRight, Link2 } from '@lucide/vue'
import { computed, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import {
  departmentMap,
  departmentModuleRegistry,
  getDepartmentModule,
  getDepartmentRoute,
  isModuleDepartmentId,
  type ModuleDepartmentId,
} from '@/data/enterpriseMock'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import InjectionSchedulingDashboard from '@/components/modules/injection/InjectionSchedulingDashboard.vue'
import PermissionMatrix from '@/components/modules/PermissionMatrix.vue'
import TodoQueue from '@/components/modules/TodoQueue.vue'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const appStore = useAppStore()

const currentDepartmentId = computed<ModuleDepartmentId>(() => {
  const department = String(route.params.department ?? '')
  return isModuleDepartmentId(department) ? department : 'engineering'
})

const currentDepartment = computed(() => departmentMap[currentDepartmentId.value])
const departmentEntry = computed(() => departmentModuleRegistry[currentDepartmentId.value])

const currentModule = computed(() => {
  const moduleId = String(route.params.module ?? '')
  return getDepartmentModule(currentDepartmentId.value, moduleId) ?? departmentEntry.value.modules[0]
})

const isInjectionScheduling = computed(() => currentModule.value.id === 'injection-scheduling')

watch(currentDepartmentId, (departmentId) => {
  appStore.setActiveDepartment(departmentId)
}, { immediate: true })
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center gap-2 text-sm text-slate-500">
      <RouterLink :to="getDepartmentRoute(currentDepartmentId)" class="inline-flex items-center gap-2 text-slate-600 hover:text-slate-950">
        <ArrowLeft class="size-4" aria-hidden="true" />
        返回{{ currentDepartment.name }}模块中心
      </RouterLink>
      <span>/</span>
      <span>{{ currentModule.title }}</span>
    </div>

    <section class="rounded-[28px] border border-teal-200 bg-[linear-gradient(135deg,rgba(255,255,255,0.96),rgba(240,253,250,0.98))] p-7 shadow-[0_18px_48px_rgba(15,23,42,0.08)]">
      <div class="flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
        <div class="max-w-4xl">
          <div class="flex flex-wrap items-center gap-3">
            <StatusPill :label="currentModule.status" :tone="currentModule.statusTone" />
            <span class="text-sm text-slate-500">{{ currentDepartment.name }} / {{ currentModule.owner }}</span>
          </div>
          <h1 class="mt-4 text-4xl font-semibold tracking-tight text-slate-950">{{ currentModule.title }}</h1>
          <p class="mt-4 max-w-3xl text-base leading-8 text-slate-700">
            {{ currentModule.summary }}
          </p>

          <div class="mt-6 flex flex-wrap gap-3">
            <RouterLink
              :to="getDepartmentRoute(currentDepartmentId)"
              class="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-700"
            >
              返回模块中心
            </RouterLink>
            <a
              v-if="currentModule.href"
              :href="currentModule.href"
              target="_blank"
              rel="noreferrer"
              class="inline-flex items-center gap-2 rounded-xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white"
            >
              打开系统
              <ArrowUpRight class="size-4" aria-hidden="true" />
            </a>
          </div>
        </div>

        <div class="grid min-w-[300px] gap-3 sm:grid-cols-3 xl:w-[360px] xl:grid-cols-1">
          <div
            v-for="metric in currentModule.statusMetrics"
            :key="`${currentModule.id}-${metric.label}`"
            class="rounded-2xl border border-slate-200 bg-white px-4 py-4"
          >
            <p class="text-xs uppercase tracking-[0.24em] text-slate-500">{{ metric.label }}</p>
            <p class="mt-3 text-3xl font-semibold text-slate-950">{{ metric.value }}</p>
          </div>
        </div>
      </div>
    </section>

    <div class="grid gap-6 xl:grid-cols-[1fr_360px]">
      <div class="space-y-6">
        <InjectionSchedulingDashboard v-if="isInjectionScheduling" />

        <template v-else>
          <SectionPanel
            title="模块页面结构"
            subtitle="点击模块入口后，建议直接进入这个层级，再往下细分业务分区"
          >
            <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              <article
                v-for="(child, index) in currentModule.children"
                :key="`${currentModule.id}-${child.label}`"
                class="rounded-2xl border border-slate-200 bg-slate-50 p-5"
              >
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <p class="text-xs uppercase tracking-[0.24em] text-slate-500">Section {{ index + 1 }}</p>
                    <h3 class="mt-2 text-lg font-semibold text-slate-950">{{ child.label }}</h3>
                  </div>
                  <ChevronRight class="mt-1 size-4 text-slate-400" aria-hidden="true" />
                </div>
                <p class="mt-4 text-sm leading-6 text-slate-600">
                  {{ child.summary || '这里承接该模块的一个业务分区，后续可继续细化为真实页面。' }}
                </p>
              </article>
            </div>
          </SectionPanel>

          <SectionPanel
            title="模块首期落地范围"
            subtitle="先把入口、分区和状态层做稳，再逐步接真实数据和更深的业务流程"
          >
            <div class="grid gap-4 md:grid-cols-2">
              <article class="rounded-2xl border border-slate-200 bg-white p-5">
                <p class="text-xs uppercase tracking-[0.24em] text-slate-500">Routing</p>
                <h3 class="mt-2 text-lg font-semibold text-slate-950">模块详情独立页面</h3>
                <p class="mt-4 text-sm leading-6 text-slate-600">
                  当前模块已经从部门中心列表拆出，后续可以在这个页面下继续承接驾驶舱、分区导航和真实接口数据。
                </p>
              </article>
              <article class="rounded-2xl border border-slate-200 bg-white p-5">
                <p class="text-xs uppercase tracking-[0.24em] text-slate-500">System Link</p>
                <h3 class="mt-2 text-lg font-semibold text-slate-950">系统入口保留</h3>
                <p class="mt-4 text-sm leading-6 text-slate-600">
                  页面既可以作为 Royal Regent Nexus 内的业务详情页，也保留一键打开外部系统的入口，方便渐进式迁移。
                </p>
              </article>
              <article class="rounded-2xl border border-slate-200 bg-white p-5">
                <p class="text-xs uppercase tracking-[0.24em] text-slate-500">Data</p>
                <h3 class="mt-2 text-lg font-semibold text-slate-950">状态指标先独立</h3>
                <p class="mt-4 text-sm leading-6 text-slate-600">
                  模块关键指标已从卡片里抽出来，后面更适合单独挂真实数据源。
                </p>
              </article>
              <article class="rounded-2xl border border-slate-200 bg-white p-5">
                <p class="text-xs uppercase tracking-[0.24em] text-slate-500">UX</p>
                <h3 class="mt-2 text-lg font-semibold text-slate-950">从入口卡片过渡到业务工作台</h3>
                <p class="mt-4 text-sm leading-6 text-slate-600">
                  用户点击模块后会先进入说明和结构层，再进入外部系统或下一步子页面，路径会更清楚。
                </p>
              </article>
            </div>
          </SectionPanel>
        </template>
      </div>

      <aside class="space-y-6">
        <SectionPanel title="当前待办" subtitle="这些事项适合作为这个模块的第一批实施内容">
          <div class="space-y-3">
            <article
              v-for="todo in currentModule.todos"
              :key="todo"
              class="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4"
            >
              <p class="text-sm font-medium leading-6 text-slate-800">{{ todo }}</p>
            </article>
          </div>
        </SectionPanel>

        <SectionPanel title="模块路径" subtitle="当前模块在 Nexus 中的挂载位置">
          <div class="space-y-3 text-sm text-slate-700">
            <div class="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
              <div class="flex items-center gap-2 text-slate-500">
                <Link2 class="size-4" aria-hidden="true" />
                内部路由
              </div>
              <p class="mt-3 font-mono text-xs text-slate-800">{{ currentModule.route }}</p>
            </div>
            <div v-if="currentModule.href" class="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
              <p class="text-slate-500">外部系统入口</p>
              <p class="mt-3 font-mono text-xs text-slate-800">{{ currentModule.href }}</p>
            </div>
          </div>
        </SectionPanel>

        <PermissionMatrix :rows="departmentEntry.permissionRows" />
        <TodoQueue :items="departmentEntry.todos" title="部门并行待办" subtitle="除了当前模块外，该部门还在推进的事项" />
      </aside>
    </div>
  </div>
</template>
