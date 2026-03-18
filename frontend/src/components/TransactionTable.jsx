function formatDate(iso) {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatAmount(amount) {
  const num = typeof amount === "string" ? parseFloat(amount) : amount;
  const isNeg = num < 0;
  const formatted = Math.abs(num).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
  });
  return (
    <span className={isNeg ? "amount-neg" : "amount-pos"}>
      {isNeg ? `-${formatted}` : `+${formatted}`}
    </span>
  );
}

function categoryBadge(category) {
  return <span className={`badge badge-${category}`}>{category}</span>;
}

export default function TransactionTable({ transactions, loading }) {
  if (loading) {
    return <p className="table-status">Loading transactions...</p>;
  }

  if (transactions.length === 0) {
    return <p className="table-status">No transactions found for this filter.</p>;
  }

  return (
    <div className="table-wrap">
      <table className="txn-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Merchant</th>
            <th>Category</th>
            <th>Amount</th>
            <th>Payment</th>
            <th>City</th>
            <th>Description</th>
          </tr>
        </thead>
        <tbody>
          {transactions.map((t) => (
            <tr key={t.transaction_id}>
              <td className="cell-date">{formatDate(t.timestamp)}</td>
              <td className="cell-merchant">{t.merchant_name}</td>
              <td>{categoryBadge(t.spending_category)}</td>
              <td className="cell-amount">{formatAmount(t.amount)}</td>
              <td className="cell-payment">{t.payment_method.replace(/_/g, " ")}</td>
              <td>{t.city}</td>
              <td className="cell-desc">{t.description || "\u2014"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
