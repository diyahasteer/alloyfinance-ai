import { useState, useEffect, useCallback, useMemo } from "react";
import { Routes, Route, Link } from "react-router-dom";
import { useTransactions } from "./hooks/useTransactions";
import TransactionForm from "./components/TransactionForm";
import TransactionTable from "./components/TransactionTable";
import NL2SQLPanel from "./components/NL2SQLPanel";
import CustomerPanel from "./components/CustomerPanel";
import MonthlyReportsPanel from "./components/MonthlyReportsPanel";
import SemanticClusters from "./components/SemanticClusters";
import AIAnalysisPanel from "./components/AIAnalysisPanel";
import PerformanceDashboard from "./components/PerformanceDashboard";
import { searchApi } from "./api/search";
import { clustersApi } from "./api/clusters";

const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Behavioral/emotional concept chips — showcases embedding power since
// there is no hard category mapping for these concepts.
const CONCEPT_CHIPS = [
  "impulse purchases",
  "self-care spending",
  "social spending",
  "productive work tools",
  "comfort food",
  "recurring habits",
  "guilty pleasures",
  "one-time splurges",
];

const SF_TIME_CHIPS = [
  { label: "Last 7d",   value: "7d"  },
  { label: "Last 30d",  value: "30d" },
  { label: "Last 3mo",  value: "90d" },
  { label: "All time",  value: "all" },
];

const THRESHOLD_LABELS = [
  { value: 0.50, label: "Broad"       },
  { value: 0.70, label: "Balanced"    },
  { value: 0.85, label: "Strict"      },
  { value: 0.95, label: "Very Strict" },
];

function thresholdLabel(v) {
  return [...THRESHOLD_LABELS].reverse().find((t) => v >= t.value)?.label ?? "Broad";
}

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

const TRANSACTION_TYPES = ["debit", "credit", "transfer", "refund"];
const PAYMENT_METHODS = ["credit_card", "debit_card", "bank_transfer", "cash", "mobile_wallet"];

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

  const logout = () => {
    localStorage.removeItem("token");
    setUser(null);
  };

  return { user, loading, login, signup, logout };
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

  return (
    <Routes>
      <Route
        path="/performance"
        element={!auth.user ? <LoginScreen auth={auth} /> : <PerformanceLayout auth={auth} />}
      />
      <Route
        path="*"
        element={!auth.user ? <LoginScreen auth={auth} /> : <Dashboard auth={auth} />}
      />
    </Routes>
  );
}

function PerformanceLayout({ auth }) {
  return (
    <div className="app app--wide">
      <header className="header">
        <div className="header-row">
          <div>
            <h1>AlloyFinance</h1>
            <p className="header-sub">Performance</p>
          </div>
          <div className="user-info">
            {auth.user.picture && (
              <img className="avatar" src={auth.user.picture} alt="" referrerPolicy="no-referrer" />
            )}
            <span className="user-name">{auth.user.name || auth.user.email}</span>
            <Link
              to="/"
              className="btn btn-filter"
              style={{ textDecoration: "none", display: "inline-block" }}
            >
              Back to app
            </Link>
            <button className="btn btn-logout" onClick={auth.logout}>
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="main">
        <PerformanceDashboard />
      </main>
    </div>
  );
}

function LoginScreen({ auth }) {
  const [mode, setMode] = useState("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      if (mode === "signup") {
        await auth.signup(name, email, password);
      } else {
        await auth.login(email, password);
      }
    } catch (err) {
      setError(err.message || "Authentication failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="app">
      <div className="login-container">
        <div className="login-card">
          <h1 className="login-title">AlloyFinance</h1>
          <p className="login-sub">
            {mode === "signup" ? "Create your account" : "Sign in to manage your transactions"}
          </p>
          {error && <p className="global-error">{error}</p>}
          <form className="auth-form" onSubmit={handleSubmit}>
            {mode === "signup" && (
              <label className="field">
                <span>Name (optional)</span>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  type="text"
                  placeholder="Jane Doe"
                />
              </label>
            )}
            <label className="field">
              <span>Email</span>
              <input
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                type="email"
                placeholder="foo@bar.com"
                required
              />
            </label>
            <label className="field">
              <span>Password</span>
              <div className="password-input-wrap">
                <input
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  type={showPassword ? "text" : "password"}
                  placeholder="********"
                  required
                  minLength={8}
                />
                <button
                  type="button"
                  className="password-toggle"
                  onClick={() => setShowPassword((prev) => !prev)}
                >
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>
            </label>
            <button className="btn btn-primary auth-submit" type="submit" disabled={submitting}>
              {submitting ? "Please wait..." : mode === "signup" ? "Create account" : "Sign in"}
            </button>
          </form>
          <button
            className="auth-toggle"
            type="button"
            onClick={() => {
              setMode((prev) => (prev === "login" ? "signup" : "login"));
              setError("");
            }}
          >
            {mode === "signup" ? "Already have an account? Sign in" : "Need an account? Sign up"}
          </button>
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
    fetchAll,
    createTransaction,
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

  // Semantic filter state
  const [sfQuery, setSfQuery] = useState("");
  const [sfThreshold, setSfThreshold] = useState(0.75);
  const [sfTimeRange, setSfTimeRange] = useState("all");
  const [sfResults, setSfResults] = useState(null);
  const [sfLoading, setSfLoading] = useState(false);
  const [sfError, setSfError] = useState("");

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

  const handleSemanticFilter = useCallback(async (concept) => {
    const q = (concept ?? sfQuery).trim();
    if (!q) return;
    setSfLoading(true);
    setSfError("");
    setSfResults(null);
    try {
      const timeOpts = sfTimeRange !== "all" ? { timeRange: sfTimeRange } : {};
      const data = await clustersApi.semanticFilter({ category: q, threshold: sfThreshold, ...timeOpts });
      setSfResults(data);
    } catch (err) {
      setSfError(err.message);
    } finally {
      setSfLoading(false);
    }
  }, [sfQuery, sfThreshold, sfTimeRange]);

  const filterLabel = () => {
    if (activeFilter === "recent") return "Recent transactions";
    if (activeFilter === "all-time") return "All time";
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
            <span className="user-name">{auth.user.name || auth.user.email}</span>
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
            className={`btn btn-filter ${tab === "monthly-reports" ? "active" : ""}`}
            onClick={() => setTab("monthly-reports")}
          >
            Monthly Reports
          </button>
          <button
            className={`btn btn-filter ${tab === "nl2sql" ? "active" : ""}`}
            onClick={() => setTab("nl2sql")}
          >
            NL2SQL
          </button>
          <button
            className={`btn btn-filter ${tab === "search" ? "active" : ""}`}
            onClick={() => setTab("search")}
          >
            Semantic Search
          </button>
          <button
            className={`btn btn-filter ${tab === "insights" ? "active" : ""}`}
            onClick={() => setTab("insights")}
          >
            Insights
          </button>
          <button
            className={`btn btn-filter ${tab === "semantic-clusters" ? "active" : ""}`}
            onClick={() => setTab("semantic-clusters")}
          >
            Semantic Clusters
          </button>
          <button
            className={`btn btn-filter ${tab === "ai-analysis" ? "active" : ""}`}
            onClick={() => setTab("ai-analysis")}
          >
            AI Analysis
          </button>
        </div>

        {tab === "insights" && <CustomerPanel />}
        {tab === "nl2sql" && <NL2SQLPanel />}
        {tab === "monthly-reports" && <MonthlyReportsPanel />}
        {tab === "semantic-clusters" && <SemanticClusters />}

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
        {tab === "ai-analysis" && <AIAnalysisPanel />}

        {tab === "transactions" && (
          <>
            <section className="controls">
              <div className="filter-group">
                <button
                  className={`btn btn-filter ${activeFilter === "recent" ? "active" : ""}`}
                  onClick={() => {
                    setCategoryFilter("");
                    setTypeFilter("");
                    setPaymentFilter("");
                    fetchRecent();
                  }}
                >
                  Recent
                </button>
                <button
                  className={`btn btn-filter ${activeFilter === "all-time" ? "active" : ""}`}
                  onClick={() => {
                    setCategoryFilter("");
                    setTypeFilter("");
                    setPaymentFilter("");
                    fetchAll();
                  }}
                >
                  All Time
                </button>
                <button
                  className={`btn btn-filter ${activeFilter === "current-month" ? "active" : ""}`}
                  onClick={() => {
                    setCategoryFilter("");
                    setTypeFilter("");
                    setPaymentFilter("");
                    fetchCurrentMonth();
                  }}
                >
                  This Month
                </button>
                <button
                  className={`btn btn-filter ${activeFilter === "previous-month" ? "active" : ""}`}
                  onClick={() => {
                    setCategoryFilter("");
                    setTypeFilter("");
                    setPaymentFilter("");
                    fetchPreviousMonth();
                  }}
                >
                  Last Month
                </button>

                <select className="category-select" value={categoryFilter} onChange={handleCategoryChange}>
                  <option value="">All Categories</option>
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>

                {activeFilter === "all-time" && (
                  <>
                    <select
                      className="category-select"
                      value={typeFilter}
                      onChange={(e) => setTypeFilter(e.target.value)}
                    >
                      <option value="">All Types</option>
                      {TRANSACTION_TYPES.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                    <select
                      className="category-select"
                      value={paymentFilter}
                      onChange={(e) => setPaymentFilter(e.target.value)}
                    >
                      <option value="">All Payments</option>
                      {PAYMENT_METHODS.map((m) => (
                        <option key={m} value={m}>
                          {m.replace(/_/g, " ")}
                        </option>
                      ))}
                    </select>
                  </>
                )}
              </div>

              <button className="btn btn-primary" onClick={() => setShowForm((s) => !s)}>
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
                <span className="txn-count">{filteredTransactions.length} transactions</span>
              </div>
              <TransactionTable transactions={filteredTransactions} loading={loading} />
            </section>

            <section className="card">
              <div className="table-header">
                <h2>Semantic Filter</h2>
              </div>

              {/* Time chips */}
              <div className="filter-group" style={{ marginBottom: "0.6rem" }}>
                {SF_TIME_CHIPS.map((chip) => (
                  <button
                    key={chip.value}
                    className={`btn btn-filter ${sfTimeRange === chip.value ? "active" : ""}`}
                    onClick={() => setSfTimeRange(chip.value)}
                  >
                    {chip.label}
                  </button>
                ))}
              </div>

              {/* Free text + button */}
              <div className="semantic-filter-row">
                <input
                  className="category-select"
                  style={{ flex: 1 }}
                  type="text"
                  placeholder='e.g. "impulse purchases" or "work tools"'
                  value={sfQuery}
                  onChange={(e) => { setSfQuery(e.target.value); if (!e.target.value) setSfResults(null); }}
                  onKeyDown={(e) => { if (e.key === "Enter") handleSemanticFilter(); }}
                />
                <button
                  className="btn btn-primary"
                  onClick={() => handleSemanticFilter()}
                  disabled={sfLoading || !sfQuery.trim()}
                >
                  {sfLoading ? "Filtering…" : "Filter"}
                </button>
              </div>

              {/* Behavioral concept chips */}
              <div className="nl-chips" style={{ marginTop: "0.4rem" }}>
                {CONCEPT_CHIPS.map((chip) => (
                  <button
                    key={chip}
                    className="nl-chip"
                    onClick={() => { setSfQuery(chip); handleSemanticFilter(chip); }}
                  >
                    {chip}
                  </button>
                ))}
              </div>

              {/* Threshold slider with labels */}
              <div className="semantic-threshold-row">
                <label className="cluster-slider-label">
                  <span>
                    Similarity: <strong>{thresholdLabel(sfThreshold)}</strong>{" "}
                    <span style={{ color: "#94a3b8" }}>({(sfThreshold * 100).toFixed(0)}%)</span>
                  </span>
                  <input
                    type="range"
                    min={50}
                    max={95}
                    step={5}
                    value={sfThreshold * 100}
                    onChange={(e) => setSfThreshold(Number(e.target.value) / 100)}
                    className="cluster-slider"
                  />
                </label>
              </div>

              {sfError && <p className="global-error">{sfError}</p>}

              {sfResults && (
                <>
                  <div className="table-header" style={{ marginTop: "0.75rem" }}>
                    <span className="txn-count">
                      {sfResults.total_matched === 0
                        ? "No matching transactions"
                        : `Showing ${sfResults.transactions.length} of ${sfResults.total_matched} above ${thresholdLabel(sfThreshold)} threshold`}
                    </span>
                  </div>

                  {sfResults.suggested_concepts?.length > 0 && (
                    <div style={{ marginBottom: "0.5rem" }}>
                      <span style={{ fontSize: "0.8rem", color: "#64748b" }}>Try also: </span>
                      <div className="nl-chips" style={{ display: "inline-flex", flexWrap: "wrap" }}>
                        {sfResults.suggested_concepts.map((c) => (
                          <button
                            key={c}
                            className="nl-chip"
                            onClick={() => { setSfQuery(c); handleSemanticFilter(c); }}
                          >
                            {c}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  <TransactionTable transactions={sfResults.transactions} loading={false} />
                </>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
