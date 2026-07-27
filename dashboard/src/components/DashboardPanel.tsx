import { useEffect, useState } from 'react'
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from 'recharts'
import { Layers, FileText, PieChart as PieIcon, TrendingUp } from 'lucide-react'
import { api } from '../api'
import {
  CHART,
  SERIES,
  foldToCap,
  tooltipItemStyle,
  tooltipLabelStyle,
  tooltipStyle,
} from '../theme'

interface Trends {
  sector_distribution: Record<string, number>
  stage_distribution: Record<string, number>
  monthly_deal_counts: Array<{ date: string; count: number }>
}

const STAGE_ORDER = ['pre-seed', 'seed', 'series-a', 'series-b', 'growth']

export default function DashboardPanel() {
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
          api.get('/ingest/documents'),
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
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
        <div className="loading-spinner" />
      </div>
    )
  }

  // Every slice is on screen at once, so this is an all-pairs comparison —
  // fold past the validated cap into a neutral "Other" rather than inventing hues.
  const sectorData = foldToCap(
    Object.entries(trends.sector_distribution).map(([name, value]) => ({ name, value })),
  )

  // Single series across labelled categories: the axis carries identity, so one
  // colour. Painting each bar a different hue is a rainbow, not an encoding.
  const stageData = Object.entries(trends.stage_distribution)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => {
      const ai = STAGE_ORDER.indexOf(a.name.toLowerCase())
      const bi = STAGE_ORDER.indexOf(b.name.toLowerCase())
      return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi)
    })

  const metrics = [
    { label: 'Deals Screened', value: stats.dealsCount, Icon: Layers, color: SERIES[0] },
    { label: 'Ingested Files', value: stats.docsCount, Icon: FileText, color: SERIES[1] },
    { label: 'Investment Memos', value: stats.memosCount, Icon: TrendingUp, color: SERIES[3] },
  ]

  const steps = [
    <>Go to <strong>Document Ingest</strong> and upload a pitch deck PDF or paste a report URL.</>,
    <>The agents extract metrics, retrieve comparable deals, and screen for risk in parallel.</>,
    <>Open <strong>Deal Browser</strong> for the scorecard, or <strong>Investment Memos</strong> for the write-up.</>,
    <>Use <strong>RAG Chat</strong> to interrogate any indexed document directly.</>,
  ]

  return (
    <div>
      <div className="metrics-container">
        {metrics.map(({ label, value, Icon, color }) => (
          <div className="metric-box" key={label}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="metric-label">{label}</span>
              <Icon size={16} color={color} />
            </div>
            <span className="metric-value">{value}</span>
          </div>
        ))}
      </div>

      <div className="dashboard-grid">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', minWidth: 0 }}>
          <div className="chart-section">
            <ChartCard
              title="Industry Sectors"
              icon={<PieIcon size={14} />}
              empty={sectorData.length === 0}
              emptyLabel="No deal data yet."
            >
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={sectorData}
                    cx="50%"
                    cy="46%"
                    innerRadius={52}
                    outerRadius={76}
                    paddingAngle={2}
                    dataKey="value"
                    stroke={CHART.surface}
                    strokeWidth={2}
                    isAnimationActive={false}
                  >
                    {sectorData.map((entry) => (
                      <Cell key={entry.name} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={tooltipStyle} itemStyle={tooltipItemStyle} labelStyle={tooltipLabelStyle} />
                  <Legend verticalAlign="bottom" height={30} iconType="circle" iconSize={8} />
                </PieChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard
              title="Deal Stages"
              icon={<Layers size={14} />}
              empty={stageData.length === 0}
              emptyLabel="No stage data yet."
            >
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={stageData} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                  <CartesianGrid stroke={CHART.grid} vertical={false} />
                  <XAxis dataKey="name" stroke={CHART.axis} fontSize={11} tickLine={false} axisLine={false} />
                  <YAxis stroke={CHART.axis} fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
                  <Tooltip
                    cursor={{ fill: 'rgba(255,255,255,0.04)' }}
                    contentStyle={tooltipStyle}
                    itemStyle={tooltipItemStyle}
                    labelStyle={tooltipLabelStyle}
                  />
                  <Bar dataKey="value" name="Deals" fill={SERIES[0]} radius={[4, 4, 0, 0]} maxBarSize={44} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>

          <ChartCard
            title="Deal Flow Timeline"
            icon={<TrendingUp size={14} />}
            height={260}
            empty={trends.monthly_deal_counts.length === 0}
            emptyLabel="No timeline data yet."
          >
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trends.monthly_deal_counts} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
                <CartesianGrid stroke={CHART.grid} vertical={false} />
                <XAxis dataKey="date" stroke={CHART.axis} fontSize={11} tickLine={false} axisLine={false} />
                <YAxis stroke={CHART.axis} fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
                <Tooltip contentStyle={tooltipStyle} itemStyle={tooltipItemStyle} labelStyle={tooltipLabelStyle} />
                <Line
                  type="monotone"
                  dataKey="count"
                  name="Deals"
                  stroke={SERIES[0]}
                  strokeWidth={2}
                  dot={{ r: 3, fill: SERIES[0], strokeWidth: 0 }}
                  activeDot={{ r: 5, stroke: CHART.surface, strokeWidth: 2 }}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>

        <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <h3
            style={{
              fontSize: '0.73rem',
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              color: 'var(--text-secondary)',
              fontWeight: 600,
            }}
          >
            Getting Started
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', fontSize: '0.85rem' }}>
            {steps.map((text, i) => (
              <div style={{ display: 'flex', gap: '11px' }} key={i}>
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.7rem',
                    color: SERIES[0],
                    border: '1px solid rgba(131,21,249,0.35)',
                    borderRadius: '5px',
                    width: '20px',
                    height: '20px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  {i + 1}
                </span>
                <span style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>{text}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function ChartCard({
  title,
  icon,
  children,
  empty,
  emptyLabel,
  height = 300,
}: {
  title: string
  icon: React.ReactNode
  children: React.ReactNode
  empty?: boolean
  emptyLabel?: string
  height?: number
}) {
  return (
    <div className="glass-card" style={{ height, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
      <h3
        style={{
          marginBottom: '14px',
          display: 'flex',
          alignItems: 'center',
          gap: '7px',
          fontSize: '0.73rem',
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          color: 'var(--text-secondary)',
          fontWeight: 600,
        }}
      >
        {icon} {title}
      </h3>
      <div style={{ flex: 1, minHeight: 0 }}>
        {empty ? (
          <div
            style={{
              height: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--text-muted)',
              fontSize: '0.85rem',
            }}
          >
            {emptyLabel}
          </div>
        ) : (
          children
        )}
      </div>
    </div>
  )
}
