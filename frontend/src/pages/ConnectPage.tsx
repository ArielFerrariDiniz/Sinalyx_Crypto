import { ConnectionForm } from '../components/ConnectionForm';
import { Notice } from '../components/Notice';

export function ConnectPage({ busy, error, message, onConnect }: {
  busy: boolean; error: string; message: string;
  onConnect: (apiKey: string, secretKey: string) => Promise<void>;
}) {
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
    <section className="panel connect-panel" aria-labelledby="connect-title">
      <div className="panel-eyebrow"><span className="binance-mark" aria-hidden="true">◆</span> CONEXÃO BINANCE</div>
      <h2 id="connect-title">Conecte sua conta</h2><p className="muted">Informe suas credenciais para começar.</p>
      {message && <Notice kind="success">{message}</Notice>}
      {error && <Notice kind="error">{error}</Notice>}
      <ConnectionForm busy={busy} onConnect={onConnect} />
    </section>
  </main>;
}
