import { apiDelete, apiGet, apiPost } from './client.ts'
import type { Answers, ExpectedData, MerchantCategories, MonthView } from './types.ts'

export function startReview(month: string): Promise<{ id: string }> {
  return apiPost('/api/reviews', { month })
}

export function clearReview(id: string): Promise<void> {
  return apiDelete(`/api/reviews/${id}`)
}

export function getMonth(month: string): Promise<MonthView> {
  return apiGet(`/api/months/${month}`)
}

export function getExpected(id: string): Promise<ExpectedData> {
  return apiGet(`/api/reviews/${id}/expected`)
}

export function answerReview(id: string, answers: Answers): Promise<void> {
  return apiPost(`/api/reviews/${id}/answers`, { answers })
}

export function recategorizeReview(id: string, categories: MerchantCategories): Promise<void> {
  return apiPost(`/api/reviews/${id}/categories`, { categories })
}
