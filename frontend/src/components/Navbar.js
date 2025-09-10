import React from "react";
import { Link } from "react-router-dom";

export default function Navbar() {
  return (
    <nav style={{ padding: "15px", background: "#282c34" }}>
      <Link to="/" style={{ margin: "10px", color: "white" }}>Overview</Link>
      <Link to="/vendors" style={{ margin: "10px", color: "white" }}>Vendors</Link>
      <Link to="/bills" style={{ margin: "10px", color: "white" }}>Bills</Link>
      <Link to="/stock" style={{ margin: "10px", color: "white" }}>Stock</Link>
    </nav>
  );
}
