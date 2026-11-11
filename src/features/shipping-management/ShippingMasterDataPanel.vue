<script setup lang="ts">
import type { ShippingFactoryProfile } from './contracts'

defineProps<{ profile: ShippingFactoryProfile }>()
</script>

<template>
  <div class="space-y-4">
    <div class="grid gap-4 xl:grid-cols-2">
      <section class="enterprise-panel rounded-xl" aria-labelledby="shipping-customers-title">
        <header class="border-b border-slate-100 px-5 py-4">
          <h2 id="shipping-customers-title" class="text-[15px] font-semibold text-slate-950">客户与柜号序列</h2>
          <p class="mt-1 text-[11px] text-slate-500">柜号按客户独立自增，起点 1000，格式为「港口 客户 序号 柜」。</p>
        </header>
        <div class="overflow-x-auto">
          <table class="w-full min-w-[520px] border-collapse text-left text-[12px]">
            <thead class="bg-slate-50 text-[11px] font-semibold text-slate-500">
              <tr>
                <th scope="col" class="px-4 py-2">客户</th>
                <th scope="col" class="px-4 py-2 text-right">下一柜号</th>
                <th scope="col" class="px-4 py-2">收货人代码</th>
                <th scope="col" class="px-4 py-2">备注</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-for="customer in profile.customers" :key="customer.name" class="bg-white">
                <td class="px-4 py-2.5 font-semibold text-slate-900">{{ customer.name }}</td>
                <td class="px-4 py-2.5 text-right tabular-nums text-slate-700">{{ customer.cabinetSeq }}</td>
                <td class="px-4 py-2.5 tabular-nums text-slate-600">{{ customer.consigneeCode }}</td>
                <td class="px-4 py-2.5 text-[11px] text-slate-500">{{ customer.note }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="enterprise-panel rounded-xl" aria-labelledby="shipping-ports-title">
        <header class="border-b border-slate-100 px-5 py-4">
          <h2 id="shipping-ports-title" class="text-[15px] font-semibold text-slate-950">港口与国家映射</h2>
          <p class="mt-1 text-[11px] text-slate-500">装港决定柜号前缀；目的国用于柜纸「国家」列与报关资料。</p>
        </header>
        <div class="overflow-x-auto">
          <table class="w-full min-w-[460px] border-collapse text-left text-[12px]">
            <thead class="bg-slate-50 text-[11px] font-semibold text-slate-500">
              <tr>
                <th scope="col" class="px-4 py-2">装港</th>
                <th scope="col" class="px-4 py-2">目的国家</th>
                <th scope="col" class="px-4 py-2">备注</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-for="port in profile.ports" :key="port.port" class="bg-white">
                <td class="px-4 py-2.5 font-semibold text-slate-900">{{ port.port }}</td>
                <td class="px-4 py-2.5 text-slate-700">{{ port.country }}</td>
                <td class="px-4 py-2.5 text-[11px] text-slate-500">{{ port.note }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <section class="enterprise-panel rounded-xl" aria-labelledby="shipping-factories-title">
      <header class="border-b border-slate-100 px-5 py-4">
        <h2 id="shipping-factories-title" class="text-[15px] font-semibold text-slate-950">工厂英文名映射</h2>
        <p class="mt-1 text-[11px] text-slate-500">邮件里的英文厂名需映射为中文简称，柜纸 A 列与分厂 CBM 统计依赖这张表。</p>
      </header>
      <div class="overflow-x-auto">
        <table class="w-full min-w-[640px] border-collapse text-left text-[12px]">
          <thead class="bg-slate-50 text-[11px] font-semibold text-slate-500">
            <tr>
              <th scope="col" class="px-4 py-2">英文厂名</th>
              <th scope="col" class="px-4 py-2">中文简称</th>
              <th scope="col" class="px-4 py-2">本地工厂</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="mapping in profile.factoryMappings" :key="mapping.english" class="bg-white">
              <td class="px-4 py-2.5 text-slate-700">{{ mapping.english }}</td>
              <td class="px-4 py-2.5 font-semibold text-slate-900">{{ mapping.chinese }}</td>
              <td class="px-4 py-2.5">
                <span
                  class="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset"
                  :class="mapping.local ? 'bg-teal-50 text-teal-700 ring-teal-200/70' : 'bg-slate-100 text-slate-600 ring-slate-200'"
                >
                  {{ mapping.local ? '本地工厂' : '外部仓库 / 合作方' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <p class="rounded-xl border border-slate-200 bg-slate-50/70 px-4 py-3 text-[11px] leading-5 text-slate-500">
      {{ profile.note }} 本页为界面预览示例数据；正式接入后，基础资料由船务主管维护，并按厂区隔离。
    </p>
  </div>
</template>
