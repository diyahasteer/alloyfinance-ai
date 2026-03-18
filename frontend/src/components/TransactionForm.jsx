import { useState } from "react";

const SPENDING_CATEGORIES = [
  "groceries",
  "dining",
  "shopping",
  "subscriptions",
  "utilities",
  "rent",
  "healthcare",
  "transportation",
  "entertainment",
  "income",
  "other",
];

const PAYMENT_METHODS = [
  "credit_card",
  "debit_card",
  "bank_transfer",
  "mobile_wallet",
  "cash",
];

const INITIAL = {
  amount: "",
  merchant_name: "",
  merchant_category: "",
  spending_category: "groceries",
  transaction_type: "debit",
  payment_method: "debit_card",
  city: "",
  country: "US",
  currency: "USD",
  description: "",
};

export default function TransactionForm({ onSubmit }) {
  const [form, setForm] = useState(INITIAL);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const set = (field) => (e) =>
    setForm((prev) => ({ ...prev, [field]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({
        ...form,
        amount: parseFloat(form.amount),
        description: form.description || null,
      });
      setForm(INITIAL);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="txn-form" onSubmit={handleSubmit}>
      <h2>Add Transaction</h2>

      {error && <p className="form-error">{error}</p>}

      <div className="form-grid">
        <label className="field">
          <span>Amount</span>
          <input
            type="number"
            step="0.01"
            required
            placeholder="-42.50"
            value={form.amount}
            onChange={set("amount")}
          />
        </label>

        <label className="field">
          <span>Merchant</span>
          <input
            type="text"
            required
            placeholder="Trader Joe's"
            value={form.merchant_name}
            onChange={set("merchant_name")}
          />
        </label>

        <label className="field">
          <span>Merchant Category</span>
          <input
            type="text"
            required
            placeholder="supermarket"
            value={form.merchant_category}
            onChange={set("merchant_category")}
          />
        </label>

        <label className="field">
          <span>Spending Category</span>
          <select value={form.spending_category} onChange={set("spending_category")}>
            {SPENDING_CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Type</span>
          <select value={form.transaction_type} onChange={set("transaction_type")}>
            <option value="debit">Debit</option>
            <option value="credit">Credit</option>
          </select>
        </label>

        <label className="field">
          <span>Payment Method</span>
          <select value={form.payment_method} onChange={set("payment_method")}>
            {PAYMENT_METHODS.map((m) => (
              <option key={m} value={m}>
                {m.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>City</span>
          <input
            type="text"
            required
            placeholder="Berkeley"
            value={form.city}
            onChange={set("city")}
          />
        </label>

        <label className="field field-wide">
          <span>Description</span>
          <input
            type="text"
            placeholder="Weekly grocery run (for search later)"
            value={form.description}
            onChange={set("description")}
          />
        </label>
      </div>

      <button type="submit" className="btn btn-primary" disabled={submitting}>
        {submitting ? "Adding..." : "Add Transaction"}
      </button>
    </form>
  );
}
