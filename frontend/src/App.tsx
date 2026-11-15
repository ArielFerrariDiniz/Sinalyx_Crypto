import { useEffect, useState } from 'react';
import { api, ApiError, type Portfolio } from './services/api';
import { ConnectPage } from './pages/ConnectPage';
import { PortfolioPage } from './pages/PortfolioPage';
import { VaultAccessPage, type VaultState } from './pages/VaultAccessPage';

type AppViewState = VaultState | 'ready';

const INVALID_CREDENTIAL_CODES = new Set([
  'invalid_api_key', 'invalid_signature', 'key_or_permission', 'permission_denied',
]);

export default function App() {
  const [connected, setConnected] = useState(false);
  const [data, setData] = useState<Portfolio | null>(null);
  const [busy, setBusy] = useState<'' | 'connect' | 'refresh' | 'disconnect'>('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [warnings, setWarnings] = useState<string[]>([]);
  const [vaultState, setVaultState] = useState<AppViewState>('loading');

  function handleError(caught: unknown) {
    const apiError = caught instanceof ApiError ? caught : null;
    setError(apiError?.message ?? 'Não foi possível concluir a consulta. Tente novamente.');
    if (apiError?.code.startsWith('vault_')) {
      setConnected(false); setData(null); setWarnings([]);
      setVaultState(apiError.code === 'vault_locked' ? 'locked' : 'unavailable');
    } else if (apiError && INVALID_CREDENTIAL_CODES.has(apiError.code)) {
      setConnected(false); setData(null); setWarnings([]); setVaultState('ready');
    } else if (apiError?.code === 'session_missing') {
      setConnected(false); setData(null); setWarnings([]); setVaultState('ready');
    } else if (apiError?.code === 'local_connection' && vaultState === 'loading') {
      setVaultState('unavailable');
    }
  }

  async function restoreSession(isActive: () => boolean = () => true) {
    try {
      const session = await api.session();
      if (!isActive()) return;
      setError(session.connected ? '' : session.warnings[0] ?? ''); setMessage(''); setWarnings(session.warnings);
      setConnected(session.connected); setVaultState('ready');
      if (!session.connected) { setData(null); return; }
      setBusy('refresh');
      const portfolio = await api.portfolio();
      if (isActive()) setData(portfolio);
    } catch (caught) {
      if (isActive()) handleError(caught);
    } finally {
      if (isActive()) setBusy('');
    }
  }

  useEffect(() => {
    let active = true;
    void restoreSession(() => active);
    return () => { active = false; };
  }, []);

  async function unlockVault() {
    setBusy('connect'); setError('');
    try {
      await api.unlockVault();
      await restoreSession();
    } catch (caught) { handleError(caught); }
    finally { setBusy(''); }
  }

  async function refresh() {
    setBusy('refresh'); setError(''); setMessage('');
    try { setData(await api.portfolio()); }
    catch (caught) { handleError(caught); }
    finally { setBusy(''); }
  }

  async function connect(apiKey: string, secretKey: string) {
    setBusy('connect'); setError(''); setMessage('');
    try {
      const result = await api.connect(apiKey, secretKey);
      setWarnings(result.warnings);
      setConnected(true); setData(null);
      setBusy('refresh');
      try {
        setData(await api.portfolio());
        setMessage('Conexão validada. Carteira Spot atualizada.');
      } catch (caught) { handleError(caught); }
    } catch (caught) { handleError(caught); }
    finally { setBusy(''); }
  }

  async function disconnect() {
    setBusy('disconnect'); setError(''); setMessage('');
    try {
      await api.disconnect();
      setData(null); setConnected(false); setWarnings([]); setVaultState('ready');
      setMessage('Conta desconectada. As credenciais foram removidas do cofre seguro do Linux.');
    } catch (caught) { handleError(caught); }
    finally { setBusy(''); }
  }

  return <div className="app-shell">
    <header className="app-header"><div className="brand"><span className="brand-icon" aria-hidden="true">◈</span>
      <div><span className="brand-name">Crypto Trading Bot</span><p>Gerenciamento de carteira Binance</p></div></div>
      <span className={`connection-badge ${connected ? 'is-connected' : ''}`}><span className="status-dot" />
        {connected ? 'Binance conectada' : 'Somente leitura'}</span></header>
    {vaultState !== 'ready' ? <VaultAccessPage key={vaultState} state={vaultState} busy={!!busy} error={error}
      onUnlock={unlockVault} onRetry={() => restoreSession()} />
      : connected ? <PortfolioPage data={data} busy={busy} error={error} message={message} warnings={warnings} onRefresh={refresh} onDisconnect={disconnect} />
      : <ConnectPage busy={!!busy} error={error} message={message} onConnect={connect} />}
    <footer className="app-footer"><span>CRYPTO TRADING BOT <span className="footer-separator">/</span> CARTEIRA SPOT</span><span>Execução local <span className="status-dot" /></span></footer>
  </div>;
}
