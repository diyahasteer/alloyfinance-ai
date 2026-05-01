import { useEffect, useMemo, useState } from "react";
import { jsPDF } from "jspdf";
import { monthlyReportsApi } from "../api/monthlyReports";

function currentMonthValue() {
  const now = new Date();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  return `${now.getFullYear()}-${mm}`;
}

function formatMoney(value) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value || 0);
}

function formatMonth(value) {
  if (!value || typeof value !== "string" || !value.includes("-")) {
    return "Unknown month";
  }
  const [y, m] = value.split("-");
  return new Date(Number(y), Number(m) - 1, 1).toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });
}

function formatGeneratedAt(value) {
  if (!value) return "Unknown";
  return new Date(value).toLocaleString();
}

function asArray(value) {
  if (Array.isArray(value)) return value;
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }
  return [];
}

function suggestionToText(item) {
  if (typeof item === "string") return item;
  if (item && typeof item === "object") {
    const title = typeof item.title === "string" ? item.title : "";
    const rationale = typeof item.rationale === "string" ? item.rationale : "";
    const savings = Number(item.estimated_savings_usd || 0);
    const savingsText = savings > 0 ? ` (Estimated savings: ${formatMoney(savings)})` : "";
    const core = [title, rationale].filter(Boolean).join(": ");
    return core ? `${core}${savingsText}` : `Suggestion${savingsText}`;
  }
  return String(item ?? "");
}

function normalizeReport(raw) {
  const yearMonth = typeof raw?.year_month === "string" ? raw.year_month : "";
  return {
    year_month: yearMonth,
    total_spent: Number(raw?.total_spent || 0),
    comments: typeof raw?.comments === "string" ? raw.comments : "",
    suggestions: asArray(raw?.suggestions).map(suggestionToText).filter(Boolean),
    category_breakdown: asArray(raw?.category_breakdown),
    merchant_breakdown: asArray(raw?.merchant_breakdown),
    generated_at: raw?.generated_at || null,
  };
}

export default function MonthlyReportsPanel() {
  const [yearMonth, setYearMonth] = useState(currentMonthValue());
  const [reports, setReports] = useState([]);
  const [selectedMonth, setSelectedMonth] = useState("");
  const [selectedReport, setSelectedReport] = useState(null);
  const [loadingList, setLoadingList] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [loadingReport, setLoadingReport] = useState(false);
  const [error, setError] = useState("");

  const selectedSummary = useMemo(() => {
    if (!selectedReport) return "";
    return `${formatMonth(selectedReport.year_month)} report`;
  }, [selectedReport]);

  const loadReports = async () => {
    setLoadingList(true);
    setError("");
    try {
      const data = await monthlyReportsApi.list();
      const normalized = asArray(data)
        .map(normalizeReport)
        .filter((row) => row.year_month);
      setReports(normalized);
      if (normalized.length > 0) {
        const firstMonth = normalized[0].year_month;
        setSelectedMonth((prev) => prev || firstMonth);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingList(false);
    }
  };

  const loadSingleReport = async (month) => {
    if (!month) return;
    setLoadingReport(true);
    setError("");
    try {
      const data = await monthlyReportsApi.get(month);
      const normalized = normalizeReport(data);
      setSelectedReport(normalized);
      setSelectedMonth(month);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingReport(false);
    }
  };

  useEffect(() => {
    loadReports();
  }, []);

  useEffect(() => {
    if (selectedMonth) {
      loadSingleReport(selectedMonth);
    } else {
      setSelectedReport(null);
    }
  }, [selectedMonth]);

  const handleGenerate = async () => {
    setGenerating(true);
    setError("");
    try {
      const created = normalizeReport(await monthlyReportsApi.generate(yearMonth));
      await loadReports();
      setSelectedMonth(created.year_month);
      setSelectedReport(created);
    } catch (err) {
      setError(err.message);
    } finally {
      setGenerating(false);
    }
  };

  const handleDownloadPdf = () => {
    if (!selectedReport) return;
    const doc = new jsPDF();
    const left = 15;
    const maxWidth = 180;
    let y = 20;

    doc.setFontSize(18);
    doc.text(`AlloyFinance Monthly Report - ${selectedReport.year_month}`, left, y);
    y += 10;

    doc.setFontSize(12);
    doc.text(`Total spent: ${formatMoney(selectedReport.total_spent)}`, left, y);
    y += 8;
    doc.text(`Generated at: ${formatGeneratedAt(selectedReport.generated_at)}`, left, y);
    y += 10;

    doc.setFontSize(13);
    doc.text("Comments", left, y);
    y += 7;
    doc.setFontSize(11);
    const commentsLines = doc.splitTextToSize(selectedReport.comments || "", maxWidth);
    doc.text(commentsLines, left, y);
    y += commentsLines.length * 6 + 6;

    doc.setFontSize(13);
    doc.text("Saving Suggestions", left, y);
    y += 7;
    doc.setFontSize(11);
    (selectedReport.suggestions || []).forEach((item, idx) => {
      const lines = doc.splitTextToSize(`${idx + 1}. ${item}`, maxWidth);
      doc.text(lines, left, y);
      y += lines.length * 6 + 2;
    });

    y += 4;
    doc.setFontSize(13);
    doc.text("Top Categories", left, y);
    y += 7;
    doc.setFontSize(11);
    (selectedReport.category_breakdown || []).slice(0, 8).forEach((row) => {
      doc.text(`${row.category}: ${formatMoney(row.total_spent)}`, left, y);
      y += 6;
    });

    doc.save(`monthly-report-${selectedReport.year_month}.pdf`);
  };

  return (
    <div className="monthly-panel">
      <section className="card">
        <div className="table-header">
          <h2>Generate Monthly Report</h2>
        </div>
        <div className="monthly-generate-row">
          <label className="field monthly-month-field">
            <span>Month</span>
            <input type="month" value={yearMonth} onChange={(e) => setYearMonth(e.target.value)} />
          </label>
          <button className="btn btn-primary" onClick={handleGenerate} disabled={generating || !yearMonth}>
            {generating ? "Generating..." : "Generate report"}
          </button>
        </div>
      </section>

      <section className="card">
        <div className="table-header">
          <h2>Previous Reports</h2>
          <span className="txn-count">{reports.length} saved</span>
        </div>
        {loadingList ? (
          <p className="table-status">Loading reports...</p>
        ) : reports.length === 0 ? (
          <p className="table-status">No reports yet. Generate your first monthly report above.</p>
        ) : (
          <div className="reports-list">
            {reports.map((report) => (
              <button
                key={report.year_month}
                className={`report-list-item ${selectedMonth === report.year_month ? "active" : ""}`}
                onClick={() => setSelectedMonth(report.year_month)}
              >
                <span>{formatMonth(report.year_month)}</span>
                <span>{formatMoney(report.total_spent)}</span>
              </button>
            ))}
          </div>
        )}
      </section>

      {error && <p className="global-error">{error}</p>}

      <section className="card">
        <div className="table-header">
          <h2>{selectedSummary || "Report Details"}</h2>
          <button className="btn btn-filter" disabled={!selectedReport} onClick={handleDownloadPdf}>
            Download PDF
          </button>
        </div>
        {loadingReport ? (
          <p className="table-status">Loading report...</p>
        ) : !selectedReport ? (
          <p className="table-status">Select a report to view it.</p>
        ) : (
          <div className="report-content">
            <div className="report-kpi">
              <p className="txn-count">Total spent</p>
              <h3>{formatMoney(selectedReport.total_spent)}</h3>
            </div>

            <div>
              <h4>Comments</h4>
              <p>{selectedReport.comments || "No comments available."}</p>
            </div>

            <div>
              <h4>Saving suggestions</h4>
              <ul className="report-list">
                {asArray(selectedReport.suggestions).map((item, idx) => (
                  <li key={`${idx}-${item}`}>{item}</li>
                ))}
              </ul>
            </div>

            <div>
              <h4>Top categories</h4>
              <ul className="report-list">
                {asArray(selectedReport.category_breakdown).slice(0, 6).map((row, idx) => (
                  <li key={`${row?.category || "unknown"}-${idx}`}>
                    <span>{row?.category || "unknown"}</span>
                    <span>{formatMoney(row?.total_spent)}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
