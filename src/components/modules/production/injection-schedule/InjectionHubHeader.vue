<script setup lang="ts">
import { computed } from 'vue'
import { CalendarDays, LoaderCircle, LockKeyhole, ShieldCheck } from '@lucide/vue'
import AccountMenu from '@/components/layout/AccountMenu.vue'

export type InjectionHubSection =
  | 'overview'
  | 'orders'
  | 'operations'
  | 'versions'
  | 'masters'
  | 'rules'

const props = defineProps<{
  activeSection: InjectionHubSection
  factoryName: string
  dateRangeLabel: string
  previewLabel: string
  titleOverride?: string
  descriptionOverride?: string
  actionBusy?: boolean
  validateDisabled?: boolean
  publishDisabled?: boolean
}>()

const emit = defineEmits<{
  'update:activeSection': [section: InjectionHubSection]
  back: []
  validate: []
  publish: []
}>()

const brandLogoUrl = '/brand/huadeng_group_dynamic_logo.svg'

const sectionEntries: Array<{
  id: InjectionHubSection
  label: string
  title: string
  description: string
}> = [
  {
    id: 'overview',
    label: '排产总览',
    title: '注塑排产中枢',
    description: '按厂区隔离数据 · 机台时间轴、待排订单与智能匹配同屏协同',
  },
  {
    id: 'orders',
    label: '待排订单',
    title: '待排订单池',
    description: '把待落机订单转成可筛选、可推荐、可调整的结构化队列',
  },
  {
    id: 'operations',
    label: '动态排程',
    title: '自动排程与动态重排',
    description: '生成可审计草稿、处理急单与停机，并按白夜班实绩滚动更新欠数和 ETA',
  },
  {
    id: 'versions',
    label: '计划版本',
    title: '计划版本',
    description: '对比草稿与已发布计划，校验冲突并保留每次调整记录',
  },
  {
    id: 'masters',
    label: '机台·模具',
    title: '机台 / 模具与排程规则',
    description: '公共组件复用，主数据和策略按 factoryId 分区',
  },
  {
    id: 'rules',
    label: '规则配置',
    title: '排程规则配置',
    description: '维护换模换色、班次日历、材料限制与智能评分权重',
  },
]

const activeEntry = computed(() => (
  sectionEntries.find((entry) => entry.id === props.activeSection) ?? sectionEntries[0]
))

function selectSection(section: InjectionHubSection) {
  if (section !== props.activeSection) {
    emit('update:activeSection', section)
  }
}
</script>

<template>
  <header class="w-full text-slate-900" data-testid="injection-hub-header">
    <div class="injection-hub-topbar bg-[#0B1F2A] text-white">
      <div class="flex h-[68px] items-center gap-3 px-4 sm:px-5 lg:px-7">
        <button
          type="button"
          class="flex min-w-0 shrink-0 items-center gap-3 rounded-lg text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#14B8A6] focus-visible:ring-offset-2 focus-visible:ring-offset-[#0B1F2A]"
          aria-label="返回生产部模块"
          title="返回生产部模块"
          @click="emit('back')"
        >
          <span class="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-[10px] bg-white shadow-sm">
            <img
              :src="brandLogoUrl"
              alt="华登集团"
              class="size-full object-contain"
            >
          </span>
          <span class="hidden min-w-0 items-baseline gap-2 md:flex">
            <span class="truncate text-[22px] font-bold tracking-[-0.02em] text-white">
              Royal Regent Nexus
            </span>
            <span class="shrink-0 text-[13px] font-medium text-slate-400">· 生产部</span>
          </span>
        </button>

        <nav
          class="mx-auto hidden h-full min-w-0 items-stretch lg:flex"
          aria-label="注塑排产中枢主导航"
        >
          <button
            v-for="section in sectionEntries"
            :key="section.id"
            type="button"
            class="relative flex h-full min-w-[112px] items-center justify-center px-4 text-[15px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#14B8A6]"
            :class="section.id === activeSection
              ? 'text-white'
              : 'text-[#9FB4BE] hover:bg-white/[0.04] hover:text-white'"
            :aria-current="section.id === activeSection ? 'page' : undefined"
            @click="selectSection(section.id)"
          >
            {{ section.label }}
            <span
              v-if="section.id === activeSection"
              class="absolute inset-x-5 bottom-1 h-1 rounded-full bg-[#14B8A6]"
              aria-hidden="true"
            />
          </button>
        </nav>

        <div class="ml-auto flex shrink-0 items-center gap-2.5">
          <span
            class="hidden h-8 items-center rounded-full border border-teal-200/20 bg-teal-300/10 px-3 text-[13px] font-semibold text-teal-100 sm:inline-flex"
          >
            {{ factoryName }}
          </span>
          <div class="injection-hub-account">
            <AccountMenu />
          </div>
        </div>
      </div>

      <nav
        class="injection-hub-mobile-nav flex h-11 items-stretch overflow-x-auto border-t border-white/10 px-3 lg:hidden"
        aria-label="注塑排产中枢主导航"
      >
        <button
          v-for="section in sectionEntries"
          :key="`mobile-${section.id}`"
          type="button"
          class="relative flex min-w-[96px] shrink-0 items-center justify-center px-3 text-[13px] font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#14B8A6]"
          :class="section.id === activeSection ? 'text-white' : 'text-[#9FB4BE]'"
          :aria-current="section.id === activeSection ? 'page' : undefined"
          @click="selectSection(section.id)"
        >
          {{ section.label }}
          <span
            v-if="section.id === activeSection"
            class="absolute inset-x-4 bottom-0 h-1 rounded-t-full bg-[#14B8A6]"
            aria-hidden="true"
          />
        </button>
      </nav>
    </div>

    <div class="border-b border-[#E8EEF0] bg-white">
      <div class="flex min-h-[88px] flex-col justify-center gap-3 px-4 py-4 sm:px-5 md:flex-row md:items-center md:justify-between lg:px-7">
        <div class="min-w-0">
          <h1 class="text-[clamp(1.65rem,2vw,2rem)] font-bold leading-tight tracking-[-0.035em] text-[#0F172A]">
            {{ titleOverride || activeEntry.title }}
          </h1>
          <p class="mt-0.5 truncate text-[14px] text-[#64748B]">
            {{ descriptionOverride || activeEntry.description }}
          </p>
        </div>

        <div class="flex shrink-0 flex-wrap items-center gap-2">
          <span
            v-if="dateRangeLabel"
            class="inline-flex h-8 items-center gap-1.5 rounded-full border border-[#DDE5E8] bg-[#F8FAFB] px-3 text-[12px] font-medium text-[#334155]"
          >
            <CalendarDays class="size-3.5 text-[#64748B]" aria-hidden="true" />
            {{ dateRangeLabel }}
          </span>
          <span
            v-if="previewLabel"
            class="inline-flex h-8 items-center rounded-full border border-teal-200 bg-[#E6F7F4] px-3 text-[12px] font-semibold text-[#0F766E]"
          >
            {{ previewLabel }}
          </span>
        </div>
      </div>
    </div>

    <div class="border-b border-[#E8EEF0] bg-[#FBFCFC] lg:h-[55px]">
      <div class="flex min-h-[55px] flex-wrap items-center gap-3 px-4 py-[7px] sm:px-5 lg:h-full lg:min-h-0 lg:flex-nowrap lg:px-7">
        <slot name="toolbar">
          <div class="flex min-w-0 flex-wrap items-center gap-2">
            <span class="inline-flex h-8 items-center rounded-full border border-teal-200 bg-[#E6F7F4] px-3 text-[12px] font-semibold text-[#0F766E]">
              {{ factoryName }}
            </span>
            <span class="inline-flex h-8 items-center rounded-full border border-[#DDE5E8] bg-white px-3 text-[12px] font-medium text-[#64748B]">
              {{ activeEntry.label }}
            </span>
          </div>

          <div class="ml-auto flex flex-wrap items-center justify-end gap-2">
            <button
              type="button"
              class="inline-flex h-10 items-center justify-center gap-2 rounded-[10px] border border-[#CBD5E1] bg-white px-4 text-[13px] font-semibold text-[#334155] transition hover:border-teal-300 hover:bg-teal-50 hover:text-[#0F766E] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30 disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="validateDisabled || actionBusy"
              @click="emit('validate')"
            >
              <LoaderCircle v-if="actionBusy" class="size-4 animate-spin" aria-hidden="true" />
              <ShieldCheck v-else class="size-4" aria-hidden="true" />
              校验冲突
            </button>
            <button
              type="button"
              class="inline-flex h-10 items-center justify-center gap-2 rounded-[10px] bg-[#0F766E] px-5 text-[13px] font-semibold text-white shadow-[0_8px_20px_-14px_rgba(15,118,110,0.9)] transition hover:bg-[#115E59] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/40 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:shadow-none"
              :disabled="publishDisabled || actionBusy"
              @click="emit('publish')"
            >
              <LockKeyhole class="size-4" aria-hidden="true" />
              发布计划
            </button>
          </div>
        </slot>
      </div>
    </div>
  </header>
</template>

<style scoped>
.injection-hub-topbar {
  background: #0b1f2a;
}

.injection-hub-mobile-nav {
  scrollbar-width: none;
}

.injection-hub-mobile-nav::-webkit-scrollbar {
  display: none;
}

.injection-hub-account :deep(> div > button[aria-label='账号与头像设置']) {
  border-color: rgb(255 255 255 / 16%);
  background: rgb(255 255 255 / 7%);
  color: #f8fafc;
}

.injection-hub-account :deep(> div > button[aria-label='账号与头像设置']:hover) {
  border-color: rgb(45 212 191 / 42%);
  background: rgb(20 184 166 / 13%);
}

.injection-hub-account :deep(> div > button[aria-label='账号与头像设置'] > span:nth-child(2) > span:first-child) {
  color: #f8fafc;
}

.injection-hub-account :deep(> div > button[aria-label='账号与头像设置'] > span:nth-child(2) > span:last-child),
.injection-hub-account :deep(> div > button[aria-label='账号与头像设置'] > svg) {
  color: #9fb4be;
}
</style>
