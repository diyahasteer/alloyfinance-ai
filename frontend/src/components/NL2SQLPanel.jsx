import { useState } from "react";
import { nl2sqlApi } from "../api/nl2sql";

const CHIPS = [
  "Show total spending by category",
  "Which categories am I over budget on?",
  "What did I spend at restaurants last month?",
  "Top 5 merchants by total spend",
  "How much did I spend on groceries this month?",
  "Show all debit transactions in New York",
  "Compare my spending to my budget limits",
];

export default function NL2SQLPanel({ userId }) {
  const [question, setQuestion] = useState("");
  const [sql, setSql] = useState("");
  const [result, setResult] = useState(null);
  const [genLoading, setGenLoading] = useState(false);
  const [runLoading, setRunLoading] = useState(false);
  const [genError, setGenError] = useState("");
  const [runError, setRunError] = useState("");

  const handleGenerate = async () => {
    const q = question.trim();
    if (!q) return;
    const finalQuery = userId ? `${q} for user: ${userId}` : q;
    // eslint-disable-next-line no-console
    console.log("[NL2SQL] original:", q, "| userId:", userId, "| sent:", finalQuery);
    setGenLoading(true);
    setGenError("");
    setSql("");
    setResult(null);
    setRunError("");
    try {
      const data = await nl2sqlApi.generate(finalQuery);
      setSql(data.sql);
    } catch (e) {
      setGenError(e.message);
    } finally {
      setGenLoading(false);
    }
  };

  const handleRun = async () => {
    if (!sql) return;
    setRunLoading(true);
    setRunError("");
    setResult(null);
    try {
      const data = await nl2sqlApi.execute(sql);
      setResult(data);
    } catch (e) {
      setRunError(e.message);
    } finally {
      setRunLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      handleGenerate();
    }
  };

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
        <p className="nl-hint">Press ⌘ Enter or click Generate SQL</p>

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
            onClick={handleGenerate}
            disabled={!question.trim() || genLoading}
          >
            {genLoading ? "Generating…" : "Generate SQL"}
          </button>
        </div>

        {genError && <p className="global-error" style={{ marginTop: "0.75rem" }}>{genError}</p>}
      </section>

      {sql && (
        <section className="card">
          <div className="table-header">
            <h2>Generated SQL</h2>
          </div>
          <pre className="sql-block">{sql}</pre>
          <div style={{ marginTop: "1rem", display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <button
              className="btn btn-primary"
              onClick={handleRun}
              disabled={runLoading}
            >
              {runLoading ? "Running…" : "Run SQL"}
            </button>
          </div>
          {runError && <p className="global-error" style={{ marginTop: "0.75rem" }}>{runError}</p>}
        </section>
      )}

      {result && (
        <section className="card">
          <div className="table-header">
            <h2>Results</h2>
            <span className="txn-count">
              {result.rows.length} row{result.rows.length !== 1 ? "s" : ""}
            </span>
          </div>
          {result.truncated && (
            <p className="nl-truncated">Showing first 200 rows — refine your query to see fewer results.</p>
          )}
          {result.rows.length === 0 ? (
            <p className="table-status">No rows returned.</p>
          ) : (
            <div className="table-wrap">
              <table className="txn-table">
                <thead>
                  <tr>
                    {result.columns.map((col) => (
                      <th key={col}>{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((row, i) => (
                    <tr key={i}>
                      {row.map((cell, j) => (
                        <td key={j}>
                          {cell === null || cell === undefined ? (
                            <span className="nl-null">null</span>
                          ) : (
                            String(cell)
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
