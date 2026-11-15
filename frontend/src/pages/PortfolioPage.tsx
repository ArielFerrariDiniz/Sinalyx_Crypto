import type { Portfolio } from '../services/api';
import { decimal, updatedTime } from '../services/format';
import { Notice } from '../components/Notice';
import { PortfolioTable } from '../components/PortfolioTable';
import { Spinner } from '../components/Spinner';
import { WalletSummaryGrid } from '../components/WalletSummaryGrid';
import { buildQueryDetails, emptyAssetsMessage, filterAssetsWithBalance, filterWalletsWithBalance } from '../services/portfolioView';

export function PortfolioPage({ data, busy, error, message, warnings, onRefresh, onDisconnect }: {
  data: Portfolio | null; busy: '' | 'connect' | 'refresh' | 'disconnect'; error: string; message: string;
  warnings: string[];
  onRefresh: () => Promise<void>; onDisconnect: () => Promise<void>;
}) {
  const assets = data ? filterAssetsWithBalance(data.assets) : [];
  const wallets = data ? filterWalletsWithBalance(data.wallets) : [];
  const queryDetails = buildQueryDetails(data, error, warnings);
  const noQuotes = assets.length > 0 && assets.every(asset => asset.value_usdt === null);
  return <main className="portfolio-page" aria-busy={!!busy}>
    <div className="portfolio-heading"><div><div className="eyebrow">VISÃO GERAL</div><h1>Carteira Binance</h1>
      <p className="muted">Saldos consolidados por produto, com valores estimados em USDT.</p></div>
      <div className="actions"><button className="button button-secondary" onClick={onRefresh} disabled={!!busy}>
        {busy === 'refresh' ? <Spinner /> : <span aria-hidden="true">↻</span>}{busy === 'refresh' ? 'Atualizando…' : 'Atualizar carteira'}</button>
        <button className="button button-quiet" onClick={onDisconnect} disabled={!!busy}>
          {busy === 'disconnect' && <Spinner />}{busy === 'disconnect' ? 'Removendo credenciais…' : 'Desconectar e remover credenciais'}</button></div></div>
    {message && <Notice kind="success">{message}</Notice>}
    <details className="query-details">
      <summary><span>Detalhes da consulta</span><span className="query-details-count">
        {error ? 'Atualização não concluída' : queryDetails.length ? `${queryDetails.length} ${queryDetails.length === 1 ? 'detalhe' : 'detalhes'}` : 'Sem pendências'}
      </span></summary>
      {queryDetails.length ? <ul>{queryDetails.map((detail, index) => <li key={`${index}-${detail}`}>{detail}</li>)}</ul>
        : <p>As fontes desta atualização foram consultadas sem alertas.</p>}
      {data && error && <p className="stale-data-note">Os valores da carteira correspondem à última consulta concluída.</p>}
    </details>
    {data ? <>
      <section className="summary-grid" aria-label="Resumo da carteira">
        <div className="panel summary-card total-card"><span className="summary-label">Patrimônio {data.is_partial ? 'parcial' : 'total'} estimado</span>
          <div className="total-value">{noQuotes ? '—' : decimal(data.total_usdt, 2)} <span>USDT</span></div>
          <span className="summary-note">{noQuotes ? 'Aguardando cotações disponíveis' : 'Soma dos saldos líquidos com cotação disponível'}</span></div>
        <div className="panel summary-card"><span className="summary-label">Ativos com saldo</span><div className="stat-value">{assets.length}</div>
          <span className="summary-note">{data.unpriced_assets.length ? `${data.unpriced_assets.length} sem cotação` : 'Moedas em todas as fontes'}</span></div>
        <div className="panel summary-card"><span className="summary-label">Última atualização</span><div className="time-value">{updatedTime(data.updated_at)}</div>
          <span className="summary-note">Horário local · atualização manual</span></div>
      </section>
      <WalletSummaryGrid wallets={wallets} />
      <PortfolioTable assets={assets} emptyMessage={emptyAssetsMessage(data, wallets)} />
      <p className="valuation-note">Cotações estimadas pelo último preço dos pares Spot ativos, com conversão intermediária quando disponível. Earn contabiliza apenas o principal/posição consultado; recompensas informativas não são somadas. Futures usa o saldo líquido e a margem inicial reportados por ativo; o valor nocional das posições não entra no patrimônio.</p>
    </> : <div className="panel first-load" role="status">{busy === 'refresh' ? <><Spinner /> Consultando as carteiras Binance…</>
      : <p>A conexão foi validada. Clique em “Atualizar carteira” para consultar seus saldos.</p>}</div>}
  </main>;
}
