import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { metricsApi } from "../api/metrics";
import "./PerformanceDashboard.css";

const COLORS = {
  teal: "#2dd4bf",
  purple: "#a78bfa",
  amber: "#fbbf24",
  coral: "#fb7185",
  lime: "#a3e635",
};

/** Traffic-light class for latency KPI (lower is better). */
function latencyClass(ms, greenMax, yellowMax) {
  if (ms == null || Number.isNaN(ms)) return "neutral";
  if (ms < greenMax) return "good";
  if (ms < yellowMax) return "warn";
  return "bad";
}

function truncRateClass(rate) {
  if (rate == null) return "neutral";
  if (rate < 5) return "good";
  if (rate < 25) return "warn";
  return "bad";
}

function fmtMs(v) {
  if (v == null || Number.isNaN(v)) return "—";
  return `${Math.round(v)} ms`;
}

function fmtNum(v) {
  if (v == null || Number.isNaN(v)) return "—";
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: 1 });
}

/** Histogram buckets for BarChart (Recharts has no Histogram). */
function bucketE2e(records, bins = 12) {
  const vals = records.map((r) => r.e2e_total_ms).filter((v) => v != null && !Number.isNaN(v));
  if (!vals.length) return [];
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;
  const width = span / bins;
  const rows = Array.from({ length: bins }, (_, i) => ({
    name: `${Math.round(min + i * width)}–${Math.round(min + (i + 1) * width)}`,
    count: 0,
    mid: min + (i + 0.5) * width,
  }));
  for (const v of vals) {
    let idx = Math.floor((v - min) / width);
    if (idx >= bins) idx = bins - 1;
    if (idx < 0) idx = 0;
    rows[idx].count += 1;
  }
  return rows;
}

export default function PerformanceDashboard() {
  const [records, setRecords] = useState([]);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");
  const [lastFetchAt, setLastFetchAt] = useState(null);
  const [tick, setTick] = useState(0);

  const load = useCallback(async () => {
    try {
      const [recs, sum] = await Promise.all([metricsApi.fetchMetrics(), metricsApi.fetchSummary()]);
      setRecords(Array.isArray(recs) ? recs : []);
      setSummary(sum);
      setError("");
      setLastFetchAt(Date.now());
    } catch (e) {
      setError(e.message || String(e));
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  useEffect(() => {
    const id = setInterval(() => setTick((x) => x + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const secondsAgo = useMemo(() => {
    if (!lastFetchAt) return null;
    void tick;
    return Math.floor((Date.now() - lastFetchAt) / 1000);
  }, [lastFetchAt, tick]);

  const handleClear = async () => {
    try {
      await metricsApi.clearMetrics();
      await load();
    } catch (e) {
      setError(e.message || String(e));
    }
  };

  const last50 = useMemo(() => records.slice(-50), [records]);

  const seriesLatency = useMemo(() => {
    return last50.map((r) => ({
      t: r.timestamp,
      mcp_routing_ms: r.mcp_routing_ms ?? null,
      nl2sql_total_ms: r.nl2sql_total_ms ?? null,
      semantic_total_ms: r.semantic_total_ms ?? null,
      gemini_call_ms: r.gemini_call_ms ?? null,
      e2e_total_ms: r.e2e_total_ms ?? null,
    }));
  }, [last50]);

  const seriesNl2sqlSteps = useMemo(() => {
    return last50
      .filter((r) => r.nl2sql_translation_ms != null || r.nl2sql_execution_ms != null)
      .map((r) => ({
        t: r.timestamp,
        translation: r.nl2sql_translation_ms ?? 0,
        execution: r.nl2sql_execution_ms ?? 0,
      }));
  }, [last50]);

  const seriesSemanticSteps = useMemo(() => {
    return last50
      .filter((r) => r.semantic_embedding_ms != null || r.semantic_vector_search_ms != null)
      .map((r) => ({
        t: r.timestamp,
        embedding: r.semantic_embedding_ms ?? 0,
        search: r.semantic_vector_search_ms ?? 0,
      }));
  }, [last50]);

  const histData = useMemo(() => bucketE2e(records, 12), [records]);

  const scatterNl2sql = useMemo(() => {
    return records
      .filter((r) => r.nl2sql_row_count != null && r.nl2sql_total_ms != null)
      .map((r) => ({
        x: r.nl2sql_row_count,
        y: r.nl2sql_total_ms,
        id: r.id,
      }));
  }, [records]);

  const pieBreakdown = useMemo(() => {
    const s = summary || {};
    const n = s.nl2sql_pct?.avg;
    const g = s.gemini_pct?.avg;
    const o = s.other_pct?.avg;
    const parts = [];
    if (n != null) parts.push({ name: "NL2SQL %", value: Math.max(0, n), fill: COLORS.teal });
    if (g != null) parts.push({ name: "Gemini %", value: Math.max(0, g), fill: COLORS.purple });
    if (o != null) parts.push({ name: "Other %", value: Math.max(0, o), fill: COLORS.amber });
    return parts.length ? parts : [{ name: "No data", value: 1, fill: "#334155" }];
  }, [summary]);

  const lineGeminiBytes = useMemo(() => {
    return last50
      .filter((r) => r.gemini_response_bytes != null)
      .map((r) => ({ t: r.timestamp, bytes: r.gemini_response_bytes }));
  }, [last50]);

  const lineSemanticMatches = useMemo(() => {
    return last50
      .filter((r) => r.semantic_match_count != null)
      .map((r) => ({ t: r.timestamp, matches: r.semantic_match_count }));
  }, [last50]);

  const tableRows = useMemo(() => {
    return [...records].slice(-20).reverse();
  }, [records]);

  const st = (key) => summary?.[key];

  const kpiRouting = st("mcp_routing_ms");
  const kpiNl2sql = st("nl2sql_total_ms");
  const kpiSemantic = st("semantic_total_ms");
  const kpiGemini = st("gemini_call_ms");
  const kpiE2e = st("e2e_total_ms");
  const truncRate = summary?.nl2sql_truncation_rate_pct;

  const HIGH_E2E = 4000;
  const HIGH_NL2SQL = 3000;

  return (
    <div className="perf-root">
      <div className="perf-header">
        <div>
          <p style={{ margin: 0, fontSize: "0.9rem", color: "#94a3b8" }}>
            Live metrics from in-memory store (last 500 requests)
          </p>
        </div>
        <div className="perf-actions">
          {secondsAgo != null && (
            <span className="perf-updated">Last updated: {secondsAgo}s ago</span>
          )}
          <button type="button" className="perf-btn-clear" onClick={handleClear}>
            Clear metrics
          </button>
        </div>
      </div>

      {error && <div className="perf-error">{error}</div>}

      <div className="perf-kpi-row">
        <div className={`perf-kpi ${latencyClass(kpiRouting?.avg, 150, 600)}`}>
          <div className="perf-kpi-title">Avg MCP routing</div>
          <div className="perf-kpi-avg">{fmtMs(kpiRouting?.avg)}</div>
          <div className="perf-kpi-sub">p95 {fmtMs(kpiRouting?.p95)}</div>
        </div>
        <div className={`perf-kpi ${latencyClass(kpiNl2sql?.avg, 800, 2500)}`}>
          <div className="perf-kpi-title">Avg NL2SQL total</div>
          <div className="perf-kpi-avg">{fmtMs(kpiNl2sql?.avg)}</div>
          <div className="perf-kpi-sub">p95 {fmtMs(kpiNl2sql?.p95)}</div>
        </div>
        <div className={`perf-kpi ${latencyClass(kpiSemantic?.avg, 400, 1200)}`}>
          <div className="perf-kpi-title">Avg semantic search</div>
          <div className="perf-kpi-avg">{fmtMs(kpiSemantic?.avg)}</div>
          <div className="perf-kpi-sub">p95 {fmtMs(kpiSemantic?.p95)}</div>
        </div>
        <div className={`perf-kpi ${latencyClass(kpiGemini?.avg, 800, 2000)}`}>
          <div className="perf-kpi-title">Avg Gemini call</div>
          <div className="perf-kpi-avg">{fmtMs(kpiGemini?.avg)}</div>
          <div className="perf-kpi-sub">p95 {fmtMs(kpiGemini?.p95)}</div>
        </div>
        <div className={`perf-kpi ${latencyClass(kpiE2e?.avg, 1500, 4000)}`}>
          <div className="perf-kpi-title">Avg E2E</div>
          <div className="perf-kpi-avg">{fmtMs(kpiE2e?.avg)}</div>
          <div className="perf-kpi-sub">p95 {fmtMs(kpiE2e?.p95)}</div>
        </div>
        <div className={`perf-kpi ${truncRateClass(truncRate)}`}>
          <div className="perf-kpi-title">NL2SQL truncation rate</div>
          <div className="perf-kpi-avg">
            {truncRate != null ? `${fmtNum(truncRate)}%` : "—"}
          </div>
          <div className="perf-kpi-sub">sample {summary?.sample_size ?? 0}</div>
        </div>
      </div>

      <div className="perf-grid-2">
        <div className="perf-panel">
          <div className="perf-panel-title">Latency over time (last 50)</div>
          <div className="perf-chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={seriesLatency} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2f3d" />
                <XAxis dataKey="t" tick={{ fill: "#64748b", fontSize: 10 }} hide />
                <YAxis tick={{ fill: "#64748b", fontSize: 10 }} />
                <Tooltip
                  contentStyle={{ background: "#1a1d27", border: "1px solid #2a2f3d" }}
                  labelStyle={{ color: "#94a3b8" }}
                />
                <Legend />
                <Line type="monotone" dataKey="mcp_routing_ms" name="MCP routing" stroke={COLORS.teal} dot={false} isAnimationActive animationDuration={400} />
                <Line type="monotone" dataKey="nl2sql_total_ms" name="NL2SQL total" stroke={COLORS.purple} dot={false} isAnimationActive animationDuration={400} />
                <Line type="monotone" dataKey="semantic_total_ms" name="Semantic total" stroke={COLORS.amber} dot={false} isAnimationActive animationDuration={400} />
                <Line type="monotone" dataKey="gemini_call_ms" name="Gemini" stroke={COLORS.coral} dot={false} isAnimationActive animationDuration={400} />
                <Line type="monotone" dataKey="e2e_total_ms" name="E2E" stroke={COLORS.lime} dot={false} isAnimationActive animationDuration={400} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="perf-panel">
          <div className="perf-panel-title">NL2SQL sub-steps (stacked)</div>
          <div className="perf-chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={seriesNl2sqlSteps} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2f3d" />
                <XAxis dataKey="t" tick={{ fill: "#64748b", fontSize: 10 }} hide />
                <YAxis tick={{ fill: "#64748b", fontSize: 10 }} />
                <Tooltip contentStyle={{ background: "#1a1d27", border: "1px solid #2a2f3d" }} />
                <Legend />
                <Area type="monotone" dataKey="translation" name="Translation" stackId="a" stroke={COLORS.teal} fill={COLORS.teal} isAnimationActive animationDuration={400} />
                <Area type="monotone" dataKey="execution" name="Execution" stackId="a" stroke={COLORS.purple} fill={COLORS.purple} isAnimationActive animationDuration={400} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="perf-grid-2">
        <div className="perf-panel">
          <div className="perf-panel-title">Semantic sub-steps (stacked)</div>
          <div className="perf-chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={seriesSemanticSteps} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2f3d" />
                <XAxis dataKey="t" tick={{ fill: "#64748b", fontSize: 10 }} hide />
                <YAxis tick={{ fill: "#64748b", fontSize: 10 }} />
                <Tooltip contentStyle={{ background: "#1a1d27", border: "1px solid #2a2f3d" }} />
                <Legend />
                <Area type="monotone" dataKey="embedding" name="Embedding" stackId="s" stroke={COLORS.teal} fill={COLORS.teal} isAnimationActive animationDuration={400} />
                <Area type="monotone" dataKey="search" name="Vector search" stackId="s" stroke={COLORS.amber} fill={COLORS.amber} isAnimationActive animationDuration={400} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="perf-panel">
          <div className="perf-panel-title">E2E latency distribution</div>
          <div className="perf-chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={histData} margin={{ top: 8, right: 8, left: 0, bottom: 24 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2f3d" />
                <XAxis dataKey="name" tick={{ fill: "#64748b", fontSize: 9 }} interval={0} angle={-35} textAnchor="end" height={60} />
                <YAxis tick={{ fill: "#64748b", fontSize: 10 }} allowDecimals={false} />
                <Tooltip contentStyle={{ background: "#1a1d27", border: "1px solid #2a2f3d" }} />
                <Bar dataKey="count" name="Requests" fill={COLORS.teal} radius={[4, 4, 0, 0]} isAnimationActive animationDuration={400} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="perf-grid-2">
        <div className="perf-panel">
          <div className="perf-panel-title">Row count vs NL2SQL latency</div>
          <div className="perf-chart-wrap tall">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2f3d" />
                <XAxis type="number" dataKey="x" name="rows" tick={{ fill: "#64748b", fontSize: 10 }} />
                <YAxis type="number" dataKey="y" name="ms" tick={{ fill: "#64748b", fontSize: 10 }} />
                <ZAxis range={[60, 60]} />
                <Tooltip cursor={{ strokeDasharray: "3 3" }} contentStyle={{ background: "#1a1d27", border: "1px solid #2a2f3d" }} />
                <Scatter name="NL2SQL" data={scatterNl2sql} fill={COLORS.purple} isAnimationActive animationDuration={400} />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="perf-panel">
          <div className="perf-panel-title">E2E breakdown (avg %)</div>
          <div className="perf-chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pieBreakdown} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={88} label isAnimationActive animationDuration={400}>
                  {pieBreakdown.map((entry) => (
                    <Cell key={entry.name} fill={entry.fill} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: "#1a1d27", border: "1px solid #2a2f3d" }} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="perf-grid-2">
        <div className="perf-panel">
          <div className="perf-panel-title">Gemini response bytes (last 50 w/ data)</div>
          <div className="perf-chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={lineGeminiBytes} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2f3d" />
                <XAxis dataKey="t" tick={{ fill: "#64748b", fontSize: 10 }} hide />
                <YAxis tick={{ fill: "#64748b", fontSize: 10 }} />
                <Tooltip contentStyle={{ background: "#1a1d27", border: "1px solid #2a2f3d" }} />
                <Line type="monotone" dataKey="bytes" name="bytes" stroke={COLORS.coral} dot={false} isAnimationActive animationDuration={400} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="perf-panel">
          <div className="perf-panel-title">Semantic match count (last 50)</div>
          <div className="perf-chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={lineSemanticMatches} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2f3d" />
                <XAxis dataKey="t" tick={{ fill: "#64748b", fontSize: 10 }} hide />
                <YAxis tick={{ fill: "#64748b", fontSize: 10 }} allowDecimals={false} />
                <Tooltip contentStyle={{ background: "#1a1d27", border: "1px solid #2a2f3d" }} />
                <Line type="monotone" dataKey="matches" name="matches" stroke={COLORS.teal} dot={false} isAnimationActive animationDuration={400} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="perf-panel" style={{ marginBottom: "1rem" }}>
        <div className="perf-panel-title">Recent records (newest first, max 20)</div>
        <div className="perf-table-wrap">
          <table className="perf-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Tool</th>
                <th>E2E</th>
                <th>MCP</th>
                <th>NL2SQL Σ</th>
                <th>Semantic Σ</th>
                <th>Gemini</th>
                <th>Rows</th>
                <th>Trunc</th>
              </tr>
            </thead>
            <tbody>
              {tableRows.map((r) => (
                <tr key={r.id}>
                  <td>{r.timestamp}</td>
                  <td>{r.tool}</td>
                  <td className={r.e2e_total_ms > HIGH_E2E ? "perf-cell-high" : ""}>{fmtMs(r.e2e_total_ms)}</td>
                  <td>{fmtMs(r.mcp_routing_ms)}</td>
                  <td className={r.nl2sql_total_ms > HIGH_NL2SQL ? "perf-cell-high" : ""}>{fmtMs(r.nl2sql_total_ms)}</td>
                  <td>{fmtMs(r.semantic_total_ms)}</td>
                  <td>{fmtMs(r.gemini_call_ms)}</td>
                  <td>{r.nl2sql_row_count ?? "—"}</td>
                  <td>{r.nl2sql_truncated === true ? "yes" : r.nl2sql_truncated === false ? "no" : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
