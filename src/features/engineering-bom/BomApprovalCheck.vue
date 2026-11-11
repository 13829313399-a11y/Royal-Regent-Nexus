<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { Button } from '@/components/ui/button'
import { engineeringApi as api, type Bom, type BomApprovalCheck } from './api'

const props = defineProps<{ bom: Bom; disabled?: boolean }>()
const emit = defineEmits<{ denied: [error: unknown] }>()
const result = ref<BomApprovalCheck | null>(null), busy = ref(false), error = ref('')
let generation = 0
function invalidate() { generation++; result.value = null; busy.value = false; error.value = '' }
watch(() => [props.bom.id, props.bom.version, props.disabled], invalidate, { flush: 'sync' })
onBeforeUnmount(invalidate)
async function check() {
  if (props.disabled || busy.value) return
  const token = ++generation
  result.value = null; error.value = ''; busy.value = true
  try {
    const response = await api.approvalCheck(props.bom.id, props.bom.version)
    if (token === generation && !props.disabled) result.value = response
  } catch (e) {
    if (token !== generation) return
    const response = (e as { response?: { status?: number; data?: { detail?: unknown } } }).response
    if ([401, 403].includes(response?.status || 0)) { invalidate(); emit('denied', e); return }
    error.value = typeof response?.data?.detail === 'string' ? response.data.detail : '检查失败，请重新核对。'
  } finally { if (token === generation) busy.value = false }
}
</script>

<template>
  <SectionPanel title="BOM 审核前检查" subtitle="检查当前已保存版本；逐行列出首项阻断，修正后重新检查。">
    <div class="space-y-3">
      <Button variant="outline" :disabled="disabled || busy" @click="check">{{ busy ? '正在检查…' : '检查已保存 BOM' }}</Button>
      <p v-if="disabled" class="text-sm text-amber-800">请先保存修改或完成当前操作，再检查已保存版本。</p>
      <p v-if="error" role="alert" class="text-red-800">{{ error }}</p>
      <template v-if="result">
        <p class="text-sm text-slate-600">检查版本 v{{ result.version }} · {{ result.checked_rows }} 条用料 · {{ result.checked_at }}</p>
        <p role="status" :class="result.ready_for_approval ? 'text-teal-800' : 'text-amber-800'">{{ result.ready_for_approval ? '本次检查未发现审核阻断；仍需执行工程审核。' : `本次发现 ${result.issues.length} 项阻断，请核对后重查。` }}</p>
        <ul v-if="result.issues.length" class="space-y-2">
          <li v-for="(issue, index) in result.issues" :key="`${issue.key}:${index}`" class="rounded-md border border-slate-200 p-3 text-sm break-words">
            <p>{{ issue.row === null ? '整份 BOM' : `第 ${issue.row} 行` }} · {{ issue.code }} {{ issue.name }} <span v-if="issue.attribute">／ {{ issue.attribute }}</span></p>
            <p class="mt-1">{{ issue.message }}</p>
          </li>
        </ul>
      </template>
      <p class="text-sm text-slate-500">结果仅反映检查时的状态。物料变化后需重查，审核时会重新校验；同编码用料逐行保留，正式下发仍未开放。</p>
    </div>
  </SectionPanel>
</template>
