import { useEffect } from 'react';
import { Activity, AlertTriangle, CheckCircle2, Wrench, XCircle } from 'lucide-react';
import { api } from '../api';
import { useApi, useDocumentTitle } from '../hooks';
import Logo from '../components/Logo';
import { ErrorPanel } from '../components/States';
import { fmtDateTime, fmtDuration, fmtMs, fmtPercent, timeAgo } from '../utils';

const OVERALL = {
  operational: { label: 'Tüm sistemler çalışıyor', tone: 'up', Icon: CheckCircle2 },
  degraded: { label: 'Bazı sistemlerde yavaşlık var', tone: 'amber', Icon: AlertTriangle },
  outage: { label: 'Bazı sistemlerde kesinti var', tone: 'down', Icon: XCircle },
  maintenance: { label: 'Planlı bakım devam ediyor', tone: 'blue', Icon: Wrench },
  empty: { label: 'Henüz izlenen servis yok', tone: 'muted', Icon: Activity },
};

const COMPONENT_LABEL = {
  up: 'Çalışıyor',
  degraded: 'Yavaş',
  down: 'Kesinti',
  maintenance: 'Bakımda',
  paused: 'Duraklatıldı',
  unknown: 'Bekliyor',
};

function dayTone(percent) {
  if (percent === null || percent === undefined) return 'empty';
  if (percent >= 99.9) return 'up';
  if (percent >= 99) return 'amber';
  return 'down';
}

function DailyBars({ days = [] }) {
  return (
    <div className="daily-bars" role="img" aria-label="Son 30 günün uptime durumu">
      {days.map((day) => (
        <span
          key={day.day}
          className={`daily-bar ${dayTone(day.uptime_percent)}`}
          title={`${day.day} · ${day.uptime_percent === null ? 'veri yok' : fmtPercent(day.uptime_percent)}`}
        />
      ))}
    </div>
  );
}

export default function StatusPage() {
  useDocumentTitle('Durum Sayfası');
  const site = useApi((signal) => api.site(signal), []);
  useEffect(() => {
    const accent = site.data?.accent_color;
    if (!accent) return undefined;
    document.documentElement.style.setProperty('--mint', accent);
    return () => document.documentElement.style.removeProperty('--mint');
  }, [site.data]);
  const { data, loading, error, reload } = useApi((signal) => api.statusPage(signal), [], {
    pollMs: 60_000,
  });

  if (loading && !data) {
    return (
      <div className="status-shell">
        <p className="status-loading">Durum bilgileri yükleniyor…</p>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="status-shell">
        <ErrorPanel error={error} onRetry={reload} />
      </div>
    );
  }

  const overall = OVERALL[data.overall_status] || OVERALL.empty;
  const OverallIcon = overall.Icon;

  return (
    <div className="status-shell">
      <header className="status-head">
        <div className="login-brand">
          {site.data?.logo_url ? (
            <img className="status-logo" src={site.data.logo_url} alt="" />
          ) : (
            <Logo size={36} />
          )}
          <span>
            <strong>{data.workspace_name}</strong>
            <small>{data.title}</small>
          </span>
        </div>
        <span className="status-updated">Güncellendi {timeAgo(data.generated_at)}</span>
      </header>

      <section className={`status-banner ${overall.tone}`}>
        <span className="status-banner-icon" aria-hidden="true">
          <OverallIcon size={24} />
        </span>
        <div>
          <h1>{overall.label}</h1>
          <p>{data.description}</p>
        </div>
      </section>

      <div className="status-stats">
        <div>
          <span>Uptime · 24 saat</span>
          <strong>{fmtPercent(data.uptime_24h)}</strong>
        </div>
        <div>
          <span>Uptime · 7 gün</span>
          <strong>{fmtPercent(data.uptime_7d)}</strong>
        </div>
        <div>
          <span>Uptime · 30 gün</span>
          <strong>{fmtPercent(data.uptime_30d)}</strong>
        </div>
        <div>
          <span>Ortalama yanıt</span>
          <strong>{fmtMs(data.avg_response_ms)}</strong>
        </div>
      </div>

      <section className="panel status-panel">
        <header className="section-head">
          <div>
            <h2>Servisler</h2>
            <p>
              {data.totals.operational} / {data.totals.monitors} servis sorunsuz çalışıyor
            </p>
          </div>
        </header>

        {data.components.length === 0 ? (
          <div className="mini-empty">Bu sayfada gösterilecek servis yok.</div>
        ) : (
          <ul className="status-components">
            {data.components.map((component) => (
              <li key={component.id} className="status-component">
                <div className="status-component-head">
                  <div>
                    <strong>{component.name}</strong>
                    {component.description ? <span>{component.description}</span> : null}
                  </div>
                  <span className={`status-pill ${component.status}`}>
                    {COMPONENT_LABEL[component.status] || component.status}
                  </span>
                </div>
                <DailyBars days={component.daily} />
                <div className="status-component-foot">
                  <span>30 gün önce</span>
                  <span>{fmtPercent(component.uptime_30d)} uptime</span>
                  <span>Bugün</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="status-columns">
        <section className="panel status-panel">
          <header className="section-head">
            <div>
              <h2>Son olaylar</h2>
              <p>Son 30 günde kaydedilen kesintiler</p>
            </div>
          </header>
          {data.incidents.length === 0 ? (
            <div className="mini-empty">Son dönemde kesinti kaydı yok.</div>
          ) : (
            <ul className="status-list">
              {data.incidents.map((incident) => (
                <li key={incident.id}>
                  <span className={`status-pill ${incident.status === 'open' ? 'down' : 'up'}`}>
                    {incident.status === 'open' ? 'Açık' : 'Çözüldü'}
                  </span>
                  <div className="status-list-copy">
                    <strong>{incident.monitor_name}</strong>
                    <span>{incident.cause}</span>
                  </div>
                  <div className="status-list-meta">
                    <span>{fmtDateTime(incident.started_at)}</span>
                    <span>
                      {incident.duration_seconds ? fmtDuration(incident.duration_seconds) : 'Devam ediyor'}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        {data.maintenance.length > 0 ? (
          <section className="panel status-panel">
            <header className="section-head">
              <div>
                <h2>Planlı bakımlar</h2>
                <p>Aktif ve yaklaşan bakım pencereleri</p>
              </div>
            </header>
            <ul className="status-list">
              {data.maintenance.map((window) => (
                <li key={window.id}>
                  <span className={`status-pill ${window.active ? 'maintenance' : 'unknown'}`}>
                    {window.active ? 'Aktif' : 'Planlı'}
                  </span>
                  <div className="status-list-copy">
                    <strong>{window.title}</strong>
                    <span>{window.monitor_name || 'Tüm servisler'}</span>
                  </div>
                  <div className="status-list-meta">
                    <span>{fmtDateTime(window.starts_at)}</span>
                    <span>{fmtDateTime(window.ends_at)}</span>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>

      <footer className="status-foot">
        <span>PulseWatch ile izleniyor</span>
        {data.support_url ? (
          <a href={data.support_url} target="_blank" rel="noreferrer">
            Destek
          </a>
        ) : null}
        <a href="/api/status-page/feed.xml" target="_blank" rel="noreferrer">Kesinti akışı (RSS)</a>
      </footer>
    </div>
  );
}
