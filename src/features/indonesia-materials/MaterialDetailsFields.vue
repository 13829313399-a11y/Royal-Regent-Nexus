<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { Data } from '@/api/indonesiaMaterials'
import Fields from './Fields.vue'
import { clone, materialFields } from './forms'
import { choiceFields, maintainedOptions } from './options'
import { useMaterials } from './workspace'
const props = defineProps<{ model: Data; existing?: boolean }>()
const emit = defineEmits<{ reading: [value: boolean] }>()
const error = ref('')
const reading = ref(false)
const ws = useMaterials()
const historical = props.existing ? clone(props.model) : {}
const fields = computed(() => choiceFields(materialFields, ws.records, ws.optionDefaults, historical).map(field => ({ ...field, readonly: field.key === 'code' && props.existing })))
watch(() => props.model.customs_unit, () => {
  if (props.model.billing_mode !== 'automatic') return
  const rule = maintainedOptions(ws.records, ws.optionDefaults, 'customs_unit').find(item => item.data.value === props.model.customs_unit)?.data
  if (rule) Object.assign(props.model, { billing_unit: props.model.customs_unit, billing_basis: rule.billing_basis, billing_factor: rule.kg_per_unit })
}, { immediate: true })
let reader: FileReader | undefined
let alive = true
function finished() { if (reading.value) { reading.value = false; emit('reading', false) } }
function imageChanged(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]; input.value = ''
  if (!file) return
  if (!['image/png', 'image/jpeg'].includes(file.type) || file.size > 1_400_000) { error.value = '请选择小于 1.4 MB 的 PNG 或 JPEG 图片。'; return }
  const original = props.model
  reader = new FileReader(); reading.value = true; emit('reading', true)
  reader.onload = () => { if (alive && props.model === original) { original.image_data = reader!.result; error.value = '' }; finished() }
  reader.onerror = () => { error.value = '图片读取失败，请重新选择。'; finished() }
  reader.onabort = finished
  reader.readAsDataURL(file)
}
onBeforeUnmount(() => { alive = false; reader?.abort(); finished() })
</script>
<template>
  <div class="im-stack">
    <Fields :model="model" :fields="fields.slice(0, 6)" />
    <p class="im-note">送货数量、总重量、采购金额和立方数，在出货时按数量与装箱信息自动计算。</p>
    <label class="im-field"><span>物料图片</span><input type="file" accept="image/png,image/jpeg" :disabled="reading" @change="imageChanged"></label>
    <p v-if="reading" role="status" class="im-note">正在读取图片，请稍候再保存。</p>
    <p v-if="error" role="alert" class="im-error">{{ error }}</p>
    <div v-if="model.image_data" class="im-material-image"><img :src="model.image_data" alt="物料图片"><button type="button" :disabled="reading" @click="model.image_data = ''">移除图片</button></div>
    <Fields :model="model" :fields="fields.slice(6, 14)" />
    <h4>采购计价与备料参数</h4>
    <p class="im-note">单价单位随报关单位：KGM 按千克、TNE 按吨、PCE 按件，换算自动处理。按重量计价直接使用上方的单个净重，无须重复填写；免费备品不计采购金额。其他单位可在基础选项配置。</p>
    <Fields :model="model" :fields="fields.slice(14)" />
  </div>
</template>
