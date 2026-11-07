import { useState } from 'react';
import { Plus, Trash2, UserRound } from 'lucide-react';
import { api } from '../api';
import ConfirmDialog from '../components/ConfirmDialog';
import { DashboardSkeleton, EmptyState, ErrorPanel } from '../components/States';
import { useApi, useDocumentTitle } from '../hooks';
import { useApp } from '../context/AppContext';
import { timeAgo } from '../utils';

const EMPTY_FORM = { email: '', name: '', password: '', role: 'viewer' };

export default function Users() {
  useDocumentTitle('Kullanıcılar');
  const { notify, me } = useApp();
  const users = useApi((signal) => api.users(signal), []);
  const [form, setForm] = useState(EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null);

  if (users.loading && !users.data) return <DashboardSkeleton />;
  if (users.error && !users.data) return <ErrorPanel error={users.error} onRetry={users.reload} />;

  const items = users.data || [];

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function handleCreate(event) {
    event.preventDefault();
    setBusy(true);
    try {
      await api.createUser(form);
      notify('success', 'Kullanıcı eklendi', form.email);
      setForm(EMPTY_FORM);
      users.reload();
    } catch (err) {
      notify('error', 'Kullanıcı eklenemedi', err.message);
    } finally {
      setBusy(false);
    }
  }

  async function changeUser(user, payload) {
    try {
      await api.updateUser(user.id, payload);
      users.reload();
    } catch (err) {
      notify('error', 'Değişiklik kaydedilemedi', err.message);
    }
  }

  async function confirmDelete() {
    setBusy(true);
    try {
      await api.deleteUser(pendingDelete.id);
      notify('success', 'Kullanıcı silindi', pendingDelete.email);
      setPendingDelete(null);
      users.reload();
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
          <p className="eyebrow">Erişim</p>
          <h1 className="page-title">Kullanıcılar</h1>
          <p className="page-sub">
            Yönetici her şeyi yapar. Görüntüleyici yalnızca izleme ekranlarını okur ve değişiklik yapamaz.
          </p>
        </div>
      </div>

      <section className="panel form-panel">
        <form onSubmit={handleCreate}>
          <header className="section-head">
            <div>
              <h2>Yeni kullanıcı</h2>
              <p>Şifre en az 8 karakter olmalı. Google ile girecek kullanıcıya şifre gerekmez.</p>
            </div>
          </header>
          <div className="form-grid">
            <div className="field">
              <label htmlFor="user-email">E-posta</label>
              <input
                id="user-email"
                type="email"
                required
                value={form.email}
                onChange={(event) => update('email', event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="user-name">Ad</label>
              <input
                id="user-name"
                required
                maxLength={120}
                value={form.name}
                onChange={(event) => update('name', event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="user-password">Şifre</label>
              <input
                id="user-password"
                type="password"
                minLength={8}
                required
                autoComplete="new-password"
                value={form.password}
                onChange={(event) => update('password', event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="user-role">Rol</label>
              <select id="user-role" value={form.role} onChange={(event) => update('role', event.target.value)}>
                <option value="viewer">Görüntüleyici</option>
                <option value="admin">Yönetici</option>
              </select>
            </div>
          </div>
          <footer className="modal-actions">
            <button type="submit" className="btn primary" disabled={busy}>
              <Plus size={16} /> {busy ? 'Ekleniyor…' : 'Kullanıcı ekle'}
            </button>
          </footer>
        </form>
      </section>

      {items.length === 0 ? (
        <section className="panel">
          <EmptyState icon={<UserRound size={28} />} title="Kullanıcı yok" message="İlk kullanıcıyı yukarıdan ekleyin." />
        </section>
      ) : (
        <section className="panel">
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Kullanıcı</th>
                  <th>Rol</th>
                  <th>Durum</th>
                  <th>Son giriş</th>
                  <th aria-label="İşlemler" />
                </tr>
              </thead>
              <tbody>
                {items.map((user) => {
                  const self = user.email === me?.email;
                  return (
                    <tr key={user.id}>
                      <td>
                        <strong>{user.name}</strong>
                        <span className="muted-cell">
                          {user.email} · {user.auth_provider === 'google' ? 'Google' : 'Şifre'}
                        </span>
                      </td>
                      <td>
                        <select
                          aria-label={`${user.name} rolü`}
                          value={user.role}
                          disabled={self}
                          onChange={(event) => changeUser(user, { role: event.target.value })}
                        >
                          <option value="viewer">Görüntüleyici</option>
                          <option value="admin">Yönetici</option>
                        </select>
                      </td>
                      <td>
                        <label className="switch-row compact">
                          <span className={`switch ${user.active ? 'on' : ''}`}>
                            <input
                              type="checkbox"
                              checked={user.active}
                              disabled={self}
                              aria-label={`${user.name} etkin`}
                              onChange={(event) => changeUser(user, { active: event.target.checked })}
                            />
                            <i />
                          </span>
                        </label>
                      </td>
                      <td className="muted-cell">{user.last_login_at ? timeAgo(user.last_login_at) : 'Hiç girmedi'}</td>
                      <td>
                        <button
                          type="button"
                          className="icon-btn sm danger"
                          disabled={self}
                          aria-label={`${user.name} kullanıcısını sil`}
                          onClick={() => setPendingDelete(user)}
                        >
                          <Trash2 size={14} />
                        </button>
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
        title="Kullanıcıyı sil"
        message={`"${pendingDelete?.email || ''}" silinecek. Bu kullanıcı artık giriş yapamaz.`}
        confirmLabel="Sil"
        busy={busy}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}
