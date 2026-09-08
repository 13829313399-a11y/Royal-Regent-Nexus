<script setup lang="ts">
import { computed, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { cartonPositionsApi, type CartonLocation } from '@/api/cartonPositions'
import { getApiErrorMessage } from '@/lib/http'
const props = defineProps<{ modelValue?: string; locations: CartonLocation[]; factoryId: string; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [string]; created: [] }>()
const auth = useAuthStore()
const canCreate = computed(() => ['carton', 'pmc-warehouse'].some(d => auth.can('carton_procurement:master_manage', props.factoryId, d)))
const adding = ref(false), busy = ref(false), warehouse = ref(''), bin = ref(''), error = ref('')
async function save() {
  if (busy.value) return
  busy.value = true; error.value = ''
  const factory = props.factoryId
  try {
    const location = await cartonPositionsApi.create(factory, warehouse.value, bin.value)
    if (factory !== props.factoryId) return
    emit('created'); emit('update:modelValue', location.id); adding.value = false
    warehouse.value = ''; bin.value = ''
  } catch (e) { error.value = getApiErrorMessage(e) } finally { busy.value = false }
}
</script>
<template>
  <div class="min-w-40 space-y-2">
    <div class="flex gap-1"><select :value="modelValue || ''" :disabled="disabled" aria-label="仓库及仓位" class="h-9 min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-2 text-xs" @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value)"><option value="">选择仓库／仓位</option><option v-for="place in locations.filter(p => p.status !== 'INACTIVE')" :key="place.id" :value="place.id">{{ place.label }}</option></select><button v-if="!disabled && canCreate" type="button" aria-label="新增仓位" class="rounded-lg border border-teal-200 px-2 text-teal-700" @click="adding = !adding">＋</button></div>
    <div v-if="adding && !disabled" class="space-y-2 rounded-lg border border-teal-100 bg-teal-50 p-2">
      <input v-model="warehouse" :disabled="busy" aria-label="新仓库名称" placeholder="仓库，如一仓" maxlength="64" class="h-8 w-full rounded border px-2 text-xs">
      <input v-model="bin" :disabled="busy" aria-label="新仓位编号" placeholder="仓位，如 A-01" maxlength="64" class="h-8 w-full rounded border px-2 text-xs">
      <button type="button" :disabled="busy || !warehouse.trim() || !bin.trim()" class="rounded bg-teal-700 px-3 py-1 text-xs text-white disabled:opacity-40" @click="save">保存仓位</button>
      <p v-if="error" role="alert" class="text-xs text-red-600">{{ error }}</p>
    </div>
  </div>
</template>
