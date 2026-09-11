<script setup lang="ts">
import { ref } from 'vue'
import { Button } from '@/components/ui/button'
import { http } from '@/lib/http'
import { useSprayWorkspace, errorText } from '../workspace'
const s = useSprayWorkspace(), kind = ref('orders'), busy = ref(false)
const reports = [{value:'orders',label:'工单'}, {value:'shipments',label:'送退货凭据'}, {value:'returnables',label:'容器往来'}]
const costs = [{value:'shipment-lines',label:'送货计价明细'}, {value:'settlements',label:'月结'}, {value:'wages',label:'报工工资状态'}]
async function download() {
  busy.value = true
  try {
    const response = await http.get<Blob>(`/spray-production/exports/${kind.value}`, {params:{factory_id:s.factory},responseType:'blob'})
    const url = URL.createObjectURL(response.data), link = document.createElement('a')
    link.href = url; link.download = `喷油-${s.factory}-${kind.value}.xlsx`; link.click(); URL.revokeObjectURL(url)
  } catch(e) { s.error = errorText(e) } finally { busy.value = false }
}
</script>
<template><div v-if="s.can('export')" class="spray-actions"><select v-model="kind" aria-label="导出账册"><option v-for="r in [...reports,...(s.can('cost_read')?costs:[])]" :key="r.value" :value="r.value">{{ r.label }}</option></select><Button variant="outline" size="sm" :disabled="busy" @click="download">导出明细</Button></div></template>
