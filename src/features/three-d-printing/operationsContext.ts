import { inject, type InjectionKey } from "vue";
import type { useOperations } from "./composables/useOperations";
export const operationsKey: InjectionKey<ReturnType<typeof useOperations>> =
  Symbol("3d-operations");
export function useOperationsContext() {
  const value = inject(operationsKey);
  if (!value) throw new Error("Operations context required");
  return value;
}
