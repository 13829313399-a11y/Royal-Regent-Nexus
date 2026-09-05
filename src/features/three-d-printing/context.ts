import { inject, type InjectionKey } from "vue";
import type { useWorkspace } from "./composables/useWorkspace";
export const workspaceKey: InjectionKey<ReturnType<typeof useWorkspace>> =
  Symbol("three-d-workspace");
export function useWorkspaceContext() {
  const value = inject(workspaceKey);
  if (!value) throw new Error("3D workspace context missing");
  return value;
}
