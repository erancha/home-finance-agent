import { describe, expect, it } from 'vitest'
import contract from '../../../../docs/a2a-contract.md?raw'
import { CATEGORY_MEANINGS } from './categoryMeanings.ts'

/** The rows of the contract's taxonomy table: category to meaning. */
function contractMeanings(): Record<string, string> {
  const taxonomy = contract.split('\n## Taxonomy\n')[1].split('\n## ')[0]
  const rows = [...taxonomy.matchAll(/^\| `([a-z]+)` \| (.+) \|$/gm)]
  return Object.fromEntries(rows.map(([, category, meaning]) => [category, meaning]))
}

describe('CATEGORY_MEANINGS', () => {
  it('is the taxonomy table of the A2A contract, word for word', () => {
    const meanings = contractMeanings()
    expect(Object.keys(meanings)).toHaveLength(14)
    expect(CATEGORY_MEANINGS).toEqual(meanings)
  })
})
