import { useEffect, useState } from "react";

export default function App() {
  const [message, setMessage] = useState("Loading...");
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const res = await fetch("http://localhost:8000/api/hello?name=React");
        if (!res.ok) {
          throw new Error(`Request failed with status ${res.status}`);
        }
        const data = await res.json();
        setMessage(data.message);
      } catch (err) {
        setError(err.message || "Failed to load");
      }
    }

    load();
  }, []);

  return (
    <main className="page">
      <section className="card">
        <h1>AlloyFinance</h1>
        <p className="subtitle">React ↔ FastAPI wired up</p>
        {error ? (
          <p className="error">{error}</p>
        ) : (
          <p className="message">{message}</p>
        )}
        <div className="meta">
          <span>Backend: http://localhost:8000</span>
          <span>Endpoint: /api/hello</span>
        </div>
      </section>
    </main>
  );
}
