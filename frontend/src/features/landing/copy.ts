/** The words of the signed-out landing page; **marked** words show in bold. */

/** The product's name, as the tab's title and the card's heading name it. */
export const APP_TITLE = 'Home Finance Agent'
/** The line under the title: what the agent does, in one line. */
export const APP_TAGLINE = 'An AI agent that reviews your monthly card spending'

/** The pitch's opening lines: the question a person brings, then how little the agent asks. */
export const LANDING_LEAD = [
  "**Where did this month's card money go?** The agent gathers every charge from your cards," +
    ' sorts them into categories and sets them against your budget.',
  '**It asks only what it cannot decide,** like a merchant it does not recognize, and remembers' +
    ' your answer for next month.',
]

/** The way through a month, as numbered steps, since visitors skim prose but follow steps. */
export const LANDING_STEPS = [
  {
    title: 'Load your statements',
    text: "on each card's own page, signed in with the same Google account.",
  },
  { title: 'Pick a month and press start', text: "every card's charges come in as you watch." },
  {
    title: 'Read the summary',
    text:
      'a pie of spending by category, and the totals against your budget in a few plain' +
      ' sentences.',
  },
]

/** What the "More" toggle adds under the pitch. */
export const LANDING_DETAILS = [
  'Works with **American Express Israel** and **Cal** cards, in shekels.',
  'The totals are computed, **never guessed**: the AI only puts them into words.',
  'A question **waits as long as it takes**, even across a restart.',
  "A missing statement links straight to the card's page: load the file there, press" +
    ' **continue**, and the review goes on.',
  'In a finished review, choose a category in the **spending pie** to list just its charges;' +
    ' moving a merchant to another category redoes the totals and the summary.',
  'Mid-month, **Include expected charges** adds the standing orders and installments still to' +
    ' come, so you see where the month is heading.',
  'Each person sees **only their own** reviews and statements.',
]

export const MORE = 'More'
export const LESS = 'Less'

/** The mark before the invite link, the same as the invite message's own. */
export const INVITE_MARK = '💬'
export const INVITE_LINK = 'Invite friends on WhatsApp'
/** The invite message's paragraphs, in the voice of the friend who sends it: what it is, what it
 * does with the cards, and how little it asks. The page's own address follows the last one. */
export const INVITE_MESSAGE = [
  'Hi! 👋 I got a recommendation for Home Finance Agent, an AI agent that reviews your monthly' +
    ' card spending.',
  "💳 It gathers the month's charges from your American Express Israel and Cal cards, sorts them" +
    ' into categories and compares them with your budget.',
  '💬 It asks only about what it cannot decide, and remembers your answers for next month.',
  'Have a look:',
]

export const SOURCE_LINK = 'Source code on GitHub'
