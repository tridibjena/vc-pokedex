import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AttributionControl,
  LngLatBounds,
  Map as MapLibre,
  Marker,
  NavigationControl,
  setWorkerUrl,
} from 'maplibre-gl'
import type { LayerSpecification, StyleSpecification } from 'maplibre-gl'
// MapLibre v6 finds its worker relative to its own module URL, which no longer
// exists once Vite bundles it. Build the worker as its own entry and hand over
// the URL explicitly.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import 'maplibre-gl/dist/maplibre-gl.css'
import { asVerdict, hasPin, verdictColor, verdictTextColor } from '../dex'
import type { DexEntry } from '../dex'
import { CANVAS, CYAN, INK, PAPER, VERDICT } from '../theme'

setWorkerUrl(workerUrl)

/** OpenFreeMap: free vector tiles, no key, no request cap. */
const STYLE_URL = 'https://tiles.openfreemap.org/styles/positron'

const WORLD = { center: [12, 24] as [number, number], zoom: 1.25 }

/** The basemap in the page's palette — cream land, cyan water, ink labels. */
const MAP_COLORS = {
  land: CANVAS,
  water: CYAN,
  waterLabel: '#1d5a63',
  park: '#a8ddd0',
  wood: '#c4e3cf',
  ice: '#f8f4ea',
  residential: '#ede2c8',
  building: '#e4d8bb',
  buildingLine: '#cdbf9f',
  aeroway: '#e3d8bf',
  roadMajor: '#8d8371',
  roadMinor: '#b3a993',
  rail: '#b3a993',
  boundary: '#8d8371',
  label: INK,
  halo: PAPER,
}

const ENGLISH_NAME = ['coalesce', ['get', 'name_en'], ['get', 'name:latin'], ['get', 'name']]

function setPaint(layer: LayerSpecification, props: Record<string, unknown>) {
  const l = layer as { paint?: Record<string, unknown> }
  l.paint = { ...(l.paint ?? {}), ...props }
}

function hide(layer: LayerSpecification) {
  const l = layer as { layout?: Record<string, unknown> }
  l.layout = { ...(l.layout ?? {}), visibility: 'none' }
}

/**
 * Recolour the OpenMapTiles layers before the first paint.
 *
 * Done on the style JSON rather than with setPaintProperty after load, so the
 * stock grey basemap never flashes. Keyed on source-layer — part of the
 * OpenMapTiles schema — rather than on layer ids, which differ per style.
 */
export function comicize(style: StyleSpecification): StyleSpecification {
  const c = MAP_COLORS
  for (const layer of style.layers) {
    const src = 'source-layer' in layer ? layer['source-layer'] : undefined
    const id = layer.id
    switch (layer.type) {
      case 'background':
        setPaint(layer, { 'background-color': c.land })
        break
      case 'fill':
        if (src === 'water') setPaint(layer, { 'fill-color': c.water, 'fill-opacity': 1 })
        else if (src === 'park') setPaint(layer, { 'fill-color': c.park, 'fill-opacity': 0.9 })
        else if (/ice|glacier/.test(id)) setPaint(layer, { 'fill-color': c.ice })
        else if (src === 'landcover') setPaint(layer, { 'fill-color': c.wood })
        else if (src === 'landuse') setPaint(layer, { 'fill-color': c.residential })
        else if (src === 'building')
          setPaint(layer, { 'fill-color': c.building, 'fill-outline-color': c.buildingLine })
        else if (src === 'aeroway') setPaint(layer, { 'fill-color': c.aeroway })
        else if (src === 'transportation') setPaint(layer, { 'fill-color': c.land })
        break
      case 'line':
        if (src === 'waterway') setPaint(layer, { 'line-color': c.water })
        else if (src === 'transportation') {
          const color = /rail/.test(id) ? c.rail : /motorway|major|trunk|primary/.test(id) ? c.roadMajor : c.roadMinor
          setPaint(layer, { 'line-color': color })
        } else if (src === 'boundary') setPaint(layer, { 'line-color': c.boundary })
        else if (src === 'aeroway') setPaint(layer, { 'line-color': c.roadMinor })
        break
      case 'symbol':
        if (/shield/.test(id)) {
          hide(layer)
          break
        }
        // One script per label: the stock style appends the native-script name
        // ("Belarus Беларусь"), which reads as noise at this scale.
        if (JSON.stringify(layer.layout?.['text-field'] ?? '').includes('name')) {
          const l = layer as { layout?: Record<string, unknown> }
          l.layout = { ...l.layout, 'text-field': ENGLISH_NAME }
        }
        setPaint(layer, {
          'text-color': src === 'water_name' || src === 'waterway' ? c.waterLabel : c.label,
          'text-halo-color': c.halo,
          'text-halo-width': 1.6,
        })
        break
    }
  }
  return style
}

/**
 * When a flight counts as arriving: inside the destination's region (within
 * this many zoom levels of landing — state scale for a city at zoom 11) and
 * slowing down, its zoom-in speed fallen below EASED_FRACTION of its peak.
 *
 * Reporting there, rather than at moveend, opens the spotlight during the
 * gentle last stretch of the descent — not after a pause at the end, and not
 * mid-dive while the map is still rushing in.
 */
const APPROACH_ZOOMS = 4
const EASED_FRACTION = 0.35

/** Teardrop pin, tip at (17, 41). Drawn twice: an offset ink copy is the shadow. */
const PIN_PATH = 'M17 41 C17 41 3 26 3 16 A14 14 0 1 1 31 16 C31 26 17 41 17 41 Z'
const PIN_SVG = `<svg class="dex-pin-glyph" viewBox="-1 -1 38 46" aria-hidden="true"><path class="dex-pin-shadow" d="${PIN_PATH}"/><path class="dex-pin-body" d="${PIN_PATH}"/></svg>`

/**
 * Spread pins that share a coordinate.
 *
 * Most HQs resolve to a city centre, so three Bengaluru startups would stack on
 * one point and only the top one could be clicked. Fan them out on a ring a
 * few kilometres across — within the precision a city-centre pin claims.
 */
function positions(entries: DexEntry[]): Map<string, [number, number]> {
  const groups = new Map<string, DexEntry[]>()
  for (const e of entries) {
    if (!hasPin(e)) continue
    const k = `${e.lat.toFixed(4)},${e.lng.toFixed(4)}`
    groups.set(k, [...(groups.get(k) ?? []), e])
  }
  const out = new Map<string, [number, number]>()
  for (const group of groups.values()) {
    group.forEach((e, i) => {
      if (group.length === 1) {
        out.set(e.key, [e.lng!, e.lat!])
        return
      }
      // ~3–5 km: enough to separate pins at city zoom, and still inside the
      // city the shared pin stands for.
      const angle = (2 * Math.PI * i) / group.length - Math.PI / 2
      const r = 0.03 * (1 + group.length / 8)
      const lat = e.lat! + r * Math.sin(angle)
      const lng = e.lng! + (r * Math.cos(angle)) / Math.max(0.2, Math.cos((e.lat! * Math.PI) / 180))
      out.set(e.key, [lng, lat])
    })
  }
  return out
}

/**
 * A flight target nudged off-centre, as a one-flight `offset`.
 *
 * Not `padding`: MapLibre keeps a flight's padding as the map's padding after
 * it lands, and fitBounds adds its own padding on top — so a spotlight flight
 * (500px clear on the right) left every later "back to the map" framed
 * against a lopsided viewport, shifted and zoomed out. An offset moves only
 * that one flight's target.
 */
export interface Inset {
  top: number
  bottom: number
  left: number
  right: number
}

function offsetFor(p: Inset): [number, number] {
  return [(p.left - p.right) / 2, (p.top - p.bottom) / 2]
}

function signature(e: DexEntry): string {
  return [e.companyName, e.recommendation, e.overallScore, e.lat, e.lng, e.location].join('|')
}

function pinElement(e: DexEntry): HTMLButtonElement {
  const el = document.createElement('button')
  el.type = 'button'
  el.className = 'dex-pin'
  const verdict = asVerdict(e.recommendation)
  el.dataset.verdict = verdict?.toLowerCase() ?? 'none'
  el.style.setProperty('--pin-color', verdictColor(e.recommendation, e.overallScore))
  el.style.setProperty('--pin-ink', verdictTextColor(e.recommendation))

  const score = e.overallScore != null ? e.overallScore.toFixed(1) : '?'
  const where = e.location ? `, ${e.location}${e.geoPrecision === 'address' ? '' : ' (approximate)'}` : ''
  el.setAttribute('aria-label', `${e.companyName}: ${verdict ?? 'unscored'} ${score}${where}`)
  el.title = `${e.companyName} · ${verdict ?? 'unscored'} ${score}`

  // MapLibre positions the marker element with its own `transform`, so the
  // hover/selection scaling lives one level down, on the bubble.
  const bubble = document.createElement('span')
  bubble.className = 'dex-pin-bubble'
  bubble.innerHTML = PIN_SVG
  const scoreEl = document.createElement('span')
  scoreEl.className = 'dex-pin-score'
  scoreEl.textContent = score
  bubble.append(scoreEl)

  const label = document.createElement('strong')
  label.className = 'dex-pin-label'
  label.textContent = e.companyName // textContent: the name is model output
  el.append(bubble, label)
  return el
}

interface Props {
  entries: DexEntry[]
  selectedKey: string | null
  hoveredKey: string | null
  /** The entry in the spotlight: its pin is sized up, the rest fade. */
  spotlitKey: string | null
  onSelect: (key: string) => void
  onHover: (key: string | null) => void
  /** The flight to this selection has slowed into its landing (see APPROACH_ZOOMS). */
  onArrive: (key: string) => void
  /** Changes whenever the visible set changes enough to re-frame the map. */
  fitKey: string
  /** Bumped to re-fly to the selection even when it hasn't changed. */
  focusNonce: number
  /** Where the flight puts the pin — clear of whatever covers the map. */
  flyPadding: Inset
}

interface PinRecord {
  marker: Marker
  el: HTMLButtonElement
  sig: string
}

export default function DexMap({
  entries,
  selectedKey,
  hoveredKey,
  spotlitKey,
  onSelect,
  onHover,
  onArrive,
  fitKey,
  focusNonce,
  flyPadding,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibre | null>(null)
  const pinsRef = useRef<Map<string, PinRecord>>(new Map())
  const [ready, setReady] = useState(false)
  const [failed, setFailed] = useState(false)

  // Latest callbacks without re-binding every marker's listeners on each render.
  const onSelectRef = useRef(onSelect)
  const onHoverRef = useRef(onHover)
  const onArriveRef = useRef(onArrive)
  onSelectRef.current = onSelect
  onHoverRef.current = onHover
  onArriveRef.current = onArrive
  // Incremented per flight, so a flight cut short by a newer one never reports
  // arriving.
  const flightRef = useRef(0)

  const pinned = useMemo(() => entries.filter(hasPin), [entries])
  const where = useMemo(() => positions(pinned), [pinned])

  // ── Create the map once ────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false
    let map: MapLibre | null = null
    const pins = pinsRef.current

    fetch(STYLE_URL)
      .then((r) => {
        if (!r.ok) throw new Error(`style ${r.status}`)
        return r.json() as Promise<StyleSpecification>
      })
      .then((style) => {
        if (cancelled || !containerRef.current) return
        map = new MapLibre({
          container: containerRef.current,
          style: comicize(style),
          center: WORLD.center,
          zoom: WORLD.zoom,
          minZoom: 1,
          maxZoom: 17,
          attributionControl: false,
          dragRotate: false,
          pitchWithRotate: false,
        })
        map.touchZoomRotate.disableRotation()

        // Halftone dots over the tiles but under the pins: markers are appended
        // to the same canvas container later, so they stack above this.
        const halftone = document.createElement('div')
        halftone.className = 'map-halftone'
        halftone.setAttribute('aria-hidden', 'true')
        map.getCanvasContainer().appendChild(halftone)
        map.addControl(new NavigationControl({ showCompass: false }), 'top-right')
        // OSM / OpenMapTiles attribution is a licence requirement — keep it.
        map.addControl(new AttributionControl({ compact: true }), 'bottom-right')

        const container = containerRef.current
        const syncZoomClasses = () => {
          const z = map!.getZoom()
          container.classList.toggle('is-overview', z < 3.2)
          container.classList.toggle('show-labels', z >= 9.5)
        }
        map.on('zoom', syncZoomClasses)
        syncZoomClasses()

        map.on('load', () => !cancelled && setReady(true))
        mapRef.current = map
      })
      .catch(() => !cancelled && setFailed(true))

    return () => {
      cancelled = true
      pins.forEach((p) => p.marker.remove())
      pins.clear()
      map?.remove()
      mapRef.current = null
      setReady(false)
    }
  }, [])

  // ── Sync markers with entries ──────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    const pins = pinsRef.current
    const live = new Set<string>()

    for (const e of pinned) {
      const pos = where.get(e.key)
      if (!pos) continue
      live.add(e.key)
      const sig = signature(e)
      const existing = pins.get(e.key)
      if (existing && existing.sig === sig) {
        existing.marker.setLngLat(pos)
        continue
      }
      existing?.marker.remove()

      const el = pinElement(e)
      el.addEventListener('click', (ev) => {
        ev.stopPropagation()
        onSelectRef.current(e.key)
      })
      el.addEventListener('mouseenter', () => onHoverRef.current(e.key))
      el.addEventListener('mouseleave', () => onHoverRef.current(null))
      el.addEventListener('focus', () => onHoverRef.current(e.key))
      el.addEventListener('blur', () => onHoverRef.current(null))

      const marker = new Marker({ element: el, anchor: 'bottom' }).setLngLat(pos).addTo(map)
      pins.set(e.key, { marker, el, sig })
    }

    for (const [key, p] of pins) {
      if (!live.has(key)) {
        p.marker.remove()
        pins.delete(key)
      }
    }
  }, [ready, pinned, where])

  // ── Selection / hover state on the pins ───────────────────────────────
  useEffect(() => {
    for (const [key, p] of pinsRef.current) {
      p.el.classList.toggle('is-selected', key === selectedKey)
      p.el.classList.toggle('is-hovered', key === hoveredKey && key !== selectedKey)
      p.el.classList.toggle('is-spotlit', key === spotlitKey)
      p.el.setAttribute('aria-pressed', String(key === selectedKey))
    }
  }, [selectedKey, hoveredKey, spotlitKey, ready, pinned])

  // ── Frame everything when the visible set changes ──────────────────────
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    const pts = [...where.values()]
    // Room for the floating search bar and chip rail over the top of the map.
    const padding = { top: 150, bottom: 70, left: 70, right: 70 }
    if (pts.length === 0) {
      map.easeTo({ ...WORLD, duration: 600 })
    } else if (pts.length === 1) {
      map.flyTo({ center: pts[0], zoom: 10, offset: offsetFor(padding), duration: 900 })
    } else {
      const bounds = pts.reduce((b, p) => b.extend(p), new LngLatBounds(pts[0], pts[0]))
      map.fitBounds(bounds, { padding, maxZoom: 11, duration: 900 })
    }
    // `where` deliberately omitted: polling refreshes it every few seconds,
    // and re-framing on every poll would yank the map out from under the user.
  }, [ready, fitKey])

  // ── Fly to the selection, then report arriving ─────────────────────────
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map || !selectedKey) return
    const pos = where.get(selectedKey)
    if (!pos) return
    const key = selectedKey
    const flight = ++flightRef.current
    const targetZoom = Math.max(map.getZoom(), 11)
    map.flyTo({
      center: pos,
      zoom: targetZoom,
      // Read at flight time; deliberately not a dependency, so resizing the
      // window doesn't re-fly.
      offset: offsetFor(flyPadding),
      speed: 1.6,
      curve: 1.3,
    })

    // Arrival is whichever comes first: the descent reaching region scale
    // with the pin on screen, or this flight's own moveend (a short hop that
    // never zooms out). Listening only after flyTo means the moveend it fires
    // while interrupting an earlier flight isn't taken for this one; the token
    // discards an earlier flight's late events.
    let reported = false
    const report = () => {
      if (reported) return
      reported = true
      map.off('move', approach)
      if (flight === flightRef.current) onArriveRef.current(key)
    }
    let lastZoom = map.getZoom()
    let lastTime = performance.now()
    let rate = 0 // smoothed zoom-in speed, levels per second
    let peak = 0
    const approach = () => {
      if (flight !== flightRef.current) {
        map.off('move', approach)
        return
      }
      const zoom = map.getZoom()
      const now = performance.now()
      const dt = (now - lastTime) / 1000
      if (dt > 0) {
        const instant = Math.max(0, (zoom - lastZoom) / dt) // zooming in only
        rate = peak ? rate * 0.6 + instant * 0.4 : instant // damp frame jitter
        peak = Math.max(peak, rate)
      }
      lastZoom = zoom
      lastTime = now
      if (zoom < targetZoom - APPROACH_ZOOMS) return
      // Still diving in fast. (A hop that never zooms has no peak at all and
      // is left to moveend.)
      if (!peak || rate > peak * EASED_FRACTION) return
      const pt = map.project(pos)
      const box = map.getContainer()
      if (pt.x >= 0 && pt.y >= 0 && pt.x <= box.clientWidth && pt.y <= box.clientHeight) report()
    }
    // Nothing to animate (reduced motion, or already in place): arrived now.
    if (!map.isMoving()) {
      report()
      return
    }
    map.on('move', approach)
    map.once('moveend', report)
    return () => {
      map.off('move', approach)
    }
  }, [ready, selectedKey, focusNonce])

  // Scored entries with no HQ; a scan still running isn't missing anything yet.
  const unpinned = entries.filter((e) => e.state === 'ready' && !hasPin(e)).length

  return (
    <div className="dex-map">
      <div ref={containerRef} className="dex-map-canvas" />

      {failed && (
        <div className="dex-map-notice">
          <strong>Map tiles unavailable.</strong> The Dex still works from the list.
        </div>
      )}

      <div className="map-legend" aria-label="Map legend">
        <span className="map-legend-title">Verdict</span>
        <ul>
          {(Object.keys(VERDICT) as Array<keyof typeof VERDICT>).map((v) => (
            <li key={v}>
              <span className="map-legend-swatch" style={{ background: VERDICT[v] }} />
              {v}
            </li>
          ))}
        </ul>
        <p className="map-legend-note">
          Number = overall score. Pins mark the HQ — the city centre unless an address was found.
          {unpinned > 0 && ` ${unpinned} without a known HQ ${unpinned === 1 ? 'is' : 'are'} list-only.`}
        </p>
      </div>
    </div>
  )
}
