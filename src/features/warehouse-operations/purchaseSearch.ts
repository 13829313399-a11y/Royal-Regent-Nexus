import type { InjectionKey, Ref } from 'vue'

export const purchaseSearchKey: InjectionKey<{ search: Ref<string>; submitted: Ref<number>; focus?: () => void }> = Symbol('fabric-purchase-search')
