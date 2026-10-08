import type { InjectionKey, Ref } from 'vue'

export const purchaseSearchKey: InjectionKey<{ search: Ref<string>; submitted: Ref<number> }> = Symbol('fabric-purchase-search')
