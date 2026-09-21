<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { yinhuiExportIssues, yinhuiTotals, type YinhuiConversionResult } from '@/lib/customerPriceConverters/yinhui'
import { setYinhuiDraftMoq } from '@/lib/customerPriceConverters/yinhuiDraft'
import { YINHUI_PROFILES, YINHUI_MATERIAL_PRICES_HKD_KG } from '@/lib/customerPriceConverters/yinhuiProfiles'
import { translateQuoteDescriptions } from '@/api/quoteTranslation'
import { getApiErrorMessage } from '@/lib/http'
import { hasChineseQuoteText, pendingYinhuiDescriptions, translateYinhuiDescriptions } from '@/lib/customerPriceConverters/yinhuiTranslation'

const props = withDefaults(defineProps<{ result: YinhuiConversionResult; disabled?: boolean; factoryId?: string }>(), { factoryId: 'huaxing' })
const confirmed = defineModel<boolean>('confirmed', { required: true })
const translating = ref(false)
const translationMessage = ref('')
const pendingNames = computed(() => pendingYinhuiDescriptions(props.result.quoteData))
let translationRequest: AbortController | undefined
async function translateNames() {
  translationRequest?.abort()
  if (props.disabled || props.factoryId !== 'huaxing' || !pendingNames.value) { translating.value = false; return }
  const controller = new AbortController()
  translationRequest = controller
  const result = props.result
  const isCurrent = () => !controller.signal.aborted && props.result === result && translationRequest === controller
  confirmed.value = false
  translating.value = true
  translationMessage.value = '正在翻译产品、包装及 Tool Plan 名称；BOM 明细保留原文…'
  try {
    const report = await translateYinhuiDescriptions(result.quoteData, texts => translateQuoteDescriptions(texts, props.factoryId, controller.signal), isCurrent)
    if (isCurrent()) translationMessage.value = report.warning || (report.remaining ? `已翻译 ${report.translated} 项，剩余 ${report.remaining} 项可重试或手工核对。` : `已自动翻译 ${report.translated} 项名称，请核对专业术语后确认导出。`)
  } catch (error) {
    if (isCurrent()) translationMessage.value = `自动翻译暂未完成：${getApiErrorMessage(error)} 原文已保留，可重试或手工修改。`
  } finally {
    if (isCurrent()) translating.value = false
  }
}
watch([() => props.result, () => props.factoryId, () => props.disabled], () => {
  translationMessage.value = ''
  void translateNames()
}, { immediate: true })
onBeforeUnmount(() => translationRequest?.abort())
const imageUrl = ref('')
watch(() => props.result, () => { confirmed.value = false }, { deep: true })
watch(() => props.result.quoteData.image, (picture) => {
  if (imageUrl.value) URL.revokeObjectURL(imageUrl.value)
  imageUrl.value = picture && typeof URL.createObjectURL === 'function'
    ? URL.createObjectURL(new Blob([new Uint8Array(picture.bytes)], { type: picture.extension === 'png' ? 'image/png' : 'image/jpeg' })) : ''
}, { immediate: true })
onBeforeUnmount(() => { if (imageUrl.value) URL.revokeObjectURL(imageUrl.value) })
const fields = [
  { key: 'model', label: 'MODEL # 型号', type: 'text' },
  { key: 'productName', label: 'PRODUCT 英文名称', type: 'text' },
  { key: 'quoteDate', label: 'DATE 报价日期', type: 'date' },
  { key: 'packaging', label: 'PACKAGING 包装', type: 'text' },
  { key: 'moq', label: 'PROD MOQ', type: 'number' },
  { key: 'stage', label: 'STAGE 阶段（按实际填）', type: 'text' },
  { key: 'freightLclHkd', label: 'FOB YT LCL 每件运费 HKD', type: 'number' },
  { key: 'freightFclHkd', label: 'FOB YT 40FT 每件运费 HKD', type: 'number' },
] as const
function setField(key: typeof fields[number]['key'], event: Event) {
  const value = (event.target as HTMLInputElement).value
  if (key === 'moq') setYinhuiDraftMoq(props.result, value)
  else if (key === 'freightLclHkd' || key === 'freightFclHkd') props.result.quoteData[key] = value === '' ? null : Number(value)
  else props.result.quoteData[key] = value
}
const groups = computed(() => [
  { name: '塑料外购', rows: props.result.quoteData.plastic },
  { name: '五金 / 外购', rows: props.result.quoteData.mechanical },
  { name: '电子', rows: props.result.quoteData.electronic },
  { name: '车缝 / 布料', rows: props.result.quoteData.fabric || [] },
  { name: '包装', rows: props.result.quoteData.packagingRows },
  { name: '报关 / 文件费（总表 H32）', rows: props.result.quoteData.documentFees || [] },
])
const errors = computed(() => yinhuiExportIssues(props.result.quoteData))
const error = computed(() => errors.value.length > 0)
const total = computed(() => yinhuiTotals(props.result.quoteData))
const profile = computed(() => YINHUI_PROFILES[props.result.quoteData.templateId || 'standard'])
</script>

<template>
  <fieldset class="mt-4 rounded-xl border border-amber-200 bg-amber-50/50 p-4" :disabled="disabled" data-testid="yinhui-review">
    <legend class="px-2 text-sm font-semibold text-slate-900">银辉临时映射 · 输出前核对</legend>
    <p class="mb-3 text-sm text-slate-600">沿用提供的六张客表及其字体、线条。当前明细汇入第一套 BOM；第二套保持空白。报关 / 文件费单列总表 H32，由出厂价公式计入一次，不计入包装材料。此处修改只影响本次报客文件。</p>
    <p class="mb-3 text-xs text-slate-600">版式：{{ profile.label }} · 统一塑料 HKD/kg：{{ Object.entries(YINHUI_MATERIAL_PRICES_HKD_KG).map(([name, price]) => `${name} ${price}`).join(' / ') }}</p>
    <div v-if="result.manualReviewReasons?.length" class="mb-4 rounded-lg border border-orange-300 bg-orange-100 p-3 text-sm text-orange-950" role="alert" data-testid="yinhui-manual-review">
      <p class="font-semibold">Tool Plan 未能可靠识别，已转为人工放行</p>
      <p class="mt-1">系统已保留主明细的料重、料型和啤工生成临时行。以下问题只作提醒，不阻止导入或确认；金额可能受影响，请核对后再放行。</p>
      <ul class="mt-2 list-disc space-y-1 pl-5"><li v-for="reason in result.manualReviewReasons" :key="reason">{{ reason }}</li></ul>
    </div>
    <ul class="mb-4 list-disc space-y-1 pl-5 text-sm text-amber-900">
      <li v-for="warning in result.warnings" :key="warning">{{ warning }}</li>
      <li>原模板的 LOCAL DELIVERY / FOB YT 20FT 未提供运费分母，原公式会显示 #DIV/0!；按要求保留公式，发送客户前请补齐或核对这两行。</li>
    </ul>
    <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      <label v-for="field in fields" :key="field.key" class="grid gap-1 text-xs font-medium text-slate-700">
        {{ field.label }}
        <input :data-testid="`yinhui-${field.key}`" :type="field.key === 'moq' ? 'text' : field.type" :step="field.type === 'number' ? 'any' : undefined" :value="field.key === 'moq' && !result.quoteData.moq ? '' : result.quoteData[field.key]" class="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm" @input="setField(field.key, $event)">
      </label>
      <label class="grid gap-1 text-xs font-medium text-slate-700">Adaptor
        <select v-model="result.quoteData.adaptor" class="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"><option value="">待填写</option><option>included</option><option>not included</option></select>
      </label>
      <label class="grid gap-1 text-xs font-medium text-slate-700">Try me function
        <select v-model="result.quoteData.tryMe" class="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"><option value="">待填写</option><option>YES</option><option>NO</option></select>
      </label>
      <p class="text-sm leading-6 text-slate-700">外箱：{{ result.quoteData.cartonCm.map(v => v.toFixed(2)).join(' × ') }} cm<br>装箱：{{ result.quoteData.cartonPack }} 件</p>
      <img v-if="imageUrl" :src="imageUrl" alt="从内部报价提取的主产品图，请核对" class="max-h-28 max-w-full rounded border border-slate-200 object-contain">
      <p v-else class="text-sm text-amber-800">未提取到主产品图，请在生成文件中补充。</p>
    </div>
    <details class="mt-4 rounded-lg border border-slate-200 bg-white p-3">
      <summary class="cursor-pointer text-sm font-semibold text-slate-800">核对 BOM 原文与 Tool Plan 名称（金额不在此修改）</summary>
      <div class="mt-3 max-h-96 overflow-auto">
        <table class="w-full text-left text-xs">
          <thead><tr class="border-b border-slate-200 text-slate-500"><th class="p-2">类别</th><th class="p-2">物料名称（保留原文）</th><th class="p-2">用量</th><th class="p-2">HKD 合计</th><th class="p-2">来源</th></tr></thead>
          <tbody v-for="group in groups" :key="group.name">
            <tr v-for="(line, index) in group.rows" :key="index" class="border-b border-slate-100">
              <td class="p-2">{{ group.name }}</td><td class="min-w-72 p-2"><input v-model="line.description" :aria-label="`${group.name}第 ${index + 1} 行物料名称`" class="w-full rounded border border-slate-300 px-2 py-1"><p v-if="line.originalDescription && line.originalDescription !== line.description" class="mt-1 text-slate-500">原文：{{ line.originalDescription }}</p></td>
              <td class="p-2">{{ line.quantity }}</td><td class="p-2">{{ line.amountHkd.toFixed(6) }}</td><td class="p-2">{{ line.source }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="result.quoteData.tools.length" class="mt-3 max-h-64 overflow-auto border-t border-slate-200 pt-3">
        <p class="mb-2 text-xs font-semibold">Tool Plan 零件名称</p>
        <label v-for="(line, index) in result.quoteData.tools" :key="index" class="mb-2 grid gap-1 text-xs">
          {{ index + 1 }} · {{ line.moldNo || '未填模号' }}
          <input v-model="line.description" :aria-label="`Tool Plan 第 ${index + 1} 行英文描述`" class="rounded border border-slate-300 px-2 py-1" :class="hasChineseQuoteText(line.description) ? 'border-amber-500' : ''">
          <span class="grid gap-2 sm:grid-cols-2"><input v-model="line.moldNo" :aria-label="`Tool Plan 第 ${index + 1} 行模号`" placeholder="客户模号（无依据可留空）" class="rounded border border-slate-300 px-2 py-1"><input v-model="line.partNo" :aria-label="`Tool Plan 第 ${index + 1} 行零件号`" placeholder="零件号（无依据可留空）" class="rounded border border-slate-300 px-2 py-1"></span>
          <span v-if="line.originalDescription" class="text-slate-500">原文：{{ line.originalDescription }}</span>
        </label>
      </div>
    </details>
    <div class="mt-3 flex flex-wrap items-center gap-3 text-sm" aria-live="polite">
      <p data-testid="yinhui-translation-status" class="text-slate-700">{{ translationMessage || 'BOM 明细保留原表中文；仅产品、包装及 Tool Plan 名称使用项目离线模型翻译。' }}</p>
      <button v-if="pendingNames" type="button" data-testid="yinhui-translate" class="rounded border border-teal-500 bg-white px-3 py-1 text-teal-800" :disabled="translating || disabled" @click="translateNames">{{ translating ? '正在自动翻译…' : `重试自动翻译（${pendingNames} 项）` }}</button>
    </div>
    <p v-if="total.missingMaterialPrices.length" class="mt-3 rounded-md border border-amber-300 bg-amber-100 p-3 text-sm text-amber-950" role="alert" data-testid="yinhui-missing-prices">
      报客料价待补：{{ total.missingMaterialPrices.join('、') }}。对应 Tool Plan 单价留空，合计暂未包含这些料价；仍可确认后导出。文件名标注“待补料价”，客表 STAGE 标注 PRICE PENDING，请补齐后再发送客户。
    </p>
    <p class="mt-3 text-sm font-semibold text-slate-800">{{ result.quoteData.importIssues?.length ? '已识别成本小计（草稿待补正）' : total.missingMaterialPrices.length ? '已知成本小计（待补料价）' : 'EX-FACTORY' }} HKD {{ total.exFactory.toFixed(6) }} · USD {{ (total.exFactory / 7.8).toFixed(6) }} · 模具费 HKD {{ total.tooling.toFixed(2) }}</p>
    <div v-if="error" class="mt-2 text-sm text-red-700" role="alert" data-testid="yinhui-export-issues"><p>输出前还需处理 {{ errors.length }} 项：</p><ul class="mt-1 list-disc pl-5"><li v-for="item in errors" :key="item">{{ item }}</li></ul></div>
    <label class="mt-3 flex items-start gap-2 text-sm text-slate-800"><input v-model="confirmed" data-testid="yinhui-confirm" type="checkbox" :disabled="Boolean(error) || translating || disabled" class="mt-1"><span>已核对型号、MOQ、产品及物料名称、图片、料型、模具费及运费；确认按上述临时映射生成。<strong v-if="result.manualReviewReasons?.length">我已人工核对 Tool Plan 提醒及其金额影响，同意放行。</strong><strong v-if="total.missingMaterialPrices.length">我已知悉缺失料价将留空、当前合计不完整，同意先导出并补齐料价。</strong></span></label>
  </fieldset>
</template>
