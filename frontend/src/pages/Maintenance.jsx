import { useState } from 'react';
import { CalendarClock, Plus, Trash2 } from 'lucide-react';
import { api } from '../api';
import ConfirmDialog from '../components/ConfirmDialog';
import { DashboardSkeleton, EmptyState, ErrorPanel } from '../components/States';
import { useApi, useDocumentTitle } from '../hooks';
import { useApp } from '../context/AppContext';
import { fmtDateTime } from '../utils';

const EMPTY_FORM = { title: '', monitorId: '', startsAt: '', endsAt: '', description: '' };

function windowState(item, now) {
  const start = new Date(item.starts_at);
  const end = new Date(item.ends_at);
  if (now >= start && now <= end) return { label: 'Devam ediyor', tone: 'maintenance' };
  if (now < start) return { label: 'Planlı', tone: 'unknown' };
  return { label: 'Tamamlandı', tone: 'paused' };
}

export default function Maintenance() {
  useDocumentTitle('Bakım');
  const { notify, isAdmin } = useApp();
  const windows = useApi((signal) => api.maintenance(signal), []);
  const monitors = useApi((signal) => api.monitors(signal), []);
  const [form, setForm] = useState(EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null);

  if (windows.loading && !windows.data) return <DashboardSkeleton />;
  if (windows.error && !windows.data) return <ErrorPanel error={windows.error} onRetry={windows.reload} />;

  const now = new Date();
  const items = windows.data || [];
  const monitorName = (id) => (monitors.data || []).find((item) => item.id === id)?.name;

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function handleCreate(event) {
    event.preventDefault();
    if (new Date(form.endsAt) <= new Date(form.startsAt)) {
      notify('error', 'Tarih aralığı geçersiz', 'Bitiş zamanı başlangıçtan sonra olmalı.');
      return;
    }
    setBusy(true);
    try {
      await api.createMaintenance({
        title: form.title.trim(),
        description: form.description.trim() || null,
        monitor_id: form.monitorId ? Number(form.monitorId) : null,
        starts_at: new Date(form.startsAt).toISOString(),
        ends_at: new Date(form.endsAt).toISOString(),
      });
      notify('success', 'Bakım penceresi eklendi', form.title.trim());
      setForm(EMPTY_FORM);
      windows.reload();
    } catch (err) {
      notify('error', 'Bakım eklenemedi', err.message);
    } finally {
      setBusy(false);
    }
  }

  async function confirmDelete() {
    setBusy(true);
    try {
      await api.deleteMaintenance(pendingDelete.id);
      notify('success', 'Bakım penceresi silindi');
      setPendingDelete(null);
      windows.reload();
    } catch (err) {
      notify('error', 'Silinemedi', err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="eyebrow">Planlı işler</p>
          <h1 className="page-title">Bakım pencereleri</h1>
          <p className="page-sub">
            Bakım süresince ilgili API'ler için kesinti kaydı açılmaz ve bildirim gönderilmez.
          </p>
        </div>
      </div>

      {isAdmin ? (
        <section className="panel form-panel">
          <form onSubmit={handleCreate}>
            <header className="section-head">
              <div>
                <h2>Yeni bakım penceresi</h2>
                <p>Bir API seçin ya da tüm API'ler için tanımlayın.</p>
              </div>
            </header>
            <div className="form-grid">
              <div className="field">
                <label htmlFor="maint-title">Başlık</label>
                <input
                  id="maint-title"
                  required
                  maxLength={160}
                  value={form.title}
                  onChange={(event) => update('title', event.target.value)}
                  placeholder="Veritabanı bakımı"
                />
              </div>
              <div className="field">
                <label htmlFor="maint-monitor">Kapsam</label>
                <select
                  id="maint-monitor"
                  value={form.monitorId}
                  onChange={(event) => update('monitorId', event.target.value)}
                >
                  <option value="">Tüm API'ler</option>
                  {(monitors.data || []).map((monitor) => (
                    <option key={monitor.id} value={monitor.id}>
                      {monitor.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="maint-start">Başlangıç</label>
                <input
                  id="maint-start"
                  type="datetime-local"
                  required
                  value={form.startsAt}
                  onChange={(event) => update('startsAt', event.target.value)}
                />
              </div>
              <div className="field">
                <label htmlFor="maint-end">Bitiş</label>
                <input
                  id="maint-end"
                  type="datetime-local"
                  required
                  value={form.endsAt}
                  onChange={(event) => update('endsAt', event.target.value)}
                />
              </div>
              <div className="field full">
                <label htmlFor="maint-description">Açıklama (isteğe bağlı)</label>
                <input
                  id="maint-description"
                  maxLength={600}
                  value={form.description}
                  onChange={(event) => update('description', event.target.value)}
                />
              </div>
            </div>
            <footer className="modal-actions">
              <button type="submit" className="btn primary" disabled={busy}>
                <Plus size={16} /> {busy ? 'Ekleniyor…' : 'Bakımı ekle'}
              </button>
            </footer>
          </form>
        </section>
      ) : null}

      {items.length === 0 ? (
        <section className="panel">
          <EmptyState
            icon={<CalendarClock size={28} />}
            title="Planlı bakım yok"
            message="Bakım planladığınızda burada görünür ve durum sayfasında yayınlanır."
          />
        </section>
      ) : (
        <section className="panel">
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Başlık</th>
                  <th>Kapsam</th>
                  <th>Başlangıç</th>
                  <th>Bitiş</th>
                  <th>Durum</th>
                  <th aria-label="İşlemler" />
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const state = windowState(item, now);
                  return (
                    <tr key={item.id}>
                      <td>
                        <strong>{item.title}</strong>
                        {item.description ? <span className="muted-cell">{item.description}</span> : null}
                      </td>
                      <td>{item.monitor_id ? monitorName(item.monitor_id) || `#${item.monitor_id}` : 'Tüm API’ler'}</td>
                      <td className="mono-cell">{fmtDateTime(item.starts_at)}</td>
                      <td className="mono-cell">{fmtDateTime(item.ends_at)}</td>
                      <td>
                        <span className={`status-pill ${state.tone}`}>{state.label}</span>
                      </td>
                      <td>
                        {isAdmin ? (
                          <button
                            type="button"
                            className="icon-btn sm danger"
                            aria-label={`${item.title} bakımını sil`}
                            onClick={() => setPendingDelete(item)}
                          >
                            <Trash2 size={14} />
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Bakım penceresini sil"
        message={`"${pendingDelete?.title || ''}" silinecek.`}
        confirmLabel="Sil"
        busy={busy}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}
