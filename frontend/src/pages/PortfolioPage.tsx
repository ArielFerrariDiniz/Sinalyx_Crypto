import type { Portfolio } from '../services/api';
import { decimal, updatedTime } from '../services/format';
import { Notice } from '../components/Notice';
import { PortfolioTable } from '../components/PortfolioTable';
import { Spinner } from '../components/Spinner';
import { WalletSummaryGrid } from '../components/WalletSummaryGrid';

export function PortfolioPage({ data, busy, error, message, warnings, onRefresh, onDisconnect }: {
  data: Portfolio | null; busy: '' | 'connect' | 'refresh' | 'disconnect'; error: string; message: string;
  warnings: string[];
  onRefresh: () => Promise<void>; onDisconnect: () => Promise<void>;
}) {
  const noQuotes = data !== null && data.asset_count > 0 && data.unpriced_assets.length === data.asset_count;
  return <main className="portfolio-page" aria-busy={!!busy}>
    <div className="portfolio-heading"><div><div className="eyebrow">VISÃO GERAL</div><h1>Carteira Binance</h1>
      <p className="muted">Saldos consolidados por produto, com valores estimados em USDT.</p></div>
      <div className="actions"><button className="button button-secondary" onClick={onRefresh} disabled={!!busy}>
        {busy === 'refresh' ? <Spinner /> : <span aria-hidden="true">↻</span>}{busy === 'refresh' ? 'Atualizando…' : 'Atualizar carteira'}</button>
        <button className="button button-quiet" onClick={onDisconnect} disabled={!!busy}>
          {busy === 'disconnect' && <Spinner />}{busy === 'disconnect' ? 'Removendo credenciais…' : 'Desconectar e remover credenciais'}</button></div></div>
    {error && <Notice kind="error">{error}{data && ' Os valores exibidos são da última consulta bem-sucedida.'}</Notice>}
    {message && <Notice kind="success">{message}</Notice>}
    {(data?.warnings ?? warnings).map(warning => <Notice kind="warning" key={warning}>{warning}</Notice>)}
    {data?.is_partial && <Notice kind="warning">{noQuotes ? 'Nenhum ativo possui cotação disponível.' : 'A estimativa exibida é parcial.'}
      {data.unpriced_assets.length > 0 && ` Ativos sem cotação e fora do total: ${data.unpriced_assets.join(', ')}.`}</Notice>}
    {data?.coverage_notes.map(note => <Notice kind="warning" key={note}>{note}</Notice>)}
    {data ? <>
      <section className="summary-grid" aria-label="Resumo da carteira">
        <div className="panel summary-card total-card"><span className="summary-label">Patrimônio {data.is_partial ? 'parcial' : 'total'} estimado</span>
          <div className="total-value">{noQuotes ? '—' : decimal(data.total_usdt, 2)} <span>USDT</span></div>
          <span className="summary-note">{noQuotes ? 'Aguardando cotações disponíveis' : 'Soma dos saldos líquidos com cotação disponível'}</span></div>
        <div className="panel summary-card"><span className="summary-label">Ativos com saldo</span><div className="stat-value">{data.asset_count}</div>
          <span className="summary-note">{data.unpriced_assets.length ? `${data.unpriced_assets.length} sem cotação` : 'Moedas em todas as fontes'}</span></div>
        <div className="panel summary-card"><span className="summary-label">Última atualização</span><div className="time-value">{updatedTime(data.updated_at)}</div>
          <span className="summary-note">Horário local · atualização manual</span></div>
      </section>
      <WalletSummaryGrid wallets={data.wallets} />
      <PortfolioTable assets={data.assets} />
      <p className="valuation-note">Cotações estimadas pelo último preço dos pares Spot ativos, com conversão intermediária quando disponível. Earn contabiliza apenas o principal/posição consultado; recompensas informativas não são somadas. Futures usa o saldo líquido e a margem inicial reportados por ativo; o valor nocional das posições não entra no patrimônio.</p>
    </> : <div className="panel first-load" role="status">{busy === 'refresh' ? <><Spinner /> Consultando as carteiras Binance…</>
      : <p>A conexão foi validada. Clique em “Atualizar carteira” para consultar seus saldos.</p>}</div>}
  </main>;
}
