import { useEffect, useState } from 'react'
import { getAgents } from '../../api/agents.ts'
import {
  answerReview,
  clearReview,
  getExpected,
  getMonth,
  recategorizeReview,
  startReview,
} from '../../api/reviews.ts'
import type {
  Answers,
  ExpectedData,
  MerchantCategories,
  MonthView,
  ReviewStatus,
  SequencedEvent,
  TotalsData,
} from '../../api/types.ts'
import { useReviewEvents } from '../../hooks/useReviewEvents.ts'
import { EventFeed } from './EventFeed.tsx'
import { MonthPicker, currentMonth } from './MonthPicker.tsx'
import { QuestionCard } from './QuestionCard.tsx'
import { Report } from './Report.tsx'
import { TotalsChart } from './TotalsChart.tsx'
import { TransactionsSection } from './TransactionsSection.tsx'

const MONTH_PARAM = 'month'

/** Which raw transactions are listed; picks counts the choices made in the totals. */
interface Shown {
  category: string | null
  standingOrders: boolean
  picks: number
}

const SHOW_ALL: Shown = { category: null, standingOrders: false, picks: 0 }

/** The expected charges as fetched against one totals event; later totals make them stale. */
interface Fetched {
  totalsSeq: number
  data: ExpectedData
}

/** The status an event sets: review.status names it and review.failed fails the review. */
function statusOf(event: SequencedEvent): ReviewStatus | null {
  if (event.type === 'review.status') return event.data.status
  if (event.type === 'review.failed') return 'failed'
  return null
}

/**
 * The review's status, taken from its log. The server writes each status together with its
 * event, so every replica's API already reports any status read here. Until the log holds a status
 * event, the status read with the month applies. Once answers or categories are accepted while the
 * latest status event is the one numbered sentAt, the review counts as running until a later status
 * event arrives.
 */
function currentStatus(
  events: SequencedEvent[],
  monthStatus: ReviewStatus,
  sentAt: number | null,
): { status: ReviewStatus; seq: number } {
  const logged = events.flatMap((e) => {
    const status = statusOf(e)
    return status === null ? [] : [{ status, seq: e.seq }]
  })
  const latest = logged.at(-1) ?? { status: monthStatus, seq: 0 }
  return sentAt !== null && latest.seq <= sentAt ? { status: 'running', seq: latest.seq } : latest
}

/** The review's totals as they read with the expected rows counted; every reader of the totals,
 * the raw transactions included, then treats expected rows as it treats charged ones. */
function withExpectedRows(actual: TotalsData, expected: ExpectedData): TotalsData {
  const agents = new Set([...Object.keys(actual.categories), ...Object.keys(expected.categories)])
  return {
    ...actual,
    totals: expected.totals,
    standingOrders: expected.standingOrders,
    categories: Object.fromEntries(
      [...agents].map((a) => [a, { ...actual.categories[a], ...expected.categories[a] }]),
    ),
    chosen: Object.fromEntries(
      [...agents].map((a) => [a, [...(actual.chosen[a] ?? []), ...(expected.chosen[a] ?? [])]]),
    ),
  }
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

/** The month lives in the URL so a reload or a shared link reopens the month and its review. */
function putMonthInUrl(month: string) {
  const url = new URL(window.location.href)
  url.searchParams.set(MONTH_PARAM, month)
  window.history.replaceState(window.history.state, '', url)
}

export function ReviewPage() {
  const [agents, setAgents] = useState<string[] | null>(null)
  const [month, setMonth] = useState(
    () => new URLSearchParams(window.location.search).get(MONTH_PARAM) ?? currentMonth(new Date()),
  )
  const [fetchedView, setFetchedView] = useState<MonthView | null>(null)
  // Bumped after a start or a clear, so the month is read again.
  const [viewVersion, setViewVersion] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // The seq of the latest status event at the moment answers or categories were accepted.
  const [sentAt, setSentAt] = useState<number | null>(null)
  const [shown, setShown] = useState<Shown>(SHOW_ALL)
  // The person's own tick or untick; until they make one, a review that skipped a card agent shows
  // the expected charges, since the skipped card's recurring charges are otherwise missing.
  const [expectedChoice, setExpectedChoice] = useState<boolean | null>(null)
  const [fetchedExpected, setFetchedExpected] = useState<Fetched | null>(null)
  // A view of a month no longer picked is stale and shows nothing.
  const view = fetchedView !== null && fetchedView.month === month ? fetchedView : null
  const review = view === null ? null : view.review
  const reviewId = review === null ? null : review.id
  // The review-scoped state starts over whenever another review is shown.
  const [stateOf, setStateOf] = useState<string | null>(null)
  if (stateOf !== reviewId) {
    setStateOf(reviewId)
    setSentAt(null)
    setShown(SHOW_ALL)
    setExpectedChoice(null)
    setFetchedExpected(null)
  }
  const { events, streamError } = useReviewEvents(reviewId)
  const current = review === null ? null : currentStatus(events, review.status, sentAt)
  const status = current === null ? null : current.status
  const question = events.findLast((e) => e.type === 'review.question')
  const pause = status === 'waiting' && question?.type === 'review.question' ? question : null
  const totals = events.findLast((e) => e.type === 'review.totals')
  const report = events.findLast((e) => e.type === 'review.report')
  const failure = events.findLast((e) => e.type === 'review.failed')
  const inProgress = status === 'running' || status === 'waiting'
  // A reload replays the log one event at a time, passing through the running and waiting states
  // of a review that has long ended; the review's status, fetched with the month, tells a live
  // review apart.
  const liveInThisPage =
    inProgress && review !== null && (review.status === 'running' || review.status === 'waiting')
  const completed = status === 'completed'
  const totalsSeq = totals?.type === 'review.totals' ? totals.seq : null
  const withExpected =
    expectedChoice ?? (totals?.type === 'review.totals' && totals.data.skipped.length > 0)
  const expected =
    withExpected && completed && fetchedExpected !== null && fetchedExpected.totalsSeq === totalsSeq
      ? fetchedExpected.data
      : null
  const actualTotals = totals?.type === 'review.totals' ? totals.data : null
  const shownTotals =
    actualTotals !== null && expected !== null ? withExpectedRows(actualTotals, expected) : actualTotals
  // The server refuses to clear a running review; one that ended or waits for answers can go.
  const clearable = status !== null && status !== 'running'

  useEffect(() => {
    let current = true
    getAgents().then(
      (response) => current && setAgents(response.agents),
      (e: unknown) => current && setError(errorText(e)),
    )
    return () => {
      current = false
    }
  }, [])

  useEffect(() => {
    // A cleared month field names no month to read.
    if (month === '') return
    let current = true
    getMonth(month).then(
      (fetched) => current && setFetchedView(fetched),
      (e: unknown) => current && setError(errorText(e)),
    )
    return () => {
      current = false
    }
  }, [month, viewVersion])

  // Fetched on the first tick and kept while the box is toggled; new totals, as after a
  // recategorize, make the kept answer stale and the next shown state fetches again.
  const expectedStale =
    withExpected && completed && totalsSeq !== null && fetchedExpected?.totalsSeq !== totalsSeq
  useEffect(() => {
    if (!expectedStale || reviewId === null || totalsSeq === null) return
    let current = true
    getExpected(reviewId).then(
      (data) => current && setFetchedExpected({ totalsSeq, data }),
      (e: unknown) => current && setError(errorText(e)),
    )
    return () => {
      current = false
    }
  }, [expectedStale, reviewId, totalsSeq])

  function pick(picked: string) {
    setError(null)
    setMonth(picked)
    if (picked !== '') putMonthInUrl(picked)
  }

  /** Start or clear, then read the month again: a refusal too may mean the month moved on. */
  async function act(action: () => Promise<unknown>) {
    setError(null)
    setBusy(true)
    try {
      await action()
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
      setViewVersion((v) => v + 1)
    }
  }

  async function submit(statusSeq: number, answers: Answers) {
    if (reviewId === null) return
    setError(null)
    setBusy(true)
    try {
      await answerReview(reviewId, answers)
      setSentAt(statusSeq)
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }

  async function recategorize(categories: MerchantCategories): Promise<boolean> {
    if (reviewId === null || current === null) return false
    const statusSeq = current.seq
    setError(null)
    try {
      await recategorizeReview(reviewId, categories)
      setSentAt(statusSeq)
      return true
    } catch (e) {
      setError(errorText(e))
      return false
    }
  }

  return (
    <main>
      <h1>Monthly card review</h1>
      <MonthPicker
        month={month}
        view={view}
        clearable={clearable}
        busy={busy}
        agents={agents}
        onMonth={pick}
        onStart={() => {
          putMonthInUrl(month)
          void act(() => startReview(month))
        }}
        onClear={() => {
          if (reviewId !== null) void act(() => clearReview(reviewId))
        }}
      />
      {error !== null && <p role="alert" className="error">{error}</p>}
      {streamError !== null && <p role="alert" className="error">Stream error: {streamError}</p>}
      {failure?.type === 'review.failed' && (
        <p role="alert" className="failure">Review failed: {failure.data.message}</p>
      )}
      {reviewId !== null && (
        <EventFeed events={events} working={status === 'running'} inProgress={inProgress} />
      )}
      {pause !== null && current !== null && (
        <QuestionCard
          key={pause.seq}
          questions={pause.data.questions}
          submitting={busy}
          onSubmit={(answers) => submit(current.seq, answers)}
        />
      )}
      {completed && totalsSeq !== null && (
        <section>
          <label>
            <input
              type="checkbox"
              checked={withExpected}
              onChange={(e) => setExpectedChoice(e.target.checked)}
            />{' '}
            Include expected charges
          </label>{' '}
          {expected !== null && (
            <span className="muted">
              {expected.basedOn === null
                ? 'No earlier month has a completed review to project from.'
                : `Expected charges are projected from ${expected.basedOn}.`}
            </span>
          )}
        </section>
      )}
      {reviewId !== null && (
        <TransactionsSection
          key={reviewId}
          events={events}
          expected={expected === null ? [] : expected.transactions}
          totals={shownTotals}
          onRecategorize={completed ? recategorize : null}
          category={shown.category}
          standingOrders={shown.standingOrders}
          onStandingOrders={(standingOrders) => setShown((s) => ({ ...s, standingOrders }))}
          inProgress={liveInThisPage}
          picks={shown.picks}
        />
      )}
      {shownTotals !== null && shownTotals.totals.length > 0 && (
        <TotalsChart
          totals={shownTotals.totals}
          standingOrders={shownTotals.standingOrders}
          withExpected={expected !== null}
          skipped={shownTotals.skipped}
          selected={shown.category}
          onSelect={(category) =>
            setShown(({ picks }) => ({ category, standingOrders: false, picks: picks + 1 }))
          }
          onSelectStandingOrders={() =>
            setShown(({ picks }) => ({ category: null, standingOrders: true, picks: picks + 1 }))
          }
        />
      )}
      {report?.type === 'review.report' && <Report text={report.data.text} outOfSync={expected !== null} />}
    </main>
  )
}
