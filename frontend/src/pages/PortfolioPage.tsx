import { useState } from 'react';
import type { Portfolio } from '../services/api';
import { updatedTime } from '../services/format';
import { formatMoney, type DisplayCurrency } from '../services/currency';
import { Notice } from '../components/Notice';
import { PortfolioTable } from '../components/PortfolioTable';
import { Spinner } from '../components/Spinner';
import { WalletSummaryGrid } from '../components/WalletSummaryGrid';
import { buildQueryDetails, emptyAssetsMessage, filterAssetsWithBalance, filterWalletsWithBalance } from '../services/portfolioView';
import { financialValue } from '../services/privacy';

export function PortfolioPage({ data, busy, error, message, warnings, privacyHidden, onTogglePrivacy, onRefresh, onDisconnect }: {
  data: Portfolio | null; busy: '' | 'connect' | 'refresh' | 'disconnect'; error: string; message: string;
  warnings: string[]; privacyHidden: boolean; onTogglePrivacy: () => void;
  onRefresh: () => Promise<void>; onDisconnect: () => Promise<void>;
}) {
  const [currency, setCurrency] = useState<DisplayCurrency>('BRL');
  const assets = data ? filterAssetsWithBalance(data.assets) : [];
  const wallets = data ? filterWalletsWithBalance(data.wallets) : [];
  const queryDetails = buildQueryDetails(data, error, warnings);
  const noQuotes = assets.length > 0 && assets.every(asset => asset.value_usdt === null);
  const brlQuoteUnavailable = currency === 'BRL' && !!data
    && (data.usdt_brl_rate === null || data.usdt_brl_updated_at === null);
  const totalValue = data && !noQuotes && !brlQuoteUnavailable
    ? formatMoney(data.total_usdt, currency, data.usdt_brl_rate, 2)
    : null;
  return <main className="portfolio-page" aria-busy={!!busy}>
    <div className="portfolio-heading">
      <div><div className="eyebrow">VISÃO GERAL</div><h1>Carteira Binance</h1>
        <p className="muted">{currency === 'USD'
          ? 'Valores em USDT, referência aproximada a USD; USDT pode variar em relação ao dólar.'
          : 'Valores monetários convertidos pela cotação Spot USDT/BRL.'}</p></div>
      <div className="actions">
        <div className="display-controls">
          <div className="currency-switch" role="group" aria-label="Moeda de exibição">
            <button type="button" className={currency === 'USD' ? 'currency-option is-active' : 'currency-option'}
              aria-pressed={currency === 'USD'} onClick={() => setCurrency('USD')}>USD</button>
            <button type="button" className={currency === 'BRL' ? 'currency-option is-active' : 'currency-option'}
              aria-pressed={currency === 'BRL'} onClick={() => setCurrency('BRL')}>BRL</button>
          </div>
          <button type="button" className="button button-quiet privacy-toggle" aria-pressed={privacyHidden}
            aria-label={privacyHidden ? 'Mostrar valores financeiros' : 'Ocultar valores financeiros'}
            title={privacyHidden ? 'Mostrar valores financeiros' : 'Ocultar valores financeiros'} onClick={onTogglePrivacy}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M2.5 12s3.3-6 9.5-6 9.5 6 9.5 6-3.3 6-9.5 6-9.5-6-9.5-6Z" />
              <circle cx="12" cy="12" r="2.5" />
              {privacyHidden && <path d="m4 4 16 16" />}
            </svg>
          </button>
        </div>
        <button className="button button-secondary" onClick={onRefresh} disabled={!!busy}>
          {busy === 'refresh' ? <Spinner /> : <span aria-hidden="true">↻</span>}{busy === 'refresh' ? 'Atualizando…' : 'Atualizar carteira'}</button>
        <button className="button button-quiet" onClick={onDisconnect} disabled={!!busy}>
          {busy === 'disconnect' && <Spinner />}{busy === 'disconnect' ? 'Removendo credenciais…' : 'Desconectar e remover credenciais'}</button>
      </div>
    </div>
    {message && <Notice kind="success">{message}</Notice>}
    {currency === 'BRL' && data && (brlQuoteUnavailable
      ? <Notice kind="error">{data.usdt_brl_error ?? 'Cotação Spot USDT/BRL indisponível. Os valores em BRL não foram calculados.'}</Notice>
      : data.usdt_brl_updated_at && <p className="exchange-rate" role="status">
        1 USDT = {financialValue(formatMoney(data.usdt_brl_rate!, 'BRL', '1', 4) ?? '—', privacyHidden)}
        <span>Cotação atualizada {updatedTime(data.usdt_brl_updated_at)}</span>
      </p>)}
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
          <div className="total-value">{financialValue(totalValue ?? '—', privacyHidden)} <span>{currency === 'USD' ? 'USDT (aprox. USD)' : 'BRL'}</span></div>
          <span className="summary-note">{brlQuoteUnavailable ? 'Cotação USDT/BRL indisponível' : noQuotes ? 'Aguardando cotações disponíveis' : 'Soma dos saldos líquidos com cotação disponível'}</span></div>
        <div className="panel summary-card"><span className="summary-label">Ativos com saldo</span><div className="stat-value">{assets.length}</div>
          <span className="summary-note">{data.unpriced_assets.length ? `${data.unpriced_assets.length} sem cotação` : 'Moedas em todas as fontes'}</span></div>
        <div className="panel summary-card"><span className="summary-label">Última atualização</span><div className="time-value">{updatedTime(data.updated_at)}</div>
          <span className="summary-note">Horário local · atualização manual</span></div>
      </section>
      <WalletSummaryGrid wallets={wallets} currency={currency} usdtBrlRate={data.usdt_brl_rate} privacyHidden={privacyHidden} />
      <PortfolioTable assets={assets} emptyMessage={emptyAssetsMessage(data, wallets)} currency={currency}
        usdtBrlRate={data.usdt_brl_rate} privacyHidden={privacyHidden} />
      <p className="valuation-note">Cotações estimadas pelo último preço dos pares Spot ativos, com conversão intermediária quando disponível. Futures usa o saldo líquido e a margem inicial reportados por ativo; o valor nocional das posições não entra no patrimônio.</p>
    </> : <div className="panel first-load" role="status">{busy === 'refresh' ? <><Spinner /> Consultando as carteiras Binance…</>
      : <p>A conexão foi validada. Clique em “Atualizar carteira” para consultar seus saldos.</p>}</div>}
  </main>;
}
