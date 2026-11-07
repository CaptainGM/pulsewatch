import { useState } from 'react';
import { Bell, Pencil, Plus, Send, Trash2 } from 'lucide-react';
import { api } from '../api';
import { useApi, useDocumentTitle } from '../hooks';
import { useApp } from '../context/AppContext';
import ConfirmDialog from '../components/ConfirmDialog';
import { DashboardSkeleton, EmptyState, ErrorPanel } from '../components/States';
import { timeAgo } from '../utils';

const KINDS = [
  { value: 'slack', label: 'Slack' },
  { value: 'discord', label: 'Discord' },
  { value: 'telegram', label: 'Telegram' },
  { value: 'webhook', label: 'Genel webhook' },
];

const EMPTY_FORM = {
  id: null,
  name: '',
  kind: 'slack',
  enabled: true,
  webhook_url: '',
  bot_token: '',
  chat_id: '',
  url: '',
  secret: '',
};

const STATUS_TAGS = {
  sent: { tone: 'up', label: 'Son gönderim başarılı' },
  failed: { tone: 'down', label: 'Son gönderim başarısız' },
  unknown: { tone: 'unknown', label: 'Henüz denenmedi' },
};

function kindLabel(kind) {
  return KINDS.find((item) => item.value === kind)?.label || kind;
}

function formFromChannel(channel) {
  const config = channel.config || {};
  return {
    id: channel.id,
    name: channel.name,
    kind: channel.kind,
    enabled: channel.enabled,
    webhook_url: config.webhook_url || '',
    bot_token: config.bot_token || '',
    chat_id: config.chat_id || '',
    url: config.url || '',
    secret: config.secret || '',
  };
}

function configFromForm(form) {
  if (form.kind === 'telegram') {
    return { bot_token: form.bot_token.trim(), chat_id: form.chat_id.trim() };
  }
  if (form.kind === 'webhook') {
    const config = { url: form.url.trim() };
    if (form.secret.trim()) config.secret = form.secret.trim();
    return config;
  }
  return { webhook_url: form.webhook_url.trim() };
}

export default function Channels() {
  useDocumentTitle('Bildirim Kanalları');
  const { notify } = useApp();
  const { data, loading, error, reload } = useApi((signal) => api.channels(signal), []);
  const [form, setForm] = useState(null);
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState(false);
  const [testingId, setTestingId] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null);

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function openNew() {
    setFormError('');
    setForm({ ...EMPTY_FORM });
  }

  function openEdit(channel) {
    setFormError('');
    setForm(formFromChannel(channel));
  }

  async function handleSave(event) {
    event.preventDefault();
    setBusy(true);
    setFormError('');
    const payload = {
      name: form.name.trim(),
      kind: form.kind,
      enabled: form.enabled,
      config: configFromForm(form),
    };
    try {
      if (form.id) {
        await api.updateChannel(form.id, payload);
      } else {
        await api.createChannel(payload);
      }
      notify('success', form.id ? 'Kanal güncellendi' : 'Kanal eklendi', payload.name);
      setForm(null);
      reload();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleTest(channel) {
    setTestingId(channel.id);
    try {
      const result = await api.testChannel(channel.id);
      notify(
        result.success ? 'success' : 'error',
        result.success ? `${channel.name} çalışıyor` : `${channel.name} gönderilemedi`,
        result.message,
      );
      reload();
    } catch (err) {
      notify('error', 'Test gönderilemedi', err.message);
    } finally {
      setTestingId(null);
    }
  }

  async function toggleEnabled(channel) {
    try {
      await api.updateChannel(channel.id, { enabled: !channel.enabled });
      reload();
    } catch (err) {
      notify('error', 'Kanal güncellenemedi', err.message);
    }
  }

  async function confirmDelete() {
    const channel = pendingDelete;
    setBusy(true);
    try {
      await api.deleteChannel(channel.id);
      notify('success', 'Kanal silindi', channel.name);
      setPendingDelete(null);
      reload();
    } catch (err) {
      notify('error', 'Kanal silinemedi', err.message);
    } finally {
      setBusy(false);
    }
  }

  if (loading && !data) return <DashboardSkeleton />;
  if (error && !data) return <ErrorPanel error={error} onRetry={reload} />;

  const channels = data || [];

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="eyebrow">Uyarı yönlendirme</p>
          <h1 className="page-title">Bildirim Kanalları</h1>
          <p className="page-sub">
            Bir servis çöktüğünde veya toparlandığında bildirim bu kanallara gönderilir. Monitörler
            için ayrı kanal seçilmezse tüm aktif kanallar kullanılır.
          </p>
        </div>
        <div className="page-head-actions">
          <button type="button" className="btn primary" onClick={openNew}>
            <Plus size={16} /> Yeni kanal
          </button>
        </div>
      </div>

      {form ? (
        <section className="panel form-panel">
          <form onSubmit={handleSave}>
            <header className="section-head">
              <div>
                <h2>{form.id ? 'Kanalı düzenle' : 'Yeni kanal'}</h2>
                <p>Bilgiler sunucuda saklanır. Gizli alanlar bu ekranda da görünür.</p>
              </div>
            </header>

            <div className="form-grid">
              <div className="field">
                <label htmlFor="channel-name">Kanal adı</label>
                <input
                  id="channel-name"
                  required
                  maxLength={120}
                  value={form.name}
                  onChange={(event) => update('name', event.target.value)}
                  placeholder="Ekip Slack kanalı"
                />
              </div>

              <div className="field">
                <label htmlFor="channel-kind">Tür</label>
                <select
                  id="channel-kind"
                  value={form.kind}
                  onChange={(event) => update('kind', event.target.value)}
                >
                  {KINDS.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </div>

              {form.kind === 'slack' || form.kind === 'discord' ? (
                <div className="field full">
                  <label htmlFor="channel-webhook">Webhook adresi</label>
                  <input
                    id="channel-webhook"
                    type="url"
                    required
                    value={form.webhook_url}
                    onChange={(event) => update('webhook_url', event.target.value)}
                    placeholder={
                      form.kind === 'slack'
                        ? 'https://hooks.slack.com/services/...'
                        : 'https://discord.com/api/webhooks/...'
                    }
                  />
                </div>
              ) : null}

              {form.kind === 'telegram' ? (
                <>
                  <div className="field">
                    <label htmlFor="channel-token">Bot token</label>
                    <input
                      id="channel-token"
                      type="password"
                      autoComplete="off"
                      required
                      value={form.bot_token}
                      onChange={(event) => update('bot_token', event.target.value)}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="channel-chat">Chat ID</label>
                    <input
                      id="channel-chat"
                      required
                      value={form.chat_id}
                      onChange={(event) => update('chat_id', event.target.value)}
                    />
                  </div>
                </>
              ) : null}

              {form.kind === 'webhook' ? (
                <>
                  <div className="field full">
                    <label htmlFor="channel-url">Hedef adres</label>
                    <input
                      id="channel-url"
                      type="url"
                      required
                      value={form.url}
                      onChange={(event) => update('url', event.target.value)}
                      placeholder="https://sistemim.local/alarm"
                    />
                  </div>
                  <div className="field full">
                    <label htmlFor="channel-secret">İmza anahtarı (isteğe bağlı)</label>
                    <input
                      id="channel-secret"
                      type="password"
                      autoComplete="off"
                      value={form.secret}
                      onChange={(event) => update('secret', event.target.value)}
                    />
                    <small className="field-hint">
                      Doluysa her istek X-PulseWatch-Signature başlığıyla HMAC-SHA256 imzalanır.
                    </small>
                  </div>
                </>
              ) : null}
            </div>

            <label className="switch-row">
              <span>
                <strong>Kanal etkin</strong>
                <small>Kapalıysa bu kanala bildirim gönderilmez.</small>
              </span>
              <span className={`switch ${form.enabled ? 'on' : ''}`}>
                <input
                  type="checkbox"
                  checked={form.enabled}
                  onChange={(event) => update('enabled', event.target.checked)}
                  aria-label="Kanal etkin"
                />
                <i />
              </span>
            </label>

            {formError ? (
              <div className="form-error" role="alert">
                {formError}
              </div>
            ) : null}

            <footer className="modal-actions">
              <button type="button" className="btn ghost" onClick={() => setForm(null)}>
                Vazgeç
              </button>
              <button type="submit" className="btn primary" disabled={busy}>
                {busy ? 'Kaydediliyor…' : 'Kaydet'}
              </button>
            </footer>
          </form>
        </section>
      ) : null}

      {channels.length === 0 && !form ? (
        <section className="panel">
          <EmptyState
            icon={<Bell size={28} />}
            title="Henüz bildirim kanalı yok"
            message="Slack, Discord, Telegram veya kendi sisteminize giden bir webhook ekleyin. Bir servis çöktüğünde ilk bildirim oraya gider."
            action={
              <button type="button" className="btn primary" onClick={openNew}>
                <Plus size={16} /> Kanal ekle
              </button>
            }
          />
        </section>
      ) : (
        <div className="channel-grid">
          {channels.map((channel) => {
            const tag = STATUS_TAGS[channel.last_status] || STATUS_TAGS.unknown;
            return (
              <article
                key={channel.id}
                className={`panel channel-card ${channel.enabled ? '' : 'is-disabled'}`}
              >
                <header className="channel-card-head">
                  <span className={`channel-kind ${channel.kind}`}>{kindLabel(channel.kind)}</span>
                  <span className={`status-pill ${tag.tone}`}>
                    {channel.enabled ? tag.label : 'Pasif'}
                  </span>
                </header>
                <h3>{channel.name}</h3>
                <p className="channel-meta">
                  {channel.last_tested_at
                    ? `Son deneme ${timeAgo(channel.last_tested_at)}`
                    : 'Henüz deneme yapılmadı'}
                </p>
                {channel.last_error ? <p className="channel-error">{channel.last_error}</p> : null}
                <footer className="channel-actions">
                  <button
                    type="button"
                    className="btn ghost sm"
                    onClick={() => handleTest(channel)}
                    disabled={testingId === channel.id}
                  >
                    <Send size={14} /> {testingId === channel.id ? 'Gönderiliyor…' : 'Test et'}
                  </button>
                  <button type="button" className="btn ghost sm" onClick={() => toggleEnabled(channel)}>
                    {channel.enabled ? 'Duraklat' : 'Etkinleştir'}
                  </button>
                  <button
                    type="button"
                    className="icon-btn sm"
                    aria-label={`${channel.name} kanalını düzenle`}
                    onClick={() => openEdit(channel)}
                  >
                    <Pencil size={14} />
                  </button>
                  <button
                    type="button"
                    className="icon-btn sm danger"
                    aria-label={`${channel.name} kanalını sil`}
                    onClick={() => setPendingDelete(channel)}
                  >
                    <Trash2 size={14} />
                  </button>
                </footer>
              </article>
            );
          })}
        </div>
      )}

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Kanalı sil"
        message={`"${pendingDelete?.name || ''}" kanalı silinecek. Bu işlem geri alınamaz.`}
        confirmLabel="Sil"
        busy={busy}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}
