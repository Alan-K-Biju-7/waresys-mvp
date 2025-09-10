import React, { useEffect, useState } from "react";

export default function Bills() {
  const [bills, setBills] = useState([]);

  useEffect(() => {
    fetch("http://localhost:8000/bills").then(r => r.json()).then(setBills);
  }, []);

  return (
    <div>
      <h2>Bills</h2>
      <table border="1" cellPadding="10">
        <thead>
          <tr>
            <th>ID</th><th>Type</th><th>Party</th><th>Date</th><th>Status</th>
          </tr>
        </thead>
        <tbody>
          {bills.map(b => (
            <tr key={b.id}>
              <td>{b.id}</td>
              <td>{b.bill_type}</td>
              <td>{b.party_name}</td>
              <td>{b.bill_date}</td>
              <td>{b.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
