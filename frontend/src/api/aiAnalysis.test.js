import assert from "node:assert/strict";
import test from "node:test";

import {
  ANALYSIS_METHODS,
  analyzeQuestion,
  analyzeWithEmbeddings,
  analyzeWithNl2Sql,
  analyzeWithNl2SqlInsight,
  EMBEDDINGS_PLACEHOLDER_MESSAGE,
} from "./aiAnalysis.js";

test("analyzeWithEmbeddings returns the coming-soon placeholder", async () => {
  const result = await analyzeWithEmbeddings("How are my subscriptions trending?");

  assert.equal(result.method, "embeddings");
  assert.equal(result.answer, EMBEDDINGS_PLACEHOLDER_MESSAGE);
});

test("analyzeWithNl2Sql reuses the generate and execute NL2SQL client flow", async () => {
  const calls = [];
  const nl2sqlClient = {
    generate: async (question) => {
      calls.push(["generate", question]);
      return { sql: "SELECT spending_category, SUM(amount) FROM transactions GROUP BY spending_category" };
    },
    execute: async (sql) => {
      calls.push(["execute", sql]);
      return {
        columns: ["spending_category", "sum"],
        rows: [["dining", -42]],
        truncated: false,
      };
    },
  };

  const result = await analyzeWithNl2Sql("How much did I spend on dining?", {
    nl2sqlClient,
  });

  assert.deepEqual(calls, [
    ["generate", "How much did I spend on dining?"],
    ["execute", "SELECT spending_category, SUM(amount) FROM transactions GROUP BY spending_category"],
  ]);
  assert.equal(result.method, "nl2sql");
  assert.equal(result.sql, "SELECT spending_category, SUM(amount) FROM transactions GROUP BY spending_category");
  assert.deepEqual(result.rows, [["dining", -42]]);
});

test("analyzeWithNl2SqlInsight calls the AI Analysis NL2SQL backend flow", async () => {
  const calls = [];
  const analysisClient = {
    nl2sql: async (query) => {
      calls.push(["nl2sql", query]);
      return {
        method: "nl2sql",
        insight: "Dining accounted for the returned spending.",
        answer: "Dining accounted for the returned spending.",
        sql: "SELECT spending_category, SUM(amount) FROM transactions GROUP BY spending_category",
        columns: ["spending_category", "sum"],
        rows: [["dining", -42]],
        truncated: false,
      };
    },
  };

  const result = await analyzeWithNl2SqlInsight("How much did I spend on dining?", { analysisClient });

  assert.deepEqual(calls, [["nl2sql", "How much did I spend on dining?"]]);
  assert.equal(result.insight, "Dining accounted for the returned spending.");
  assert.deepEqual(result.rows, [["dining", -42]]);
});

test("analyzeQuestion routes NL2SQL mode through the insight backend flow", async () => {
  const analysisClient = {
    nl2sql: async (query) => ({
      method: "nl2sql",
      insight: `Insight for ${query}`,
      columns: [],
      rows: [],
      truncated: false,
    }),
  };

  const result = await analyzeQuestion({
    method: ANALYSIS_METHODS.NL2SQL,
    question: "What were my top merchants?",
    analysisClient,
  });

  assert.equal(result.insight, "Insight for What were my top merchants?");
});
