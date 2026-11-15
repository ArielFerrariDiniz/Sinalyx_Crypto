import type { Asset, AssetSource } from '../services/api';
import { earnDisplayValues, isEarnSource } from '../services/earnDisplay';
import { decimal } from '../services/format';
import { splitAssetsByQuoteAvailability } from '../services/portfolioView';

export function PortfolioTable({ assets, emptyMessage }: { assets: Asset[]; emptyMessage: string }) {
  const { priced, unpriced } = splitAssetsByQuoteAvailability(assets);

  return (
    <section className="panel holdings">
      <div className="section-heading"><h2>Ativos consolidados</h2><span className="muted">Saldos por carteira · estimativa em USDT</span></div>
      {priced.length === 0 ? (
        <div className="empty-state"><span className="empty-icon" aria-hidden="true">◇</span>
          <h3>{unpriced.length ? 'Nenhum ativo com cotação disponível' : 'Nenhum ativo detalhado'}</h3>
          <p>{unpriced.length ? 'Os saldos sem cotação estão em “Outros ativos”.' : emptyMessage}</p></div>
      ) : <AssetTable assets={priced} label="Tabela consolidada de ativos com cotação Binance" />}

      {unpriced.length > 0 && <details className="other-assets">
        <summary><span>Outros ativos</span><span className="other-assets-count">{unpriced.length} sem cotação · fora da estimativa</span></summary>
        <AssetTable assets={unpriced} label="Tabela de outros ativos sem cotação" />
      </details>}
    </section>
  );
}

function AssetTable({ assets, label }: { assets: Asset[]; label: string }) {
  return <div className="table-scroll" tabIndex={0} role="region" aria-label={label}>
    <table>
      <caption className="sr-only">Saldos por ativo e origem, valores estimados em USDT</caption>
      <thead><tr><th scope="col">Ativo</th><th scope="col">Carteiras / origem</th><th scope="col">Disponível</th>
        <th scope="col">Bloqueado</th><th scope="col">Aplicado</th><th scope="col">Passivo</th>
        <th scope="col">Total líquido</th><th scope="col">Preço USDT</th><th scope="col">Valor USDT</th></tr></thead>
      <tbody>{assets.map(asset => <tr key={asset.asset}>
        <th scope="row"><span className="asset-symbol">{asset.asset}</span></th>
        <td className="source-cell"><div className="source-list">{asset.sources.map((source, index) => <SourceDetails
          source={source} asset={asset} key={`${source.wallet_id}-${index}`} />)}</div></td>
        <td title={asset.free}>{decimal(asset.free)}</td>
        <td title={asset.locked} className="muted">{decimal(asset.locked)}</td>
        <td title={asset.applied}>{decimal(asset.applied)}</td>
        <td title={asset.liability}>{asset.liability === '0' ? '—' : decimal(asset.liability)}</td>
        <td title={asset.net_total}>{decimal(asset.net_total)}</td>
        <td title={asset.price_usdt === null ? 'Saldo positivo sem cotação confiável.' : asset.price_usdt ?? undefined}>{asset.price_usdt === null
          ? <span className="unpriced">Sem cotação</span>
          : <>{decimal(asset.price_usdt, 8)}{asset.conversion_path && asset.conversion_path.length > 2 &&
            <span className="conversion">via {asset.conversion_path.slice(1, -1).join(' → ')}</span>}</>}</td>
        <td className="asset-value" title={asset.value_usdt === null ? 'Mantido visível, mas fora do patrimônio estimado por falta de cotação.' : asset.value_usdt ?? undefined}>{asset.value_usdt === null
          ? <span className="unpriced">Fora da estimativa</span> : decimal(asset.value_usdt, 2)}</td>
      </tr>)}</tbody>
    </table>
  </div>;
}

function SourceDetails({ source, asset }: { source: AssetSource; asset: Asset }) {
  if (isEarnSource(source)) {
    const values = earnDisplayValues(source);
    return <div className="source-item earn-source-item">
      <strong>{source.wallet}</strong>
      <span className="earn-applied">Aplicado {decimal(source.applied)} {asset.asset}</span>
      <dl className="earn-metrics">
        <div><dt>APR atual</dt><dd>{values.apr}</dd></div>
        <div><dt>Rendimento de ontem</dt><dd>{values.yesterday}</dd></div>
        <div><dt>Recompensas acumuladas</dt><dd>{values.cumulativeRewards}</dd></div>
      </dl>
    </div>;
  }

  return <div className="source-item">
    <strong>{source.wallet}</strong>
    <span>Disponível {decimal(source.available)} · bloqueado {decimal(source.locked)} · aplicado {decimal(source.applied)}
      {source.liability !== '0' && <> · passivo {decimal(source.liability)}</>}</span>
    {source.position_details.map(detail => <small className="position-detail" key={detail}>{detail}</small>)}
    {source.reward_notes.length > 0 && <div className="source-rewards">
      {source.reward_notes.map(note => <small className="reward-note" key={note}>{note}</small>)}
    </div>}
  </div>;
}
