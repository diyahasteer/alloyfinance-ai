import { useState } from "react";
import { analyzeWithNl2Sql } from "../api/aiAnalysis";
import NL2SQLResultTable from "./NL2SQLResultTable";

const CHIPS = [
  "Show total spending by category",
  "Which categories am I over budget on?",
  "What did I spend at restaurants last month?",
  "Top 5 merchants by total spend",
  "How much did I spend on groceries this month?",
  "Show all debit transactions in New York",
  "Compare my spending to my budget limits",
];

export default function NL2SQLPanel() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleAsk = async () => {
    const q = question.trim();
    if (!q) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const data = await analyzeWithNl2Sql(q);
      setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && !loading) {
      handleAsk();
    }
  };

  const resultRowCount = result?.rows?.length || 0;

  return (
    <div className="nl-panel">
      <section className="card">
        <div className="table-header">
          <h2>Ask a question</h2>
        </div>

        <textarea
          className="nl-textarea"
          placeholder="e.g. Show total spending by category this month"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={3}
        />
        <p className="nl-hint">Press ⌘ Enter or click Ask question</p>

        <div className="nl-chips">
          {CHIPS.map((chip) => (
            <button
              key={chip}
              className="nl-chip"
              onClick={() => setQuestion(chip)}
            >
              {chip}
            </button>
          ))}
        </div>

        <div style={{ marginTop: "1rem", display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <button
            className="btn btn-primary"
            onClick={handleAsk}
            disabled={!question.trim() || loading}
          >
            {loading ? "Loading..." : "Ask question"}
          </button>
        </div>

        {error && <p className="global-error" style={{ marginTop: "0.75rem" }}>{error}</p>}
      </section>

      {result && (
        <section className="card">
          <div className="table-header">
            <h2>Results</h2>
            <span className="txn-count">
              {resultRowCount} row{resultRowCount !== 1 ? "s" : ""}
            </span>
          </div>
          <NL2SQLResultTable result={result} />
        </section>
      )}
    </div>
  );
}
