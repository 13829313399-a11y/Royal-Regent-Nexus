import type { InjectionKey } from 'vue'

export interface ClosingReadLocation {month:string;id?:string;eventId?:string}

// Parent-owned URL bookkeeping does not navigate or discard any business form.
// External routes and browser Back still run the ordinary draft/unknown-write guards.
export const closingPresentationKey:InjectionKey<(path:string)=>boolean>=Symbol('cutting-closing-presentation')
