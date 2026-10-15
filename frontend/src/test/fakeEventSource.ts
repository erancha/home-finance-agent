type Listener = (event: MessageEvent<string>) => void

/** Stand-in for EventSource: tests push frames with emit() and inspect instances. */
export class FakeEventSource {
  static instances: FakeEventSource[] = []

  readonly listeners = new Map<string, Listener[]>()
  closed = false
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null

  readonly url: string

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: Listener) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener])
  }

  removeEventListener(type: string, listener: Listener) {
    this.listeners.set(type, (this.listeners.get(type) ?? []).filter((l) => l !== listener))
  }

  emit(type: string, data: string, lastEventId = '') {
    const event = new MessageEvent(type, { data, lastEventId })
    for (const listener of this.listeners.get(type) ?? []) listener(event)
  }

  open() {
    this.onopen?.()
  }

  close() {
    this.closed = true
  }

  static reset() {
    FakeEventSource.instances = []
  }

  static last(): FakeEventSource {
    const instance = FakeEventSource.instances.at(-1)
    if (instance === undefined) throw new Error('no EventSource was created')
    return instance
  }
}
