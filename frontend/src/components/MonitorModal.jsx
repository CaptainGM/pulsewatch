import { useEffect, useRef, useState } from 'react';
import { Loader2, PlugZap, ShieldAlert, X } from 'lucide-react';
import { api } from '../api';

const INTERVALS = [
  { value: 30, label: '30 saniye' },
  { value: 60, label: '1 dakika' },
  { value: 120, label: '2 dakika' },
  { value: 300, label: '5 dakika' },
  { value: 600, label: '10 dakika' },
  { value: 900, label: '15 dakika' },
  { value: 1800, label: '30 dakika' },
  { value: 3600, label: '1 saat' },
];

const TIMEOUTS = [3, 5, 10, 20, 30, 60];

function initialForm(monitor) {
  if (!monitor) {
    return {
      name: '',
      url: '',
      method: 'GET',
      expected_codes: '200',
      interval_seconds: 60,
      timeout_seconds: 10,
      webhook_url: '',
      alert_after_failures: 2,
      active: true,
      body: '',
    };
  }
  return {
    name: monitor.name,
    url: monitor.url,
    method: monitor.method,
    expected_codes: (monitor.expected_codes || [200]).join(', '),
    interval_seconds: monitor.interval_seconds,
    timeout_seconds: monitor.timeout_seconds,
    webhook_url: monitor.webhook_url || '',
    alert_after_failures: monitor.alert_after_failures,
    active: monitor.active,
    body: monitor.body || '',
  };
}

export default function MonitorModal({ monitor = null, onClose, onSaved }) {
  const isEdit = Boolean(monitor);
  const [form, setForm] = useState(() => initialForm(monitor));
  const [headersText, setHeadersText] = useState(() =>
    JSON.stringify(monitor?.headers || {}, null, 2),
  );
  const [advanced, setAdvanced] = useState(
    Boolean(
      monitor &&
        (monitor.webhook_url ||
          monitor.body ||
          Object.keys(monitor.headers || {}).length > 0),
    ),
  );
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const nameRef = useRef(null);

  useEffect(() => {
    document.body.classList.add('modal-open');
    nameRef.current?.focus();
    function onKey(event) {
      if (event.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', onKey);
    return () => {
      document.body.classList.remove('modal-open');
      document.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
    setError('');
  }

  function parseHeaders() {
    const trimmed = headersText.trim();
    if (!trimmed) return {};
    let parsed;
    try {
      parsed = JSON.parse(trimmed);
    } catch {
      throw new Error('Header alanı geçerli bir JSON nesnesi olmalı.');
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error('Header alanı JSON nesnesi olmalı (örn. {"Authorization": "Bearer …"}).');
    }
    return Object.fromEntries(
      Object.entries(parsed).map(([key, value]) => [key, String(value)]),
    );
  }

  async function handleTestWebhook() {
    setTestResult(null);
    if (!/^https?:\/\/.+/i.test(form.webhook_url.trim())) {
      setTestResult({ ok: false, message: 'Önce geçerli bir webhook adresi girin.' });
      return;
    }
    setTesting(true);
    try {
      const result = await api.testWebhook(form.webhook_url.trim());
      setTestResult({ ok: result.success, message: result.message });
    } catch (err) {
      setTestResult({ ok: false, message: err.message });
    } finally {
      setTesting(false);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError('');

    if (!form.name.trim()) {
      setError('Monitör adı zorunludur.');
      nameRef.current?.focus();
      return;
    }
    if (!/^https?:\/\/[^\s]+$/i.test(form.url.trim())) {
      setError('Geçerli bir http:// veya https:// adresi girin.');
      return;
    }

    const codes = form.expected_codes
      .split(/[,;\s]+/)
      .filter(Boolean)
      .map((code) => Number(code));
    if (!codes.length || codes.some((code) => !Number.isInteger(code) || code < 100 || code > 599)) {
      setError('Beklenen kodlar 100–599 arasında, virgülle ayrılmış sayılar olmalı.');
      return;
    }

    let headers;
    try {
      headers = parseHeaders();
    } catch (err) {
      setError(err.message);
      return;
    }

    const payload = {
      name: form.name.trim(),
      url: form.url.trim(),
      method: form.method,
      headers,
      body: form.body.trim() || null,
      expected_codes: codes,
      interval_seconds: Number(form.interval_seconds),
      timeout_seconds: Number(form.timeout_seconds),
      active: form.active,
      alert_after_failures: Number(form.alert_after_failures),
      webhook_url: form.webhook_url.trim() || null,
    };

    setSaving(true);
    try {
      const saved = isEdit
        ? await api.updateMonitor(monitor.id, payload)
        : await api.createMonitor(payload);
      onSaved(saved, isEdit);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="monitor-modal-title">
        <header className="modal-head">
          <div>
            <p className="eyebrow">{isEdit ? 'Monitörü düzenle' : 'Yeni API'}</p>
            <h2 id="monitor-modal-title">
              {isEdit ? monitor.name : 'İzlenecek bir API ekleyin'}
            </h2>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Kapat">
            <X size={18} />
          </button>
        </header>

        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            {error ? (
              <div className="form-error" role="alert">
                <ShieldAlert size={16} /> {error}
              </div>
            ) : null}

            <div className="form-grid">
              <div className="field full">
                <label htmlFor="monitor-name">Monitör adı</label>
                <input
                  id="monitor-name"
                  ref={nameRef}
                  type="text"
                  value={form.name}
                  maxLength={120}
                  placeholder="Örn. Ödeme API"
                  onChange={(event) => update('name', event.target.value)}
                  required
                />
              </div>

              <div className="field full">
                <label htmlFor="monitor-url">API adresi</label>
                <input
                  id="monitor-url"
                  type="url"
                  value={form.url}
                  placeholder="https://api.ornek.com/health"
                  onChange={(event) => update('url', event.target.value)}
                  required
                />
                <small>Her kontrolde bu adrese istek gönderilir. Yönlendirmeler takip edilir.</small>
              </div>

              <div className="field">
                <label htmlFor="monitor-method">HTTP metodu</label>
                <select
                  id="monitor-method"
                  value={form.method}
                  onChange={(event) => update('method', event.target.value)}
                >
                  {['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'].map((method) => (
                    <option key={method} value={method}>
                      {method}
                    </option>
                  ))}
                </select>
              </div>

              <div className="field">
                <label htmlFor="monitor-codes">Beklenen durum kodları</label>
                <input
                  id="monitor-codes"
                  type="text"
                  value={form.expected_codes}
                  placeholder="200, 201, 204"
                  onChange={(event) => update('expected_codes', event.target.value)}
                />
                <small>Virgülle ayırın. Örn. 200, 202.</small>
              </div>

              <div className="field">
                <label htmlFor="monitor-interval">Kontrol aralığı</label>
                <select
                  id="monitor-interval"
                  value={form.interval_seconds}
                  onChange={(event) => update('interval_seconds', Number(event.target.value))}
                >
                  {INTERVALS.map((interval) => (
                    <option key={interval.value} value={interval.value}>
                      {interval.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="field">
                <label htmlFor="monitor-timeout">Zaman aşımı</label>
                <select
                  id="monitor-timeout"
                  value={form.timeout_seconds}
                  onChange={(event) => update('timeout_seconds', Number(event.target.value))}
                >
                  {TIMEOUTS.map((timeout) => (
                    <option key={timeout} value={timeout}>
                      {timeout} saniye
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <label className="switch-row">
              <span>
                <strong>Aktif izleme</strong>
                <small>Kapatırsanız otomatik kontroller durur.</small>
              </span>
              <span className={`switch ${form.active ? 'on' : ''}`}>
                <input
                  type="checkbox"
                  checked={form.active}
                  onChange={(event) => update('active', event.target.checked)}
                  aria-label="Aktif izleme"
                />
                <i />
              </span>
            </label>

            <button
              type="button"
              className="advanced-toggle"
              onClick={() => setAdvanced((value) => !value)}
              aria-expanded={advanced}
            >
              <span>Gelişmiş ayarlar</span>
              <span>{advanced ? 'Gizle' : 'Göster'}</span>
            </button>

            {advanced ? (
              <div className="advanced-section">
                <div className="form-grid">
                  <div className="field">
                    <label htmlFor="monitor-threshold">Alarm eşiği</label>
                    <input
                      id="monitor-threshold"
                      type="number"
                      min="1"
                      max="20"
                      value={form.alert_after_failures}
                      onChange={(event) =>
                        update('alert_after_failures', Number(event.target.value))
                      }
                    />
                    <small>Üst üste kaç hatadan sonra olay açılsın?</small>
                  </div>

                  <div className="field">
                    <label htmlFor="monitor-webhook">Webhook adresi (opsiyonel)</label>
                    <div className="input-with-action">
                      <input
                        id="monitor-webhook"
                        type="url"
                        value={form.webhook_url}
                        placeholder="https://hooks.slack.com/…"
                        onChange={(event) => {
                          update('webhook_url', event.target.value);
                          setTestResult(null);
                        }}
                      />
                      <button
                        type="button"
                        className="btn ghost sm"
                        onClick={handleTestWebhook}
                        disabled={testing}
                      >
                        {testing ? <Loader2 size={14} className="spin" /> : <PlugZap size={14} />}
                        Test
                      </button>
                    </div>
                    <small>Slack, Discord veya genel webhook. Boşsa global webhook kullanılır.</small>
                    {testResult ? (
                      <small className={testResult.ok ? 'text-success' : 'text-danger'}>
                        {testResult.message}
                      </small>
                    ) : null}
                  </div>

                  <div className="field full">
                    <label htmlFor="monitor-headers">Özel header&apos;lar (JSON)</label>
                    <textarea
                      id="monitor-headers"
                      rows={4}
                      value={headersText}
                      spellCheck={false}
                      placeholder={'{\n  "Authorization": "Bearer token"\n}'}
                      onChange={(event) => setHeadersText(event.target.value)}
                    />
                  </div>

                  <div className="field full">
                    <label htmlFor="monitor-body">İstek gövdesi (opsiyonel)</label>
                    <textarea
                      id="monitor-body"
                      rows={3}
                      value={form.body}
                      spellCheck={false}
                      placeholder='{"ping": true}'
                      onChange={(event) => update('body', event.target.value)}
                    />
                    <small>POST/PUT/PATCH isteklerinde gönderilir.</small>
                  </div>
                </div>
              </div>
            ) : null}
          </div>

          <footer className="modal-actions">
            <span className="modal-note">
              {isEdit ? 'Kaydedince yeni ayarlar hemen uygulanır.' : 'Kaydettikten sonra ilk kontrol başlar.'}
            </span>
            <button type="button" className="btn ghost" onClick={onClose} disabled={saving}>
              Vazgeç
            </button>
            <button type="submit" className="btn primary" disabled={saving}>
              {saving ? <Loader2 size={16} className="spin" /> : null}
              {isEdit ? 'Değişiklikleri kaydet' : 'Monitör ekle'}
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
}
