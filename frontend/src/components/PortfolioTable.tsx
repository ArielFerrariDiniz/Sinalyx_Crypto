import type { Asset } from '../services/api';
import { earnDisplayValues, isEarnSource } from '../services/earnDisplay';
import { formatMoney, type DisplayCurrency } from '../services/currency';
import { decimal } from '../services/format';
import { splitAssetsByQuoteAvailability } from '../services/portfolioView';
import { financialValue } from '../services/privacy';

export function PortfolioTable({ assets, emptyMessage, currency, usdtBrlRate, privacyHidden }: {
  assets: Asset[]; emptyMessage: string; currency: DisplayCurrency; usdtBrlRate: string | null; privacyHidden: boolean;
}) {
  const { priced, unpriced } = splitAssetsByQuoteAvailability(assets);

  return (
    <section className="panel holdings">
      <div className="section-heading"><h2>Ativos consolidados</h2><span className="muted">Saldos consolidados · estimativa em {currency === 'USD' ? 'USDT' : 'BRL'}</span></div>
      {priced.length === 0 ? (
        <div className="empty-state"><span className="empty-icon" aria-hidden="true">◇</span>
          <h3>{unpriced.length ? 'Nenhum ativo com cotação disponível' : 'Nenhum ativo detalhado'}</h3>
          <p>{unpriced.length ? 'Os saldos sem cotação estão em “Outros ativos”.' : emptyMessage}</p></div>
      ) : <AssetTable assets={priced} label="Tabela consolidada de ativos com cotação Binance"
        currency={currency} usdtBrlRate={usdtBrlRate} privacyHidden={privacyHidden} />}

      {unpriced.length > 0 && <details className="other-assets">
        <summary><span>Outros ativos</span><span className="other-assets-count">{unpriced.length} sem cotação · fora da estimativa</span></summary>
        <AssetTable assets={unpriced} label="Tabela de outros ativos sem cotação"
          currency={currency} usdtBrlRate={usdtBrlRate} privacyHidden={privacyHidden} />
      </details>}
    </section>
  );
}

function AssetTable({ assets, label, currency, usdtBrlRate, privacyHidden }: {
  assets: Asset[]; label: string; currency: DisplayCurrency; usdtBrlRate: string | null; privacyHidden: boolean;
}) {
  const valueUnit = currency === 'USD' ? 'USDT' : 'BRL';
  return <div className="table-scroll" tabIndex={0} role="region" aria-label={label}>
    <table>
      <caption className="sr-only">Saldos por ativo e origem, valores estimados em {valueUnit}</caption>
      <thead>
        <tr>{[
            'Ativo',
            'Origem',
            'Disponível',
            'Bloqueado',
            'Aplicado',
            'Passivo',
            'Total líquido',
            `Preço ${valueUnit}`,
            `Valor ${valueUnit}`,
          ].map(header => <th key={header} scope="col" style={{ textAlign: 'center' }}>{header}</th>)}
        </tr>
      </thead>
      <tbody>{assets.map(asset => <tr key={asset.asset}>
        <th scope="row"><span className="asset-symbol">{asset.asset}</span></th>
        <td className="source-cell"><div className="source-list">
          <span className="source-origin">Binance</span>
          <EarnMetrics asset={asset} privacyHidden={privacyHidden} />
        </div></td>
        <td title={privacyHidden ? undefined : asset.free}>{financialValue(decimal(asset.free), privacyHidden)}</td>
        <td title={privacyHidden ? undefined : asset.locked} className="muted">{financialValue(decimal(asset.locked), privacyHidden)}</td>
        <td title={privacyHidden ? undefined : asset.applied}>{financialValue(decimal(asset.applied), privacyHidden)}</td>
        <td title={privacyHidden ? undefined : asset.liability}>{financialValue(asset.liability === '0' ? '—' : decimal(asset.liability), privacyHidden)}</td>
        <td title={privacyHidden ? undefined : asset.net_total}>{financialValue(decimal(asset.net_total), privacyHidden)}</td>
        <td title={privacyHidden ? undefined : asset.price_usdt === null ? 'Saldo positivo sem cotação confiável.' : asset.price_usdt ?? undefined}>
          {asset.price_usdt === null
            ? <span className="unpriced">{financialValue('Sem cotação', privacyHidden)}</span>
            : privacyHidden ? financialValue('', true)
              : formatMoney(asset.price_usdt, currency, usdtBrlRate, 8) ?? <span className="muted">—</span>}
          {asset.price_usdt !== null && !privacyHidden && currency === 'USD' && asset.conversion_path && asset.conversion_path.length > 2 &&
            <span className="conversion">via {asset.conversion_path.slice(1, -1).join(' → ')}</span>}
        </td>
        <td className="asset-value" title={privacyHidden ? undefined : asset.value_usdt === null ? 'Mantido visível, mas fora do patrimônio estimado por falta de cotação.' : asset.value_usdt ?? undefined}>
          {privacyHidden ? financialValue('', true) : asset.value_usdt === null
            ? <span className="unpriced">Fora da estimativa</span>
            : formatMoney(asset.value_usdt, currency, usdtBrlRate, 2) ?? <span className="muted">—</span>}
        </td>
      </tr>)}</tbody>
    </table>
  </div>;
}

function EarnMetrics({ asset, privacyHidden }: { asset: Asset; privacyHidden: boolean }) {
  const values = asset.sources.filter(isEarnSource).map(earnDisplayValues);
  if (values.length === 0) return null;

  return <dl className="earn-metrics">
    <div><dt>APR atual:</dt><dd>{financialValue(values.map(item => item.apr).join(' · '), privacyHidden)}</dd></div>
    <div><dt>Rendimento de ontem:</dt><dd>{financialValue(values.map(item => item.yesterday).join(' · '), privacyHidden)}</dd></div>
    <div><dt>Recompensas acumuladas:</dt><dd>{financialValue(values.map(item => item.cumulativeRewards).join(' · '), privacyHidden)}</dd></div>
  </dl>;
}
