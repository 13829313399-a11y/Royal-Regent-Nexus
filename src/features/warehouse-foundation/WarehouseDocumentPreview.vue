<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { X, FileText, Link2, Plus, Trash2 } from '@lucide/vue'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { Button } from '@/components/ui/button'
import WarehousePreviewFields from './WarehousePreviewFields.vue'
import type { WarehouseDocumentSpec, WarehousePreviewValues } from './documentPreview'

// Presentation-only contract: this component has no business client or persistence.
const props = defineProps<{
  spec: WarehouseDocumentSpec
  warehouseTitle: string
}>()
const emit = defineEmits<{ close: [] }>()
const values = reactive<WarehousePreviewValues>({})
let nextRowId = 0
type PreviewRow = { id: number; values: WarehousePreviewValues }
const rows = reactive<Record<string, PreviewRow[]>>(Object.fromEntries(
  props.spec.groups.filter(group => group.repeatable).map(group => [group.repeatable!.id, [{ id: nextRowId++, values: {} }]]),
))
const removing = ref<number>()
const body = ref<HTMLElement>()
const view = ref<'form' | 'detail'>('form')
const discard = ref(false)
watch(view, async () => { await nextTick(); if (body.value) body.value.scrollTop = 0 })
const hasValues = (record: WarehousePreviewValues) => Object.values(record).some(value => value !== undefined && String(value).trim() !== '')
const dirty = computed(() => hasValues(values) || Object.values(rows).some(items => items.some(row => hasValues(row.values))))
function requestClose() { if (dirty.value) discard.value = true; else emit('close') }
function addRow(id: string) { rows[id]!.push({ id: nextRowId++, values: {} }) }
function removeRow(id: string, row: PreviewRow) {
  if (hasValues(row.values) && removing.value !== row.id) { removing.value = row.id; return }
  rows[id] = rows[id]!.filter(item => item.id !== row.id)
  removing.value = undefined
}
function scrollToSection(index: number) { body.value?.querySelectorAll<HTMLElement>('.warehouse-preview-section')[index]?.scrollIntoView({ block: 'start' }) }
defineExpose({ hasChanges: () => dirty.value })
</script>

<template>
  <DialogRoot :open="true" @update:open="value => { if (!value) requestClose() }">
    <DialogPortal>
      <DialogOverlay class="warehouse-guide-overlay" />
      <DialogContent class="warehouse-document-preview" @escape-key-down.prevent="requestClose" @interact-outside.prevent>
        <header class="warehouse-guide-heading">
          <div><p class="warehouse-preview-eyebrow">{{ warehouseTitle }} · 单据预览</p><DialogTitle>{{ spec.title }}</DialogTitle><DialogDescription>{{ spec.description }}内容仅用于预览，关闭或离开后清空，不生成正式单据。</DialogDescription></div>
          <button class="warehouse-guide-close" type="button" aria-label="关闭单据预览" @click="requestClose"><X :size="20" /></button>
        </header>
        <div ref="body" class="warehouse-preview-body">
          <div class="warehouse-preview-tabs" role="group" aria-label="预览方式">
            <button type="button" :aria-pressed="view === 'form'" @click="view = 'form'"><FileText :size="15" />填写预览</button>
            <button type="button" :aria-pressed="view === 'detail'" @click="view = 'detail'"><Link2 :size="15" />详情预览</button>
          </div>
          <nav v-if="spec.groups.length > 3" class="warehouse-preview-index" aria-label="单据分区">
            <button v-for="(group, index) in spec.groups" :key="group.title" type="button" @click="scrollToSection(index)">{{ index + 1 }}. {{ group.title }}</button>
          </nav>
          <section v-for="(group, index) in spec.groups" :key="group.title" class="warehouse-preview-section">
            <h3><span>{{ index + 1 }}</span>{{ group.title }}</h3>
            <p v-if="group.description" class="warehouse-preview-group-description">{{ group.description }}</p>
            <template v-if="group.repeatable">
              <fieldset v-for="(row, rowIndex) in rows[group.repeatable.id]" :key="row.id" class="warehouse-preview-row" :aria-label="`${group.repeatable.itemLabel} ${rowIndex + 1}`">
                <legend>{{ group.repeatable.itemLabel }} {{ rowIndex + 1 }}</legend>
                <WarehousePreviewFields :fields="group.fields" :values="row.values" :detail="view === 'detail'" @change="(id, value) => row.values[id] = value" />
                <div v-if="view === 'form'" class="warehouse-preview-row-actions">
                  <template v-if="removing === row.id"><p role="alert">这条明细已有填写，移除后会清空。</p><Button variant="outline" size="sm" @click="removing = undefined">保留明细</Button><Button variant="outline" size="sm" @click="removeRow(group.repeatable.id, row)">确认移除</Button></template>
                  <Button v-else variant="ghost" size="sm" :aria-label="`移除${group.repeatable.itemLabel} ${rowIndex + 1}`" @click="removeRow(group.repeatable.id, row)"><Trash2 :size="14" />移除此行</Button>
                </div>
              </fieldset>
              <p v-if="!rows[group.repeatable.id]?.length" class="warehouse-preview-row-empty">尚未填写{{ group.repeatable.itemLabel }}。</p>
              <Button v-if="view === 'form'" variant="outline" size="sm" @click="addRow(group.repeatable.id)"><Plus :size="15" />{{ group.repeatable.addLabel }}</Button>
            </template>
            <WarehousePreviewFields v-else :fields="group.fields" :values="values" :detail="view === 'detail'" @change="(id, value) => values[id] = value" />
          </section>
          <section class="warehouse-preview-section"><h3>单据追溯</h3><div class="warehouse-preview-trace"><span v-for="step in spec.trace" :key="step">{{ step }}</span></div><p>正式业务接入后，可在这些分区查看关联记录。当前没有库存或收发数据。</p></section>
        </div>
        <footer class="warehouse-preview-footer">
          <template v-if="discard"><p role="alert">关闭后将清空本次填写的预览内容。</p><div><Button variant="outline" @click="discard = false">继续查看</Button><Button @click="emit('close')">关闭并清空</Button></div></template>
          <template v-else><p>样式预览 · 收发确认与库存记账待接入</p><div><Button variant="outline" @click="requestClose">关闭预览</Button><Button v-if="view === 'form'" @click="view = 'detail'">查看填写内容</Button><Button v-else variant="outline" @click="view = 'form'">返回填写</Button></div></template>
        </footer>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
