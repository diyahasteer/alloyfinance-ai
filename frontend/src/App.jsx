import { useState, useEffect, useCallback } from "react";
import { GoogleLogin } from "@react-oauth/google";
import { useTransactions } from "./hooks/useTransactions";
import TransactionForm from "./components/TransactionForm";
import TransactionTable from "./components/TransactionTable";
import NL2SQLPanel from "./components/NL2SQLPanel";

const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

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

function useAuth() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const checkAuth = useCallback(async () => {
    const token = localStorage.getItem("token");
    if (!token) {
      setLoading(false);
      return;
    }
    try {
      const res = await fetch(`${BASE_URL}/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        setUser(await res.json());
      } else {
        localStorage.removeItem("token");
      }
    } catch {
      localStorage.removeItem("token");
    }
    setLoading(false);
  }, []);

  useEffect(() => { checkAuth(); }, [checkAuth]);

  const login = async (credential) => {
    const res = await fetch(`${BASE_URL}/auth/google`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credential }),
    });
    if (!res.ok) throw new Error("Login failed");
    const data = await res.json();
    localStorage.setItem("token", data.token);
    setUser(data.user);
  };

  const logout = () => {
    localStorage.removeItem("token");
    setUser(null);
  };

  return { user, loading, login, logout };
}

export default function App() {
  const auth = useAuth();

  if (auth.loading) {
    return (
      <div className="app">
        <div className="login-container">
          <p style={{ color: "#64748b" }}>Loading...</p>
        </div>
      </div>
    );
  }

  if (!auth.user) {
    return <LoginScreen onLogin={auth.login} />;
  }

  return <Dashboard auth={auth} />;
}

function LoginScreen({ onLogin }) {
  const [error, setError] = useState(null);

  return (
    <div className="app">
      <div className="login-container">
        <div className="login-card">
          <h1 className="login-title">AlloyFinance</h1>
          <p className="login-sub">Sign in to manage your transactions</p>
          {error && <p className="global-error">{error}</p>}
          <div className="login-button-wrap">
            <GoogleLogin
              onSuccess={async (response) => {
                try {
                  await onLogin(response.credential);
                } catch {
                  setError("Login failed. Please try again.");
                }
              }}
              onError={() => setError("Google sign-in failed.")}
              theme="outline"
              size="large"
              width="300"
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function Dashboard({ auth }) {
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

  const [tab, setTab] = useState("transactions");
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
        <div className="header-row">
          <div>
            <h1>AlloyFinance</h1>
            <p className="header-sub">Transaction Tracker</p>
          </div>
          <div className="user-info">
            {auth.user.picture && (
              <img className="avatar" src={auth.user.picture} alt="" referrerPolicy="no-referrer" />
            )}
            <span className="user-name">{auth.user.name}</span>
            <button className="btn btn-logout" onClick={auth.logout}>
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="main">
        <div className="filter-group">
          <button
            className={`btn btn-filter ${tab === "transactions" ? "active" : ""}`}
            onClick={() => setTab("transactions")}
          >
            Transactions
          </button>
          <button
            className={`btn btn-filter ${tab === "nl2sql" ? "active" : ""}`}
            onClick={() => setTab("nl2sql")}
          >
            NL2SQL
          </button>
        </div>

        {tab === "nl2sql" && <NL2SQLPanel />}

        {tab === "transactions" && (
          <>
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

            {showForm && (
              <section className="card">
                <TransactionForm onSubmit={handleCreate} />
              </section>
            )}

            {error && <p className="global-error">{error}</p>}

            <section className="card">
              <div className="table-header">
                <h2>{filterLabel()}</h2>
                <span className="txn-count">{transactions.length} transactions</span>
              </div>
              <TransactionTable transactions={transactions} loading={loading} />
            </section>
          </>
        )}
      </main>
    </div>
  );
}
