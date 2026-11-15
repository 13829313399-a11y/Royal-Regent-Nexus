<script setup lang="ts">
import { ref, type Component } from 'vue'
import { DialogClose, DialogContent, DialogDescription, DialogOverlay, DialogPortal, DialogRoot, DialogTitle } from 'reka-ui'
import { X } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import './fabric-detail.css'

withDefaults(defineProps<{
  open?: boolean
  title: string
  description?: string
  icon: Component
  closeLabel: string
  wide?: boolean
}>(), { open: true })
const emit = defineEmits<{ close: []; closeAutoFocus: [event: Event] }>()
const closeButton = ref<{ $el: HTMLElement }>()

function focusClose(event: Event) {
  if (!closeButton.value?.$el) return
  event.preventDefault()
  closeButton.value.$el.focus()
}

</script>

<template>
  <DialogRoot :open="open" @update:open="value => { if (!value) emit('close') }">
    <DialogPortal>
      <DialogOverlay class="fabric-detail-overlay" />
      <DialogContent class="fabric-detail-dialog" :class="{ 'fabric-detail-dialog-wide': wide }" aria-modal="true"
        v-bind="description ? {} : { 'aria-describedby': undefined }" @open-auto-focus="focusClose" @close-auto-focus="emit('closeAutoFocus', $event)">
        <header class="fabric-detail-header">
          <span class="fabric-detail-icon"><component :is="icon" :size="20" aria-hidden="true" /></span>
          <div class="fabric-detail-heading">
            <DialogTitle>{{ title }}</DialogTitle>
            <DialogDescription v-if="description">{{ description }}</DialogDescription>
          </div>
          <div v-if="$slots.status" class="fabric-detail-status"><slot name="status" /></div>
          <DialogClose as-child>
            <Button ref="closeButton" class="fabric-detail-close" type="button" variant="ghost" size="icon" :aria-label="closeLabel">
              <X :size="20" aria-hidden="true" />
            </Button>
          </DialogClose>
        </header>
        <div class="fabric-detail-body" role="region" :aria-label="`${title}正文`" tabindex="0"><slot /></div>
        <footer v-if="$slots.actions" class="fabric-detail-actions"><slot name="actions" /></footer>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
