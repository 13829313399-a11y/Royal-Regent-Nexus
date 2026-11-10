<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { Button } from '@/components/ui/button'
import { api, errorMessage, type ExportRecord } from './api'
const items = ref<ExportRecord[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const downloading = ref('')
const failure = ref('')
const result = ref<{ url: string; name: string; passwordRequired: boolean } | null>(null)
let sequence = 0
const pages = computed(() => Math.max(1, Math.ceil(total.value / 20)))
async function load() {
  const token = ++sequence
  loading.value = true
  failure.value = ''
  try { const response = await api.history(page.value); if (token === sequence) { items.value = response.items; total.value = response.total } }
  catch (error) { if (token === sequence) { items.value = []; total.value = 0; failure.value = await errorMessage(error) } }
  finally { if (token === sequence) loading.value = false }
}
function go(next: number) { page.value = next; void load() }
async function download(record: ExportRecord) {
  if (downloading.value) return
  downloading.value = record.id
  failure.value = ''
  const token = sequence
  try {
    const response = await api.download(record.id)
    if (token !== sequence) return
    if (result.value) URL.revokeObjectURL(result.value.url)
    result.value = { url: URL.createObjectURL(response.blob), name: response.fileName, passwordRequired: response.passwordRequired }
    const link = document.createElement('a'); link.href = result.value.url; link.download = result.value.name; link.click()
  } catch (error) { if (token === sequence) failure.value = await errorMessage(error) }
  finally { downloading.value = '' }
}
onMounted(() => { void load() })
onBeforeUnmount(() => { sequence += 1; if (result.value) URL.revokeObjectURL(result.value.url) })
</script>
<template>
  <SectionPanel title="排期文件历史" subtitle="保存已生成的排期副本。文件反映生成时的数据；后续在台账修改或走货不会自动改写旧文件。">
    <template #action><Button variant="outline" :disabled="loading || Boolean(downloading)" @click="load">{{ loading ? '加载中…' : '刷新历史' }}</Button></template>
    <p v-if="failure" class="notice error" role="alert">{{ failure }}</p>
    <div v-if="result" class="notice success" role="status"><a :href="result.url" :download="result.name">重新下载 {{ result.name }}</a><p v-if="result.passwordRequired">文件保留原排期保护设置，请使用业务原密码打开。</p></div>
    <div class="trial-table"><table><thead><tr><th>客户</th><th>文件</th><th>生成时间</th><th>明细数</th><th>下载</th></tr></thead><tbody><tr v-for="item in items" :key="item.id"><td>{{ item.customer_code }}</td><td>{{ item.file_name }}</td><td>{{ item.created_at }}</td><td>{{ item.row_count }}</td><td><Button variant="outline" size="sm" :disabled="Boolean(downloading)" @click="download(item)">{{ downloading === item.id ? '下载中…' : '下载副本' }}</Button></td></tr><tr v-if="!items.length"><td colspan="5">{{ loading ? '正在读取…' : failure ? '历史暂未读取成功，请重试。' : '暂无生成记录。' }}</td></tr></tbody></table></div>
    <div class="pagination"><span>第 {{ page }} / {{ pages }} 页，共 {{ total }} 条</span><Button variant="outline" :disabled="page <= 1 || loading || Boolean(downloading)" @click="go(page - 1)">上一页</Button><Button variant="outline" :disabled="page >= pages || loading || Boolean(downloading)" @click="go(page + 1)">下一页</Button></div>
  </SectionPanel>
</template>
