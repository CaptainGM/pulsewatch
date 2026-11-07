import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  CheckCheck,
  CheckCircle2,
  Clock3,
  RefreshCw,
  Server,
  ShieldCheck,
} from 'lucide-react';
import { api } from '../api';
import { useApi, useDocumentTitle } from '../hooks';
import { useApp } from '../context/AppContext';
import StatCard from '../components/StatCard';
import { EmptyState, ErrorPanel } from '../components/States';
import { fmtDateTime, fmtDuration, fmtNumber, timeAgo } from '../utils';

const FILTERS = [
  { value: 'all', label: 'Tümü' },
  { value: 'open', label: 'Açık' },
  { value: 'resolved', label: 'Çözülen' },
];

export default function Incidents() {
  useDocumentTitle('Olaylar');
  const { refreshKey, refreshNow, notify } = useApp();
  const { data, loading, error, reload } = useApi(
    (signal) => api.incidents({ limit: 100 }, signal),
    [refreshKey],
    { pollMs: 30_000 },
  );
  const [filter, setFilter] = useState('all');
  const [ackingId, setAckingId] = useState(null);

  const incidents = data || [];
  const counts = useMemo(
    () => ({
      all: incidents.length,
      open: incidents.filter((incident) => incident.status === 'open').length,
      resolved: incidents.filter((incident) => incident.status === 'resolved').length,
      unacknowledged: incidents.filter(
        (incident) => incident.status === 'open' && !incident.acknowledged,
      ).length,
      monitors: new Set(incidents.map((incident) => incident.monitor_id)).size,
      downtime: incidents.reduce((total, incident) => total + (incident.duration_seconds || 0), 0),
    }),
    [incidents],
  );

  const visible = useMemo(
    () =>
      incidents.filter((incident) => filter === 'all' || incident.status === filter),
    [incidents, filter],
  );

  async function acknowledge(incident) {
    setAckingId(incident.id);
    try {
      await api.acknowledgeIncident(incident.id);
      notify('success', 'Olay onaylandı', `${incident.monitor_name} olayı işaretlendi.`);
      refreshNow();
    } catch (err) {
      notify('error', 'Olay onaylanamadı', err.message);
    } finally {
      setAckingId(null);
    }
  }

  return (
    <div className="page incidents-page">
      <div className="page-head">
        <div>
          <p className="eyebrow">
            <span className="eyebrow-pulse" aria-hidden="true" /> Kesinti günlüğü
          </p>
          <h1 className="page-title">Olaylar</h1>
          <p className="page-sub">
            Alarm eşiği aşıldığında açılan olaylar, süreleri ve toparlanma kayıtları.
          </p>
        </div>
        <div className="page-head-actions">
          <button type="button" className="btn ghost" onClick={reload} disabled={loading}>
            <RefreshCw size={15} className={loading ? 'spin' : ''} /> Yenile
          </button>
        </div>
      </div>

      <div className="stats-grid">
        <StatCard
          icon={<AlertTriangle size={20} />}
          tone="red"
          label="Açık olay"
          value={fmtNumber(counts.open)}
          hint={`${counts.unacknowledged} olay onay bekliyor`}
        />
        <StatCard
          icon={<CheckCircle2 size={20} />}
          tone="mint"
          label="Çözülen olay"
          value={fmtNumber(counts.resolved)}
          hint="Toparlanma tespit edildi"
        />
        <StatCard
          icon={<Clock3 size={20} />}
          tone="blue"
          label="Toplam kesinti"
          value={fmtDuration(counts.downtime)}
          hint="Kayıtlı olayların toplamı"
        />
        <StatCard
          icon={<Server size={20} />}
          tone="mint"
          label="Etkilenen servis"
          value={fmtNumber(counts.monitors)}
          hint={`${incidents.length} toplam kayıt`}
        />
      </div>

      <div className="list-toolbar">
        <div className="filter-pills" role="group" aria-label="Olay durumuna göre filtrele">
          {FILTERS.map((item) => (
            <button
              type="button"
              key={item.value}
              className={`filter-pill ${filter === item.value ? 'active' : ''}`}
              onClick={() => setFilter(item.value)}
            >
              {item.label}
              <span>{counts[item.value]}</span>
            </button>
          ))}
        </div>
        <span className="toolbar-note">
          <ShieldCheck size={14} /> Açık olaylar, servis geri geldiğinde otomatik kapanır.
        </span>
      </div>

      {error && !data ? (
        <ErrorPanel error={error} onRetry={reload} />
      ) : visible.length === 0 && !loading ? (
        <section className="panel">
          <EmptyState
            icon={<ShieldCheck size={27} />}
            title="Kayıtlı olay yok"
            message="Servisleriniz çevrimdışı olduğunda burada bir olay kaydı oluşur. Şu an her şey yolunda."
          />
        </section>
      ) : (
        <section className="panel">
          <header className="section-head">
            <div>
              <h2>Olay geçmişi</h2>
              <p>{visible.length} kayıt · en yeni önce</p>
            </div>
          </header>

          <div className="table-wrap">
            <table className="data-table incidents-table">
              <thead>
                <tr>
                  <th>Servis</th>
                  <th>Durum</th>
                  <th>Neden</th>
                  <th>Başlangıç</th>
                  <th>Süre</th>
                  <th>Hata</th>
                  <th>Onay</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((incident) => (
                  <tr key={incident.id}>
                    <td>
                      <Link to={`/monitors/${incident.monitor_id}`} className="incident-monitor-link">
                        <span className={`service-mark ${incident.status === 'open' ? 'down' : 'up'}`} />
                        <span>
                          <strong>{incident.monitor_name}</strong>
                          <small>Monitör #{incident.monitor_id}</small>
                        </span>
                      </Link>
                    </td>
                    <td>
                      <span className={`incident-state ${incident.status}`}>
                        {incident.status === 'open' ? 'Açık' : 'Çözüldü'}
                      </span>
                    </td>
                    <td className="cause-cell">
                      <strong>{incident.cause}</strong>
                      {incident.last_error && incident.last_error !== incident.cause ? (
                        <span>{incident.last_error}</span>
                      ) : null}
                    </td>
                    <td className="muted-cell" title={fmtDateTime(incident.started_at)}>
                      <span>{fmtDateTime(incident.started_at)}</span>
                      <small>{timeAgo(incident.started_at)}</small>
                    </td>
                    <td className="mono-cell">{fmtDuration(incident.duration_seconds)}</td>
                    <td className="mono-cell">{fmtNumber(incident.failure_count)}</td>
                    <td>
                      {incident.acknowledged ? (
                        <span className="ack-state">
                          <CheckCheck size={13} /> Onaylandı
                        </span>
                      ) : incident.status === 'open' ? (
                        <button
                          type="button"
                          className="btn ghost sm"
                          onClick={() => acknowledge(incident)}
                          disabled={ackingId === incident.id}
                        >
                          {ackingId === incident.id ? 'Onaylanıyor…' : 'Onayla'}
                        </button>
                      ) : (
                        <span className="muted-cell">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
