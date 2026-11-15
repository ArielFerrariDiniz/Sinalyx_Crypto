import type { Asset } from '../services/api';
import { earnDisplayValues, isEarnSource } from '../services/earnDisplay';
import { decimal } from '../services/format';
import { splitAssetsByQuoteAvailability } from '../services/portfolioView';

export function PortfolioTable({ assets, emptyMessage }: { assets: Asset[]; emptyMessage: string }) {
  const { priced, unpriced } = splitAssetsByQuoteAvailability(assets);

  return (
    <section className="panel holdings">
      <div className="section-heading"><h2>Ativos consolidados</h2><span className="muted">Saldos consolidados · estimativa em USDT</span></div>
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
      <thead>
        <tr>{[
            "Ativo",
            "Origem",
            "Disponível",
            "Bloqueado",
            "Aplicado",
            "Passivo",
            "Total líquido",
            "Preço USDT",
            "Valor USDT"
          ].map(header => (
            <th
              key={header}
              scope="col"
              style={{ textAlign: "center" }}
            >
              {header}
            </th>))}
        </tr>
      </thead>
      <tbody>{assets.map(asset => <tr key={asset.asset}>
        <th scope="row"><span className="asset-symbol">{asset.asset}</span></th>
        <td className="source-cell"><div className="source-list">
          <span className="source-origin">Binance</span>
          <EarnMetrics asset={asset} />
        </div></td>
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

function EarnMetrics({ asset }: { asset: Asset }) {
  const values = asset.sources.filter(isEarnSource).map(earnDisplayValues);
  if (values.length === 0) return null;

  return <dl className="earn-metrics">
    <div><dt>APR atual:</dt><dd>{values.map(item => item.apr).join(' · ')}</dd></div>
    <div><dt>Rendimento de ontem:</dt><dd>{values.map(item => item.yesterday).join(' · ')}</dd></div>
    <div><dt>Recompensas acumuladas:</dt><dd>{values.map(item => item.cumulativeRewards).join(' · ')}</dd></div>
  </dl>;
}
