import type { InjectionKey, Ref } from 'vue'

export const inventorySearchKey: InjectionKey<{ search: Ref<string>; submitted: Ref<number>; active: Readonly<Ref<boolean>> }> = Symbol('fabric-inventory-search')
export const exceptionSearchKey: typeof inventorySearchKey = Symbol('fabric-exception-search')
export const activitySearchKey: typeof inventorySearchKey = Symbol('fabric-activity-search')
export const monthlySearchKey: typeof inventorySearchKey = Symbol('fabric-monthly-search')
