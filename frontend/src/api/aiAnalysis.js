import { nl2sqlApi } from "./nl2sql.js";

const BASE_URL = import.meta.env?.VITE_API_URL || "http://localhost:8000";

export const ANALYSIS_METHODS = {
  NL2SQL: "nl2sql",
  EMBEDDINGS: "embeddings",
};

export const EMBEDDINGS_PLACEHOLDER_MESSAGE =
  "Embedding-based analysis is coming soon. This mode will support qualitative financial insights and semantic search.";

function authHeaders() {
  const token = localStorage.getItem("token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export const aiAnalysisApi = {
  nl2sql: async (query) => {
    const res = await fetch(`${BASE_URL}/api/ai-analysis/nl2sql`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ query }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },
};

export async function analyzeWithNl2Sql(question, { nl2sqlClient = nl2sqlApi } = {}) {
  const generated = await nl2sqlClient.generate(question.trim());
  const data = await nl2sqlClient.execute(generated.sql);

  return {
    ...data,
    method: ANALYSIS_METHODS.NL2SQL,
    question: question.trim(),
    sql: generated.sql,
  };
}

export async function analyzeWithNl2SqlInsight(question, { analysisClient = aiAnalysisApi } = {}) {
  // The AI Analysis backend scopes requests using the authenticated JWT.
  return analysisClient.nl2sql(question.trim());
}

export async function analyzeWithEmbeddings(question) {
  // Replace this placeholder with the real embeddings API call when that backend endpoint exists.
  return {
    method: ANALYSIS_METHODS.EMBEDDINGS,
    question: question.trim(),
    answer: EMBEDDINGS_PLACEHOLDER_MESSAGE,
  };
}

export async function analyzeQuestion({ method, question, analysisClient }) {
  if (method === ANALYSIS_METHODS.EMBEDDINGS) {
    return analyzeWithEmbeddings(question);
  }

  return analyzeWithNl2SqlInsight(question, { analysisClient });
}
