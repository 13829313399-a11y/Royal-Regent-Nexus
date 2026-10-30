<script setup lang="ts">
import { ref } from 'vue'
import { cartonPrintSplitsApi, printStatus, type PrintSplitInfo, type PrintFile } from '@/api/cartonPrintSplits'
import { getApiErrorMessage } from '@/lib/http'
const props = defineProps<{ info: PrintSplitInfo; factory: string; supplier?: boolean }>()
const error = ref('')
async function download(file: PrintFile) {
  error.value = ''
  try { await cartonPrintSplitsApi.download(props.factory, props.info.id, file, props.supplier) }
  catch (cause) { error.value = getApiErrorMessage(cause) }
}
</script>
<template>
  <section class="space-y-2 rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900" aria-label="印刷拆单与固定资料">
    <strong>{{ info.role === 'CHILD' ? '拆分子单' : '拆单原单' }} · {{ printStatus[info.status] }}</strong>
    <p>来源 {{ info.source_contract_no }}（{{ info.source_order_no }}）→ {{ info.targets.join('、') }}</p>
    <p>{{ info.status === 'ACTIVE' ? '按本订单和本印刷版本分项送货、验收；其他合同数量不能混入。' : '请先处理供应商拆单待办，原单暂缓执行。' }}</p>
    <div class="flex flex-wrap gap-2"><button v-for="file in info.files" :key="file.id" type="button" class="break-all rounded border border-sky-200 bg-white px-2 py-1 text-left" @click="download(file)">下载固定资料：{{ file.file_name }} · 版本 {{ file.revision }}</button></div>
    <p v-if="error" role="alert" class="text-red-700">{{ error }}</p>
  </section>
</template>
