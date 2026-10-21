/** Fired on window when the server answers 401: the sign-in ended, whatever the page was doing. */
export const SIGNED_OUT_EVENT = 'hfm:signed-out'

export class ApiException extends Error {
  readonly status: number
  readonly detail: unknown

  constructor(status: number, detail: unknown) {
    super(detailText(status, detail))
    this.status = status
    this.detail = detail
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** The 422 for an answer set names the question ids that are missing, unknown or invalid. */
function rejectedAnswersText(detail: Record<string, unknown>): string | null {
  const { missing, unknown, invalid } = detail
  if (!Array.isArray(missing) || !Array.isArray(unknown) || !isRecord(invalid)) return null
  const parts = [
    missing.length > 0 && `missing ${missing.join(', ')}`,
    unknown.length > 0 && `unknown ${unknown.join(', ')}`,
    ...Object.entries(invalid).map(([id, reason]) => `${id}: ${String(reason)}`),
  ].filter((part) => part !== false)
  return `answers rejected: ${parts.join('; ')}`
}

/** FastAPI's request validation 422 is a list of errors, each with a msg. */
function validationText(detail: unknown[]): string {
  const messages = detail.map((item) => (isRecord(item) ? String(item.msg) : String(item)))
  return `request rejected: ${messages.join('; ')}`
}

function detailText(status: number, detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return validationText(detail)
  if (isRecord(detail) && typeof detail.message === 'string') return detail.message
  const answers = isRecord(detail) ? rejectedAnswersText(detail) : null
  return answers ?? `request failed with status ${status}`
}

async function send<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    const detail =
      typeof body === 'object' && body !== null && 'detail' in body ? body.detail : response.statusText
    if (response.status === 401) window.dispatchEvent(new Event(SIGNED_OUT_EVENT))
    throw new ApiException(response.status, detail)
  }
  return (response.status === 204 ? undefined : await response.json()) as T
}

export function apiGet<T>(path: string): Promise<T> {
  return send<T>(path)
}

export function apiDelete(path: string): Promise<void> {
  return send<void>(path, { method: 'DELETE' })
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return send<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
