export default function NL2SQLResultTable({ result }) {
  if (!result) return null;

  const rows = result.rows || [];
  const columns = result.columns || [];

  return (
    <>
      {result.truncated && (
        <p className="nl-truncated">Showing first 200 rows — refine your query to see fewer results.</p>
      )}
      {rows.length === 0 ? (
        <p className="table-status">No rows returned.</p>
      ) : (
        <div className="table-wrap">
          <table className="txn-table">
            <thead>
              <tr>
                {columns.map((col) => (
                  <th key={col}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
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
    </>
  );
}
