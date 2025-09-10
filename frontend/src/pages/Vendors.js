import React, { useEffect, useState } from "react";

export default function Vendors() {
  const [vendors, setVendors] = useState([]);

  useEffect(() => {
    fetch("http://localhost:8000/vendors").then(r => r.json()).then(setVendors);
  }, []);

  return (
    <div>
      <h2>Vendors</h2>
      <table border="1" cellPadding="10">
        <thead>
          <tr>
            <th>ID</th><th>Name</th><th>GST</th><th>Address</th><th>Contact</th>
          </tr>
        </thead>
        <tbody>
          {vendors.map(v => (
            <tr key={v.id}>
              <td>{v.id}</td>
              <td>{v.name}</td>
              <td>{v.gst_number || "-"}</td>
              <td>{v.address || "-"}</td>
              <td>{v.contact || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
