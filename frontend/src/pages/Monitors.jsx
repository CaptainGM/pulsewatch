import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import TransferButtons from '../components/TransferButtons';
import {
  ExternalLink,
  Pause,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Search,
  Server,
  Trash2,
} from 'lucide-react';
import { api } from '../api';
import { useApi, useDocumentTitle } from '../hooks';
import { useApp } from '../context/AppContext';
import { MethodChip, StatusBadge } from '../components/StatusBadge';
import { EmptyState, ErrorPanel } from '../components/States';
import ConfirmDialog from '../components/ConfirmDialog';
import {
  fmtDateTime,
  fmtMs,
  intervalLabel,
  timeAgo,
} from '../utils';

const FILTERS = [
  { value: 'all', label: 'Tümü' },
  { value: 'up', label: 'Çalışan' },
  { value: 'down', label: 'Çevrimdışı' },
  { value: 'paused', label: 'Duraklatılan' },
];

export default function Monitors() {
  useDocumentTitle('API’ler');
  const { refreshKey, refreshNow, openMonitorModal, notify } = useApp();
  const { data, loading, error, reload } = useApi(
    (signal) => api.monitors(signal),
    [refreshKey],
    { pollMs: 30_000 },
  );
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const [checkingId, setCheckingId] = useState(null);
  const [toggleId, setToggleId] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const monitors = data || [];
  const counts = useMemo(
    () => ({
      all: monitors.length,
      up: monitors.filter((monitor) => monitor.active && monitor.status === 'up').length,
      down: monitors.filter((monitor) => monitor.active && monitor.status === 'down').length,
      paused: monitors.filter((monitor) => !monitor.active).length,
    }),
    [monitors],
  );

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return monitors.filter((monitor) => {
      const statusKey = !monitor.active ? 'paused' : monitor.status;
      if (filter !== 'all' && statusKey !== filter) return false;
      if (!needle) return true;
      return (
        monitor.name.toLowerCase().includes(needle) ||
        (monitor.url || '').toLowerCase().includes(needle)
      );
    });
  }, [monitors, filter, query]);

  async function runCheck(monitor) {
    setCheckingId(monitor.id);
    try {
      const result = await api.checkNow(monitor.id);
      notify(
        result.check.success ? 'success' : 'error',
        result.check.success ? `${monitor.name} çalışıyor` : `${monitor.name} yanıt vermiyor`,
        `${result.check.status_code ? `HTTP ${result.check.status_code} · ` : ''}${fmtMs(result.check.response_time_ms)}`,
      );
      refreshNow();
    } catch (err) {
      notify('error', 'Kontrol yapılamadı', err.message);
    } finally {
      setCheckingId(null);
    }
  }

  async function toggleActive(monitor) {
    setToggleId(monitor.id);
    try {
      await api.updateMonitor(monitor.id, { active: !monitor.active });
      notify(
        'success',
        monitor.active ? `${monitor.name} duraklatıldı` : `${monitor.name} yeniden aktif`,
        monitor.active ? 'Otomatik kontroller durduruldu.' : 'Kontroller kaldığı yerden devam edecek.',
      );
      refreshNow();
    } catch (err) {
      notify('error', 'İşlem başarısız', err.message);
    } finally {
      setToggleId(null);
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.deleteMonitor(deleteTarget.id);
      notify('success', 'Monitör silindi', `${deleteTarget.name} ve geçmiş kayıtları kaldırıldı.`);
      setDeleteTarget(null);
      refreshNow();
    } catch (err) {
      notify('error', 'Silinemedi', err.message);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="page monitors-page">
      <div className="page-head">
        <div>
          <p className="eyebrow">
            <span className="eyebrow-pulse" aria-hidden="true" /> Servis envanteri
          </p>
          <h1 className="page-title">API&apos;ler</h1>
          <p className="page-sub">
            Eklediğiniz tüm uç noktaları yönetin, kontrol aralığını değiştirin veya anında test edin.
          </p>
        </div>
        <div className="page-head-actions">
          <TransferButtons onImported={reload} />
          <button type="button" className="btn ghost" onClick={reload} disabled={loading}>
            <RefreshCw size={15} className={loading ? 'spin' : ''} /> Yenile
          </button>
          <button type="button" className="btn primary" onClick={() => openMonitorModal()}>
            <Plus size={16} /> API Ekle
          </button>
        </div>
      </div>

      <div className="list-toolbar">
        <div className="search-field">
          <Search size={16} aria-hidden="true" />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="İsim veya URL ile ara…"
            aria-label="Monitör ara"
          />
        </div>
        <div className="filter-pills" role="group" aria-label="Duruma göre filtrele">
          {FILTERS.map((item) => (
            <button
              key={item.value}
              type="button"
              className={`filter-pill ${filter === item.value ? 'active' : ''}`}
              onClick={() => setFilter(item.value)}
            >
              {item.label}
              <span>{counts[item.value]}</span>
            </button>
          ))}
        </div>
      </div>

      {error && !data ? (
        <ErrorPanel error={error} onRetry={reload} />
      ) : monitors.length === 0 && !loading ? (
        <section className="panel">
          <EmptyState
            icon={<Server size={28} />}
            title="Henüz API eklenmedi"
            message="İzlemek istediğiniz bir health endpoint'i veya genel API adresi ekleyin."
            action={
              <button type="button" className="btn primary" onClick={() => openMonitorModal()}>
                <Plus size={16} /> API Ekle
              </button>
            }
          />
        </section>
      ) : visible.length === 0 ? (
        <section className="panel">
          <EmptyState
            icon={<Search size={26} />}
            title="Eşleşen monitör yok"
            message="Arama terimini değiştirin veya filtreyi sıfırlayın."
            action={
              <button
                type="button"
                className="btn ghost"
                onClick={() => {
                  setQuery('');
                  setFilter('all');
                }}
              >
                Filtreleri temizle
              </button>
            }
          />
        </section>
      ) : (
        <div className="monitor-grid">
          {visible.map((monitor) => (
            <article key={monitor.id} className={`monitor-card panel ${monitor.active ? '' : 'paused'}`}>
              <header className="monitor-card-head">
                <div className="monitor-card-title">
                  <span
                    className={`service-mark ${monitor.active ? monitor.status : 'paused'}`}
                    aria-hidden="true"
                  />
                  <div>
                    <Link to={`/monitors/${monitor.id}`} className="monitor-link">
                      {monitor.name}
                    </Link>
                    {monitor.url ? (
                      <a
                        href={monitor.url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="monitor-url"
                        title={monitor.url}
                      >
                        {monitor.url}
                        <ExternalLink size={11} />
                      </a>
                    ) : (
                      <span className="monitor-url">Heartbeat · dış adres yok</span>
                    )}
                  </div>
                </div>
                <StatusBadge status={monitor.status} active={monitor.active} />
              </header>

              <div className="monitor-metrics">
                <div>
                  <span>Son yanıt</span>
                  <strong>{fmtMs(monitor.last_response_time_ms)}</strong>
                </div>
                <div>
                  <span>Son kod</span>
                  <strong>{monitor.last_status_code ?? '—'}</strong>
                </div>
                <div>
                  <span>Son kontrol</span>
                  <strong title={fmtDateTime(monitor.last_checked_at)}>
                    {monitor.last_checked_at ? timeAgo(monitor.last_checked_at) : '—'}
                  </strong>
                </div>
              </div>

              <div className="monitor-tags">
                {monitor.monitor_type === 'heartbeat' ? (
                  <span className="meta-tag">Heartbeat</span>
                ) : (
                  <>
                    <MethodChip method={monitor.method} />
                    <span className="meta-tag">{(monitor.expected_codes || [200]).join(', ')}</span>
                  </>
                )}
                <span className="meta-tag">{intervalLabel(monitor.interval_seconds)}</span>
                {monitor.webhook_url ? <span className="meta-tag webhook">webhook</span> : null}
              </div>

              <footer className="monitor-card-foot">
                <Link to={`/monitors/${monitor.id}`} className="btn ghost sm">
                  Detay
                </Link>
                <div className="card-icon-actions">
                  <button
                    type="button"
                    className="icon-btn sm"
                    title="Şimdi kontrol et"
                    aria-label="Şimdi kontrol et"
                    onClick={() => runCheck(monitor)}
                    disabled={checkingId === monitor.id}
                  >
                    <RefreshCw size={14} className={checkingId === monitor.id ? 'spin' : ''} />
                  </button>
                  <button
                    type="button"
                    className="icon-btn sm"
                    title={monitor.active ? 'Duraklat' : 'Devam ettir'}
                    aria-label={monitor.active ? 'Duraklat' : 'Devam ettir'}
                    onClick={() => toggleActive(monitor)}
                    disabled={toggleId === monitor.id}
                  >
                    {monitor.active ? <Pause size={14} /> : <Play size={14} />}
                  </button>
                  <button
                    type="button"
                    className="icon-btn sm"
                    title="Düzenle"
                    aria-label="Düzenle"
                    onClick={() => openMonitorModal(monitor)}
                  >
                    <Pencil size={14} />
                  </button>
                  <button
                    type="button"
                    className="icon-btn sm danger"
                    title="Sil"
                    aria-label="Sil"
                    onClick={() => setDeleteTarget(monitor)}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </footer>
            </article>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Monitörü sil?"
        message={
          deleteTarget
            ? `${deleteTarget.name} ve tüm kontrol geçmişi kalıcı olarak silinecek. Bu işlem geri alınamaz.`
            : ''
        }
        confirmLabel="Monitörü sil"
        busy={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
