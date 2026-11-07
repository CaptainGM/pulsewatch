import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Clock3,
  Plus,
  RefreshCw,
  Server,
  ShieldCheck,
  Zap,
} from 'lucide-react';
import { api } from '../api';
import { useApi } from '../hooks';
import { useApp } from '../context/AppContext';
import WindowCard from '../components/WindowCard';
import StatCard from '../components/StatCard';
import { StatusBadge } from '../components/StatusBadge';
import Sparkline from '../components/Sparkline';
import { ErrorBarsChart, ResponseAreaChart } from '../components/Charts';
import {
  DashboardSkeleton,
  EmptyState,
  ErrorPanel,
} from '../components/States';
import {
  fmtDateTime,
  fmtDuration,
  fmtMs,
  fmtNumber,
  fmtPercent,
  fmtTime,
  timeAgo,
  uptimeTone,
} from '../utils';

const FOCUS_CODES = [
  { code: 500, label: 'Sunucu hatası', tone: 'red' },
  { code: 503, label: 'Servis kullanılamıyor', tone: 'red' },
  { code: 404, label: 'Bulunamadı', tone: 'amber' },
];

function CodeTile({ code, label, tone, count, percent, share }) {
  return (
    <div className={`code-tile ${tone}`}>
      <div className="code-tile-head">
        <strong>{code}</strong>
        <span>{label}</span>
      </div>
      <div className="code-tile-count">{fmtNumber(count)}</div>
      <div className="code-tile-bar" aria-hidden="true">
        <i style={{ width: `${Math.min(100, share)}%` }} />
      </div>
      <div className="code-tile-foot">
        <span>{percent === null ? '—' : fmtPercent(percent)} kontrol</span>
        <span>{Math.round(share)}% hata</span>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { refreshKey, refresh, openMonitorModal, notify } = useApp();
  const { data, loading, error, reload } = useApi(
    (signal) => api.dashboard(signal),
    [refreshKey],
    { pollMs: 30_000 },
  );
  const [checkingId, setCheckingId] = useState(null);
  const navigate = useNavigate();

  async function runCheck(monitor) {
    setCheckingId(monitor.id);
    try {
      const result = await api.checkNow(monitor.id);
      notify(
        result.check.success ? 'success' : 'error',
        result.check.success ? `${monitor.name} çalışıyor` : `${monitor.name} yanıt vermiyor`,
        `${result.check.status_code ? `HTTP ${result.check.status_code} · ` : ''}${fmtMs(result.check.response_time_ms)}`,
      );
      refresh();
    } catch (err) {
      notify('error', 'Kontrol yapılamadı', err.message);
    } finally {
      setCheckingId(null);
    }
  }

  if (loading && !data) return <DashboardSkeleton />;
  if (error && !data) {
    return <ErrorPanel error={error} onRetry={reload} />;
  }

  const dashboard = data;
  const totals = dashboard.totals;
  const activeCount = totals.monitors - totals.paused;
  const series = dashboard.series || [];
  const errorHours = series.filter((point) => (point.errors || 0) > 0).length;

  const statusCounts = dashboard.status_counts || [];
  const checkTotal = totals.checks || 0;
  const errorTotal = totals.errors || 0;
  const countOf = (code) => statusCounts.find((item) => item.code === code)?.count || 0;
  const otherHttpErrors = statusCounts
    .filter((item) => item.code >= 400 && !FOCUS_CODES.some((focus) => focus.code === item.code))
    .reduce((sum, item) => sum + item.count, 0);
  const codeTiles = [
    ...FOCUS_CODES.map((focus) => ({
      key: String(focus.code),
      code: String(focus.code),
      label: focus.label,
      tone: focus.tone,
      count: countOf(focus.code),
    })),
    { key: 'other', code: '4xx/5xx', label: 'Diğer HTTP hataları', tone: 'blue', count: otherHttpErrors },
    {
      key: 'net',
      code: 'Ağ',
      label: 'Zaman aşımı, bağlantı',
      tone: 'violet',
      count: dashboard.class_counts?.net || 0,
    },
  ].map((tile) => ({
    ...tile,
    percent: checkTotal ? (tile.count / checkTotal) * 100 : null,
    share: errorTotal ? (tile.count / errorTotal) * 100 : 0,
  }));

  return (
    <div className="page dashboard-page">
      <div className="page-head">
        <div>
          <p className="eyebrow">
            <span className="eyebrow-pulse" aria-hidden="true" /> Canlı sistem özeti
          </p>
          <h1 className="page-title">Sistem Durumu</h1>
          <p className="page-sub">
            Tüm servislerin son 24 saatteki erişilebilirliği, yanıt süresi ve hata eğilimleri.
          </p>
        </div>
        <div className="page-head-actions">
          <span className="range-chip">
            <Clock3 size={14} /> Son 24 saat
          </span>
          <button type="button" className="btn ghost" onClick={reload} disabled={loading}>
            <RefreshCw size={15} className={loading ? 'spin' : ''} /> Yenile
          </button>
        </div>
      </div>

      <div className="ticker" role="status">
        <span className="ticker-dot" aria-hidden="true" />
        <span>{totals.up}/{activeCount} servis çalışıyor</span>
        <span>{totals.down} kesinti</span>
        <span>{fmtPercent(dashboard.uptime_percent)} uptime</span>
        <span>{totals.errors} hata · 24 sa</span>
        <span>son güncelleme {fmtTime(dashboard.generated_at)}</span>
      </div>

      <div className="stats-grid">
        <StatCard
          icon={<Server size={20} />}
          tone="mint"
          label="Çalışan API"
          value={`${totals.up}/${Math.max(activeCount, 0)}`}
          hint={`${totals.down} çevrimdışı · ${totals.paused} duraklatıldı`}
        />
        <StatCard
          icon={<Zap size={20} />}
          tone="blue"
          label="Ortalama yanıt"
          value={fmtMs(dashboard.avg_response_ms)}
          hint={`P95: ${fmtMs(dashboard.p95_response_ms)}`}
        />
        <StatCard
          icon={<ShieldCheck size={20} />}
          tone="mint"
          label="Uptime · 24 saat"
          value={fmtPercent(dashboard.uptime_percent)}
          hint={`${fmtNumber(totals.checks)} kontrol yapıldı`}
        />
        <StatCard
          icon={<AlertTriangle size={20} />}
          tone="red"
          label="Hata · 24 saat"
          value={fmtNumber(totals.errors)}
          hint={`${fmtPercent(dashboard.error_rate_percent)} hata oranı · ${errorHours} saat`}
        />
      </div>

      {totals.monitors === 0 ? (
        <section className="panel empty-dashboard-panel">
          <EmptyState
            icon={<Activity size={28} />}
            title="Henüz izlenen bir API yok"
            message="İlk API adresinizi ekleyin; PulseWatch belirli aralıklarla kontrol edip uptime, yanıt süresi ve hataları burada gösterecek."
            action={
              <button type="button" className="btn primary" onClick={() => openMonitorModal()}>
                <Plus size={16} /> İlk API'yi ekle
              </button>
            }
          />
        </section>
      ) : (
        <>
          <div className="hero-grid">
            <WindowCard
              title="Yanıt Süresi"
              right={
                <span className="card-metric">
                  <Zap size={13} /> {fmtMs(dashboard.avg_response_ms)}
                </span>
              }
            >
              <div className="card-subhead">
                <span>Saatlik ortalama</span>
                <span>P95 {fmtMs(dashboard.p95_response_ms)}</span>
              </div>
              <ResponseAreaChart series={series} height={206} />
              <div className="card-footline">
                <span>Son 24 saat</span>
                <span>En düşük / en yüksek değerler saatlik ortalamadır.</span>
              </div>
            </WindowCard>

            <WindowCard
              title="Uptime Durumu"
              right={<span className="window-signal up"><i /><i /><i /></span>}
            >
              <div className="uptime-legend">
                <span>
                  <i className="legend-dot up" /> çalışıyor
                </span>
                <span>
                  <i className="legend-dot down" /> kesinti
                </span>
              </div>
              <div className="uptime-dots" role="img" aria-label="Son 24 saatin saatlik uptime durumu">
                {series.map((point) => {
                  const tone = point.checks === 0 ? 'empty' : point.errors > 0 ? 'down' : 'up';
                  return (
                    <span
                      key={point.start}
                      className={`uptime-dot ${tone}`}
                      title={`${fmtDateTime(point.start)} · ${fmtPercent(point.uptime_percent)} uptime · ${point.checks} kontrol`}
                    />
                  );
                })}
              </div>
              <div className="uptime-score">
                <strong>{fmtPercent(dashboard.uptime_percent)}</strong>
                <span>son 24 saat uptime</span>
              </div>
              <div className="uptime-footline">
                <span>{fmtNumber(totals.checks)} kontrol</span>
                <span className={totals.errors > 0 ? 'text-danger' : 'text-success'}>
                  {fmtNumber(totals.errors)} hata
                </span>
              </div>
            </WindowCard>

            <WindowCard
              title="Hata Oranı"
              right={
                <span className="card-metric danger">
                  <AlertTriangle size={13} /> {fmtPercent(dashboard.error_rate_percent)}
                </span>
              }
            >
              <div className="card-subhead">
                <span>4xx · 5xx · ağ hataları</span>
                <span>{fmtNumber(totals.errors)} hata</span>
              </div>
              <ErrorBarsChart series={series} height={206} />
              <div className="bar-legend">
                <span>
                  <i className="legend-swatch amber" /> 4xx
                </span>
                <span>
                  <i className="legend-swatch red" /> 5xx
                </span>
                <span>
                  <i className="legend-swatch violet" /> ağ
                </span>
                <span className="bar-legend-total">
                  2xx: {fmtNumber(dashboard.class_counts?.['2xx'] || 0)}
                </span>
              </div>
            </WindowCard>
          </div>

          <section className="panel status-code-panel">
            <header className="section-head">
              <div>
                <h2>HTTP hata kodları</h2>
                <p>Son 24 saatteki {fmtNumber(checkTotal)} kontrolde görülen durum kodları</p>
              </div>
            </header>
            <div className="status-code-grid">
              {codeTiles.map(({ key, ...tile }) => (
                <CodeTile key={key} {...tile} />
              ))}
            </div>
          </section>

          <div className="lower-grid">
            <section className="panel">
              <header className="section-head">
                <div>
                  <h2>İzlenen API&apos;ler</h2>
                  <p>{totals.monitors} monitör · canlı durum ve 24 saatlik özet</p>
                </div>
                <Link to="/monitors" className="link-button">
                  Tümünü gör <ArrowRight size={14} />
                </Link>
              </header>

              <div className="table-wrap">
                <table className="data-table dashboard-table">
                  <thead>
                    <tr>
                      <th>Servis</th>
                      <th>Durum</th>
                      <th>Yanıt</th>
                      <th>Uptime</th>
                      <th>Hata</th>
                      <th>Trend</th>
                      <th>Son kontrol</th>
                      <th aria-label="İşlemler" />
                    </tr>
                  </thead>
                  <tbody>
                    {dashboard.monitors.slice(0, 7).map((monitor) => (
                      <tr
                        key={monitor.id}
                        className="clickable-row"
                        onClick={() => navigate(`/monitors/${monitor.id}`)}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter') navigate(`/monitors/${monitor.id}`);
                        }}
                        tabIndex={0}
                      >
                        <td>
                          <div className="monitor-name-cell">
                            <span className={`service-mark ${monitor.status}`} aria-hidden="true" />
                            <div>
                              <strong>{monitor.name}</strong>
                              <span className="truncate" title={monitor.url}>
                                {monitor.url}
                              </span>
                            </div>
                          </div>
                        </td>
                        <td>
                          <StatusBadge status={monitor.status} active={monitor.active} />
                        </td>
                        <td className="mono-cell">{fmtMs(monitor.last_response_time_ms)}</td>
                        <td>
                          <span className={`metric-inline ${monitor.uptime_percent !== null && monitor.uptime_percent < 99 ? 'warn' : ''}`}>
                            {fmtPercent(monitor.uptime_percent, 2)}
                          </span>
                        </td>
                        <td className={monitor.error_count > 0 ? 'text-danger mono-cell' : 'mono-cell'}>
                          {fmtNumber(monitor.error_count)}
                        </td>
                        <td className="spark-cell">
                          <Sparkline
                            values={monitor.sparkline}
                            color={monitor.status === 'down' ? '#ff5d6c' : '#3ce7b0'}
                          />
                        </td>
                        <td className="muted-cell" title={fmtDateTime(monitor.last_checked_at)}>
                          {monitor.last_checked_at ? timeAgo(monitor.last_checked_at) : '—'}
                        </td>
                        <td>
                          <button
                            type="button"
                            className="icon-btn sm"
                            title="Şimdi kontrol et"
                            aria-label={`${monitor.name} için şimdi kontrol et`}
                            disabled={checkingId === monitor.id}
                            onClick={(event) => {
                              event.stopPropagation();
                              runCheck(monitor);
                            }}
                          >
                            <RefreshCw
                              size={14}
                              className={checkingId === monitor.id ? 'spin' : ''}
                            />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <aside className="panel incidents-panel">
              <header className="section-head">
                <div>
                  <h2>Son olaylar</h2>
                  <p>Kesinti ve toparlanma kayıtları</p>
                </div>
                <Link to="/incidents" className="link-button">
                  Tümü <ArrowRight size={14} />
                </Link>
              </header>

              {dashboard.recent_incidents.length === 0 ? (
                <div className="mini-empty">
                  <ShieldCheck size={22} />
                  <span>Kayıtlı olay yok. Her şey yolunda görünüyor.</span>
                </div>
              ) : (
                <div className="incident-list">
                  {dashboard.recent_incidents.map((incident) => (
                    <button
                      type="button"
                      key={incident.id}
                      className={`incident-row ${incident.status}`}
                      onClick={() => navigate(`/monitors/${incident.monitor_id}`)}
                    >
                      <span className={`incident-icon ${incident.status}`} aria-hidden="true">
                        {incident.status === 'open' ? (
                          <AlertTriangle size={16} />
                        ) : (
                          <ShieldCheck size={16} />
                        )}
                      </span>
                      <span className="incident-copy">
                        <strong>{incident.monitor_name}</strong>
                        <span className="truncate">{incident.cause}</span>
                      </span>
                      <span className="incident-meta">
                        <strong>
                          {incident.status === 'open'
                            ? 'Açık'
                            : fmtDuration(incident.duration_seconds)}
                        </strong>
                        <span>{timeAgo(incident.started_at)}</span>
                      </span>
                    </button>
                  ))}
                </div>
              )}

              <div className="panel-footnote">
                <Clock3 size={13} /> Bildirimler alarm eşiği aşıldığında oluşturulur.
              </div>
            </aside>
          </div>
        </>
      )}
    </div>
  );
}
