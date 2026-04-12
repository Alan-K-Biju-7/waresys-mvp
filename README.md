# 📦 Waresys — Intelligent Invoice Processing & Inventory Management System

Waresys is an AI-driven system designed to **automate invoice data extraction and warehouse inventory management**. It automatically processes invoices, interprets their contents, and synchronizes stock records, thereby reducing manual effort, minimizing errors, and improving real-time inventory visibility.

The system bridges the gap between **physical or digital invoices** and structured inventory databases using **Optical Character Recognition (OCR)**, automated data validation, and intelligent stock update mechanisms.

---

## 🧠 Project Overview

In warehouse and retail environments, invoices are commonly received as **PDFs or scanned documents**. Manual entry of invoice data into inventory systems is often:

* Time-consuming
* Prone to human error
* Difficult to audit
* Unsuitable for large-scale operations

**Waresys addresses these limitations** by automatically reading invoices, extracting structured financial and product information, and updating inventory records with minimal human intervention.

Core functional capabilities include:

* Automated invoice ingestion and processing
* Vendor, product, and quantity identification
* Financial validation and consistency checks
* Inventory updates and exception handling
* Automated flagging of anomalous or incomplete invoices

---

## ❓ Motivation and Problem Statement

Organizations frequently face the following challenges:

* Invoices arrive in **non-standardized layouts and formats**
* Manual data entry results in **stock discrepancies and accounting inaccuracies**
* Existing inventory systems lack **robust audit and review mechanisms**
* Strategic inventory planning requires **real-time stock insights**

**Waresys provides a systematic solution by offering:**

* Automated invoice processing to eliminate repetitive manual work
* Accuracy enhancement through validation and verification logic
* Transparent audit workflows to ensure accountability
* Scalable architecture supported by asynchronous background processing

---

## 🚀 Key Functional Features

### 1. Intelligent Invoice Processing (OCR)

* Supports both **text-based and scanned PDF invoices**
* Extracts:

  * Vendor name and GSTIN
  * Invoice number and billing date
  * Line items including product name, quantity, rate, and amount
  * Tax values and total payable amount
* Implements confidence-based detection to identify uncertain fields
* Automatically flags invoices requiring human review

---

### 2. Vendor and Product Recognition

* Maintains a centralized **vendor and product registry**
* Detects vendors using:

  * GSTIN proximity analysis
  * Address matching and textual heuristics
* Matches extracted invoice items to existing product records
* Reduces duplication of vendor and product entries

---

### 3. Automated Inventory Synchronization

* Updates inventory **only after invoice confirmation**
* Each confirmed invoice:

  * Generates ledger records
  * Updates stock quantities in the database
* Provides automated **low-stock alerts**
* Supports categorized stock tracking (e.g., tiles, sanitaryware, adhesives)

---

### 4. Review and Audit Mechanism

Invoices exhibiting the following anomalies are automatically flagged:

* Missing or unidentified vendor information
* Total value inconsistencies
* Ambiguous or unmatched line items

Administrators can:

* Inspect extracted invoice data
* Correct erroneous fields
* Approve invoices prior to stock updates

This ensures **data integrity, traceability, and accountability**.

---

### 5. Dashboard and Analytical Insights

The system provides a real-time dashboard displaying:

* Total registered products
* Aggregate stock quantity
* Pending invoice count
* Vendor registry statistics

Additional visualization features include:

* Category-wise inventory distribution
* Recent invoice processing activity

---

### 6. Secure Authentication and Access Control

* Implements **JWT-based authentication**
* Supports **role-based authorization**, including:

  * **Administrator** — Full system control and approval privileges
  * **User** — Limited access for invoice upload and data viewing
* Secure login mechanisms for both form-based and API-based authentication

---

## 🧩 System Workflow (High-Level Process Flow)

```
Invoice Upload
        ↓
Text Extraction (PDF / OCR)
        ↓
Vendor and Header Identification
        ↓
Line Item Parsing and Validation
        ↓
Manual Review (if required)
        ↓
Invoice Confirmation
        ↓
Inventory Update
        ↓
Dashboard Reporting
```
## Screenshots

**Dashboard**
<img width="2512" height="1416" alt="Screenshot 2025-10-15 205443" src="https://github.com/user-attachments/assets/ef06ffd2-5c8f-460e-8834-b207ee06f952" />

**Invoice upload**
<img width="2516" height="1408" alt="Screenshot 2025-10-15 205747" src="https://github.com/user-attachments/assets/c45d5099-c777-4776-acd6-55b2bb8df96a" />

**Categories**
<img width="2531" height="1406" alt="Screenshot 2025-10-15 205806" src="https://github.com/user-attachments/assets/48624844-ba1e-4f3a-a769-594ec80dddce" />

**Stock**
<img width="2517" height="1397" alt="Screenshot 2025-10-15 205816" src="https://github.com/user-attachments/assets/ed3236c6-e6d0-4ea4-9db6-44f391127d3e" />

**Notifications and alerts**

<img width="558" height="600" alt="Screenshot 2025-10-15 205824" src="https://github.com/user-attachments/assets/a34eff15-22ce-4e5c-baa0-f7e0aa907e0a" />

---

## 🏗️ System Architecture

<img width="1631" height="1248" alt="image" src="https://github.com/user-attachments/assets/36a90484-2186-4698-9692-2ce10d85d679" />

---
## ⚙️ Deployment and Setup Instructions

### Prerequisites

* Docker
* Docker Compose
* No manual database or Redis configuration required

### Execution

```bash
docker compose up --build
```

### Access Interfaces

* API Documentation: `http://localhost:8000/docs`
* Frontend Dashboard: `http://localhost:8080`

---

## 🔑 Default Administrator Credentials

Generated automatically during initialization:

* **Email:** `admin@waresys.app`
* **Password:** `admin123`

---

## 🧠 Technologies Employed

| System Layer   | Technology                |
| -------------- | ------------------------- |
| Backend        | FastAPI, SQLAlchemy       |
| OCR Engine     | Tesseract, pdfplumber     |
| Task Queue     | Celery + Redis            |
| Database       | PostgreSQL                |
| Authentication | JWT                       |
| Frontend       | React, Tailwind, Recharts |
| Deployment     | Docker                    |

---

## 💡 Demonstration Workflow

1. Upload an invoice document
2. Automated extraction and parsing of invoice data
3. Vendor and product identification
4. Optional administrative review
5. Invoice confirmation
6. Automated inventory update
7. Real-time dashboard visualization

---

## Future Improvements

1. PO and GRN matching for advanced invoice verification.
2. AI demand forecasting for smart stock replenishment.
3. Automated exception handling and approval routing.
4. Multi-warehouse support with supplier analytic

---

## 👨‍💻 Development Team

**Team Waresys**
An academic project focused on **automated invoice intelligence and warehouse inventory optimization**.

© 2025 — All Rights Reserved

---

