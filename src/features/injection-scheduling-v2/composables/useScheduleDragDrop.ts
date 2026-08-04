import { ref } from 'vue'

export function useScheduleDragDrop(
  move: (taskId: string, machineId: string, sequence: number) => void,
) {
  const draggedTaskId = ref<string | null>(null)
  const dropTargetMachineId = ref<string | null>(null)

  function start(taskId: string, event: DragEvent) {
    draggedTaskId.value = taskId
    dropTargetMachineId.value = null
    event.dataTransfer?.setData('text/plain', taskId)
    if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
  }

  function drop(machineId: string, sequence: number, event: DragEvent) {
    event.preventDefault()
    const taskId = draggedTaskId.value || event.dataTransfer?.getData('text/plain')
    draggedTaskId.value = null
    dropTargetMachineId.value = null
    if (taskId) move(taskId, machineId, sequence)
  }

  function end() {
    draggedTaskId.value = null
    dropTargetMachineId.value = null
  }

  function hover(machineId: string) {
    if (draggedTaskId.value) dropTargetMachineId.value = machineId
  }

  function leave(machineId: string) {
    if (dropTargetMachineId.value === machineId) dropTargetMachineId.value = null
  }

  return { draggedTaskId, dropTargetMachineId, start, drop, end, hover, leave }
}
