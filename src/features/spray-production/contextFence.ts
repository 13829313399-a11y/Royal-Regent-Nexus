export interface RequestContext { userId: string; factory: string; authorizationVersion: number }
export interface RequestTicket extends RequestContext { generation: number; writeRevision: number; key: string; sequence: number; signal: AbortSignal }

/** Generation, not factory equality, rejects A → B → A delayed responses. */
export class ContextFence {
  private generation = 0
  private writeRevision = 0
  private sequences = new Map<string, number>()
  private controllers = new Set<AbortController>()
  private context: RequestContext = { userId: '', factory: '', authorizationVersion: -1 }

  switch(context: RequestContext) {
    this.generation++
    this.context = { ...context }
    this.sequences.clear()
    this.abort()
  }
  begin(key: string): RequestTicket {
    const controller = new AbortController()
    this.controllers.add(controller)
    controller.signal.addEventListener('abort', () => this.controllers.delete(controller), { once: true })
    const sequence = (this.sequences.get(key) ?? 0) + 1
    this.sequences.set(key, sequence)
    return { ...this.context, generation: this.generation, writeRevision: this.writeRevision, key, sequence, signal: controller.signal }
  }
  finish(ticket: RequestTicket) {
    for (const controller of this.controllers) if (controller.signal === ticket.signal) this.controllers.delete(controller)
  }
  current(ticket: RequestTicket) {
    return !ticket.signal.aborted && ticket.generation === this.generation && ticket.writeRevision === this.writeRevision && this.sequences.get(ticket.key) === ticket.sequence
  }
  sameContext(ticket: RequestTicket) { return ticket.generation === this.generation }
  wrote() { this.writeRevision++; this.abort() }
  abort() { for (const controller of this.controllers) controller.abort(); this.controllers.clear() }
}
