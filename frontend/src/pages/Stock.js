import React, { useEffect, useState } from "react";

export default function Stock() {
  const [stock, setStock] = useState([]);

  useEffect(() => {
    fetch("http://localhost:8000/stock").then(r => r.json()).then(setStock);
  }, []);

  return (
    <div>
      <h2>Stock Ledger</h2>
      <table border="1" cellPadding="10">
        <thead>
          <tr>
            <th>Product</th><th>Qty</th><th>Txn Type</th><th>Ref Bill</th>
          </tr>
        </thead>
        <tbody>
          {stock.map((s, i) => (
            <tr key={i}>
              <td>{s.product}</td>
              <td>{s.qty}</td>
              <td>{s.type}</td>
              <td>{s.bill_id}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
