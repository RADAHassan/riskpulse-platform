import { describe, expect, it } from 'vitest'
import type { ProjectionPoint } from '../api/types'
import { money, parseFeatures, pct, shortId } from './format'
import { buildSeries, summarize, uncertaintyOf } from './viz'

const point = (over: Partial<ProjectionPoint>): ProjectionPoint => ({
  oot_index: 1, true_label: 0, raw_score: 0.01, fraud_probability: 0.001, human_review: false, is_fp: false, is_fn: false,
  pca_x: 1, pca_y: 2, tsne_x: 3, tsne_y: 4, umap_x: 5, umap_y: 6, ...over,
})

describe('format', () => {
  it('shortens ids and formats numbers', () => {
    expect(shortId('12345678-aaaa-bbbb')).toBe('12345678…')
    expect(shortId(null)).toBe('—')
    expect(pct(0.1234)).toBe('12.3 %')
    expect(pct(null)).toBe('—')
    expect(money(12.5)).toContain('12.50')
  })

  it('parses feature vectors from commas, spaces and JSON arrays', () => {
    expect(parseFeatures('1, 2.5 -3')).toEqual([1, 2.5, -3])
    expect(parseFeatures('[0.1,0.2]')).toEqual([0.1, 0.2])
    expect(parseFeatures('')).toEqual([])
  })

  it('rejects non numeric and non finite features', () => {
    expect(() => parseFeatures('1, abc')).toThrow(/not a finite number/)
    expect(() => parseFeatures('1, Infinity')).toThrow()
    expect(() => parseFeatures('NaN')).toThrow()
  })
})

describe('viz', () => {
  const pts = [
    point({}),
    point({ true_label: 1, fraud_probability: 0.99, human_review: true }),
    point({ true_label: 1, is_fn: true, fraud_probability: 0.02 }),
    point({ is_fp: true, fraud_probability: 0.5, human_review: true }),
  ]

  it('computes the same uncertainty proxy as the serving layer', () => {
    expect(uncertaintyOf(point({ fraud_probability: 0.5 }))).toBe(1)
    expect(uncertaintyOf(point({ fraud_probability: 0.9 }))).toBeCloseTo(0.2)
  })

  it('colours by class', () => {
    const s = buildSeries(pts, 'pca', 'class')
    expect(s.map((x) => x.name).sort()).toEqual(['Fraud', 'Legitimate'])
    expect(s.find((x) => x.name === 'Fraud')?.points).toHaveLength(2)
  })

  it('separates caught frauds, false negatives and false positives', () => {
    const names = buildSeries(pts, 'tsne', 'errors').map((x) => x.name)
    expect(names).toEqual(expect.arrayContaining(['Caught fraud', 'False negative (missed fraud)', 'False positive', 'Legitimate']))
  })

  it('uses the selected projection coordinates', () => {
    expect(buildSeries([point({})], 'umap', 'class')[0].points[0]).toMatchObject({ x: 5, y: 6 })
    expect(buildSeries([point({})], 'pca', 'class')[0].points[0]).toMatchObject({ x: 1, y: 2 })
  })

  it('buckets uncertainty and review routing', () => {
    expect(buildSeries(pts, 'pca', 'uncertainty').map((s) => s.name).some((n) => n.startsWith('High'))).toBe(true)
    expect(buildSeries(pts, 'pca', 'review').find((s) => s.name === 'Human review')?.points).toHaveLength(2)
  })

  it('summarises the sample', () => {
    expect(summarize(pts)).toEqual({ total: 4, frauds: 2, reviews: 2, falseNegatives: 1, falsePositives: 1 })
  })
})
