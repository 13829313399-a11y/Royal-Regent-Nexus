<script setup lang="ts">
import { computed, ref } from 'vue'
import { Clock3, ChevronDown } from '@lucide/vue'
import {
  Button,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Input,
  Popover,
  PopoverContent,
  PopoverTrigger,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui'
import { formatBusinessDateTime } from '@/lib/dateTime'
import { useWorkCenterStore } from '@/stores/workCenter'
import { customSnooze, isSnoozed, snoozePresets } from './time'
import type { WorkEntry } from './types'

const props = defineProps<{ entry: WorkEntry; serverTime?: string }>()
const center = useWorkCenterStore()
const open = ref(false),
  expanded = ref(false),
  custom = ref('')
const presets = computed(() => snoozePresets(props.serverTime))
const customUntil = computed(() => customSnooze(custom.value, props.serverTime))
async function save(until: string | null) {
  const result = await center.patch(props.entry, {
    state_version: props.entry.personal.state_version,
    snoozed_until: until,
  })
  if (result) {
    open.value = false
    center.feedback = until ? '已移至稍后提醒' : '已取消稍后提醒'
  }
}
</script>
<template>
  <Popover v-model:open="open"
    ><TooltipProvider
      ><Tooltip
        ><TooltipTrigger as-child
          ><PopoverTrigger as-child>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              :data-snooze-entry="entry.id"
              aria-label="稍后提醒"
              :disabled="!entry.can_act_now || !serverTime || center.personalBusy"
              ><Clock3 :size="16" /></Button></PopoverTrigger></TooltipTrigger
        ><TooltipContent>稍后提醒</TooltipContent></Tooltip
      ></TooltipProvider
    ><PopoverContent class="nc-snooze w-64" align="end" aria-label="稍后提醒">
      <h3>稍后提醒</h3>
      <Button v-if="isSnoozed(entry, serverTime)" variant="link" @click="save(null)">取消稍后提醒</Button>
      <Button
        v-for="option in presets"
        :key="option.label"
        variant="ghost"
        class="w-full justify-between"
        :disabled="option.disabled || center.personalBusy"
        @click="save(option.until)"
        >{{ option.label
        }}<span class="tabular-nums text-muted-foreground">{{
          formatBusinessDateTime(option.until).slice(11)
        }}</span></Button
      >
      <Collapsible v-model:open="expanded"
        ><CollapsibleTrigger as-child
          ><Button variant="ghost" class="w-full justify-between"
            >自定义上海时间<ChevronDown :size="14" /></Button
        ></CollapsibleTrigger>
        <CollapsibleContent class="grid gap-2 p-1"
          ><label class="text-xs">上海时间<Input v-model="custom" type="datetime-local" /></label
          ><Button :disabled="!customUntil || center.personalBusy" @click="customUntil && save(customUntil)"
            >确定</Button
          ></CollapsibleContent
        >
      </Collapsible>
    </PopoverContent></Popover
  >
</template>
