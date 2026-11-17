<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import { RouterLink } from 'vue-router'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { Button } from '@/components/ui/button'
import { errorMessage, type MasterRecord } from '@/features/cutting-operations/api'
import { engineeringApi as api, type CuttingChoices, type CuttingPreview, type CuttingPublish, type CuttingSelection } from './api'

const props = defineProps<{ bomId: string; version: number }>()
const emit = defineEmits<{ close: []; denied: [reason: unknown]; pending: [value: boolean] }>()
const choices = ref<CuttingChoices>()
const preview = ref<CuttingPreview>()
const previewSelection = ref<CuttingSelection>()
const result = ref<MasterRecord>()
const busy = ref(false)
const error = ref('')
const style = ref('')
const color = ref('')
const reason = ref('')
const roles = ref<Record<string, string>>({})
const applies = ref<Record<string, string[]>>({})
const pending = ref<CuttingPublish>()
const id = useId()
let active = true
const parts = computed(() => choices.value?.rows.filter(row => roles.value[row.key] === 'part') ?? [])
const materials = computed(() => choices.value?.rows.filter(row => ['required', 'optional'].includes(roles.value[row.key] ?? '')) ?? [])
const validSelection = computed(() => style.value.trim() && color.value.trim() && parts.value.length && materials.value.length &&
  materials.value.every(row => applies.value[row.key]?.some(key => parts.value.some(part => part.key === key))))

watch([style, color, roles, applies], () => { preview.value = undefined; previewSelection.value = undefined }, { deep: true, flush: 'sync' })
watch(pending, value => emit('pending', !!value), { flush: 'sync' })

function failure(reason: unknown) {
  const status = (reason as { response?: { status?: number } }).response?.status
  if (status === 401 || status === 403) emit('denied', reason)
  error.value = errorMessage(reason)
  return status
}

async function load() {
  busy.value = true
  error.value = ''
  try {
    const value = await api.cuttingChoices(props.bomId, props.version)
    if (!active) return
    choices.value = value
    result.value = value.existing ?? undefined
    applies.value = Object.fromEntries(value.rows.map(row => [row.key, []]))
  } catch (reason) {
    if (active) failure(reason)
  } finally {
    if (active) busy.value = false
  }
}

async function check() {
  if (busy.value || pending.value || !validSelection.value) return
  const partKeys = parts.value.map(row => row.key)
  const selection: CuttingSelection = {
    source_version: props.version, style: style.value, color: color.value, part_keys: partKeys,
    materials: materials.value.map(row => ({
      key: row.key, part_keys: (applies.value[row.key] ?? []).filter(key => partKeys.includes(key)),
      required_for_cutting: roles.value[row.key] === 'required',
    })),
  }
  preview.value = undefined
  busy.value = true
  error.value = ''
  try {
    const value = await api.previewCutting(props.bomId, selection)
    if (!active) return
    preview.value = value
    previewSelection.value = selection
  } catch (reason) {
    if (active) failure(reason)
  } finally {
    if (active) busy.value = false
  }
}

async function publish() {
  if (busy.value || (!pending.value && (!preview.value || !previewSelection.value || !reason.value.trim()))) return
  const body = pending.value ?? {
    factory_id: 'huakang-c', operation_id: crypto.randomUUID(), expected_version: preview.value!.expected_version,
    reason: reason.value.trim(), selection: previewSelection.value!, token: preview.value!.token,
  }
  pending.value = body
  busy.value = true
  error.value = ''
  try {
    const value = await api.publishCutting(props.bomId, body)
    if (!active) return
    result.value = value
    pending.value = undefined
    preview.value = undefined
  } catch (reason) {
    if (!active) return
    const status = failure(reason)
    if (status && status < 500) {
      pending.value = undefined
      preview.value = undefined
    }
  } finally {
    if (active) busy.value = false
  }
}

onMounted(load)
onBeforeUnmount(() => { active = false })
</script>

<template>
  <SectionPanel title="生成裁床执行 BOM" :subtitle="`工程来源 V${version}`">
    <template #action><Button variant="outline" type="button" :disabled="busy || !!pending" @click="emit('close')">关闭</Button></template>
    <p v-if="busy" role="status">正在读取或核对裁床依据…</p>
    <p v-if="error" role="alert" class="rounded-lg bg-red-50 p-3 text-red-800">{{ error }}</p>
    <Button v-if="!choices && !busy" variant="outline" type="button" @click="load">重新读取</Button>
    <div v-if="result" role="status" class="space-y-2">
      <p>已发布裁床执行 BOM {{ result.code }} V{{ result.version }}。可在裁床「生产排期」按货号选择。</p>
      <RouterLink class="font-medium text-teal-800 underline" :to="{ path: '/modules/production/cutting/master', query: { factory: 'huakang-c', master_id: result.id, master_version: result.version } }">查看裁床执行版本</RouterLink>
    </div>
    <template v-else-if="choices">
      <p class="mb-3 text-sm text-slate-600">选择裁片及用料，标明必需料和适用裁片。单套用量取自已审核工程版本，物料按编码、单位、规格和颜色核对。</p>
      <form @submit.prevent="check">
        <fieldset :disabled="busy || !!pending" class="min-w-0 space-y-4">
          <div class="grid gap-3 sm:grid-cols-2">
            <label class="min-w-0" :for="`${id}-style`">款式<input :id="`${id}-style`" v-model="style" name="cutting_style" maxlength="120" required /></label>
            <label class="min-w-0" :for="`${id}-color`">颜色<input :id="`${id}-color`" v-model="color" name="cutting_color" maxlength="120" required /></label>
          </div>
          <div class="max-w-full overflow-x-auto" tabindex="0" role="region" aria-label="工程用料行">
            <table class="w-full min-w-[640px] text-left text-sm">
              <thead class="bg-slate-50"><tr><th scope="col">工程行与物料</th><th scope="col">单套用量</th><th scope="col">裁床用途</th><th scope="col">适用裁片</th></tr></thead>
              <tbody><tr v-for="row in choices.rows" :key="row.key" class="border-b align-top">
                <td class="p-2">{{ row.row }} · {{ row.code }} {{ row.name }}<small class="block text-slate-600">{{ row.path }} · {{ row.process }}</small></td>
                <td class="p-2">{{ row.quantity }} {{ row.unit }}</td>
                <td class="p-2"><select v-model="roles[row.key]" :aria-label="`第 ${row.row} 行裁床用途`" :name="`cutting_role_${row.row}`">
                  <option :value="undefined">不纳入</option><option v-if="row.can_be_part" value="part">裁片</option>
                  <option value="required">必需料</option><option value="optional">非必需料</option>
                </select></td>
                <td class="p-2">
                  <template v-if="roles[row.key] === 'required' || roles[row.key] === 'optional'">
                    <span v-if="!parts.length">请先选择裁片</span>
                    <label v-for="part in parts" :key="part.key" class="block">
                      <input v-model="applies[row.key]" type="checkbox" :name="`cutting_part_${row.row}`" :value="part.key" :aria-label="`第 ${row.row} 行适用 ${part.name}`" /> {{ part.name }}
                    </label>
                  </template>
                </td>
              </tr></tbody>
            </table>
          </div>
          <Button type="submit" :disabled="!validSelection">预览裁床执行版本</Button>
        </fieldset>
      </form>
      <form v-if="preview" class="mt-4 space-y-3 rounded-lg border p-4" @submit.prevent="publish">
        <p>裁片配比：{{ preview.data.parts.map(part => `${part.name} ${part.pieces_per_set} 片／套`).join('、') }}</p>
        <ul><li v-for="(row, index) in preview.data.requirements" :key="index">
          {{ preview.data.engineering_source?.materials?.[index]?.code }} {{ preview.data.engineering_source?.materials?.[index]?.name }}
          · {{ row.quantity_per_set }} {{ row.unit }}／套 · 裁床物料 V{{ row.material_version }} · {{ row.stage }} · {{ row.required_for_cutting ? '必需' : '非必需' }}
        </li></ul>
        <label :for="`${id}-reason`">工程确认依据<input :id="`${id}-reason`" v-model="reason" name="cutting_basis" maxlength="500" required :disabled="busy || !!pending" /></label>
        <Button v-if="!pending" type="submit" :disabled="busy || !reason.trim()">确认发布裁床执行版本</Button>
        <Button v-else type="button" variant="outline" :disabled="busy" @click="publish">重试原发布请求</Button>
      </form>
    </template>
  </SectionPanel>
</template>

<style scoped>
input:not([type='checkbox']), select { display: block; width: 100%; margin-top: .25rem; border: 1px solid var(--border); border-radius: var(--radius); padding: .5rem; background: var(--background); }
</style>
