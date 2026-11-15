import type { WalletSummary } from '../services/api';
import { decimal } from '../services/format';

const FEATURED = [
  ['spot', 'Spot'],
  ['earn_flexible', 'Earn Flexible'],
  ['earn_locked', 'Earn Locked'],
  ['funding', 'Funding'],
] as const;

export function WalletSummaryGrid({ wallets }: { wallets: WalletSummary[] }) {
  if (wallets.length === 0) return null;
  const byId = new Map(wallets.map(wallet => [wallet.wallet_id, wallet]));
  const featured = FEATURED.flatMap(([id, title]) => {
    const wallet = byId.get(id);
    return wallet ? [{ ...wallet, title }] : [];
  });
  const featuredIds = new Set<string>(FEATURED.map(([id]) => id));
  const other = wallets.filter(wallet => !featuredIds.has(wallet.wallet_id));
  const cards = [...featured, ...other.map(wallet => ({ ...wallet, title: wallet.name }))];

  return <section className="wallet-summary" aria-label="Subtotais por carteira">
    <div className="section-heading wallet-summary-heading"><h2>Subtotais por carteira</h2>
      <span className="muted">Fontes consultadas separadamente</span></div>
    <div className="wallet-grid">
      {cards.map(wallet => <article className="panel wallet-card" key={wallet.wallet_id}>
        <div className="wallet-card-heading"><span>{wallet.title}</span>
          {wallet.status === 'partial' && <span className="wallet-status wallet-status-partial">Parcial</span>}</div>
        <div className="wallet-value">{wallet.total_usdt === null ? '—' : decimal(wallet.total_usdt, 2)} <small>USDT</small></div>
        <div className="wallet-meta">{wallet.asset_count} {wallet.asset_count === 1 ? 'ativo' : 'ativos'} com saldo</div>
      </article>)}
    </div>
  </section>;
}
