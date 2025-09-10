import React from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import Navbar from "./components/Navbar";
import Overview from "./pages/Overview";
import Vendors from "./pages/Vendors";
import Bills from "./pages/Bills";
import Stock from "./pages/Stock";

function App() {
  return (
    <Router>
      <Navbar />
      <div style={{ padding: "20px" }}>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/vendors" element={<Vendors />} />
          <Route path="/bills" element={<Bills />} />
          <Route path="/stock" element={<Stock />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;
