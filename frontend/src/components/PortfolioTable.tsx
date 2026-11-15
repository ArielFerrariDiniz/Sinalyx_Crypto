import type { Asset } from '../services/api';
import { decimal } from '../services/format';

export function PortfolioTable({ assets }: { assets: Asset[] }) {
  return (
    <section className="panel holdings">
      <div className="section-heading"><h2>Ativos consolidados</h2><span className="muted">Saldos por carteira · estimativa em USDT</span></div>
      {assets.length === 0 ? (
        <div className="empty-state"><span className="empty-icon" aria-hidden="true">◇</span>
          <h3>Nenhum saldo confirmado</h3><p>As carteiras consultadas não retornaram posições com saldo positivo.</p></div>
      ) : <div className="table-scroll" tabIndex={0} role="region" aria-label="Tabela consolidada de ativos Binance">
        <table>
          <caption className="sr-only">Saldos consolidados por ativo e origem, valores estimados em USDT</caption>
          <thead><tr><th scope="col">Ativo</th><th scope="col">Carteiras / origem</th><th scope="col">Disponível</th>
            <th scope="col">Bloqueado</th><th scope="col">Aplicado</th><th scope="col">Passivo</th>
            <th scope="col">Total líquido</th><th scope="col">Preço USDT</th><th scope="col">Valor USDT</th></tr></thead>
          <tbody>{assets.map(asset => <tr key={asset.asset}>
            <th scope="row"><span className="asset-symbol">{asset.asset}</span></th>
            <td className="source-cell"><div className="source-list">{asset.sources.map((source, index) => <div className="source-item" key={`${source.wallet_id}-${index}`}>
              <strong>{source.wallet}</strong>
              <span>Disponível {decimal(source.available)} · bloqueado {decimal(source.locked)} · aplicado {decimal(source.applied)}
                {source.liability !== '0' && <> · passivo {decimal(source.liability)}</>}</span>
              {source.position_details.map(detail => <small className="position-detail" key={detail}>{detail}</small>)}
              {source.reward_notes.map(note => <small className="reward-note" key={note}>{note}</small>)}
            </div>)}</div></td>
            <td title={asset.free}>{decimal(asset.free)}</td>
            <td title={asset.locked} className="muted">{decimal(asset.locked)}</td>
            <td title={asset.applied}>{decimal(asset.applied)}</td>
            <td title={asset.liability}>{asset.liability === '0' ? '—' : decimal(asset.liability)}</td>
            <td title={asset.net_total}>{decimal(asset.net_total)}</td>
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
