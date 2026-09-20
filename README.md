# Enfield Lab

A mobile + desktop web app for running a Royal Enfield genuine-parts business:
purchase-invoice PDF extraction, inventory with barcode/QR/OCR scanning,
billing with GST-ready invoices, customer service history, and reports.

Backend: Python/Flask + SQLite (local) or PostgreSQL (production).
Frontend: plain HTML/CSS/JS (no build step), installable as a mobile app (PWA).

## 1. Run it locally

```bash
cd backend
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000 - log in with `admin` / `enfield123` (change this
immediately in Settings, or set `ADMIN_PASSWORD` before first run - see below).

Local data is stored in `instance/enfield.db` (SQLite, created automatically).

## 2. Get a free, permanent database (Neon)

Render's own free Postgres auto-deletes after 30 days, so this app uses
**Neon** for the database instead - free forever, no expiry, just a few
seconds of "cold start" after 5 minutes idle.

1. Go to https://neon.tech and sign up (free).
2. Create a new project (any name, e.g. "enfield-lab").
3. On the project dashboard, copy the **connection string** - it looks like
   `postgresql://user:password@ep-xxxx.neon.tech/neondb?sslmode=require`.
4. Keep this for step 4 below (`DATABASE_URL`).

You do not need to run any SQL yourself - the app creates its tables
automatically the first time it starts against this database.

## 3. Put the code on GitHub

Render deploys from a git repository. From this project's folder:

```bash
git init
git add .
git commit -m "Enfield Lab - initial version"
```

Create a new (private is fine) repository on GitHub, then:

```bash
git remote add origin https://github.com/<your-username>/enfield-lab.git
git branch -M main
git push -u origin main
```

## 4. Deploy on Render (free)

1. Go to https://render.com, sign in (or use the Render connector in this
   chat), click **New +** -> **Web Service**.
2. Connect the `enfield-lab` GitHub repo you just pushed.
3. Render will detect the `Dockerfile` at the repo root automatically -
   choose **Docker** as the environment if asked.
4. Instance type: **Free**.
5. Add these environment variables under "Environment":
   - `DATABASE_URL` = the Neon connection string from step 2
   - `SECRET_KEY` = any long random string (e.g. run `python -c "import secrets; print(secrets.token_hex(32))"`)
   - `ADMIN_USERNAME` = the login username you want (default `admin`)
   - `ADMIN_PASSWORD` = a real password - do not keep the default
6. Click **Create Web Service**. First deploy takes 3-5 minutes (installing
   `tesseract-ocr` for the label-scanning feature).
7. Render gives you a free URL like `https://enfield-lab.onrender.com` -
   that's your live app. Open it, log in, and go to **Settings** to fill in
   your business address, phone, GSTIN and bank details for the invoice PDF.

Notes on the free tier:
- The free web service "sleeps" after 15 minutes with no visits and takes
  about a minute to wake back up on the next request - normal for free
  hosting, no data is lost (the data lives in Neon, not on Render).
- Neon's free database also pauses compute after 5 minutes idle and resumes
  automatically on the next query, usually within a second or two.
- If you outgrow the free tier later (busier shop, want it always-on),
  upgrading either service later is a plan change, not a rebuild.

### Installing it on a phone

Once deployed, open the Render URL in Chrome (Android) or Safari (iPhone)
and use "Add to Home Screen" - it installs like a normal app icon, using the
Enfield Lab logo.

## What's included

- **Dashboard**: sales this month, outstanding receivables, low-stock count,
  total customers, recent invoices.
- **Billing**: new invoice with searchable customer picker (+ add customer
  inline), barcode/QR scan-to-add line items, editable qty/rate/GST per
  line, auto-calculated subtotal/CGST/SGST/total, PDF generation, one-click
  WhatsApp share (uses the phone's native share sheet when available, with
  a WhatsApp link + secure PDF link as a fallback everywhere else).
- **Inventory**: manual add, barcode/QR scan-to-add, camera-photo OCR
  fallback for parts that aren't in the system yet, and one-click purchase
  invoice PDF upload that extracts every line item and updates stock levels
  automatically. Re-uploading the same invoice (matched on Invoice No. +
  Invoice Date) is blocked with a clear message instead of double-counting
  stock.
- **Customers**: searchable list, add customer, click through to a
  customer's full service/invoice history.
- **Reports**: date-range sales summary, GST collected, sales-by-day chart,
  top-selling parts, top customers.
- **Settings**: business profile (printed on invoices), invoice numbering,
  default GST%, low-stock threshold, password change, activity log.

### A note on barcode/QR scanning

The QR code and barcode printed on genuine Royal Enfield part labels encode
a unique per-unit traceability number, not the part number or price - that
information only exists as printed text on the label. So scanning works two
ways:

- If the part is **already in inventory**, scanning it looks it up instantly
  by Part No, saved barcode, or saved QR value - fast, no typing.
- If it's a **brand-new part**, scanning shows "not found" and offers to
  read the label with the camera instead (OCR), which pulls out the Part
  No, MRP and description straight from the printed text so you only have
  to double-check it, not type it from scratch. Bulk-adding a new
  shipment is still fastest via the purchase-invoice PDF upload, which has
  100% structured data straight from the supplier.

## Project layout

```
enfield-lab/
  Dockerfile
  backend/
    app.py                  Flask app factory + auth guard
    db.py                   SQLite/Postgres data layer
    config.py
    schema.sql               SQLite schema
    schema_pg.sql             PostgreSQL schema
    routes/                  API blueprints (one file per screen)
    services/
      pdf_parser.py           Purchase-invoice PDF extraction
      invoice_pdf.py          Customer invoice PDF generation
      util.py                 Activity log, invoice numbering, WhatsApp links
    templates/index.html      Single-page app shell
    static/
      css/style.css
      js/app.js               All frontend logic (vanilla JS, no build step)
      img/                    Logo assets, PWA icons
```
