<script setup lang="ts">
import { Settings2, SlidersHorizontal, Users } from '@lucide/vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { injectionConfigRuleCards } from '@/data/injectionSchedulingMock'
</script>

<template>
  <div class="space-y-6">
    <SectionPanel
      title="规则与参数中心"
      subtitle="这一页是后续把排产逻辑从人工经验沉淀为系统规则的关键位置"
    >
      <div class="grid gap-4 xl:grid-cols-2">
        <article
          v-for="card in injectionConfigRuleCards"
          :key="card.title"
          class="rounded-2xl border border-slate-200 bg-white p-5"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="flex items-center gap-3">
              <span class="flex size-11 items-center justify-center rounded-2xl bg-slate-100 text-slate-700">
                <Settings2 class="size-5" aria-hidden="true" />
              </span>
              <div>
                <h3 class="text-lg font-semibold text-slate-950">{{ card.title }}</h3>
                <p class="mt-1 text-xs text-slate-500">{{ card.owner }}</p>
              </div>
            </div>
            <StatusPill :label="card.status" :tone="card.tone" />
          </div>

          <p class="mt-4 text-sm leading-6 text-slate-600">{{ card.summary }}</p>

          <div class="mt-4 flex flex-wrap gap-2">
            <span
              v-for="item in card.items"
              :key="item"
              class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600"
            >
              {{ item }}
            </span>
          </div>
        </article>
      </div>
    </SectionPanel>

    <div class="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
      <SectionPanel
        title="优先建设项"
        subtitle="如果要先接真实业务，这三类配置最值得优先落下来"
      >
        <div class="space-y-4">
          <article class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div class="flex items-center gap-3">
              <span class="flex size-10 items-center justify-center rounded-2xl bg-white text-slate-700">
                <SlidersHorizontal class="size-4" aria-hidden="true" />
              </span>
              <div>
                <h3 class="font-semibold text-slate-950">排机权重参数化</h3>
                <p class="mt-1 text-xs text-slate-500">把结转优先、颜色顺序、同模同机、吨位适配做成可配置权重</p>
              </div>
            </div>
          </article>
          <article class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div class="flex items-center gap-3">
              <span class="flex size-10 items-center justify-center rounded-2xl bg-white text-slate-700">
                <Settings2 class="size-4" aria-hidden="true" />
              </span>
              <div>
                <h3 class="font-semibold text-slate-950">模具目标维护台账</h3>
                <p class="mt-1 text-xs text-slate-500">支持 24H / 11H 目标维护、历史建议值和缺失预警</p>
              </div>
            </div>
          </article>
          <article class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div class="flex items-center gap-3">
              <span class="flex size-10 items-center justify-center rounded-2xl bg-white text-slate-700">
                <Users class="size-4" aria-hidden="true" />
              </span>
              <div>
                <h3 class="font-semibold text-slate-950">角色与权限边界</h3>
                <p class="mt-1 text-xs text-slate-500">计划员负责排机，生产主管负责微调，PMC 负责回报与入库</p>
              </div>
            </div>
          </article>
        </div>
      </SectionPanel>

      <SectionPanel
        title="推荐的配置分区"
        subtitle="这块后续可以直接变成真实表单页和配置列表页"
      >
        <div class="grid gap-4 md:grid-cols-2">
          <article class="rounded-2xl border border-slate-200 bg-white p-5">
            <p class="text-xs uppercase tracking-[0.22em] text-slate-500">规则层</p>
            <h3 class="mt-3 text-lg font-semibold text-slate-950">排机规则</h3>
            <p class="mt-4 text-sm leading-6 text-slate-600">
              管理结转优先、插单加权、颜色浅到深、啤重匹配、同模学习命中等规则。
            </p>
          </article>
          <article class="rounded-2xl border border-slate-200 bg-white p-5">
            <p class="text-xs uppercase tracking-[0.22em] text-slate-500">主数据层</p>
            <h3 class="mt-3 text-lg font-semibold text-slate-950">机台 / 模具映射</h3>
            <p class="mt-4 text-sm leading-6 text-slate-600">
              沉淀模具常用机台、例外机台、机械手要求、料型限制和历史人工修正。
            </p>
          </article>
          <article class="rounded-2xl border border-slate-200 bg-white p-5">
            <p class="text-xs uppercase tracking-[0.22em] text-slate-500">组织层</p>
            <h3 class="mt-3 text-lg font-semibold text-slate-950">角色权限</h3>
            <p class="mt-4 text-sm leading-6 text-slate-600">
              区分查看、排机、微调、回报、入库和参数维护权限，避免跨角色混乱操作。
            </p>
          </article>
          <article class="rounded-2xl border border-slate-200 bg-white p-5">
            <p class="text-xs uppercase tracking-[0.22em] text-slate-500">预警层</p>
            <h3 class="mt-3 text-lg font-semibold text-slate-950">异常策略</h3>
            <p class="mt-4 text-sm leading-6 text-slate-600">
              定义目标缺失、颜色逆序、机台停机、料型冲突时的拦截或人工确认策略。
            </p>
          </article>
        </div>
      </SectionPanel>
    </div>
  </div>
</template>
