import type { ProjectionPoint } from '../api/types'

export type Projection = 'pca' | 'tsne' | 'umap'
export type ColorMode = 'class' | 'errors' | 'uncertainty' | 'review'

export interface Series {
  name: string
  color: string
  points: Array<{ x: number; y: number; p: ProjectionPoint }>
}

export const uncertaintyOf = (p: ProjectionPoint): number => 2 * Math.min(p.fraud_probability, 1 - p.fraud_probability)

const xy = (p: ProjectionPoint, proj: Projection): [number, number] =>
  proj === 'pca' ? [p.pca_x, p.pca_y] : proj === 'tsne' ? [p.tsne_x, p.tsne_y] : [p.umap_x, p.umap_y]

/** Splits points into coloured series for the chosen colouring mode (colour-blind safe palette). */
export function buildSeries(points: ProjectionPoint[], proj: Projection, mode: ColorMode): Series[] {
  const groups: Record<string, Series> = {}
  const add = (key: string, name: string, color: string, p: ProjectionPoint) => {
    const [x, y] = xy(p, proj)
    ;(groups[key] ??= { name, color, points: [] }).points.push({ x, y, p })
  }
  for (const p of points) {
    if (mode === 'class') {
      if (p.true_label === 1) add('fraud', 'Fraud', '#d55e00', p)
      else add('legit', 'Legitimate', '#0072b2', p)
    } else if (mode === 'errors') {
      if (p.is_fn) add('fn', 'False negative (missed fraud)', '#d55e00', p)
      else if (p.is_fp) add('fp', 'False positive', '#cc79a7', p)
      else if (p.true_label === 1) add('tp', 'Caught fraud', '#009e73', p)
      else add('tn', 'Legitimate', '#bdbdbd', p)
    } else if (mode === 'uncertainty') {
      const u = uncertaintyOf(p)
      if (u >= 0.25) add('high', 'High uncertainty (≥ 0.25)', '#d55e00', p)
      else if (u >= 0.05) add('mid', 'Medium (0.05–0.25)', '#e69f00', p)
      else add('low', 'Low (< 0.05)', '#56b4e9', p)
    } else {
      if (p.human_review) add('review', 'Human review', '#cc79a7', p)
      else add('auto', 'Automatic path', '#bdbdbd', p)
    }
  }
  return Object.values(groups)
}

export function summarize(points: ProjectionPoint[]) {
  return {
    total: points.length,
    frauds: points.filter((p) => p.true_label === 1).length,
    reviews: points.filter((p) => p.human_review).length,
    falseNegatives: points.filter((p) => p.is_fn).length,
    falsePositives: points.filter((p) => p.is_fp).length,
  }
}
