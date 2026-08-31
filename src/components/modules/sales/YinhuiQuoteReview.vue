<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { validateYinhuiExport, yinhuiTotals, type YinhuiConversionResult } from '@/lib/customerPriceConverters/yinhui'
import { YINHUI_PROFILES, YINHUI_MATERIAL_PRICES_HKD_KG } from '@/lib/customerPriceConverters/yinhuiProfiles'

const props = defineProps<{ result: YinhuiConversionResult; disabled?: boolean }>()
const confirmed = defineModel<boolean>('confirmed', { required: true })
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
  if (key === 'moq') props.result.quoteData.moq = Number(value)
  else if (key === 'freightLclHkd' || key === 'freightFclHkd') props.result.quoteData[key] = value === '' ? null : Number(value)
  else props.result.quoteData[key] = value
}
const groups = computed(() => [
  { name: '塑料外购', rows: props.result.quoteData.plastic },
  { name: '五金 / 外购', rows: props.result.quoteData.mechanical },
  { name: '电子', rows: props.result.quoteData.electronic },
  { name: '车缝 / 布料', rows: props.result.quoteData.fabric || [] },
  { name: '包装', rows: props.result.quoteData.packagingRows },
])
const error = computed(() => {
  try { validateYinhuiExport(props.result.quoteData); return '' }
  catch (e) { return e instanceof Error ? e.message : '请完善核对资料' }
})
const total = computed(() => yinhuiTotals(props.result.quoteData))
const profile = computed(() => YINHUI_PROFILES[props.result.quoteData.templateId || 'standard'])
</script>

<template>
  <fieldset class="mt-4 rounded-xl border border-amber-200 bg-amber-50/50 p-4" :disabled="disabled" data-testid="yinhui-review">
    <legend class="px-2 text-sm font-semibold text-slate-900">银辉临时映射 · 输出前核对</legend>
    <p class="mb-3 text-sm text-slate-600">沿用提供的六张客表及其公式、字体、线条。当前明细汇入第一套 BOM；第二套保持空白。此处修改只影响本次报客文件。</p>
    <p class="mb-3 text-xs text-slate-600">版式：{{ profile.label }} · 统一塑料 HKD/kg：{{ Object.entries(YINHUI_MATERIAL_PRICES_HKD_KG).map(([name, price]) => `${name} ${price}`).join(' / ') }}</p>
    <ul class="mb-4 list-disc space-y-1 pl-5 text-sm text-amber-900">
      <li v-for="warning in result.warnings" :key="warning">{{ warning }}</li>
      <li>原模板的 LOCAL DELIVERY / FOB YT 20FT 未提供运费分母，原公式会显示 #DIV/0!；按要求保留公式，发送客户前请补齐或核对这两行。</li>
    </ul>
    <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      <label v-for="field in fields" :key="field.key" class="grid gap-1 text-xs font-medium text-slate-700">
        {{ field.label }}
        <input :data-testid="`yinhui-${field.key}`" :type="field.type" :step="field.type === 'number' ? 'any' : undefined" :value="result.quoteData[field.key]" class="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm" @input="setField(field.key, $event)">
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
      <summary class="cursor-pointer text-sm font-semibold text-slate-800">核对 / 补全英文物料名称（金额不在此修改）</summary>
      <div class="mt-3 max-h-96 overflow-auto">
        <table class="w-full text-left text-xs">
          <thead><tr class="border-b border-slate-200 text-slate-500"><th class="p-2">类别</th><th class="p-2">英文描述</th><th class="p-2">用量</th><th class="p-2">HKD 合计</th><th class="p-2">来源</th></tr></thead>
          <tbody v-for="group in groups" :key="group.name">
            <tr v-for="(line, index) in group.rows" :key="index" class="border-b border-slate-100">
              <td class="p-2">{{ group.name }}</td><td class="min-w-72 p-2"><input v-model="line.description" :aria-label="`${group.name}第 ${index + 1} 行英文描述`" class="w-full rounded border border-slate-300 px-2 py-1" :class="/[\u3400-\u9fff]/.test(line.description) ? 'border-amber-500' : ''"></td>
              <td class="p-2">{{ line.quantity }}</td><td class="p-2">{{ line.amountHkd.toFixed(6) }}</td><td class="p-2">{{ line.source }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>
    <p class="mt-3 text-sm font-semibold text-slate-800">EX-FACTORY HKD {{ total.exFactory.toFixed(6) }} · USD {{ (total.exFactory / 7.8).toFixed(6) }} · 模具费 HKD {{ total.tooling.toFixed(2) }}</p>
    <p v-if="error" class="mt-2 text-sm text-red-700" role="alert">{{ error }}</p>
    <label class="mt-3 flex items-start gap-2 text-sm text-slate-800"><input v-model="confirmed" data-testid="yinhui-confirm" type="checkbox" :disabled="Boolean(error) || disabled" class="mt-1">已核对型号、MOQ、英文描述、图片、料型、模具费及运费；确认按上述临时映射生成。</label>
  </fieldset>
</template>
