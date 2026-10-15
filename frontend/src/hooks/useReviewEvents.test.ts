import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FakeEventSource } from '../test/fakeEventSource.ts'
import { useReviewEvents } from './useReviewEvents.ts'

beforeEach(() => {
  FakeEventSource.reset()
  vi.stubGlobal('EventSource', FakeEventSource)
})
afterEach(() => vi.unstubAllGlobals())

describe('useReviewEvents', () => {
  it('opens nothing without a review id', () => {
    renderHook(() => useReviewEvents(null))
    expect(FakeEventSource.instances).toHaveLength(0)
  })

  it('accumulates events in arrival order and tracks the last event id', () => {
    const { result } = renderHook(() => useReviewEvents('r1'))
    const source = FakeEventSource.last()
    expect(source.url).toBe('/api/reviews/r1/events')
    act(() => {
      source.emit('agent.status', '{"agent":"amex","state":"working","text":"hi"}', '1')
      source.emit('review.report', '{"text":"done"}', '2')
    })
    expect(result.current.events.map((e) => e.type)).toEqual(['agent.status', 'review.report'])
    expect(result.current.lastEventId).toBe('2')
  })

  it('logs, reports and skips a malformed frame', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const { result } = renderHook(() => useReviewEvents('r1'))
    act(() => {
      FakeEventSource.last().emit('review.report', '{oops', '1')
      FakeEventSource.last().emit('review.report', '{"text":"ok"}', '2')
      FakeEventSource.last().emit('review.report', '{"text":"no id"}', '')
    })
    expect(error).toHaveBeenCalledTimes(2)
    expect(result.current.events).toHaveLength(1)
    expect(result.current.streamError).toBe('review.report frame without a sequence number')
    error.mockRestore()
  })

  it('keeps each sequence number once', () => {
    const { result } = renderHook(() => useReviewEvents('r1'))
    act(() => {
      FakeEventSource.last().emit('agent.status', '{"agent":"amex","state":"working","text":null}', '1')
      FakeEventSource.last().emit('review.report', '{"text":"done"}', '2')
      FakeEventSource.last().emit('review.report', '{"text":"done"}', '2')
    })
    expect(result.current.events.map((e) => e.seq)).toEqual([1, 2])
  })

  it('closes on unmount', () => {
    const { unmount } = renderHook(() => useReviewEvents('r1'))
    unmount()
    expect(FakeEventSource.last().closed).toBe(true)
  })

  it('reopens with a clean slate when the id changes', () => {
    const { result, rerender } = renderHook(({ id }) => useReviewEvents(id), {
      initialProps: { id: 'r1' },
    })
    act(() => FakeEventSource.last().emit('review.report', '{"text":"a"}', '1'))
    rerender({ id: 'r2' })
    expect(FakeEventSource.instances).toHaveLength(2)
    expect(FakeEventSource.instances[0].closed).toBe(true)
    expect(FakeEventSource.last().url).toBe('/api/reviews/r2/events')
    expect(result.current.events).toEqual([])
    expect(result.current.lastEventId).toBeNull()
    expect(result.current.streamError).toBeNull()
  })
})
