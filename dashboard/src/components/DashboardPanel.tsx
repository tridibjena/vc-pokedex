import { useEffect, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { ArrowRight } from 'lucide-react'
import { api } from '../api'
import { shortSector } from '../dex'
import { CHART, INK, PINK, tooltipItemStyle, tooltipLabelStyle, tooltipStyle } from '../theme'

interface Trends {
  sector_distribution: Record<string, number>
  stage_distribution: Record<string, number>
  monthly_deal_counts: Array<{ date: string; count: number }>
}

const STAGE_ORDER = ['pre-seed', 'seed', 'series-a', 'series-b', 'growth']

const AXIS = { stroke: CHART.axis, fontSize: 11, tickLine: false, axisLine: false } as const
const TICK = { fill: INK, fontSize: 11, fontWeight: 700, fontFamily: 'var(--mono-face)' }

export default function DashboardPanel({ onOpenDex }: { onOpenDex: () => void }) {
  const [trends, setTrends] = useState<Trends>({
    sector_distribution: {},
    stage_distribution: {},
    monthly_deal_counts: [],
  })
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState({ dealsCount: 0, docsCount: 0, memosCount: 0 })

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        const [trendsRes, dealsRes, docsRes, reportsRes] = await Promise.all([
          api.get('/reports/trends'),
          api.get('/reports/deals?limit=1'),
          api.get('/research/documents'),
          api.get('/reports/list'),
        ])
        setTrends(trendsRes.data)
        setStats({
          dealsCount: dealsRes.data.total,
          docsCount: docsRes.data.total,
          memosCount: reportsRes.data.total,
        })
      } catch (err) {
        console.error('Failed to load dashboard data:', err)
      } finally {
        setLoading(false)
      }
    }
    fetchDashboardData()
  }, [])

  if (loading) {
    return (
      <div className="panel-loading panel-loading-tall">
        <span className="spinner" />
      </div>
    )
  }

  // Sectors as a ranked bar chart rather than a donut: many categories read
  // far better as lengths along one axis, and one colour suffices because the
  // axis labels carry identity. Normalised so legacy free-text sectors merge.
  const sectorTotals = new Map<string, number>()
  for (const [name, value] of Object.entries(trends.sector_distribution)) {
    const key = shortSector(name)
    sectorTotals.set(key, (sectorTotals.get(key) ?? 0) + value)
  }
  const sectorData = [...sectorTotals.entries()]
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 10)

  const stageData = Object.entries(trends.stage_distribution)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => {
      const ai = STAGE_ORDER.indexOf(a.name.toLowerCase())
      const bi = STAGE_ORDER.indexOf(b.name.toLowerCase())
      return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi)
    })

  const metrics = [
    { label: 'Deals screened', value: stats.dealsCount, tone: 'pop' },
    { label: 'Dex entries', value: stats.docsCount, tone: 'cyan' },
    { label: 'Memos written', value: stats.memosCount, tone: 'pink' },
  ]

  const steps = [
    <>Type a startup's name into the search bar on <strong>The Dex</strong>. No upload, no data entry.</>,
    <>Six agents research it, benchmark it against 232 SEC filings and screen for risk, in parallel.</>,
    <>It lands as a pin at its HQ, with a scorecard, a bull and bear case, and a full memo.</>,
    <>Interrogate any entry in <strong>RAG Chat</strong>, or add your own term sheets and decks under Sources.</>,
  ]

  return (
    <div className="dash">
      <div className="stat-row">
        {metrics.map(({ label, value, tone }) => (
          <div className={`stat-tile stat-${tone}`} key={label}>
            <span className="stat-value">{value ?? 0}</span>
            <span className="stat-label">{label}</span>
          </div>
        ))}
      </div>

      <div className="dash-grid">
        <ChartCard title="Sectors" empty={sectorData.length === 0} height={Math.max(220, sectorData.length * 34 + 40)}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={sectorData} layout="vertical" margin={{ top: 4, right: 36, left: 8, bottom: 4 }} barCategoryGap={6}>
              <CartesianGrid stroke={CHART.grid} horizontal={false} strokeDasharray="3 3" />
              <XAxis type="number" {...AXIS} allowDecimals={false} tick={TICK} />
              <YAxis type="category" dataKey="name" {...AXIS} width={92} tick={TICK} />
              <Tooltip cursor={{ fill: 'rgba(22,23,19,0.06)' }} contentStyle={tooltipStyle} itemStyle={tooltipItemStyle} labelStyle={tooltipLabelStyle} />
              <Bar dataKey="value" name="Deals" fill={CHART.series} stroke={CHART.seriesStroke} strokeWidth={2} maxBarSize={24} isAnimationActive={false}>
                <LabelList dataKey="value" position="right" style={{ fill: INK, fontSize: 12, fontWeight: 900, fontFamily: 'var(--mono-face)' }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Stages" empty={stageData.length === 0} height={300}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={stageData} margin={{ top: 20, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid stroke={CHART.grid} vertical={false} strokeDasharray="3 3" />
              <XAxis dataKey="name" {...AXIS} tick={TICK} />
              <YAxis {...AXIS} allowDecimals={false} tick={TICK} />
              <Tooltip cursor={{ fill: 'rgba(22,23,19,0.06)' }} contentStyle={tooltipStyle} itemStyle={tooltipItemStyle} labelStyle={tooltipLabelStyle} />
              <Bar dataKey="value" name="Deals" fill={CHART.series} stroke={CHART.seriesStroke} strokeWidth={2} maxBarSize={48} isAnimationActive={false}>
                <LabelList dataKey="value" position="top" style={{ fill: INK, fontSize: 12, fontWeight: 900, fontFamily: 'var(--mono-face)' }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Deals by month" empty={trends.monthly_deal_counts.length === 0} height={280}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={trends.monthly_deal_counts} margin={{ top: 12, right: 16, left: -18, bottom: 0 }}>
              <CartesianGrid stroke={CHART.grid} vertical={false} strokeDasharray="3 3" />
              <XAxis dataKey="date" {...AXIS} tick={TICK} />
              <YAxis {...AXIS} allowDecimals={false} tick={TICK} />
              <Tooltip
                cursor={{ stroke: INK, strokeWidth: 1, strokeDasharray: '4 3' }}
                contentStyle={tooltipStyle}
                itemStyle={tooltipItemStyle}
                labelStyle={tooltipLabelStyle}
              />
              <Line
                type="linear"
                dataKey="count"
                name="Deals"
                stroke={INK}
                strokeWidth={2.5}
                dot={{ r: 5, fill: PINK, stroke: INK, strokeWidth: 2 }}
                activeDot={{ r: 7, fill: PINK, stroke: INK, strokeWidth: 2 }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <section className="comic-card how-card">
          <h3 className="section-title">How it works</h3>
          <ol className="steps">
            {steps.map((text, i) => (
              <li key={i}>
                <span className="step-num">{i + 1}</span>
                <span>{text}</span>
              </li>
            ))}
          </ol>
          <button type="button" className="btn btn-pink" onClick={onOpenDex}>
            Open the map <ArrowRight size={15} />
          </button>
        </section>
      </div>
    </div>
  )
}

function ChartCard({
  title,
  children,
  empty,
  height,
}: {
  title: string
  children: React.ReactNode
  empty?: boolean
  height: number
}) {
  return (
    <section className="comic-card chart-card">
      <h3 className="section-title">{title}</h3>
      <div style={{ height }} className="chart-body">
        {empty ? <div className="chart-empty">Nothing screened yet — scan a startup to fill this in.</div> : children}
      </div>
    </section>
  )
}
