import { Notice } from '../components/Notice';
import { Spinner } from '../components/Spinner';

export type VaultState = 'loading' | 'locked' | 'unavailable';

export function VaultAccessPage({ state, busy, error, onUnlock, onRetry }: {
  state: VaultState; busy: boolean; error: string;
  onUnlock: () => Promise<void>; onRetry: () => Promise<void>;
}) {
  const title = state === 'loading' ? 'Carregando carteira'
    : state === 'locked' ? 'Cofre do Linux bloqueado' : 'Cofre local indisponível';

  return <main className="connect-layout">
    <section className="intro">
      <div className="eyebrow"><span className="status-dot" /> BINANCE SPOT</div>
      <h1>Sua carteira.<br /><span>Com clareza.</span></h1>
      <p className="intro-copy">Acompanhe seus saldos e o valor estimado dos seus ativos em USDT, em um só lugar.</p>
      <div className="principles">
        <div><span className="principle-icon" aria-hidden="true">↳</span><p><strong>Acesso somente leitura</strong><span>Consulta de saldos e preços da carteira Spot.</span></p></div>
        <div><span className="principle-icon" aria-hidden="true">⌁</span><p><strong>Credenciais no cofre local</strong><span>Protegidas pelo cofre seguro do Linux.</span></p></div>
        <div><span className="principle-icon" aria-hidden="true">◷</span><p><strong>Sem expiração por inatividade</strong><span>A conexão fica salva até você removê-la.</span></p></div>
      </div>
    </section>
    <section className="panel connect-panel" aria-labelledby="vault-title">
      <div className="panel-eyebrow"><span className="binance-mark" aria-hidden="true">◆</span> COFRE LOCAL</div>
      <h2 id="vault-title">{title}</h2>
      <p className="muted">{state === 'loading' ? 'Consultando o cofre seguro do Linux…'
        : state === 'locked' ? 'Desbloqueie o cofre pela janela segura do sistema. O aplicativo não pede uma senha própria.'
        : 'Verifique se o serviço Secret Service está ativo e se há um cofre padrão persistente.'}</p>
      {error && <Notice kind="error">{error}</Notice>}
      <div className="connection-form">
        {state === 'loading' ? <div role="status"><Spinner /> Consultando o cofre…</div>
          : <button className="button button-primary" disabled={busy}
            onClick={state === 'locked' ? onUnlock : onRetry}>
            {busy && <Spinner />}{state === 'locked' ? 'Desbloquear cofre do Linux' : 'Tentar novamente'}
          </button>}
      </div>
    </section>
  </main>;
}
