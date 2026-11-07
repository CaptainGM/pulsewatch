import { useCallback, useEffect, useState } from 'react';
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom';
import { AppProvider, useApp } from './context/AppContext';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Monitors from './pages/Monitors';
import MonitorDetail from './pages/MonitorDetail';
import Incidents from './pages/Incidents';
import Channels from './pages/Channels';
import ApiKeys from './pages/ApiKeys';
import Maintenance from './pages/Maintenance';
import Sla from './pages/Sla';
import Users from './pages/Users';
import Settings from './pages/Settings';
import StatusPage from './pages/StatusPage';
import Login from './pages/Login';
import { api, AUTH_REQUIRED_EVENT, getToken, setToken, takeOAuthFragment } from './api';
import { EmptyState, ErrorPanel } from './components/States';

const OAUTH_ERRORS = {
  state: 'Giriş isteği doğrulanamadı. Tekrar deneyin.',
  token: 'Google oturumu alınamadı.',
  profile: 'Google hesap bilgisi okunamadı.',
  unverified: 'Google hesabının e-postası doğrulanmamış.',
  domain: 'Bu e-posta alan adı bu panel için izinli değil.',
  not_registered: 'Bu hesap için kullanıcı tanımlı değil. Bir yönetici ekleyebilir.',
  disabled: 'Bu hesap pasif durumda.',
};

function NotFound() {
  return (
    <EmptyState
      title="Sayfa bulunamadı"
      message="Aradığınız sayfa taşınmış veya hiç var olmamış olabilir."
      action={
        <Link to="/" className="btn primary">
          Genel bakışa dön
        </Link>
      }
    />
  );
}

function AdminOnly({ children }) {
  const { me, isAdmin } = useApp();
  if (!me) return null;
  if (!isAdmin) {
    return (
      <EmptyState
        title="Yetkiniz yok"
        message="Bu sayfa yalnızca yöneticilere açık."
        action={
          <Link to="/" className="btn primary">
            Genel bakışa dön
          </Link>
        }
      />
    );
  }
  return children;
}

function AuthGate({ children }) {
  const [state, setState] = useState({
    phase: 'checking',
    error: null,
    needsLogin: false,
    notice: '',
    config: null,
  });

  const loadConfig = useCallback(async () => {
    setState((current) => ({ ...current, phase: 'checking', error: null }));
    const oauth = takeOAuthFragment();
    if (oauth?.token) setToken(oauth.token);
    try {
      const config = await api.authConfig();
      setState({
        phase: 'ready',
        error: null,
        needsLogin: config.enabled && !getToken(),
        notice: oauth?.error ? OAUTH_ERRORS[oauth.error] || 'Google ile giriş yapılamadı.' : '',
        config,
      });
    } catch (error) {
      setState({ phase: 'error', error, needsLogin: false, notice: '', config: null });
    }
  }, []);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  useEffect(() => {
    function onAuthRequired() {
      setState((current) => ({ ...current, needsLogin: true }));
    }
    window.addEventListener(AUTH_REQUIRED_EVENT, onAuthRequired);
    return () => window.removeEventListener(AUTH_REQUIRED_EVENT, onAuthRequired);
  }, []);

  if (state.phase === 'checking') {
    return (
      <div className="boot-screen">
        <span className="boot-pulse" aria-hidden="true" />
        <span>PulseWatch yükleniyor…</span>
      </div>
    );
  }

  if (state.phase === 'error') {
    return (
      <div className="boot-screen">
        <div className="boot-error">
          <ErrorPanel error={state.error} onRetry={loadConfig} />
        </div>
      </div>
    );
  }

  if (state.needsLogin) {
    return (
      <Login
        config={state.config}
        notice={state.notice}
        onLoggedIn={() => setState((current) => ({ ...current, needsLogin: false }))}
      />
    );
  }

  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/status" element={<StatusPage />} />

        <Route
          element={
            <AuthGate>
              <AppProvider>
                <Layout />
              </AppProvider>
            </AuthGate>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="monitors" element={<Monitors />} />
          <Route path="monitors/:monitorId" element={<MonitorDetail />} />
          <Route path="incidents" element={<Incidents />} />
          <Route path="sla" element={<Sla />} />
          <Route path="maintenance" element={<Maintenance />} />
          <Route path="channels" element={<AdminOnly><Channels /></AdminOnly>} />
          <Route path="api-keys" element={<AdminOnly><ApiKeys /></AdminOnly>} />
          <Route path="users" element={<AdminOnly><Users /></AdminOnly>} />
          <Route path="settings" element={<AdminOnly><Settings /></AdminOnly>} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
