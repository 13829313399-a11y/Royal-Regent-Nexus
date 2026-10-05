<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { BookOpen, Check, ChevronRight, ExternalLink, Printer, Search, X } from '@lucide/vue'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { cartonDailyChecklist, cartonGuideSections, type CartonGuideDestination } from '@/features/carton-procurement/usageGuide'

defineProps<{ factoryName: string; canReviewSupplierDeliveries: boolean }>()
const emit = defineEmits<{ close: []; navigate: [destination: CartonGuideDestination] }>()
const query = ref('')
const selectedChapter = ref('master')
const reader = ref<HTMLElement | null>(null)
const checkedItems = ref<number[]>([])
const printFeedback = ref('')
const failedImages = ref<string[]>([])
const groups = ['首次启用', '每天工作', '需要时处理'] as const
const visibleSections = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase()
  return cartonGuideSections.filter(section => !keyword || [
    section.number, section.title, section.summary, section.entry, section.result,
    ...section.steps, ...section.reminders, ...(section.table?.rows.flat() ?? []),
  ].join(' ').toLocaleLowerCase().includes(keyword))
})

async function scrollToChapter(id: string) {
  selectedChapter.value = id
  await nextTick()
  reader.value?.querySelector<HTMLElement>(`#carton-guide-${id}`)?.scrollIntoView?.({ block: 'start', behavior: 'auto' })
}

async function printGuide() {
  query.value = ''
  printFeedback.value = ''
  await nextTick()
  try {
    const images = Array.from(reader.value?.querySelectorAll('img') ?? [])
    const results = await Promise.allSettled(images.map(image => typeof image.decode === 'function' ? image.decode() : Promise.resolve()))
    if (failedImages.value.length || results.some(result => result.status === 'rejected')) {
      printFeedback.value = '教程示意图未能完整加载，请刷新页面后再打印。文字内容仍可在这里阅读。'
      return
    }
    window.print()
  } catch (error) {
    const reason = error instanceof Error && error.message.trim() ? error.message : '浏览器未能打开打印窗口'
    printFeedback.value = `打印未完成：${reason}。可使用浏览器的打印菜单重试。`
  }
}

function imageFailed(id: string) {
  if (!failedImages.value.includes(id)) failedImages.value.push(id)
}
</script>

<template>
  <DialogRoot :open="true" @update:open="!$event && emit('close')">
    <DialogPortal>
      <DialogOverlay class="carton-guide-overlay fixed inset-0 z-[149] bg-slate-950/45 backdrop-blur-sm" />
      <DialogContent class="carton-usage-guide fixed left-1/2 top-1/2 z-[150] flex h-[92dvh] w-[calc(100%_-_24px)] max-w-6xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl" @close-auto-focus.prevent>
        <header class="shrink-0 border-b border-slate-200 bg-white px-4 py-4 sm:px-6">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex items-center gap-2 text-[11px] font-semibold text-teal-700"><BookOpen class="size-4" aria-hidden="true" />{{ factoryName }} · 仓库与纸箱采购</div>
              <DialogTitle class="mt-1 text-lg font-bold text-slate-950 sm:text-xl">纸箱模块使用教程</DialogTitle>
              <DialogDescription class="mt-1 text-xs leading-5 text-slate-500">先准备基础资料和历史结余，再从每日看板开始下单、收料和出库。</DialogDescription>
            </div>
            <div class="carton-guide-tools flex shrink-0 items-center gap-2">
              <button type="button" class="hidden h-9 items-center gap-1.5 rounded-lg border border-slate-200 px-3 text-xs font-semibold text-slate-600 hover:bg-slate-50 sm:inline-flex" @click="printGuide"><Printer class="size-4" aria-hidden="true" />打印 / 保存 PDF</button>
              <button type="button" aria-label="关闭使用教程" class="inline-flex size-9 items-center justify-center rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50" @click="emit('close')"><X class="size-4" aria-hidden="true" /></button>
            </div>
          </div>
          <p v-if="printFeedback" role="alert" class="carton-guide-tools mt-2 rounded-lg bg-amber-50 p-2 text-xs text-amber-900">{{ printFeedback }}</p>
        </header>

        <div class="carton-guide-body flex min-h-0 flex-1 flex-col lg:flex-row">
          <aside class="carton-guide-sidebar flex shrink-0 flex-col border-b border-slate-200 bg-slate-50/70 lg:w-60 lg:border-b-0 lg:border-r">
            <label class="relative m-3 block">
              <Search class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
              <input v-model="query" type="search" aria-label="查找教程步骤" placeholder="查找：排期、入库、失败…" class="h-9 w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 text-xs outline-none focus:border-teal-500">
            </label>
            <nav aria-label="使用教程目录" class="flex gap-1 overflow-x-auto px-3 pb-3 lg:min-h-0 lg:flex-1 lg:flex-col lg:gap-3 lg:overflow-y-auto">
              <div v-for="group in groups" :key="group" class="flex shrink-0 gap-1 lg:block">
                <p class="mb-1 hidden px-2 text-[10px] font-bold tracking-wide text-slate-400 lg:block">{{ group }}</p>
                <button v-for="section in visibleSections.filter(row => row.group === group)" :key="section.id" type="button" :aria-current="selectedChapter === section.id ? 'location' : undefined" class="flex shrink-0 items-center gap-2 whitespace-nowrap rounded-lg px-2.5 py-2 text-left text-xs lg:mb-0.5 lg:w-full lg:whitespace-normal" :class="selectedChapter === section.id ? 'bg-teal-100 font-bold text-teal-900' : 'text-slate-600 hover:bg-white'" @click="scrollToChapter(section.id)">
                  <span class="font-mono text-[10px] text-teal-700">{{ section.number }}</span><span>{{ section.title }}</span>
                </button>
              </div>
            </nav>
            <p class="hidden border-t border-slate-200 p-4 text-[11px] leading-5 text-slate-500 lg:block">教程只提供操作说明。实际业务按当前厂区、账号权限和实物情况处理。</p>
          </aside>

          <main ref="reader" aria-label="纸箱教程正文" class="carton-guide-reader min-h-0 min-w-0 flex-1 space-y-6 overflow-y-auto bg-slate-50 p-4 sm:p-6">
            <section v-if="!query.trim()" class="rounded-xl border border-teal-200 bg-white p-4 sm:p-5">
              <p class="text-[11px] font-bold text-teal-700">先看完整顺序</p>
              <h2 class="mt-1 text-base font-bold text-slate-950">上线只做一次，日常按实际业务走</h2>
              <p class="mt-2 text-sm leading-6 text-slate-600">首次启用：基础资料 → 期初库存 → 按需要衔接历史订单。之后每天先看工作看板；有新排期就核对，有采购就落单，有到货就验收，有领料就登记出库。</p>
              <figure class="mt-4"><img :src="'/carton-guide/workflow.svg'" alt="纸箱操作顺序：首次维护基础资料、期初库存与可选历史订单；日常看板、排期、落单、供应商接单送货、验收入库和领料出库" width="1080" height="545" class="h-auto w-full rounded-lg border border-slate-100" @error="imageFailed('workflow')"><figcaption class="mt-2 text-[11px] leading-5 text-slate-500">配图为操作示意及演示数据；每个步骤只有在真实业务发生时才办理。</figcaption></figure>
              <div class="mt-4 grid gap-2 text-xs leading-6 sm:grid-cols-3">
                <p class="rounded-lg bg-teal-50 px-3 py-2"><b class="text-teal-900">仓库落单</b><br>确认订单并锁定，自动生成首次采购。</p>
                <p class="rounded-lg bg-sky-50 px-3 py-2"><b class="text-sky-900">供应商送货</b><br>接单并登记送货，形成仓库待核实。</p>
                <p class="rounded-lg bg-amber-50 px-3 py-2"><b class="text-amber-900">仓库验收</b><br>按有效实收和实际仓位确认入库。</p>
              </div>
            </section>

            <p v-if="!visibleSections.length" role="status" class="rounded-xl border bg-white p-6 text-sm text-slate-600">没有找到相关步骤。可换用“下单”“期初”“收料”“超时”等词，或清空查找内容。</p>

            <section v-for="section in visibleSections" :id="`carton-guide-${section.id}`" :key="section.id" class="carton-guide-chapter scroll-mt-4 overflow-hidden rounded-xl border border-slate-200 bg-white">
              <header class="border-b border-slate-100 bg-gradient-to-r from-teal-50 to-white px-4 py-4 sm:px-5">
                <div class="flex items-center gap-3"><span class="inline-flex size-9 shrink-0 items-center justify-center rounded-lg bg-teal-700 font-mono text-sm font-bold text-white">{{ section.number }}</span><div><p class="text-[10px] font-semibold text-teal-700">{{ section.group }}</p><h2 class="mt-0.5 text-base font-bold text-slate-950">{{ section.title }}</h2></div></div>
                <p class="mt-3 text-sm leading-6 text-slate-600">{{ section.summary }}</p>
                <p class="mt-2 text-xs font-semibold leading-5 text-teal-800">位置：{{ section.entry }}</p>
              </header>
              <div class="space-y-4 p-4 sm:p-5">
                <figure v-if="section.image">
                  <img :src="section.image.src" :alt="section.image.alt" width="1080" height="510" class="h-auto w-full rounded-lg border border-slate-100" @error="imageFailed(section.id)">
                  <figcaption class="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] leading-5 text-slate-500"><span>{{ section.image.caption }}</span><a :href="section.image.src" target="_blank" rel="noopener" class="carton-guide-tools inline-flex items-center gap-1 font-semibold text-teal-700 hover:underline" :aria-label="`查看大图：${section.title}`">查看大图<ExternalLink class="size-3" aria-hidden="true" /></a></figcaption>
                  <p v-if="failedImages.includes(section.id)" role="alert" class="mt-2 text-xs text-amber-800">这张示意图未能加载，可刷新页面重试；下面的操作说明仍可阅读。</p>
                </figure>
                <ol class="space-y-3">
                  <li v-for="(step, index) in section.steps" :key="index" class="flex gap-3 text-sm leading-7 text-slate-700"><span class="mt-1 inline-flex size-5 shrink-0 items-center justify-center rounded-full bg-slate-100 text-[10px] font-bold text-slate-500">{{ index + 1 }}</span><span>{{ step }}</span></li>
                </ol>
                <div v-if="section.table" class="overflow-x-auto rounded-lg border border-slate-200"><table class="w-full min-w-[480px] text-left text-xs leading-6"><thead class="bg-slate-50 text-slate-500"><tr><th v-for="column in section.table.columns" :key="column" class="px-3 py-2 font-semibold">{{ column }}</th></tr></thead><tbody class="divide-y divide-slate-100"><tr v-for="(row, index) in section.table.rows" :key="index"><td v-for="(cell, cellIndex) in row" :key="cellIndex" class="px-3 py-2 text-slate-700">{{ cell }}</td></tr></tbody></table></div>
                <div class="rounded-lg border border-teal-100 bg-teal-50/70 p-3 text-sm leading-6 text-teal-900"><p class="flex items-start gap-2"><Check class="mt-1 size-4 shrink-0" aria-hidden="true" /><span><b>完成后检查：</b>{{ section.result }}</span></p></div>
                <div class="rounded-lg border border-amber-100 bg-amber-50/60 p-3"><p class="text-xs font-bold text-amber-900">操作时留意</p><ul class="mt-2 space-y-2 text-xs leading-6 text-amber-900"><li v-for="reminder in section.reminders" :key="reminder" class="flex gap-2"><span aria-hidden="true">·</span><span>{{ reminder }}</span></li></ul></div>
                <div class="carton-guide-tools flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3">
                  <button v-if="section.destination !== 'supplier-receiving' || canReviewSupplierDeliveries" type="button" class="inline-flex items-center gap-1.5 rounded-lg bg-teal-700 px-3 py-2 text-xs font-bold text-white hover:bg-teal-800" @click="emit('navigate', section.destination)">{{ section.actionLabel }}<ChevronRight class="size-3.5" aria-hidden="true" /></button>
                  <p v-else class="text-xs text-slate-500">本厂供应商待收入口需具备相应收料权限。供应商使用自己的协同账号操作。</p>
                  <button type="button" class="text-xs font-semibold text-slate-500 hover:text-teal-700" @click="reader?.scrollTo?.({ top: 0, behavior: 'auto' })">回到教程开头</button>
                </div>
              </div>
            </section>

            <section v-if="!query.trim()" class="carton-guide-checklist rounded-xl border border-teal-200 bg-white p-4 sm:p-5">
              <h2 class="text-base font-bold text-slate-950">每天收尾，再检查这五件事</h2>
              <p class="mt-1 text-xs leading-6 text-slate-500">勾选仅帮助本次阅读自查，不会修改业务记录。</p>
              <div class="mt-3 space-y-3"><label v-for="(item, index) in cartonDailyChecklist" :key="item" class="flex items-start gap-3 text-sm leading-6 text-slate-700"><input v-model="checkedItems" type="checkbox" :value="index" class="mt-1 accent-teal-700"><span>{{ item }}</span></label></div>
            </section>
          </main>
        </div>

        <footer class="carton-guide-tools flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-slate-200 bg-white px-4 py-3 text-[11px] text-slate-500 sm:px-6">
          <span>共 {{ cartonGuideSections.length }} 个步骤 · 有错误先查原因，结果不确定先查台账</span>
          <button type="button" class="inline-flex items-center gap-1 font-semibold text-teal-700 sm:hidden" @click="printGuide"><Printer class="size-3.5" aria-hidden="true" />打印 / 保存 PDF</button>
          <button type="button" class="rounded-lg border border-slate-200 px-3 py-1.5 font-semibold text-slate-600" @click="emit('close')">返回当前工作</button>
        </footer>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style>
@media print {
  @page carton-tutorial { size: A4; margin: 14mm; }
  body:has(.carton-usage-guide) { overflow: visible !important; height: auto !important; }
  body:has(.carton-usage-guide) > *:not(.carton-usage-guide):not(:has(.carton-usage-guide)) { display: none !important; }
  .carton-guide-overlay, .carton-guide-sidebar, .carton-guide-tools { display: none !important; }
  .carton-usage-guide {
    page: carton-tutorial; position: static !important; inset: auto !important; transform: none !important;
    display: block !important; width: 100% !important; height: auto !important;
    max-width: none !important; max-height: none !important; overflow: visible !important;
    border: 0 !important; box-shadow: none !important; border-radius: 0 !important;
  }
  .carton-guide-body, .carton-guide-reader { display: block !important; height: auto !important; overflow: visible !important; }
  .carton-guide-reader { padding: 0 !important; background: white !important; }
  .carton-guide-chapter { margin-top: 6mm; overflow: visible; }
  .carton-guide-chapter header, .carton-usage-guide figure, .carton-usage-guide tr { break-inside: avoid; }
  .carton-usage-guide li, .carton-usage-guide p, .carton-usage-guide td { font-size: 10.5pt; }
  .carton-guide-checklist { margin-top: 6mm; break-inside: avoid; }
  .carton-usage-guide input[type="checkbox"] { appearance: auto; }
}
</style>
