<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { Button } from '@/components/ui/button'
import IamDialogSurface from './IamDialogSurface.vue'
const props = defineProps<{ dirty: boolean; busy?: boolean; description?: string }>()
const open = ref(false)
let pending: Promise<boolean> | undefined
let resolve: ((value: boolean) => void) | undefined
function permitLeave() {
  if (props.busy) return Promise.resolve(false)
  if (!props.dirty) return Promise.resolve(true)
  if (pending) return pending
  open.value = true
  pending = new Promise<boolean>((done) => {
    resolve = done
  })
  return pending
}
function answer(value: boolean) {
  open.value = false
  resolve?.(value)
  resolve = undefined
  pending = undefined
}
onBeforeUnmount(() => answer(false))
defineExpose({ permitLeave })
</script>
<template>
  <IamDialogSurface
    :open="open"
    title="离开当前编辑"
    :description="description || '当前修改尚未提交，离开后不会保留。'"
    @update:open="answer(false)"
    ><p>放弃当前修改并继续？</p>
    <template #footer
      ><Button @click="answer(false)">继续编辑</Button
      ><Button variant="outline" @click="answer(true)">放弃修改并继续</Button></template
    ></IamDialogSurface
  >
</template>
