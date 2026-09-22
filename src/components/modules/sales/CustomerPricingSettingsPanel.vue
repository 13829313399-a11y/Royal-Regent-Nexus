<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { customerPricingSettingsApi } from '@/api/customerPricingSettings'
import type { CustomerPricingSettings } from '@/lib/customerPriceConverters/pricingSettings'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'

const props = defineProps<{ factoryId: string; customerId: string; customerName: string }>()
const emit = defineEmits<{ saved: [settings: CustomerPricingSettings] }>()
const auth = useAuthStore()
const canRead = computed(() => auth.can('customer_price:settings_read', props.factoryId, 'sales-business'))
const canManage = computed(() => canRead.value && auth.can('customer_price:settings_manage', props.factoryId, 'sales-business'))
const expanded = ref(false)
const draft = ref<CustomerPricingSettings | null>(null)
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const message = ref('')
let generation = 0

async function load() {
  const request = ++generation
  draft.value = null
  error.value = ''; message.value = ''
  if (!canRead.value || !expanded.value || !props.customerId) { loading.value = false; return }
  loading.value = true
  try {
    const result = await customerPricingSettingsApi.get(props.factoryId, props.customerId)
    if (request !== generation) return
    if (result.factory_id !== props.factoryId || result.customer_id !== props.customerId) throw new Error('返回的客户基础信息范围不一致')
    draft.value = result
  } catch (e) { if (request === generation) error.value = getApiErrorMessage(e) }
  finally { if (request === generation) loading.value = false }
}
watch(() => [props.factoryId, props.customerId, canRead.value, expanded.value], load)

async function save() {
  if (!draft.value || !canManage.value || saving.value) return
  const request = generation
  saving.value = true; error.value = ''; message.value = ''
  try {
    const payload = JSON.parse(JSON.stringify(draft.value)) as CustomerPricingSettings
    payload.materials = payload.materials.filter(r => r.material.trim() || Number(r.price) > 0)
    for (const row of payload.materials) {
      row.material = row.material.trim()
      if (!row.material || !Number.isFinite(row.price) || row.price < 0) throw new Error('料价行须填写料型及非负单价')
    }
    const result = await customerPricingSettingsApi.save(payload)
    if (request !== generation || !canRead.value) return
    if (result.factory_id !== props.factoryId || result.customer_id !== props.customerId) throw new Error('返回的客户基础信息范围不一致')
    draft.value = result; message.value = '已保存，下一次转换使用新参数；已生成的报价保留原参数。'
    emit('saved', result)
  } catch (e) { if (request === generation) error.value = getApiErrorMessage(e) }
  finally { saving.value = false }
}
</script>

<template>
  <section v-if="canRead" data-testid="customer-pricing-settings" class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
    <button type="button" class="flex w-full items-center justify-between text-left" :aria-expanded="expanded" @click="expanded = !expanded">
      <span><strong class="text-sm text-slate-900">{{ customerName }} · 客户基础信息</strong><span class="mt-1 block text-xs text-slate-500">维护报客料价、分类倍率及客户费率</span></span>
      <span class="text-sm text-teal-700">{{ expanded ? '收起' : '展开维护' }}</span>
    </button>
    <div v-if="expanded" class="mt-5 space-y-5">
      <p v-if="loading" class="text-sm text-slate-500">正在读取…</p>
      <p v-if="error" role="alert" class="text-sm text-rose-700">{{ error }}</p>
      <p v-if="message" role="status" class="text-sm text-teal-700">{{ message }}</p>
      <template v-if="draft">
        <p class="text-xs text-slate-500">参数版本 {{ draft.revision }}<span v-if="draft.updated_at"> · {{ draft.updated_by_name }} · {{ draft.updated_at }}</span> · 倍率 1 表示不加乘；费率使用小数，如 0.1 表示 10%。</p>
        <fieldset :disabled="!canManage || saving" class="space-y-5 disabled:opacity-80">
          <div v-if="draft.materials.length || ['buzzbee', 'yinhui', 'three-sixty', 'dicky'].includes(customerId)">
            <div class="mb-2 flex items-center justify-between"><strong class="text-sm">报客料价</strong><button v-if="canManage" type="button" class="text-sm text-teal-700" @click="draft.materials.push({ material: '', price: 0, currency: customerId === 'three-sixty' ? 'USD' : 'HKD', unit: customerId === 'dicky' ? 'lb' : 'kg' })">新增料型</button></div>
            <div class="max-h-80 overflow-auto"><table class="w-full text-left text-sm"><thead class="sticky top-0 bg-slate-50"><tr><th class="p-2">料型／专用料价名称</th><th class="p-2">单价</th><th class="p-2">币种</th><th class="p-2">单位</th><th /></tr></thead><tbody>
              <tr v-for="(row, index) in draft.materials" :key="index" class="border-t border-slate-100">
                <td class="p-2"><input v-model="row.material" :aria-label="`料型 ${index + 1}`" class="w-full rounded border border-slate-200 px-2 py-1.5"></td>
                <td class="p-2"><input v-model.number="row.price" type="number" min="0" step="any" :aria-label="`料价 ${index + 1}`" class="w-28 rounded border border-slate-200 px-2 py-1.5"></td>
                <td class="p-2">{{ row.currency }}</td><td class="p-2">{{ row.unit === 'kg' ? '公斤' : '磅' }}</td>
                <td class="p-2"><button v-if="canManage" type="button" class="text-xs text-rose-700" @click="draft.materials.splice(index, 1)">移除</button></td>
              </tr>
            </tbody></table></div>
          </div>
          <div class="grid gap-4 md:grid-cols-3">
            <label v-for="(definition, key) in draft.rate_definitions" :key="key" class="block text-sm">
              <span class="mb-1 block text-slate-700">{{ definition.label }}</span>
              <input v-model.number="draft.rates[key]" type="number" step="any" :min="definition.kind === 'multiplier' || definition.kind === 'exchange' ? 0.000001 : 0" :aria-label="definition.label" class="w-full rounded border border-slate-200 px-3 py-2">
              <span v-if="definition.description" class="mt-1 block text-xs text-slate-500">{{ definition.description }}</span>
            </label>
          </div>
          <label v-for="(definition, key) in draft.text_definitions" :key="key" class="block text-sm"><span class="mb-1 block">{{ definition.label }}</span><textarea v-model="draft.texts[key]" :aria-label="definition.label" rows="3" class="w-full rounded border border-slate-200 p-2" /></label>
        </fieldset>
        <div class="flex items-center gap-3"><button v-if="canManage" type="button" :disabled="saving" class="rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50" @click="save">{{ saving ? '保存中…' : '保存基础信息' }}</button><button type="button" :disabled="saving || loading" class="text-sm text-slate-600" @click="load">重新读取</button><span v-if="!canManage" class="text-xs text-slate-500">当前为只读权限</span></div>
      </template>
    </div>
  </section>
</template>
