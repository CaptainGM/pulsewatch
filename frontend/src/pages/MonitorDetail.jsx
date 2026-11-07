import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Clock3,
  ExternalLink,
  Globe2,
  Pause,
  Pencil,
  Play,
  RefreshCw,
  ShieldCheck,
  Trash2,
  XCircle,
  Zap,
} from 'lucide-react';
import { api } from '../api';
import { useApi, useDocumentTitle } from '../hooks';
import { useApp } from '../context/AppContext';
import StatCard from '../components/StatCard';
import WindowCard from '../components/WindowCard';
import { MethodChip, StatusBadge, StatusCode } from '../components/StatusBadge';
import { ResponseAreaChart } from '../components/Charts';
import { EmptyState, ErrorPanel } from '../components/States';
import ConfirmDialog from '../components/ConfirmDialog';
import RegionsCard from '../components/RegionsCard';
import {
  fmtDate,
  fmtDateTime,
  fmtDuration,
  fmtMs,
  fmtNumber,
  fmtPercent,
  intervalLabel,
  statusTone,
  timeAgo,
} from '../utils';

const CODE_LABELS = {
  400: 'Bad Request',
  401: 'Unauthorized',
  403: 'Forbidden',
  404: 'Not Found',
  429: 'Too Many Requests',
  500: 'Internal Server Error',
  502: 'Bad Gateway',
  503: 'Service Unavailable',
  504: 'Gateway Timeout',
};

export default function MonitorDetail() {
  const { monitorId } = useParams();
  const id = Number(monitorId);
  const navigate = useNavigate();
  const { refreshKey, refreshNow, openMonitorModal, notify } = useApp();
  const [limit, setLimit] = useState(50);
  const [checking, setChecking] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const monitorQuery = useApi((signal) => api.monitor(id, signal), [id, refreshKey], {
    pollMs: 30_000,
  });
  const statsQuery = useApi(
    (signal) => api.stats(id, { hours: 24, buckets: 48 }, signal),
    [id, refreshKey],
    { pollMs: 30_000 },
  );
  const checksQuery = useApi(
    (signal) => api.checks(id, { limit }, signal),
    [id, refreshKey, limit],
    { pollMs: 30_000 },
  );
  const incidentsQuery = useApi(
    (signal) => api.incidents({ monitor_id: id, limit: 8 }, signal),
    [id, refreshKey],
    { pollMs: 45_000 },
  );

  const monitor = monitorQuery.data;
  const stats = statsQuery.data;
  const checks = checksQuery.data || [];
  const incidents = incidentsQuery.data || [];

  useDocumentTitle(monitor?.name || 'Monitör detayı');

  async function runCheck() {
    setChecking(true);
    try {
      const result = await api.checkNow(id);
      notify(
        result.check.success ? 'success' : 'error',
        result.check.success ? `${monitor.name} çalışıyor` : `${monitor.name} yanıt vermiyor`,
        `${result.check.status_code ? `HTTP ${result.check.status_code} · ` : ''}${fmtMs(result.check.response_time_ms)}`,
      );
      refreshNow();
    } catch (err) {
      notify('error', 'Kontrol yapılamadı', err.message);
    } finally {
      setChecking(false);
    }
  }

  async function toggleActive() {
    setToggling(true);
    try {
      await api.updateMonitor(id, { active: !monitor.active });
      notify(
        'success',
        monitor.active ? 'İzleme duraklatıldı' : 'İzleme devam ediyor',
        monitor.active ? 'Otomatik kontroller durduruldu.' : 'Bir sonraki kontrol başlatılacak.',
      );
      refreshNow();
    } catch (err) {
      notify('error', 'İşlem başarısız', err.message);
    } finally {
      setToggling(false);
    }
  }

  async function confirmDelete() {
    setDeleting(true);
    try {
      await api.deleteMonitor(id);
      notify('success', 'Monitör silindi', `${monitor.name} ve geçmiş kayıtları kaldırıldı.`);
      navigate('/monitors');
    } catch (err) {
      notify('error', 'Silinemedi', err.message);
      setDeleting(false);
    }
  }

  async function acknowledge(incident) {
    try {
      await api.acknowledgeIncident(incident.id);
      notify('success', 'Olay onaylandı', `${incident.monitor_name} olayı işaretlendi.`);
      refreshNow();
    } catch (err) {
      notify('error', 'Olay onaylanamadı', err.message);
    }
  }

  if (monitorQuery.loading && !monitor) {
    return (
      <div className="page">
        <div className="skeleton skeleton-title" />
        <div className="stats-grid">
          {[0, 1, 2, 3].map((item) => (
            <div key={item} className="skeleton skeleton-stat" />
          ))}
        </div>
        <div className="skeleton skeleton-chart" />
      </div>
    );
  }

  if (monitorQuery.error && !monitor) {
    return (
      <div className="page">
        <Link to="/monitors" className="back-link">
          <ArrowLeft size={15} /> API&apos;ler
        </Link>
        <ErrorPanel
          error={monitorQuery.error}
          onRetry={monitorQuery.reload}
          title="Monitör yüklenemedi"
        />
      </div>
    );
  }

  if (!monitor) return null;

  const recentChecks = checks.slice(0, 30).reverse();
  const errorMap = new Map((stats?.status_counts || []).map((item) => [item.code, item]));
  const extraCodes = (stats?.status_counts || [])
    .filter((item) => item.code >= 400 && ![500, 404, 503].includes(item.code))
    .map((item) => item.code)
    .slice(0, 3);
  const codeRows = [...new Set([500, 404, 503, ...extraCodes])].map(
    (code) => errorMap.get(code) || { code, count: 0, percent: 0 },
  );
  const maxCodeCount = Math.max(...codeRows.map((row) => row.count), 1);
  const classes = stats?.class_counts || {};

  return (
    <div className="page detail-page">
      <Link to="/monitors" className="back-link">
        <ArrowLeft size={15} /> Tüm API&apos;ler
      </Link>

      <div className="detail-head">
        <div className="detail-title">
          <div className="detail-title-row">
            <span
              className={`service-mark xl ${monitor.active ? monitor.status : 'paused'}`}
              aria-hidden="true"
            />
            <h1>{monitor.name}</h1>
            <StatusBadge status={monitor.status} active={monitor.active} />
          </div>
          <a
            className="detail-url"
            href={monitor.url}
            target="_blank"
            rel="noreferrer noopener"
          >
            <Globe2 size={14} />
            {monitor.url}
            <ExternalLink size={12} />
          </a>
          <div className="detail-meta">
            <MethodChip method={monitor.method} />
            <span>
              <Clock3 size={13} /> Her {intervalLabel(monitor.interval_seconds)}
            </span>
            <span>Timeout {monitor.timeout_seconds} sn</span>
            <span>Beklenen: {(monitor.expected_codes || [200]).join(', ')}</span>
          </div>
        </div>

        <div className="page-head-actions detail-actions">
          <button type="button" className="btn primary" onClick={runCheck} disabled={checking}>
            <RefreshCw size={15} className={checking ? 'spin' : ''} /> Şimdi kontrol et
          </button>
          <button type="button" className="btn ghost" onClick={() => openMonitorModal(monitor)}>
            <Pencil size={15} /> Düzenle
          </button>
          <button
            type="button"
            className="btn ghost"
            onClick={toggleActive}
            disabled={toggling}
          >
            {monitor.active ? <Pause size={15} /> : <Play size={15} />}
            {monitor.active ? 'Duraklat' : 'Devam ettir'}
          </button>
          <button
            type="button"
            className="btn ghost danger"
            onClick={() => setDeleteOpen(true)}
            aria-label="Monitörü sil"
          >
            <Trash2 size={15} />
          </button>
        </div>
      </div>

      <div className="stats-grid">
        <StatCard
          icon={<ShieldCheck size={20} />}
          tone="mint"
          label="Uptime · 24 saat"
          value={fmtPercent(stats?.uptime_percent)}
          hint={`${fmtNumber(stats?.success_count || 0)} başarılı / ${fmtNumber(stats?.total_checks || 0)} kontrol`}
        />
        <StatCard
          icon={<Zap size={20} />}
          tone="blue"
          label="Ortalama yanıt"
          value={fmtMs(stats?.avg_response_ms)}
          hint={`Son: ${fmtMs(monitor.last_response_time_ms)}`}
        />
        <StatCard
          icon={<Clock3 size={20} />}
          tone="mint"
          label="P95 yanıt süresi"
          value={fmtMs(stats?.p95_response_ms)}
          hint={`Min ${fmtMs(stats?.min_response_ms)} · Maks ${fmtMs(stats?.max_response_ms)}`}
        />
        <StatCard
          icon={<AlertTriangle size={20} />}
          tone="red"
          label="Hata · 24 saat"
          value={fmtNumber(stats?.error_count || 0)}
          hint={`${fmtPercent(stats?.error_rate_percent)} hata oranı`}
        />
      </div>

      {statsQuery.error ? (
        <div className="inline-warning">
          <AlertTriangle size={16} />
          İstatistikler yüklenemedi: {statsQuery.error.message}
          <button type="button" className="link-button" onClick={statsQuery.reload}>
            Tekrar dene
          </button>
        </div>
      ) : null}

      <WindowCard
        title="Yanıt Süresi"
        className="detail-response-card"
        right={
          <span className="card-metric">
            <Zap size={13} /> {fmtMs(stats?.avg_response_ms)}
          </span>
        }
      >
        <div className="card-subhead">
          <span>Son 24 saat · {stats?.buckets ?? 48} dilim</span>
          <span>P95 {fmtMs(stats?.p95_response_ms)}</span>
        </div>
        <ResponseAreaChart series={stats?.series || []} height={252} />
        <div className="card-footline">
          <span>{fmtNumber(stats?.total_checks || 0)} kontrol</span>
          <span>
            {stats?.last_check ? `Son ölçüm ${timeAgo(stats.last_check.checked_at)}` : 'Henüz veri yok'}
          </span>
        </div>
      </WindowCard>

      <div className="detail-split">
        <WindowCard title="Uptime Durumu">
          <div className="card-subhead">
            <span>Son 30 kontrol · en yeni sağda</span>
            <span>{fmtPercent(stats?.uptime_percent)}</span>
          </div>
          <div className="uptime-dots large" role="img" aria-label="Son 30 kontrolün durumu">
            {recentChecks.length === 0 ? (
              <span className="chart-empty-note inline">Henüz kontrol kaydı yok.</span>
            ) : (
              recentChecks.map((check) => (
                <span
                  key={check.id}
                  className={`uptime-dot ${check.success ? 'up' : 'down'}`}
                  title={`${fmtDateTime(check.checked_at)} · ${check.status_code ?? 'Ağ hatası'} · ${fmtMs(check.response_time_ms)}`}
                />
              ))
            )}
          </div>
          <div className="uptime-score compact">
            <strong>{fmtPercent(stats?.uptime_percent)}</strong>
            <span>son 24 saat</span>
          </div>
          <div className="uptime-footline">
            <span className="text-success">
              <CheckCircle2 size={13} /> {fmtNumber(stats?.success_count || 0)} başarılı
            </span>
            <span className="text-danger">
              <XCircle size={13} /> {fmtNumber(stats?.error_count || 0)} başarısız
            </span>
          </div>
        </WindowCard>

        <WindowCard title="HTTP Durum Kodları">
          <div className="card-subhead">
            <span>Hata kodlarının oranı</span>
            <span>24 saat</span>
          </div>
          <div className="code-breakdown">
            {codeRows.map((row) => {
              const tone = statusTone(row.code);
              return (
                <div className="code-row" key={row.code}>
                  <span className={`code-chip ${tone}`}>{row.code}</span>
                  <div className="code-row-main">
                    <div className="code-row-top">
                      <strong>{CODE_LABELS[row.code] || 'HTTP hatası'}</strong>
                      <span>
                        {fmtNumber(row.count)} · {fmtPercent(row.percent)}
                      </span>
                    </div>
                    <div className="bar-track">
                      <i
                        className={`bar-fill ${tone}`}
                        style={{ width: `${Math.max(row.count ? 3 : 0, (row.count / maxCodeCount) * 100)}%` }}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="class-counts">
            <span><i className="legend-swatch green" /> 2xx <strong>{fmtNumber(classes['2xx'] || 0)}</strong></span>
            <span><i className="legend-swatch amber" /> 4xx <strong>{fmtNumber(classes['4xx'] || 0)}</strong></span>
            <span><i className="legend-swatch red" /> 5xx <strong>{fmtNumber(classes['5xx'] || 0)}</strong></span>
            <span><i className="legend-swatch violet" /> Ağ <strong>{fmtNumber(classes.net || 0)}</strong></span>
          </div>
        </WindowCard>
      </div>

      <RegionsCard monitorId={id} />

      <section className="panel checks-panel">
        <header className="section-head">
          <div>
            <h2>Kontrol geçmişi</h2>
            <p>En yeni kontrol en üstte · {checks.length} kayıt gösteriliyor</p>
          </div>
          <button
            type="button"
            className="btn ghost sm"
            onClick={checksQuery.reload}
            disabled={checksQuery.loading}
          >
            <RefreshCw size={14} className={checksQuery.loading ? 'spin' : ''} /> Yenile
          </button>
        </header>

        {checksQuery.error && checks.length === 0 ? (
          <ErrorPanel error={checksQuery.error} onRetry={checksQuery.reload} />
        ) : checks.length === 0 && !checksQuery.loading ? (
          <EmptyState
            icon={<Clock3 size={24} />}
            title="Kontrol kaydı yok"
            message="İlk kontrol tamamlandığında sonuçlar burada listelenecek."
            action={
              <button type="button" className="btn primary sm" onClick={runCheck}>
                <RefreshCw size={14} /> Şimdi kontrol et
              </button>
            }
          />
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table checks-table">
                <thead>
                  <tr>
                    <th>Zaman</th>
                    <th>Sonuç</th>
                    <th>Kod</th>
                    <th>Yanıt süresi</th>
                    <th>Detay</th>
                  </tr>
                </thead>
                <tbody>
                  {checks.map((check) => (
                    <tr key={check.id}>
                      <td className="muted-cell" title={fmtDateTime(check.checked_at)}>
                        {fmtDateTime(check.checked_at)}
                      </td>
                      <td>
                        <span className={`result-pill ${check.success ? 'success' : 'failure'}`}>
                          {check.success ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
                          {check.success ? 'Başarılı' : 'Başarısız'}
                        </span>
                      </td>
                      <td>
                        <StatusCode code={check.status_code} />
                      </td>
                      <td className="mono-cell">{fmtMs(check.response_time_ms)}</td>
                      <td className="error-cell" title={check.error || ''}>
                        {check.error || (check.success ? 'Beklenen yanıt alındı' : '—')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {checks.length >= limit && limit < 200 ? (
              <div className="load-more-row">
                <button
                  type="button"
                  className="btn ghost sm"
                  onClick={() => setLimit((value) => Math.min(200, value + 50))}
                >
                  Daha fazla göster
                </button>
              </div>
            ) : null}
          </>
        )}
      </section>

      <div className="detail-bottom-grid">
        <section className="panel">
          <header className="section-head">
            <div>
              <h2>Olaylar</h2>
              <p>Bu monitöre ait kesinti kayıtları</p>
            </div>
            <Link to="/incidents" className="link-button">
              Tüm olaylar
            </Link>
          </header>
          {incidents.length === 0 ? (
            <div className="mini-empty">
              <ShieldCheck size={22} />
              <span>Bu monitör için kayıtlı olay yok.</span>
            </div>
          ) : (
            <div className="incident-list">
              {incidents.map((incident) => (
                <div className={`incident-row static ${incident.status}`} key={incident.id}>
                  <span className={`incident-icon ${incident.status}`} aria-hidden="true">
                    {incident.status === 'open' ? (
                      <AlertTriangle size={16} />
                    ) : (
                      <ShieldCheck size={16} />
                    )}
                  </span>
                  <span className="incident-copy">
                    <strong>{incident.cause}</strong>
                    <span>
                      {fmtDateTime(incident.started_at)} · {incident.failure_count} hata ·{' '}
                      {fmtDuration(incident.duration_seconds)}
                    </span>
                  </span>
                  <span className={`incident-state ${incident.status}`}>
                    {incident.status === 'open' ? 'Açık' : 'Çözüldü'}
                  </span>
                  {incident.status === 'open' && !incident.acknowledged ? (
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => acknowledge(incident)}
                    >
                      Onayla
                    </button>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="panel config-panel">
          <header className="section-head">
            <div>
              <h2>Yapılandırma</h2>
              <p>Monitör ayarları</p>
            </div>
            <button
              type="button"
              className="link-button"
              onClick={() => openMonitorModal(monitor)}
            >
              <Pencil size={13} /> Düzenle
            </button>
          </header>
          <dl className="config-list">
            <div>
              <dt>Kontrol aralığı</dt>
              <dd>{intervalLabel(monitor.interval_seconds)}</dd>
            </div>
            <div>
              <dt>Zaman aşımı</dt>
              <dd>{monitor.timeout_seconds} saniye</dd>
            </div>
            <div>
              <dt>Beklenen kodlar</dt>
              <dd>{(monitor.expected_codes || [200]).join(', ')}</dd>
            </div>
            <div>
              <dt>Alarm eşiği</dt>
              <dd>{monitor.alert_after_failures} ardışık hata</dd>
            </div>
            <div>
              <dt>Webhook</dt>
              <dd className="truncate" title={monitor.webhook_url || ''}>
                {monitor.webhook_url || 'Tanımlı değil'}
              </dd>
            </div>
            <div>
              <dt>Oluşturuldu</dt>
              <dd>{fmtDate(monitor.created_at)}</dd>
            </div>
            <div>
              <dt>Son güncelleme</dt>
              <dd>{timeAgo(monitor.updated_at)}</dd>
            </div>
          </dl>
          {monitor.last_error ? (
            <div className="last-error">
              <strong>Son hata</strong>
              <span>{monitor.last_error}</span>
            </div>
          ) : null}
        </section>
      </div>

      <ConfirmDialog
        open={deleteOpen}
        title="Monitörü sil?"
        message={`${monitor.name} ve tüm kontrol geçmişi kalıcı olarak silinecek. Bu işlem geri alınamaz.`}
        confirmLabel="Monitörü sil"
        busy={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteOpen(false)}
      />
    </div>
  );
}
