import { useCallback, useEffect, useRef, useState } from 'react';
import type { MarketAsset, MarketCandlePage, MarketInterval } from '../services/api';
import { api, ApiError } from '../services/api';
import { decimal, updatedTime } from '../services/format';
import { hasNewOlderCandles, mergeCandles } from '../services/historyView';
import { CandlestickChart } from '../components/CandlestickChart';
import { Notice } from '../components/Notice';
import { Spinner } from '../components/Spinner';

const INTERVALS: MarketInterval[] = ['1m', '5m', '15m', '1h', '4h', '1d'];

function formatMetric(value: string | null, digits: number): string {
  if (value === null || !/^-?\d+(?:\.\d+)?(?:e[+-]?\d+)?$/i.test(value)) return '—';
  const negative = value.startsWith('-');
  let result = decimal(negative ? value.slice(1) : value, digits);
  if (digits > 2 && !result.startsWith('< ')) {
    const [whole, fraction = ''] = result.split(',');
    result = `${whole},${fraction.replace(/0+$/, '').padEnd(2, '0')}`;
  }
  return `${negative ? '-' : ''}${result}`;
}

function financial(value: string | null, approximate = false, digits = 2, suffix = ''): string {
  if (value === null) return '—';
  return `${approximate ? '≈ ' : ''}${formatMetric(value, digits)}${suffix}`;
}

function historicalDate(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return 'Indisponível';
  return new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC',
  }).format(new Date(value));
}

export function MarketDetailPage({ asset, marketUpdatedAt, onBack }: {
  asset: MarketAsset;
  marketUpdatedAt: string | null;
  onBack: () => void;
}) {
  const [interval, setInterval] = useState<MarketInterval>('1h');
  const [history, setHistory] = useState<MarketCandlePage | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [error, setError] = useState('');
  const requestGeneration = useRef(0);
  const olderRequest = useRef<number | null>(null);

  useEffect(() => { window.scrollTo({ top: 0 }); }, [asset.pair]);

  useEffect(() => {
    const generation = ++requestGeneration.current;
    setHistory(null);
    setError('');
    setLoading(false);
    setLoadingOlder(false);
    setLoading(true);
    void api.marketKlines(asset.pair, interval).then(page => {
      if (requestGeneration.current === generation) setHistory(page);
    }).catch(caught => {
      if (requestGeneration.current !== generation) return;
      setError(caught instanceof ApiError ? caught.message : 'Não foi possível carregar o histórico deste par.');
    }).finally(() => {
      if (requestGeneration.current === generation) setLoading(false);
    });
  }, [asset.pair, interval]);

  const loadOlder = useCallback(async () => {
    const generation = requestGeneration.current;
    if (!history?.has_older || history.oldest_open_time === null || history.oldest_open_time <= 0
      || olderRequest.current === generation) return;
    olderRequest.current = generation;
    setLoadingOlder(true);
    setError('');
    try {
      const page = await api.marketKlines(asset.pair, interval, history.oldest_open_time - 1);
      if (requestGeneration.current !== generation) return;
      setHistory(current => {
        if (!current) return current;
        const addedOlder = hasNewOlderCandles(current.candles, page.candles);
        const candles = mergeCandles(current.candles, page.candles);
        return {
          ...current,
          candles,
          earliest_open_time: page.earliest_open_time,
          oldest_open_time: candles[0]?.open_time ?? current.oldest_open_time,
          latest_open_time: candles.at(-1)?.open_time ?? current.latest_open_time,
          has_older: page.has_older && addedOlder,
          updated_at: page.updated_at,
        };
      });
    } catch (caught) {
      if (requestGeneration.current === generation) {
        setError(caught instanceof ApiError ? caught.message : 'Não foi possível carregar o período histórico anterior.');
      }
    } finally {
      if (requestGeneration.current === generation) setLoadingOlder(false);
      if (olderRequest.current === generation) olderRequest.current = null;
    }
  }, [asset.pair, history, interval]);

  return <main className="market-detail-page">
    <div className="detail-heading">
      <button className="button button-quiet" onClick={onBack}><span aria-hidden="true">←</span> Voltar ao Mercado</button>
    </div>
    <div className="detail-title-row">
      <div><div className="eyebrow">BINANCE SPOT · DETALHES</div><h1>{asset.symbol}</h1>
        <p className="muted">Par negociado: <strong>{asset.pair}</strong>
          {asset.conversion_approximate && <span> · cotações consolidadas em USDT são estimadas</span>}</p></div>
      <span className="detail-updated">Mercado atualizado {marketUpdatedAt ? updatedTime(marketUpdatedAt) : '—'}</span>
    </div>

    <section className="summary-grid detail-summary" aria-label={`Resumo de ${asset.symbol}`}>
      <div className="panel summary-card"><span className="summary-label">Preço atual em USDT</span>
        <div className="detail-metric">{financial(asset.price_usdt, asset.conversion_approximate, 8)} <small>USDT</small></div></div>
      <div className="panel summary-card"><span className="summary-label">Variação 24h</span>
        <div className={`detail-metric ${Number(asset.change_percent_24h) < 0 ? 'market-negative' : 'market-positive'}`}>
          {financial(asset.change_percent_24h, asset.conversion_approximate, 2, '%')}</div></div>
      <div className="panel summary-card"><span className="summary-label">Máxima 24h</span>
        <div className="detail-metric">{financial(asset.high_24h_usdt, asset.conversion_approximate, 8)} <small>USDT</small></div></div>
      <div className="panel summary-card"><span className="summary-label">Mínima 24h</span>
        <div className="detail-metric">{financial(asset.low_24h_usdt, asset.conversion_approximate, 8)} <small>USDT</small></div></div>
      <div className="panel summary-card"><span className="summary-label">Volume financeiro 24h</span>
        <div className="detail-metric">{financial(asset.volume_usdt_24h, asset.conversion_approximate)} <small>USDT</small></div></div>
    </section>

    {error && <Notice kind="error">{error}</Notice>}
    <section className="panel detail-chart-panel" aria-label="Histórico de preços">
      <div className="detail-chart-heading">
        <div><h2>{asset.pair}</h2><p className="muted">Candles em {asset.quote_asset} · volume em {asset.symbol}</p></div>
        <div className="interval-switch" role="group" aria-label="Intervalo dos candles">
          {INTERVALS.map(value => <button key={value} type="button" className={interval === value ? 'interval-option is-active' : 'interval-option'}
            aria-pressed={interval === value} disabled={loading || loadingOlder} onClick={() => setInterval(value)}>{value}</button>)}
        </div>
      </div>
      {loading ? <div className="market-loading"><Spinner /> Carregando candles da Binance…</div>
          : history?.candles.length ? <CandlestickChart key={`${asset.pair}-${interval}`} candles={history.candles}
            hasOlder={history.has_older} loadingOlder={loadingOlder} onLoadOlder={loadOlder} />
            : <div className="market-empty">{history ? 'A Binance não retornou candles para este par e intervalo.'
              : error ? 'O histórico não pôde ser carregado nesta tentativa.' : 'O histórico será consultado ao exibir o gráfico.'}</div>}
      <div className="detail-history-footer">
        <span>{history?.earliest_open_time !== null && history?.earliest_open_time !== undefined
          ? `Histórico disponível desde ${historicalDate(history.earliest_open_time)} UTC`
          : history ? 'Período histórico disponível não informado pela Binance' : 'Período histórico aguardando consulta'}</span>
        <span>{history ? `${history.candles.length.toLocaleString('pt-BR')} candles carregados` : ''}</span>
        {history?.has_older && <button className="button button-quiet" onClick={() => void loadOlder()} disabled={loadingOlder}>
          {loadingOlder ? <><Spinner /> Carregando período anterior…</> : 'Carregar candles anteriores'}
        </button>}
      </div>
      <p className="chart-attribution-note">Gráfico de candles e volume · Dados públicos da Binance · TradingView Lightweight Charts</p>
    </section>
  </main>;
}
