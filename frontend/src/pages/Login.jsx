import { useState } from 'react';
import { LogIn } from 'lucide-react';
import { api, setToken } from '../api';
import Logo from '../components/Logo';
import { useDocumentTitle } from '../hooks';

export default function Login({ config, notice, onLoggedIn }) {
  useDocumentTitle('Giriş');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const result = await api.login(email.trim(), password);
      setToken(result.access_token);
      onLoggedIn();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-screen">
      <form className="login-card" onSubmit={handleSubmit}>
        <div className="login-brand">
          <Logo size={44} />
          <span>
            <strong>PulseWatch</strong>
            <small>API İzleme</small>
          </span>
        </div>
        <h1>Yönetici girişi</h1>
        <p className="login-sub">Panele devam etmek için hesap bilgilerinizi girin.</p>

        {notice ? (
          <div className="form-error" role="alert">
            {notice}
          </div>
        ) : null}

        <div className="field">
          <label htmlFor="login-email">E-posta</label>
          <input
            id="login-email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="login-password">Şifre</label>
          <input
            id="login-password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>

        {error ? (
          <div className="form-error" role="alert">
            {error}
          </div>
        ) : null}

        <button type="submit" className="btn primary login-submit" disabled={busy}>
          <LogIn size={16} /> {busy ? 'Giriş yapılıyor…' : 'Giriş yap'}
        </button>

        {config?.google ? (
          <>
            <div className="login-divider">
              <span>veya</span>
            </div>
            <a className="btn ghost login-submit" href="/api/auth/google/login">
              Google ile giriş yap
            </a>
          </>
        ) : null}
      </form>
    </div>
  );
}
