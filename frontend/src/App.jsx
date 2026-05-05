import { useState, useEffect, useCallback, useMemo } from "react";
import { useTransactions } from "./hooks/useTransactions";
import TransactionForm from "./components/TransactionForm";
import TransactionTable from "./components/TransactionTable";
import NL2SQLPanel from "./components/NL2SQLPanel";
import MonthlyReportsPanel from "./components/MonthlyReportsPanel";
import { searchApi } from "./api/search";

const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const CATEGORIES = [
  "groceries", "dining", "shopping", "subscriptions", "utilities",
  "rent", "healthcare", "transportation", "entertainment", "income",
];
const TRANSACTION_TYPES = ["debit", "credit", "transfer", "refund"];
const PAYMENT_METHODS = ["credit_card", "debit_card", "bank_transfer", "cash", "mobile_wallet"];

const CAT_COLORS = {
  groceries:     "#22C55E",
  dining:        "#F59E0B",
  shopping:      "#FBBF24",
  rent:          "#3B5998",
  entertainment: "#F43F5E",
  healthcare:    "#14B8A6",
  subscriptions: "#6366F1",
  utilities:     "#8B5CF6",
  transportation:"#0EA5E9",
  income:        "#10B981",
};

function catColor(cat) { return CAT_COLORS[cat] || "#94A3B8"; }
function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }
function fmt(n) {
  return Math.abs(n).toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function useAuth() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const checkAuth = useCallback(async () => {
    const token = localStorage.getItem("token");
    if (!token) { setLoading(false); return; }
    try {
      const res = await fetch(`${BASE_URL}/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) { setUser(await res.json()); } else { localStorage.removeItem("token"); }
    } catch { localStorage.removeItem("token"); }
    setLoading(false);
  }, []);

  useEffect(() => { checkAuth(); }, [checkAuth]);

  const login = async (email, password) => {
    const res = await fetch(`${BASE_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Login failed");
    }
    const data = await res.json();
    localStorage.setItem("token", data.token);
    setUser(data.user);
  };

  const signup = async (name, email, password) => {
    const res = await fetch(`${BASE_URL}/auth/signup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Signup failed");
    }
    const data = await res.json();
    localStorage.setItem("token", data.token);
    setUser(data.user);
  };

  const logout = () => { localStorage.removeItem("token"); setUser(null); };

  return { user, loading, login, signup, logout };
}

/* ---- Spending bar chart ---- */
function SpendingChart({ data }) {
  if (!data.length) return null;
  const maxVal = data[0][1];
  return (
    <div className="spending-chart">
      {data.map(([cat, val]) => {
        const pct = Math.max((val / maxVal) * 100, 4);
        return (
          <div key={cat} className="chart-row">
            <span className="chart-label">{cap(cat)}</span>
            <div className="chart-bar-wrap">
              <div className="chart-bar" style={{ width: `${pct}%`, background: catColor(cat) }}>
                <span className="chart-bar-val">{fmt(val)}</span>
              </div>
            </div>
          </div>
        );
      })}
      <div className="chart-legend">
        {data.map(([cat]) => (
          <span key={cat} className="legend-item">
            <span className="legend-dot" style={{ background: catColor(cat) }} />
            {cap(cat)}
          </span>
        ))}
      </div>
    </div>
  );
}


function Logo() {
  return (
    <div className="logo">
      <span className="brand">AlloyFinance</span>
    </div>
  );
}

export default function App() {
  const auth = useAuth();

  if (auth.loading) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", color: "#64748b" }}>
        Loading…
      </div>
    );
  }

  if (!auth.user) return <LoginScreen auth={auth} />;
  return <Dashboard auth={auth} />;
}

function LoginScreen({ auth }) {
  const [mode, setMode] = useState("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("foo@bar.com");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      if (mode === "signup") await auth.signup(name, email, password);
      else await auth.login(email, password);
    } catch (err) {
      setError(err.message || "Authentication failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-brand">AlloyFinance</div>
        <p className="login-sub">
          {mode === "signup" ? "Create your account" : "Log in to your Account"}
        </p>
        {error && <p className="global-error">{error}</p>}
        <form className="auth-form" onSubmit={handleSubmit}>
          {mode === "signup" && (
            <label className="field">
              <span>Name (optional)</span>
              <input value={name} onChange={(e) => setName(e.target.value)} type="text" placeholder="Jane Doe" />
            </label>
          )}
          <label className="field">
            <span>Email</span>
            <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" placeholder="foo@bar.com" required />
          </label>
          <label className="field">
            <span>Password</span>
            <div className="password-input-wrap">
              <input
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                type={showPassword ? "text" : "password"}
                placeholder="••••••••"
                required
                minLength={8}
              />
              <button type="button" className="password-toggle" onClick={() => setShowPassword((p) => !p)}>
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
          </label>
          <button className="btn btn-primary auth-submit" type="submit" disabled={submitting}>
            {submitting ? "Please wait…" : mode === "signup" ? "Create account" : "Sign in"}
          </button>
        </form>
        <button
          className="auth-toggle"
          type="button"
          onClick={() => { setMode((m) => (m === "login" ? "signup" : "login")); setError(""); }}
        >
          {mode === "signup" ? "Already have an account? Sign in" : "Need an account? Sign up"}
        </button>
      </div>
    </div>
  );
}

function Dashboard({ auth }) {
  const {
    transactions, loading, error, activeFilter,
    fetchRecent, fetchByCategory, fetchCurrentMonth, fetchPreviousMonth, fetchAll, createTransaction,
  } = useTransactions();

  const [tab, setTab] = useState("transactions");
  const [showForm, setShowForm] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [paymentFilter, setPaymentFilter] = useState("");

  const handleCategoryChange = (e) => {
    const val = e.target.value;
    setCategoryFilter(val);
    if (activeFilter === "all-time") return;
    if (val) fetchByCategory(val);
    else fetchRecent();
  };

  const filteredTransactions = useMemo(() => {
    if (activeFilter !== "all-time") return transactions;
    return transactions.filter((t) => {
      if (categoryFilter && t.spending_category !== categoryFilter) return false;
      if (typeFilter && t.transaction_type !== typeFilter) return false;
      if (paymentFilter && t.payment_method !== paymentFilter) return false;
      return true;
    });
  }, [activeFilter, transactions, categoryFilter, typeFilter, paymentFilter]);

  const stats = useMemo(() => {
    const income = filteredTransactions
      .filter((t) => parseFloat(t.amount) > 0)
      .reduce((s, t) => s + parseFloat(t.amount), 0);
    const expenses = filteredTransactions
      .filter((t) => parseFloat(t.amount) < 0)
      .reduce((s, t) => s + Math.abs(parseFloat(t.amount)), 0);
    return { income, expenses, remaining: income - expenses };
  }, [filteredTransactions]);

  const categorySpending = useMemo(() => {
    const map = {};
    filteredTransactions.forEach((t) => {
      const amt = parseFloat(t.amount);
      if (amt < 0) {
        const cat = t.spending_category || "other";
        map[cat] = (map[cat] || 0) + Math.abs(amt);
      }
    });
    return Object.entries(map).sort((a, b) => b[1] - a[1]).slice(0, 7);
  }, [filteredTransactions]);

  const handleCreate = async (txn) => {
    await createTransaction(txn);
    setShowForm(false);
  };

  const handleSearch = async (e) => {
    e?.preventDefault();
    if (!searchQuery.trim()) return;
    setSearchLoading(true);
    setSearchError("");
    setSearchResults(null);
    try {
      const results = await searchApi.search(searchQuery.trim());
      setSearchResults(results);
    } catch (err) {
      setSearchError(err.message);
    } finally {
      setSearchLoading(false);
    }
  };

  const filterLabel = () => {
    if (activeFilter === "recent") return "Recent transactions";
    if (activeFilter === "all-time") return "All time";
    if (activeFilter === "current-month") return "Current month";
    if (activeFilter === "previous-month") return "Previous month";
    if (activeFilter.startsWith("category:")) return `Category: ${activeFilter.split(":")[1]}`;
    return "Transactions";
  };

  const chartTitle = () => {
    if (activeFilter === "recent") return "Recent Spending by Category";
    if (activeFilter === "current-month") return "This Month's Spending";
    if (activeFilter === "previous-month") return "Last Month's Spending";
    if (activeFilter === "all-time") return "All Time Spending";
    return "Spending by Category";
  };

  const periodLabel = () => {
    if (activeFilter === "recent") return "Recent transactions";
    if (activeFilter === "current-month") return "This month only";
    if (activeFilter === "previous-month") return "Last month only";
    if (activeFilter === "all-time") return "All time total";
    return "Selected period";
  };

  return (
    <div className="app-shell">
      {/* Navbar */}
      <nav className="navbar">
        <div className="navbar-inner">
          <Logo />
          <div className="nav-links">
            {[
              ["transactions", "Transactions"],
              ["monthly-reports", "Monthly Reports"],
              ["nl2sql", "NL2SQL"],
              ["search", "Semantic Search"],
            ].map(([t, label]) => (
              <button
                key={t}
                className={`nav-link${tab === t ? " active" : ""}`}
                onClick={() => setTab(t)}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="nav-user">
            {auth.user.picture && (
              <img className="avatar" src={auth.user.picture} alt="" referrerPolicy="no-referrer" />
            )}
            <span className="user-name">{auth.user.name || auth.user.email}</span>
            <button className="btn-signout" onClick={auth.logout}>Sign Out</button>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <div className="hero">
        <h1 className="hero-title">My Budget Dashboard</h1>
        <p className="hero-sub">Tracking your income, spending, and savings</p>
        {tab === "transactions" && (
          <button className="btn-hero" onClick={() => setShowForm(true)}>
            + New Transaction
          </button>
        )}
      </div>

      {/* New Transaction Modal */}
      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setShowForm(false)} aria-label="Close">✕</button>
            <TransactionForm onSubmit={handleCreate} />
          </div>
        </div>
      )}

      {/* Page content */}
      <div className="page-wrap">
        {tab === "transactions" && (
          <>
            {/* Spending chart — updates per active filter */}
            {categorySpending.length > 0 && (
              <div className="card">
                <div className="table-header">
                  <div>
                    <h2>{chartTitle()}</h2>
                    <p className="chart-total">{fmt(stats.expenses)} total · {categorySpending.length} categories</p>
                  </div>
                  <span className="stat-value expenses-val">{fmt(stats.expenses)}</span>
                </div>
                <SpendingChart data={categorySpending} />
              </div>
            )}

            {/* Filter controls */}
            <section className="controls">
              <div className="filter-group">
                <button
                  className={`btn btn-filter${activeFilter === "recent" ? " active" : ""}`}
                  onClick={() => { setCategoryFilter(""); setTypeFilter(""); setPaymentFilter(""); fetchRecent(); }}
                >
                  Recent
                </button>
                <button
                  className={`btn btn-filter${activeFilter === "all-time" ? " active" : ""}`}
                  onClick={() => { setCategoryFilter(""); setTypeFilter(""); setPaymentFilter(""); fetchAll(); }}
                >
                  All Time
                </button>
                <button
                  className={`btn btn-filter${activeFilter === "current-month" ? " active" : ""}`}
                  onClick={() => { setCategoryFilter(""); setTypeFilter(""); setPaymentFilter(""); fetchCurrentMonth(); }}
                >
                  This Month
                </button>
                <button
                  className={`btn btn-filter${activeFilter === "previous-month" ? " active" : ""}`}
                  onClick={() => { setCategoryFilter(""); setTypeFilter(""); setPaymentFilter(""); fetchPreviousMonth(); }}
                >
                  Last Month
                </button>
                <select className="category-select" value={categoryFilter} onChange={handleCategoryChange}>
                  <option value="">All Categories</option>
                  {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
                {activeFilter === "all-time" && (
                  <>
                    <select className="category-select" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
                      <option value="">All Types</option>
                      {TRANSACTION_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                    <select className="category-select" value={paymentFilter} onChange={(e) => setPaymentFilter(e.target.value)}>
                      <option value="">All Payments</option>
                      {PAYMENT_METHODS.map((m) => <option key={m} value={m}>{m.replace(/_/g, " ")}</option>)}
                    </select>
                  </>
                )}
              </div>
            </section>

            {error && <p className="global-error">{error}</p>}

            <section className="card">
              <div className="table-header">
                <h2>{filterLabel()}</h2>
                <span className="txn-count">{filteredTransactions.length} transactions</span>
              </div>
              <TransactionTable transactions={filteredTransactions} loading={loading} />
            </section>
          </>
        )}

        <main className="main">
          {tab === "nl2sql" && <NL2SQLPanel userId={auth.user?.id} />}
          {tab === "monthly-reports" && <MonthlyReportsPanel />}

          {tab === "search" && (
            <section className="card">
              <div className="table-header">
                <h2>Semantic Search</h2>
              </div>
              <form onSubmit={handleSearch} style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem" }}>
                <input
                  className="category-select"
                  style={{ flex: 1 }}
                  type="text"
                  placeholder="e.g. coffee and dining out"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") handleSearch(); }}
                />
                <button className="btn btn-primary" type="submit" disabled={searchLoading}>
                  {searchLoading ? "Searching…" : "Search"}
                </button>
              </form>
              {searchError && <p className="global-error">{searchError}</p>}
              {searchResults !== null && (
                <>
                  <div className="table-header" style={{ marginTop: "0.5rem" }}>
                    <span className="txn-count">
                      {searchResults.length === 0
                        ? "No similar transactions found"
                        : `Top ${searchResults.length} similar transactions`}
                    </span>
                  </div>
                  <TransactionTable transactions={searchResults} loading={false} />
                </>
              )}
            </section>
          )}
        </main>
      </div>
    </div>
  );
}
