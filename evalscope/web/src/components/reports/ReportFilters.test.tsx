import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { LocaleProvider } from '@/contexts/LocaleContext'
import ReportFiltersBar, { type ReportFilters } from './ReportFilters'

afterEach(cleanup)

const BASE_FILTERS: ReportFilters = {
  search: '',
  models: [],
  datasets: [],
  sortBy: 'time',
  sortOrder: 'desc',
  groupByModel: false,
}

function manyModels(n: number): string[] {
  return Array.from({ length: n }, (_, i) => `model-${String(i).padStart(2, '0')}`)
}

function renderBar(availableModels: string[], onChange = vi.fn()) {
  render(
    <LocaleProvider>
      <ReportFiltersBar
        filters={BASE_FILTERS}
        availableModels={availableModels}
        availableDatasets={[]}
        onChange={onChange}
      />
    </LocaleProvider>,
  )
  return onChange
}

describe('ReportFiltersBar model/dataset dropdown', () => {
  it('renders every option with no search box when the list is short', () => {
    renderBar(['gemma-3-27b-it', 'qwen-plus'])
    fireEvent.click(screen.getByRole('button', { name: 'Model' }))

    expect(screen.getByText('gemma-3-27b-it')).toBeInTheDocument()
    expect(screen.getByText('qwen-plus')).toBeInTheDocument()
    expect(screen.queryByPlaceholderText('Filter...')).not.toBeInTheDocument()
  })

  it('shows a search box and narrows rendered options once the list is long', () => {
    const options = manyModels(20)
    renderBar(options)
    fireEvent.click(screen.getByRole('button', { name: 'Model' }))

    // All 20 render up front (under the 50-row cap) until the user narrows it.
    expect(screen.getByText('model-00')).toBeInTheDocument()
    expect(screen.getByText('model-19')).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText('Filter...'), { target: { value: 'model-1' } })

    expect(screen.getByText('model-10')).toBeInTheDocument()
    expect(screen.queryByText('model-00')).not.toBeInTheDocument()
    expect(screen.queryByText('model-05')).not.toBeInTheDocument()
  })

  it('caps rendered rows and reports the remainder instead of mounting every match', () => {
    const options = manyModels(80)
    renderBar(options)
    fireEvent.click(screen.getByRole('button', { name: 'Model' }))

    expect(screen.getByText('model-00')).toBeInTheDocument()
    expect(screen.queryByText('model-79')).not.toBeInTheDocument()
    expect(screen.getByText('+ 30 more, refine search')).toBeInTheDocument()
  })

  it('still toggles selection through the filtered view', () => {
    const onChange = renderBar(manyModels(20))
    fireEvent.click(screen.getByRole('button', { name: 'Model' }))
    fireEvent.change(screen.getByPlaceholderText('Filter...'), { target: { value: 'model-07' } })
    fireEvent.click(screen.getByText('model-07'))

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ models: ['model-07'] }))
  })
})
