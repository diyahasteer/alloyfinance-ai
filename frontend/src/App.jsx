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
import { transactionsApi } from "./api/transactions";

const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

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
    <div className="app">
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
  const [categories, setCategories] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [searchPage, setSearchPage] = useState(0);

  useEffect(() => {
    transactionsApi.getCategories().then(setCategories).catch(() => {});
  }, []);

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
      return true;
    });
  }, [activeFilter, transactions, categoryFilter]);

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
    setSearchPage(0);
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
            className={`btn btn-filter ${tab === "insight" ? "active" : ""}`}
            onClick={() => setTab("insight")}
          >
            Insight
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

        {tab === "insight" && <CustomerPanel />}
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
            {searchResults !== null && (() => {
              const PAGE_SIZE = 10;
              const totalPages = Math.ceil(searchResults.length / PAGE_SIZE);
              const pageSlice = searchResults.slice(searchPage * PAGE_SIZE, (searchPage + 1) * PAGE_SIZE);
              return (
                <>
                  <div className="table-header" style={{ marginTop: "0.5rem" }}>
                    <span className="txn-count">
                      {searchResults.length === 0
                        ? "No similar transactions found"
                        : `${searchResults.length} similar transaction${searchResults.length !== 1 ? "s" : ""}`}
                    </span>
                    {totalPages > 1 && (
                      <span style={{ fontSize: "0.82rem", color: "#64748b" }}>
                        Page {searchPage + 1} of {totalPages}
                      </span>
                    )}
                  </div>
                  <TransactionTable transactions={pageSlice} loading={false} />
                  {totalPages > 1 && (
                    <div className="pagination-row">
                      <button
                        className="btn btn-filter"
                        onClick={() => setSearchPage((p) => p - 1)}
                        disabled={searchPage === 0}
                      >
                        ← Prev
                      </button>
                      <span className="pagination-info">{searchPage + 1} / {totalPages}</span>
                      <button
                        className="btn btn-filter"
                        onClick={() => setSearchPage((p) => p + 1)}
                        disabled={searchPage >= totalPages - 1}
                      >
                        Next →
                      </button>
                    </div>
                  )}
                </>
              );
            })()}
          </section>
        )}
        {tab === "ai-analysis" && <AIAnalysisPanel />}

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
                  className={`btn btn-filter ${activeFilter === "all-time" ? "active" : ""}`}
                  onClick={() => { setCategoryFilter(""); fetchAll(); }}
                >
                  All Time
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

                <select className="category-select" value={categoryFilter} onChange={handleCategoryChange}>
                  <option value="">All Categories</option>
                  {categories.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>

              <button className="btn btn-primary" onClick={() => setShowForm((s) => !s)}>
                {showForm ? "Cancel" : "+ New Transaction"}
              </button>
            </section>

            {showForm && (
              <section className="card">
                <TransactionForm onSubmit={handleCreate} categories={categories} />
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

          </>
        )}
      </main>
    </div>
  );
}
