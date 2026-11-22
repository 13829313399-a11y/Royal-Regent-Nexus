<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Clock3, ChevronDown } from '@lucide/vue'
import { PopoverAnchor } from 'reka-ui'
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
const now = ref<string>()
function updateClock() {
  now.value = center.serverNow()
  return now.value
}
watch([open, () => props.serverTime], ([isOpen], _, onCleanup) => {
  if (!isOpen) return
  updateClock()
  const timer = setInterval(updateClock, 1_000)
  onCleanup(() => clearInterval(timer))
})
const presets = computed(() => snoozePresets(now.value))
const customUntil = computed(() => customSnooze(custom.value, now.value))
function savePreset(label: string) {
  const option = snoozePresets(updateClock()).find((item) => item.label === label)
  if (option && !option.disabled) void save(option.until)
}
function saveCustom() {
  const until = customSnooze(custom.value, updateClock())
  if (until) void save(until)
}
async function save(until: string | null) {
  if (center.personalBusy || !props.entry.can_act_now) return
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
  <Popover v-model:open="open">
    <PopoverAnchor as="span" class="inline-flex">
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger as-child>
            <PopoverTrigger as-child>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                :data-snooze-entry="entry.id"
                aria-label="稍后提醒"
                :disabled="!entry.can_act_now || !serverTime || center.personalBusy"
              ><Clock3 :size="16" /></Button>
            </PopoverTrigger>
          </TooltipTrigger>
          <TooltipContent>稍后提醒</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </PopoverAnchor>
    <PopoverContent class="nc-snooze w-64" align="end" aria-label="稍后提醒">
      <h3>稍后提醒</h3>
      <Button v-if="isSnoozed(entry, now)" variant="link" :disabled="center.personalBusy" @click="save(null)">取消稍后提醒</Button>
      <Button
        v-for="option in presets"
        :key="option.label"
        variant="ghost"
        class="w-full justify-between"
        :disabled="option.disabled || center.personalBusy"
        @click="savePreset(option.label)"
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
          ><Button :disabled="!customUntil || center.personalBusy" @click="saveCustom"
            >确定</Button
          ></CollapsibleContent
        >
      </Collapsible>
    </PopoverContent></Popover
  >
</template>
