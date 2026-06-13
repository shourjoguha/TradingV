/**
 * Plotly layout template — neumorphic-friendly defaults.
 *
 * Applied via `Plotly.setPlotConfig` + per-figure spread. Keeps every Plotly
 * chart in the app on the same visual contract (bg, font, grid, hover style,
 * modebar suppression) without forcing each callsite to repeat 30 lines of
 * config.
 */
import type { Layout, Config } from 'plotly.js'
import { FONT, STROKE } from './tokens'
import { SURFACE } from './palette'

/**
 * Base layout — spread first, then per-chart layout overrides win.
 *
 * Notes:
 * - `paper_bgcolor` + `plot_bgcolor` match `--background` for seamless card embedding.
 * - `margin` is tight by default; callsites can widen if they need axis labels.
 * - `hoverlabel` carries the neumorphic card look (light bg + dark text).
 * - `xaxis.fixedrange = false` keeps pan/zoom on; set true on small embedded charts.
 */
export const BASE_LAYOUT: Partial<Layout> = {
  paper_bgcolor: SURFACE.bg,
  plot_bgcolor: SURFACE.bg,
  font: {
    family: FONT.sans,
    size: FONT.size,
    color: SURFACE.text,
  },
  margin: { t: 8, r: 12, b: 32, l: 48 },
  hovermode: 'x unified',
  hoverlabel: {
    bgcolor: '#FFFFFF',
    bordercolor: SURFACE.hairline,
    font: {
      family: FONT.mono,
      size: FONT.size,
      color: SURFACE.text,
    },
  },
  xaxis: {
    showgrid: true,
    gridcolor: SURFACE.grid,
    gridwidth: 1,
    zeroline: false,
    linecolor: SURFACE.hairline,
    linewidth: STROKE.axis,
    tickfont: { family: FONT.mono, size: FONT.size - 1, color: SURFACE.textMuted },
    showspikes: false,
  },
  yaxis: {
    showgrid: true,
    gridcolor: SURFACE.grid,
    gridwidth: 1,
    zeroline: false,
    linecolor: SURFACE.hairline,
    linewidth: STROKE.axis,
    tickfont: { family: FONT.mono, size: FONT.size - 1, color: SURFACE.textMuted },
  },
  showlegend: false,
}

/**
 * Default Plotly `config` — suppress modebar to keep the neumorphic surface
 * uncluttered. Callsites that need download/zoom buttons can override.
 */
export const BASE_CONFIG: Partial<Config> = {
  responsive: true,
  displayModeBar: false,
  displaylogo: false,
}
