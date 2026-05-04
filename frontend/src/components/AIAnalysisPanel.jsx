import { useState } from "react";
import { ANALYSIS_METHODS, analyzeQuestion } from "../api/aiAnalysis";
import NL2SQLResultTable from "./NL2SQLResultTable";

const FRIENDLY_NL2SQL_ERROR =
  "I couldn’t analyze that question. Try making it more specific, such as asking about spending, categories, merchants, budgets, or time periods.";

export default function AIAnalysisPanel() {
  const [method, setMethod] = useState(ANALYSIS_METHODS.NL2SQL);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleAnalyze = async () => {
    const trimmedQuestion = question.trim();

    if (!trimmedQuestion) {
      setError("Enter a finance question to analyze.");
      setResult(null);
      return;
    }

    setLoading(true);
    setError("");
    setResult(null);

    try {
      const analysis = await analyzeQuestion({ method, question: trimmedQuestion });
      setResult(analysis);
    } catch (err) {
      // Keep the user-facing error friendly while preserving enough detail for debugging.
      console.error("[AIAnalysis] NL2SQL analysis failed", err);
      setError(FRIENDLY_NL2SQL_ERROR);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && !loading) {
      handleAnalyze();
    }
  };

  const resultRowCount = result?.rows?.length || 0;

  return (
    <div className="nl-panel">
      <section className="card">
        <div className="table-header">
          <div>
            <h2>AI Analysis</h2>
            <p className="analysis-subtitle">Choose how AlloyFinance should analyze your question.</p>
          </div>
        </div>

        <div className="analysis-form">
          <label className="field">
            <span>Analysis method</span>
            <select
              className="category-select"
              value={method}
              onChange={(e) => {
                setMethod(e.target.value);
                setError("");
                setResult(null);
              }}
            >
              <option value={ANALYSIS_METHODS.NL2SQL}>NL2SQL</option>
              <option value={ANALYSIS_METHODS.EMBEDDINGS}>Embeddings</option>
            </select>
          </label>

          <label className="field">
            <span>Question</span>
            <textarea
              className="nl-textarea"
              placeholder="e.g. How much did I spend on food this month?"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={4}
            />
          </label>
          <p className="nl-hint">Press ⌘ Enter or click Analyze</p>

          <button className="btn btn-primary analysis-submit" onClick={handleAnalyze} disabled={loading}>
            {loading ? "Analyzing..." : "Analyze"}
          </button>
          {loading && (
            <p className="nl-hint">
              {method === ANALYSIS_METHODS.NL2SQL
                ? "Running NL2SQL and generating an AI insight..."
                : "Preparing analysis..."}
            </p>
          )}
        </div>

        {error && <p className="global-error analysis-error">{error}</p>}
      </section>

      {result && (
        <section className="card">
          <div className="table-header">
            <h2>Analysis Result</h2>
            {result.method === ANALYSIS_METHODS.NL2SQL && (
              <span className="txn-count">
                {resultRowCount} row{resultRowCount !== 1 ? "s" : ""}
              </span>
            )}
          </div>

          {result.answer && (
            <div className="analysis-insight">
              <h3>AI Insight / Summary</h3>
              <p className="analysis-answer">{result.answer}</p>
            </div>
          )}

          {result.method === ANALYSIS_METHODS.NL2SQL && (
            <>
              {result.sql && (
                <details className="sql-details">
                  <summary>Generated SQL</summary>
                  <pre className="sql-block">{result.sql}</pre>
                </details>
              )}
              <p className="analysis-answer">
                {resultRowCount > 0
                  ? "Returned data:"
                  : "The NL2SQL query ran successfully, but it did not return matching rows."}
              </p>
              <NL2SQLResultTable result={result} />
            </>
          )}
        </section>
      )}
    </div>
  );
}
