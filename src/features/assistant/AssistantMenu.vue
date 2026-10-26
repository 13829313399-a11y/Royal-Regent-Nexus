<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { DropdownMenuRoot, DropdownMenuTrigger, DropdownMenuPortal, DropdownMenuContent, DropdownMenuItem } from 'reka-ui'
defineProps<{ label: string; items: { id: string; label: string; disabled?: boolean }[] }>()
const emit = defineEmits<{ select: [id: string]; open: [value: boolean] }>()
const open = ref(false), trigger = ref<InstanceType<typeof DropdownMenuTrigger>>()
const content = ref<InstanceType<typeof DropdownMenuContent>>()
watch([open,content], async ([value]) => {
  if (!value) return
  await nextTick()
  if (open.value) (content.value?.$el as HTMLElement | undefined)?.querySelector<HTMLElement>('[role="menuitem"]:not([data-disabled])')?.focus({preventScroll:true})
}, {flush:'post'})
let selected = false
function changed(value: boolean) { open.value = value; if (value) selected = false; emit('open', value) }
function choose(id: string) { selected = true; emit('select', id) }
function closeFocus(event: Event) { if (selected) event.preventDefault() }
</script>
<template>
  <DropdownMenuRoot :open="open" :modal="false" @update:open="changed">
    <DropdownMenuTrigger ref="trigger" :aria-label="label" :title="label"><slot /></DropdownMenuTrigger>
    <DropdownMenuPortal :to="trigger?.$el?.closest('.yl-assistant') || 'body'">
      <DropdownMenuContent ref="content" class="yl-menu" align="end" :side-offset="6" :collision-padding="12" :aria-label="label" @close-auto-focus="closeFocus">
        <DropdownMenuItem v-for="item in items" :key="item.id" class="yl-menu-item" :disabled="item.disabled" @select="choose(item.id)">{{ item.label }}</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenuPortal>
  </DropdownMenuRoot>
</template>
