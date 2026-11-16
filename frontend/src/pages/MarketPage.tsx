import { useEffect, useMemo, useState } from 'react';
import type { MarketAsset, MarketSnapshot } from '../services/api';
import { api, ApiError } from '../services/api';
import { decimal, updatedTime } from '../services/format';
import { financialValue } from '../services/privacy';
import { filterMarketAssets, paginateMarketAssets, sortMarketAssets, type MarketSortKey, type SortDirection } from '../services/marketView';
import { Notice } from '../components/Notice';
import { Spinner } from '../components/Spinner';

const PAGE_SIZE = 50;

function amount(value: string | null, digits: number): string {
  if (value === null || !/^-?\d+(?:\.\d+)?(?:e[+-]?\d+)?$/i.test(value)) return '—';
  const negative = value.startsWith('-');
  let formatted = decimal(negative ? value.slice(1) : value, digits);
  if (digits > 2 && !formatted.startsWith('< ')) {
    const [whole, fraction = ''] = formatted.split(',');
    formatted = `${whole},${fraction.replace(/0+$/, '').padEnd(2, '0')}`;
  }
  return `${negative ? '-' : ''}${formatted}`;
}

export function MarketPage({ privacyHidden, onTogglePrivacy }: { privacyHidden: boolean; onTogglePrivacy: () => void }) {
  const [snapshot, setSnapshot] = useState<MarketSnapshot | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [pairFilter, setPairFilter] = useState('');
  const [sortKey, setSortKey] = useState<MarketSortKey>('volume_usdt_24h');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  const [page, setPage] = useState(0);

  async function load(refresh = false) {
    setBusy(true);
    setError('');
    try { setSnapshot(await api.market(refresh)); }
    catch (caught) {
      const message = caught instanceof ApiError ? caught.message : 'Não foi possível consultar o mercado Spot. Tente novamente.';
      setError(message);
    } finally { setBusy(false); }
  }

  useEffect(() => { void load(); }, []);
  useEffect(() => { setPage(0); }, [search, pairFilter, sortKey, sortDirection]);

  const filtered = useMemo(() => {
    const matching = filterMarketAssets(snapshot?.assets ?? [], search, pairFilter);
    return sortMarketAssets(matching, sortKey, sortDirection);
  }, [snapshot, search, pairFilter, sortKey, sortDirection]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const visible = paginateMarketAssets(filtered, page, PAGE_SIZE);

  function selectSort(key: MarketSortKey) {
    if (sortKey === key) setSortDirection(direction => direction === 'asc' ? 'desc' : 'asc');
    else { setSortKey(key); setSortDirection('desc'); }
  }

  function sortButton(key: MarketSortKey, label: string) {
    const active = sortKey === key;
    const ariaSort = active ? sortDirection === 'asc' ? 'ascending' : 'descending' : 'none';
    return <th aria-sort={ariaSort as 'ascending' | 'descending' | 'none'}><button className="market-sort" onClick={() => selectSort(key)}>
      {label}{active ? <span aria-hidden="true"> {sortDirection === 'asc' ? '↑' : '↓'}</span> : null}
    </button></th>;
  }

  function financial(value: string, approximate = false) {
    const rendered = financialValue(value, privacyHidden);
    return <>{approximate && !privacyHidden ? '≈ ' : ''}{rendered}</>;
  }

  return <main className="market-page" aria-busy={busy}>
    <div className="market-heading">
      <div><div className="eyebrow">MERCADO SPOT</div><h1>Mercado</h1>
        <p className="muted">Criptomoedas negociáveis na Binance Spot · valores normalizados em USDT</p></div>
      <div className="market-actions">
        <button type="button" className="button button-quiet privacy-toggle" aria-pressed={privacyHidden}
          aria-label={privacyHidden ? 'Mostrar valores financeiros' : 'Ocultar valores financeiros'}
          title={privacyHidden ? 'Mostrar valores financeiros' : 'Ocultar valores financeiros'} onClick={onTogglePrivacy}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M2.5 12s3.3-6 9.5-6 9.5 6 9.5 6-3.3 6-9.5 6-9.5-6-9.5-6Z" /><circle cx="12" cy="12" r="2.5" />
            {privacyHidden && <path d="m4 4 16 16" />}
          </svg>
        </button>
        <button className="button button-secondary" onClick={() => void load(true)} disabled={busy}>
          {busy ? <Spinner /> : <span aria-hidden="true">↻</span>}{busy ? 'Atualizando…' : 'Atualizar mercado'}
        </button>
      </div>
    </div>
    {error && <Notice kind="error">{error}{snapshot && <span> A tabela mostra a última consulta concluída.</span>}</Notice>}
    <section className="panel market-controls" aria-label="Filtros do mercado">
      <label><span>Pesquisar moeda</span><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Ex.: BTC" /></label>
      <label><span>Filtrar par</span><input value={pairFilter} onChange={event => setPairFilter(event.target.value)} placeholder="Ex.: BTCUSDT" /></label>
      <div className="market-meta"><span>{filtered.length.toLocaleString('pt-BR')} ativos</span>
        <span>{snapshot ? `Atualizado ${updatedTime(snapshot.updated_at)}` : 'Aguardando dados'}</span></div>
    </section>
    <section className="panel market-table-panel" aria-label="Criptomoedas negociáveis">
      {busy && !snapshot ? <div className="market-loading"><Spinner /> Consultando dados públicos da Binance…</div> :
        <div className="table-scroll"><table className="market-table"><thead><tr>
          <th scope="col">Moeda</th>{sortButton('price_usdt', 'Preço USDT')}{sortButton('change_percent_24h', 'Variação 24h')}
          <th scope="col">Máxima 24h</th><th scope="col">Mínima 24h</th>{sortButton('volume_usdt_24h', 'Volume 24h USDT')}
          <th scope="col">Par utilizado</th>
        </tr></thead><tbody>
          {visible.map((asset: MarketAsset) => <tr key={asset.asset_id}>
            <th scope="row" className="market-coin">{asset.symbol}</th>
            <td>{asset.price_usdt === null ? '—' : financial(amount(asset.price_usdt, 8), asset.conversion_approximate)}</td>
            <td className={Number(asset.change_percent_24h) < 0 ? 'market-negative' : 'market-positive'}>
              {asset.change_percent_24h === null ? '—' : financial(`${amount(asset.change_percent_24h, 2)}%`, asset.conversion_approximate)}
            </td>
            <td>{asset.high_24h_usdt === null ? '—' : financial(amount(asset.high_24h_usdt, 8), asset.conversion_approximate)}</td>
            <td>{asset.low_24h_usdt === null ? '—' : financial(amount(asset.low_24h_usdt, 8), asset.conversion_approximate)}</td>
            <td>{asset.volume_usdt_24h === null ? '—' : financial(amount(asset.volume_usdt_24h, 2), asset.conversion_approximate)}</td>
            <td className="market-pair"><span>{asset.pair}</span>{asset.conversion_approximate && asset.conversion_path.length > 0
              && <small>≈ via {asset.conversion_path.join(' → ')}</small>}</td>
          </tr>)}
        </tbody></table>
          {visible.length === 0 && <div className="market-empty">{snapshot ? 'Nenhuma moeda corresponde aos filtros.' : 'Os dados de mercado ainda não estão disponíveis.'}</div>}
        </div>}
      <div className="market-pagination"><span>Página {Math.min(page + 1, pageCount)} de {pageCount}</span>
        <div><button className="button button-quiet" disabled={page <= 0 || busy} onClick={() => setPage(value => Math.max(0, value - 1))}>Anterior</button>
          <button className="button button-quiet" disabled={page + 1 >= pageCount || busy} onClick={() => setPage(value => Math.min(pageCount - 1, value + 1))}>Próxima</button></div>
      </div>
    </section>
  </main>;
}
