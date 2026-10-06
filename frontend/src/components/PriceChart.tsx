import {
  ColorType,
  createChart,
  createSeriesMarkers,
  LineSeries,
  type ChartOptions,
  type DeepPartial,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
} from 'lightweight-charts'
import { useEffect, useRef, useState } from 'react'
import type { HistoryMarker } from '../api/history'
import { useReducedMotion } from '../hooks/useReducedMotion'
import { t } from '../strings'
import { chartPriceFormatter, chartScale, toChartPoint } from './chartData'

interface Props {
  bars: { date: string; close: string }[]
  markers: HistoryMarker[]
}

// Every colour comes from the design tokens, read at runtime, so the chart follows the theme
// without a single colour literal here.
function tokens() {
  const css = getComputedStyle(document.documentElement)
  const token = (name: string) => css.getPropertyValue(name).trim()
  return {
    background: token('--surface'),
    text: token('--text-muted'),
    grid: token('--border'),
    line: token('--accent'),
    buy: token('--accent'),
    sell: token('--violet-fill'),
    font: token('--font'),
  }
}

function chartOptions(reducedMotion: boolean): DeepPartial<ChartOptions> {
  const c = tokens()
  return {
    autoSize: true,
    layout: {
      background: { type: ColorType.Solid, color: c.background },
      textColor: c.text,
      fontFamily: c.font,
      // The logo injects a <style> element (blocked by our CSP) and sends the page path to
      // tradingview.com; the page shows a text attribution link instead, which the licence allows.
      attributionLogo: false,
    },
    grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
    rightPriceScale: { borderColor: c.grid },
    timeScale: { borderColor: c.grid },
    localization: { locale: t.locale },
    kineticScroll: { touch: !reducedMotion, mouse: false },
  }
}

// Shape and letter carry buy/sell, never green or red (those mean gain and loss in this app).
// Each sits at the exact trade price, so it lines up with the raw (unadjusted) close line.
function toMarkers(markers: HistoryMarker[]): SeriesMarker<Time>[] {
  const c = tokens()
  return markers.map((m) => ({
    time: m.date,
    position: 'atPriceMiddle',
    price: toChartPoint(m.date, m.price).value,
    shape: m.side === 'buy' ? 'arrowUp' : 'arrowDown',
    color: m.side === 'buy' ? c.buy : c.sell,
    text: m.side === 'buy' ? t.asset.buyLetter : t.asset.sellLetter,
  }))
}

export default function PriceChart({ bars, markers }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const chart = useRef<IChartApi | null>(null)
  const series = useRef<ISeriesApi<'Line'> | null>(null)
  const markerLayer = useRef<ISeriesMarkersPluginApi<Time> | null>(null)
  const reducedMotion = useReducedMotion()
  // Bumped when the theme changes, so the drawing effect re-reads the token colours.
  const [themeTick, setThemeTick] = useState(0)

  // Create the chart once; tear it down on unmount.
  useEffect(() => {
    if (!container.current) return
    const instance = createChart(container.current, chartOptions(reducedMotion))
    chart.current = instance
    series.current = instance.addSeries(LineSeries, { lineWidth: 2, priceLineVisible: false })
    markerLayer.current = createSeriesMarkers(series.current, [])
    // The theme toggle sets data-theme on <html>.
    const observer = new MutationObserver(() => setThemeTick((n) => n + 1))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => {
      observer.disconnect()
      instance.remove()
      chart.current = null
      series.current = null
      markerLayer.current = null
    }
    // Options are re-applied by the effect below; creation runs once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // New data (another range or coin): replace the line and fit it to the view.
  useEffect(() => {
    const line = series.current
    if (!chart.current || !line) return
    const points = bars.map((b) => toChartPoint(b.date, b.close))
    const { decimals, minMove } = chartScale(points.map((p) => p.value))
    const formatter = chartPriceFormatter(decimals)
    line.applyOptions({ priceFormat: { type: 'custom', formatter, minMove } })
    chart.current.applyOptions({ localization: { priceFormatter: formatter } })
    line.setData(points)
    chart.current.timeScale().fitContent()
  }, [bars])

  // Colours (and markers, which carry colours): on first draw and whenever the theme changes,
  // without resetting the user's zoom.
  useEffect(() => {
    chart.current?.applyOptions(chartOptions(reducedMotion))
    series.current?.applyOptions({ color: tokens().line })
    markerLayer.current?.setMarkers(toMarkers(markers))
  }, [markers, themeTick, reducedMotion])

  // Time runs left to right on a price chart, whatever the page direction.
  return <div ref={container} className="price-chart" dir="ltr" />
}
