import type { Asset } from '../services/api';
import { decimal } from '../services/format';

export function PortfolioTable({ assets }: { assets: Asset[] }) {
  return (
    <section className="panel holdings">
      <div className="section-heading"><h2>Seus ativos</h2><span className="muted">Saldos positivos · Spot</span></div>
      {assets.length === 0 ? (
        <div className="empty-state"><span className="empty-icon" aria-hidden="true">◇</span>
          <h3>Sua carteira Spot está vazia</h3><p>Nenhum ativo com saldo positivo foi encontrado nesta conta.</p></div>
      ) : <div className="table-scroll" tabIndex={0} role="region" aria-label="Tabela de ativos da carteira Spot">
        <table>
          <caption className="sr-only">Saldos e valores estimados dos ativos da carteira Spot em USDT</caption>
          <thead><tr><th scope="col">Ativo</th><th scope="col">Disponível</th><th scope="col">Bloqueado</th>
            <th scope="col">Total</th><th scope="col">Preço USDT</th><th scope="col">Valor USDT</th></tr></thead>
          <tbody>{assets.map(asset => <tr key={asset.asset}>
            <th scope="row"><span className="asset-symbol">{asset.asset}</span></th>
            <td title={asset.free}>{decimal(asset.free)}</td>
            <td title={asset.locked} className="muted">{decimal(asset.locked)}</td>
            <td title={asset.total}>{decimal(asset.total)}</td>
            <td title={asset.price_usdt ?? undefined}>{asset.price_usdt === null
              ? <span className="unpriced">Cotação indisponível</span>
              : <>{decimal(asset.price_usdt, 8)}{asset.conversion_path && asset.conversion_path.length > 2 &&
                <span className="conversion">via {asset.conversion_path.slice(1, -1).join(' → ')}</span>}</>}</td>
            <td className="asset-value" title={asset.value_usdt ?? undefined}>{asset.value_usdt === null
              ? <span className="unpriced">Não incluído</span> : decimal(asset.value_usdt, 2)}</td>
          </tr>)}</tbody>
        </table>
      </div>}
    </section>
  );
}
