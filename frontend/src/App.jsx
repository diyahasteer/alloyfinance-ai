import { useState } from "react";
import { useTransactions } from "./hooks/useTransactions";
import TransactionForm from "./components/TransactionForm";
import TransactionTable from "./components/TransactionTable";

const CATEGORIES = [
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
];

export default function App() {
  const {
    transactions,
    loading,
    error,
    activeFilter,
    fetchRecent,
    fetchByCategory,
    fetchCurrentMonth,
    fetchPreviousMonth,
    createTransaction,
  } = useTransactions();

  const [showForm, setShowForm] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState("");

  const handleCategoryChange = (e) => {
    const val = e.target.value;
    setCategoryFilter(val);
    if (val) fetchByCategory(val);
    else fetchRecent();
  };

  const handleCreate = async (txn) => {
    await createTransaction(txn);
    setShowForm(false);
  };

  const filterLabel = () => {
    if (activeFilter === "recent") return "Recent transactions";
    if (activeFilter === "current-month") return "Current month";
    if (activeFilter === "previous-month") return "Previous month";
    if (activeFilter.startsWith("category:"))
      return `Category: ${activeFilter.split(":")[1]}`;
    return "Transactions";
  };

  return (
    <div className="app">
      <header className="header">
        <h1>AlloyFinance</h1>
        <p className="header-sub">Transaction Tracker</p>
      </header>

      <main className="main">
        {/* Controls bar */}
        <section className="controls">
          <div className="filter-group">
            <button
              className={`btn btn-filter ${activeFilter === "recent" ? "active" : ""}`}
              onClick={() => { setCategoryFilter(""); fetchRecent(); }}
            >
              Recent
            </button>
            <button
              className={`btn btn-filter ${activeFilter === "current-month" ? "active" : ""}`}
              onClick={() => { setCategoryFilter(""); fetchCurrentMonth(); }}
            >
              This Month
            </button>
            <button
              className={`btn btn-filter ${activeFilter === "previous-month" ? "active" : ""}`}
              onClick={() => { setCategoryFilter(""); fetchPreviousMonth(); }}
            >
              Last Month
            </button>

            <select
              className="category-select"
              value={categoryFilter}
              onChange={handleCategoryChange}
            >
              <option value="">All Categories</option>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>

          <button
            className="btn btn-primary"
            onClick={() => setShowForm((s) => !s)}
          >
            {showForm ? "Cancel" : "+ New Transaction"}
          </button>
        </section>

        {/* Form (collapsible) */}
        {showForm && (
          <section className="card">
            <TransactionForm onSubmit={handleCreate} />
          </section>
        )}

        {/* Error */}
        {error && <p className="global-error">{error}</p>}

        {/* Table */}
        <section className="card">
          <div className="table-header">
            <h2>{filterLabel()}</h2>
            <span className="txn-count">{transactions.length} transactions</span>
          </div>
          <TransactionTable transactions={transactions} loading={loading} />
        </section>
      </main>
    </div>
  );
}
