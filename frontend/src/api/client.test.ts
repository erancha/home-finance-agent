import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiException, SIGNED_OUT_EVENT, apiDelete, apiGet, apiPost } from './client.ts'

function respond(status: number, body: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(body === undefined ? null : JSON.stringify(body), { status }),
    ),
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('client', () => {
  it('turns an error body into an ApiException carrying status and detail', async () => {
    const detail = { missing: ['q1'], unknown: [], invalid: {} }
    respond(422, { detail })
    const error = await apiPost('/x', {}).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiException)
    expect(error).toMatchObject({ status: 422, detail })
  })

  it('names the rejected answer ids in the message', async () => {
    respond(422, {
      detail: { missing: ['q1'], unknown: ['q9'], invalid: { q2: "'x' is not one of a, b" } },
    })
    await expect(apiPost('/x', {})).rejects.toThrow(
      "answers rejected: missing q1; unknown q9; q2: 'x' is not one of a, b",
    )
  })

  it('lists request validation messages', async () => {
    respond(422, { detail: [{ loc: ['body', 'month'], msg: 'String should match pattern' }] })
    await expect(apiPost('/x', {})).rejects.toThrow('request rejected: String should match pattern')
  })

  it('uses a string detail as the message', async () => {
    respond(409, { detail: 'review is running' })
    await expect(apiGet('/x')).rejects.toThrow('review is running')
  })

  it("uses a record detail's message as the message", async () => {
    respond(409, { detail: { message: '2026-09 already has a review', reviewId: 'r1' } })
    await expect(apiPost('/x', {})).rejects.toThrow('2026-09 already has a review')
  })

  it('sends DELETE', async () => {
    respond(204, undefined)
    await expect(apiDelete('/x')).resolves.toBeUndefined()
    expect(fetch).toHaveBeenCalledWith('/x', expect.objectContaining({ method: 'DELETE' }))
  })

  it('returns undefined for 204', async () => {
    respond(204, undefined)
    await expect(apiPost('/x', {})).resolves.toBeUndefined()
  })

  it('announces a 401 on window so the page can drop to sign-in', async () => {
    const heard = vi.fn()
    window.addEventListener(SIGNED_OUT_EVENT, heard)
    respond(401, { detail: 'sign in to continue' })
    await expect(apiGet('/x')).rejects.toThrow('sign in to continue')
    expect(heard).toHaveBeenCalledOnce()
    respond(404, { detail: 'nope' })
    await expect(apiGet('/x')).rejects.toThrow('nope')
    expect(heard).toHaveBeenCalledOnce()
    window.removeEventListener(SIGNED_OUT_EVENT, heard)
  })

  it('posts the body as JSON', async () => {
    respond(202, { id: 'r1' })
    await apiPost('/x', { a: 1 })
    expect(fetch).toHaveBeenCalledWith('/x', expect.objectContaining({ method: 'POST', body: '{"a":1}' }))
  })
})
