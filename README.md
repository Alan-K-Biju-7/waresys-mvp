---

# 🧾 **Waresys – Intelligent Invoice OCR & Warehouse Management System**

> **Version:** 1.0 • **Framework:** FastAPI + Celery + PostgreSQL + React
> **Stack:** Python, SQLAlchemy, Redis, Tesseract OCR, pdfplumber, Tailwind/React (Frontend)

---

## 📘 **Project Overview**

**Waresys** is an intelligent **invoice OCR and inventory management system** that automates data extraction from vendor invoices and synchronizes it with a warehouse stock database.
It uses **Tesseract OCR**, **pdfplumber**, and **regex-driven pipelines** to parse scanned or text-based PDFs into structured data — including vendor details, bill numbers, line items, and totals — while validating and updating inventory automatically.

---

## ⚙️ **Core Features**

### 🧠 **1. OCR & Invoice Processing**

* Parses invoices via `/bills/ocr` using **Celery background workers** or inline fallback.
* Extracts vendor name, GSTIN, invoice number, bill date, line items, and totals.
* Auto-detects vendor using **GSTIN proximity**, avoids buyer blocks, and flags low-confidence results for review.
* Supports **PDF text-layer extraction** (pdfplumber) and image-based OCR (pytesseract).

### 🏢 **2. Vendor & Product Management**

* CRUD for vendors and products (`/vendors`, `/products`).
* Vendor detection logic powered by **`vendor_detection.py`** with heuristics and POS token recognition.
* Auto-matching of line items to existing products and vendor profiles.

### 📊 **3. Stock & Inventory Tracking**

* Bill confirmation triggers automatic **ledger entries** and **stock quantity updates** via `/bills/{id}/confirm`.
* Built-in **low-stock reporting** endpoint `/stock/low`.
* Categorized stock KPIs for dashboard charts (tiles, sanitaryware, adhesives, etc.).

### 🔐 **4. Authentication & Admin Control**

* Secure **JWT-based login** via `/auth/login` or `/auth/login-json`.
* Role-based users (Admin/User).
* Seeder script `seed_admin.py` creates a default admin account:

  ```
  Email: admin@waresys.app
  Password: admin123
  ```

### 🧾 **5. Review & Audit Workflow**

* Bills that fail sanity checks (missing vendor, invalid totals, or item mismatches) are auto-added to the review queue.
* `/reviews` endpoints allow inspection and resolution before confirmation.

### 📈 **6. Dashboard & Visualization**

* `/api/dashboard/summary` returns KPIs for:

  * Total Products
  * Total Stock Quantity
  * Pending Bills
  * Total Vendors
  * Category breakdown
* `/api/bills/recent` lists latest processed invoices for visualization in frontend Recharts dashboard.

---

## 🧩 **System Architecture**

```
                        ┌────────────────────────────┐
                        │        Frontend UI         │
                        │  (React + Tailwind + API)  │
                        └────────────┬───────────────┘
                                     │
                      ┌───────────────┴────────────────┐
                      │         FastAPI Backend        │
                      │ (app/main.py, presentation API)│
                      └───────────────┬────────────────┘
                                      │
        ┌─────────────────────────────┼──────────────────────────────┐
        │                             │                              │
┌───────▼────────┐          ┌─────────▼────────┐          ┌──────────▼──────────┐
│ Celery Worker  │          │ PostgreSQL DB    │          │ Redis (Broker+Cache) │
│ (OCR pipeline) │          │ (SQLAlchemy ORM) │          │   Async Task Queue   │
└────────────────┘          └──────────────────┘          └──────────────────────┘
```

---

## 🧱 **Project Structure**

```
app/
 ├── main.py                # FastAPI entrypoint (routes, OCR upload, etc.)
 ├── auth.py                # JWT login, register, current_user
 ├── crud.py                # Database CRUD operations
 ├── models.py              # SQLAlchemy models
 ├── schemas.py             # Pydantic schemas
 ├── ocr_pipeline.py        # PDF parsing, line item & vendor extraction
 ├── vendor_detection.py    # Vendor detection heuristics using GSTIN/POS cues
 ├── parsing.py             # Legacy text-based parsing helpers
 ├── tasks.py               # Celery OCR background task handlers
 ├── celery_app.py          # Celery instance definition
 ├── db.py                  # Engine, session, init_db
 ├── config.py              # Environment config (DB, Redis, upload paths)
 ├── stock.py               # Stock update & confirmation logic
 ├── presentation_adapter.py# KPI & dashboard data API
 ├── seed_admin.py          # Seeder script for admin user
 ├── pipeline.py            # Legacy OCR + header parsing pipeline
 ├── test_vendor_detection.py
 ├── test_ocr.py
 ├── index.html             # React-based dashboard frontend
 └── uploads/               # Uploaded invoice PDFs
```

---

## 🚀 **Setup & Run**

### **1️⃣ Prerequisites**

* Docker & Docker Compose
* Tesseract OCR installed (included in container image)
* Redis and PostgreSQL (auto-managed via `docker-compose.yml`)

### **2️⃣ Build & Run**

```bash
docker compose up --build
```

Backend available at:
➡️ **[http://localhost:8000/docs](http://localhost:8000/docs)**
Frontend (React dashboard):
➡️ **[http://localhost:8080](http://localhost:8080)**

---

## 🧮 **Key API Endpoints**

| Endpoint                 | Method   | Description                                         |
| ------------------------ | -------- | --------------------------------------------------- |
| `/auth/register`         | POST     | Create user                                         |
| `/auth/login`            | POST     | Login (form)                                        |
| `/bills/ocr`             | POST     | Upload and process invoice (async Celery or inline) |
| `/bills/{id}`            | GET      | Get bill + lines                                    |
| `/bills/{id}/confirm`    | POST     | Confirm and update stock                            |
| `/products`              | GET/POST | List or create products                             |
| `/vendors`               | GET/POST | List or create vendors                              |
| `/api/dashboard/summary` | GET      | Dashboard KPIs                                      |
| `/search?q=term`         | GET      | Global search (bills, products, vendors)            |

---

## 🧠 **OCR Logic Highlights**

| Stage                | Module                | Description                                                     |
| -------------------- | --------------------- | --------------------------------------------------------------- |
| **Vendor Detection** | `vendor_detection.py` | Detects vendor name using GST proximity & address scoring       |
| **Header Parsing**   | `ocr_pipeline.py`     | Extracts invoice no., date, vendor details                      |
| **Line Extraction**  | `ocr_pipeline.py`     | Parses HSN, Qty, Rate, Amount patterns & validates              |
| **Total Validation** | `ocr_pipeline.py`     | Compares extracted totals with tax summaries                    |
| **Fallback OCR**     | `pipeline.py`         | Legacy pure Tesseract-based extraction                          |
| **Review Flagging**  | `main.py`             | Sets `needs_review` if bill_no uncertain or totals inconsistent |

---

## 🧪 **Testing**

Run tests directly inside the container:

```bash
pytest -q app/test_vendor_detection.py
python app/test_ocr.py /app/uploads/sample_invoice.pdf
```

---

## 🧰 **Environment Variables**

| Variable       | Default                                                | Description                               |
| -------------- | ------------------------------------------------------ | ----------------------------------------- |
| `DATABASE_URL` | `postgresql+psycopg://waresys:waresys@db:5432/waresys` | DB connection string                      |
| `REDIS_URL`    | `redis://redis:6379/0`                                 | Celery broker/backend                     |
| `UPLOAD_DIR`   | `/app/uploads`                                         | Directory to store PDFs                   |
| `JWT_SECRET`   | `dev-change-me`                                        | Secret key for JWT                        |
| `OCR_SYNC`     | `0`                                                    | Set `1` to process OCR inline (for demos) |

---

## 💡 **Demo Flow**

1. Upload an invoice via `/bills/ocr`
2. Celery worker extracts text → parses header + lines
3. Vendor auto-detected via GST proximity
4. Products matched or added to DB
5. Dashboard updates live with stock, category, and bill summary
6. Admin reviews flagged bills (if any)

---

## 🛠 **Tech Stack**

| Component        | Technology                         |
| ---------------- | ---------------------------------- |
| Backend          | FastAPI, SQLAlchemy ORM            |
| OCR Engine       | pdfplumber, pdf2image, pytesseract |
| Task Queue       | Celery + Redis                     |
| Database         | PostgreSQL                         |
| Auth             | JWT (python-jose)                  |
| Frontend         | React + Tailwind + Recharts        |
| Containerization | Docker + Docker Compose            |

---

## 👨‍💻 **Developed By**

**Team Waresys** — A collaborative project for intelligent invoice processing & warehouse management.
© 2025 All Rights Reserved.

---
