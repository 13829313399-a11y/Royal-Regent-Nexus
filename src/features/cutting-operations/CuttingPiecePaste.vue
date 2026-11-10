<script setup lang="ts">
import { onBeforeUnmount, ref, useId, watch } from 'vue'
import { Button } from '@/components/ui/button'
import type { PieceInput } from './reportingApi'

const props = defineProps<{ pieces: PieceInput[]; day: string }>()
const emit = defineEmits<{ apply: [pieces: PieceInput[]]; pending: [pending: boolean] }>()
const pasteId = `cutting-piece-paste-${useId()}`
const input = ref('')
const preview = ref<PieceInput[]>([])
const error = ref('')
const notice = ref('')
const headers = ['部件编码', '合格新增片数', '不良片数', '报废片数']

function resetPreview() {
  preview.value = []
  error.value = ''
  notice.value = ''
}

watch(input, value => {
  resetPreview()
  emit('pending', Boolean(value.trim()))
}, { flush: 'sync' })
watch(() => props.day, resetPreview)
onBeforeUnmount(() => emit('pending', false))

function check() {
  resetPreview()
  if (input.value.length > 24_000) {
    error.value = '粘贴内容超过 24,000 字符，请分次粘贴。'
    return
  }
  const codes = new Set(props.pieces.map(piece => piece.code))
  const seen = new Set<string>()
  const rows: PieceInput[] = []
  let firstRow = true
  for (const [index, line] of input.value.split(/\r\n?|\n/).entries()) {
    if (!line.trim()) continue
    const cells = line.split('\t').map(cell => cell.trim())
    const header = firstRow && cells.length === headers.length && cells.every((cell, i) => cell === headers[i])
    firstRow = false
    if (header) continue
    const [code, ...counts] = cells
    if (cells.length !== headers.length || !code) {
      error.value = `第 ${index + 1} 行须包含部件编码、合格新增、不良和报废共四列。`
      return
    }
    if (!codes.has(code) || seen.has(code)) {
      error.value = `第 ${index + 1} 行部件编码「${code}」${seen.has(code) ? '重复' : '不在本单 BOM 中'}。`
      return
    }
    if (counts.some(cell => !/^\d+$/.test(cell) || Number(cell) > 1_000_000_000)) {
      error.value = `第 ${index + 1} 行三项数量均须填写 0 至 1,000,000,000 的整数。`
      return
    }
    seen.add(code)
    rows.push({ code, good: Number(counts[0]), rejected: Number(counts[1]), scrap: Number(counts[2]) })
  }
  if (!rows.length) {
    error.value = '请粘贴至少一行裁片数量。'
    return
  }
  preview.value = rows
}

function apply() {
  if (!preview.value.length) return
  const changes = new Map(preview.value.map(piece => [piece.code, piece]))
  const count = changes.size
  emit('apply', props.pieces.map(piece => changes.get(piece.code) ?? piece))
  input.value = ''
  resetPreview()
  notice.value = `已填入 ${count} 个部件。请核对本单后保存或提交。`
}
</script>

<template>
  <details class="cutting-master-line">
    <summary>批量粘贴裁片数量</summary>
    <p>按下表的部件编码，从表格复制四列，依次为部件编码、合格新增片数、不良片数、报废片数。可包含同名表头。没有数量时请填写 0。</p>
    <label :for="pasteId">粘贴裁片明细<textarea :id="pasteId" v-model="input" name="piece_paste" rows="4" /></label>
    <div class="cutting-master-actions">
      <Button type="button" variant="outline" :disabled="!input.trim()" @click="check">校验并预览</Button>
      <Button v-if="input" type="button" variant="outline" @click="input = ''">清空粘贴内容</Button>
    </div>
    <p v-if="error" class="cutting-error" role="alert">{{ error }}</p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <template v-if="preview.length">
      <p role="status">{{ day || '当前业务日' }}预览 {{ preview.length }} 个部件。应用后更新所列部件的三个数量，其他部件保留原值。</p>
      <div class="cutting-table-scroll" tabindex="0" role="region" aria-label="裁片粘贴预览">
        <table>
          <thead><tr><th v-for="header in headers" :key="header" scope="col">{{ header }}</th></tr></thead>
          <tbody>
            <tr v-for="piece in preview" :key="piece.code">
              <td>{{ piece.code }}</td><td>{{ piece.good }}</td><td>{{ piece.rejected }}</td><td>{{ piece.scrap }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <Button type="button" variant="outline" @click="apply">应用到当前填报</Button>
    </template>
  </details>
</template>
