import React, { useEffect, useState } from "react";
import KPI from "../components/KPI";
import StockPieChart from "../components/StockPieChart";

export default function Overview() {
  const [vendors, setVendors] = useState([]);
  const [bills, setBills] = useState([]);
  const [stock, setStock] = useState([]);

  useEffect(() => {
    fetch("http://localhost:8000/vendors").then(r => r.json()).then(setVendors);
    fetch("http://localhost:8000/bills").then(r => r.json()).then(setBills);
    fetch("http://localhost:8000/stock").then(r => r.json()).then(setStock);
  }, []);

  return (
    <div>
      <h1>Waresys Dashboard</h1>
      <div style={{ display: "flex" }}>
        <KPI title="Vendors" value={vendors.length} />
        <KPI title="Bills" value={bills.length} />
        <KPI title="Stock Items" value={stock.length} />
      </div>
      <h2>Stock Distribution</h2>
      <StockPieChart data={stock.map(s => ({ product: s.product, qty: s.qty }))} />
    </div>
  );
}
