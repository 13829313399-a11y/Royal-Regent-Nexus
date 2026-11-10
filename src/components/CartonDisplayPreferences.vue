<script setup lang="ts">
import { ref, watch } from 'vue'
import type { DimensionPreferenceScope, DimensionUnit } from '@/features/carton-procurement/dimensionPreference'
import { useMoneyPreference, type DisplayCurrency } from '@/features/carton-procurement/moneyPreference'
const props = defineProps<{ scope?: DimensionPreferenceScope | null; dimensionUnit?: DimensionUnit; dimensionPreferenceError?: string }>()
const emit = defineEmits<{ 'update:dimensionUnit': [value: string] }>()
const { preference, error, setPreference } = useMoneyPreference(() => props.scope ?? null)
const currency = ref<DisplayCurrency>('CNY'), rate = ref(''), saved = ref(false)
watch(preference, value => { currency.value = value.currency; rate.value = value.cnyToHkd; saved.value = false }, { immediate: true, flush: 'sync' })
function save() { saved.value = setPreference(currency.value, rate.value) }
</script>
<template>
  <article class="rounded-xl border border-teal-200 bg-white p-4 shadow-sm" aria-label="尺寸与金额显示">
    <h3 class="font-bold text-slate-900">尺寸与金额显示</h3>
    <div class="mt-3 grid gap-5 lg:grid-cols-2">
      <div aria-label="我的尺寸习惯">
        <label class="flex flex-wrap items-center gap-3 text-xs font-semibold">常用尺寸单位
          <select :value="dimensionUnit || 'cm'" aria-label="我的常用尺寸单位" class="h-9 rounded-lg border border-teal-200 bg-white px-3" @change="emit('update:dimensionUnit', ($event.target as HTMLSelectElement).value)"><option value="cm">cm</option><option value="inch">inch</option><option value="mm">mm</option></select>
        </label>
        <p class="mt-2 text-xs leading-5 text-slate-500">订单默认使用此单位，可在表单临时切换；已有规格保留原单位，并显示换算参考。</p>
        <p v-if="dimensionPreferenceError" role="alert" class="mt-2 text-xs text-red-700">{{ dimensionPreferenceError }}</p>
      </div>
      <div class="space-y-2" @input="saved = false" @change="saved = false">
        <div class="flex flex-wrap items-center gap-3 text-xs">
          <label class="flex items-center gap-2 font-semibold">人民币金额显示<select v-model="currency" aria-label="我的金额显示币种" class="h-9 rounded-lg border border-teal-200 bg-white px-3"><option value="CNY">仅显示原币</option><option value="HKD">同时显示港币参考</option></select></label>
          <label class="flex flex-wrap items-center gap-2">1 人民币 = <input v-model="rate" aria-label="人民币兑港币参考汇率" inputmode="decimal" maxlength="15" placeholder="填写汇率" class="h-9 w-28 rounded-lg border px-2">港币</label>
          <button type="button" class="h-9 rounded-lg bg-teal-700 px-3 font-semibold text-white" @click="save">保存金额设置</button>
        </div>
        <p class="text-xs leading-5 text-slate-500">按手填汇率在收料单价、本月对账汇总和库存月结金额旁显示港币参考。单价参考保留 6 位、金额参考保留 2 位小数。查询、凭证与导出均使用原账币种。</p>
        <p v-if="error" role="alert" class="text-xs text-red-700">{{ error }}</p><p v-else-if="saved" role="status" class="text-xs text-teal-700">金额显示已保存</p>
      </div>
    </div>
    <p class="mt-3 text-xs text-slate-500">设置保存在本机浏览器，按登录账号和任职分别生效。</p>
  </article>
</template>
