import { useEffect, useState } from 'react'
import { REVIEW_EVENT_TYPES } from '../api/types.ts'
import type { ReviewEventType, SequencedEvent } from '../api/types.ts'

interface Stream {
  reviewId: string
  events: SequencedEvent[]
  lastEventId: string | null
  streamError: string | null
}

function parseSeq(lastEventId: string): number | null {
  const seq = Number(lastEventId)
  return lastEventId !== '' && Number.isInteger(seq) && seq > 0 ? seq : null
}

/**
 * Subscribes to one review's event stream and accumulates its events in arrival order, each
 * sequence number once.
 *
 * The browser owns reconnection and resends Last-Event-ID, so the backend replays only what
 * followed; a frame whose sequence number was already received is dropped. A frame whose data is
 * not JSON or whose id is not a sequence number is logged with console.error, reported as
 * streamError and skipped; the stream keeps going.
 */
export function useReviewEvents(reviewId: string | null) {
  const [stream, setStream] = useState<Stream | null>(null)

  useEffect(() => {
    if (reviewId === null) return
    const source = new EventSource(`/api/reviews/${reviewId}/events`)
    const update = (change: (current: Stream) => Stream) =>
      setStream((current) =>
        change(
          current?.reviewId === reviewId
            ? current
            : { reviewId, events: [], lastEventId: null, streamError: null },
        ),
      )
    const onFrame = (type: ReviewEventType) => (frame: MessageEvent<string>) => {
      let data: unknown
      try {
        data = JSON.parse(frame.data)
      } catch (error) {
        console.error(`malformed ${type} frame`, frame.data, error)
        update((current) => ({ ...current, streamError: `malformed ${type} frame` }))
        return
      }
      const seq = parseSeq(frame.lastEventId)
      if (seq === null) {
        console.error(`${type} frame without a sequence number`, frame.lastEventId)
        update((current) => ({ ...current, streamError: `${type} frame without a sequence number` }))
        return
      }
      const event = { type, data, seq } as SequencedEvent
      update((current) =>
        current.events.some((known) => known.seq === seq)
          ? current
          : { ...current, events: [...current.events, event], lastEventId: frame.lastEventId },
      )
    }
    const listeners = REVIEW_EVENT_TYPES.map((type) => [type, onFrame(type)] as const)
    for (const [type, listener] of listeners) source.addEventListener(type, listener)
    return () => {
      for (const [type, listener] of listeners) source.removeEventListener(type, listener)
      source.close()
    }
  }, [reviewId])

  const current = stream?.reviewId === reviewId ? stream : null
  return {
    events: current?.events ?? [],
    lastEventId: current?.lastEventId ?? null,
    streamError: current?.streamError ?? null,
  }
}
