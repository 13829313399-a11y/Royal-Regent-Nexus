<script setup lang="ts">
import { BookOpen, X } from '@lucide/vue'
import {
  DialogClose, DialogContent, DialogDescription, DialogOverlay, DialogPortal,
  DialogRoot, DialogTitle, DialogTrigger,
} from 'reka-ui'
import { Button } from '@/components/ui/button'

defineProps<{
  title: string
  description: string
  steps: { title: string; description: string }[]
  tips: { title: string; description: string }[]
}>()
</script>

<template>
  <DialogRoot>
    <DialogTrigger as-child>
      <slot name="trigger">
        <Button type="button" variant="outline" size="sm">
          <BookOpen class="size-4" aria-hidden="true" />
          使用教程
        </Button>
      </slot>
    </DialogTrigger>
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 z-[100] bg-slate-950/40" />
      <DialogContent class="fixed left-1/2 top-1/2 z-[101] flex max-h-[85dvh] w-[calc(100%-1.5rem)] max-w-3xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white text-slate-900 shadow-xl">
        <header class="flex shrink-0 items-start justify-between gap-4 border-b border-slate-200 px-5 py-4 sm:px-6">
          <div>
            <DialogTitle class="text-lg font-bold">{{ title }} · 使用教程</DialogTitle>
            <DialogDescription class="mt-1 text-sm leading-6 text-slate-500">{{ description }}</DialogDescription>
          </div>
          <DialogClose as-child>
            <Button type="button" variant="ghost" size="icon" aria-label="关闭使用教程" class="shrink-0">
              <X class="size-5" aria-hidden="true" />
            </Button>
          </DialogClose>
        </header>
        <div class="min-h-0 overflow-y-auto overscroll-contain px-5 py-5 sm:px-6">
          <h2 class="mb-4 text-sm font-bold text-teal-800">操作步骤</h2>
          <ol class="space-y-5">
            <li v-for="(step, index) in steps" :key="step.title" class="flex gap-3">
              <span class="flex size-7 shrink-0 items-center justify-center rounded-full bg-teal-50 text-xs font-bold text-teal-800" aria-hidden="true">{{ index + 1 }}</span>
              <div>
                <h3 class="text-sm font-semibold leading-7">{{ step.title }}</h3>
                <p class="mt-1 text-sm leading-6 text-slate-600">{{ step.description }}</p>
              </div>
            </li>
          </ol>
          <section class="mt-6 rounded-lg border border-slate-200 bg-slate-50 p-4">
            <h2 class="mb-3 text-sm font-bold">常见问题与注意事项</h2>
            <dl class="space-y-4">
              <div v-for="tip in tips" :key="tip.title">
                <dt class="text-sm font-semibold">{{ tip.title }}</dt>
                <dd class="mt-1 text-sm leading-6 text-slate-600">{{ tip.description }}</dd>
              </div>
            </dl>
          </section>
        </div>
        <footer class="flex shrink-0 justify-end border-t border-slate-200 px-5 py-3 sm:px-6">
          <DialogClose as-child><Button type="button" size="sm">知道了</Button></DialogClose>
        </footer>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
