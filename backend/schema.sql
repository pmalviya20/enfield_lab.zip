-- Enfield Lab schema.
-- Written to run on both SQLite (local dev) and PostgreSQL (production/Neon).
-- Differences are handled in db.py at execution time (placeholder style, AUTOINCREMENT vs SERIAL)
-- via the two variants below selected by DB_ENGINE.

-- ================= SQLite variant =================
-- (see schema_pg.sql for the PostgreSQL variant used in production)

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS business_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_name TEXT NOT NULL DEFAULT 'Enfield Lab',
    tagline TEXT DEFAULT 'By The Rider - For The Rider - From The Rider',
    address TEXT,
    phone TEXT,
    email TEXT,
    gstin TEXT,
    bank_name TEXT,
    bank_account_no TEXT,
    bank_ifsc TEXT,
    invoice_prefix TEXT NOT NULL DEFAULT 'INV',
    next_invoice_seq INTEGER NOT NULL DEFAULT 1,
    default_gst_percent REAL NOT NULL DEFAULT 0,
    low_stock_threshold INTEGER NOT NULL DEFAULT 3,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    gstin TEXT,
    phone TEXT,
    email TEXT,
    address TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- One row per uploaded purchase-invoice PDF, used for de-duplication.
CREATE TABLE IF NOT EXISTS purchase_invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id INTEGER REFERENCES suppliers(id),
    invoice_no TEXT NOT NULL,
    invoice_date TEXT,
    order_no TEXT,
    file_name TEXT,
    bill_total REAL,
    taxable_amount REAL,
    total_gst REAL,
    total_mrp REAL,
    line_item_count INTEGER,
    raw_text_hash TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(invoice_no, invoice_date)
);

CREATE TABLE IF NOT EXISTS purchase_invoice_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_invoice_id INTEGER NOT NULL REFERENCES purchase_invoices(id),
    sr_no INTEGER,
    part_no TEXT NOT NULL,
    description TEXT,
    hsn_no TEXT,
    mrp REAL,
    rate REAL,
    qty REAL,
    gst_percent REAL,
    gst_amount REAL,
    amount REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS inventory_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    part_no TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL,
    re_model TEXT,
    hsn_no TEXT,
    mrp REAL NOT NULL DEFAULT 0,
    rate REAL NOT NULL DEFAULT 0,
    gst_percent REAL NOT NULL DEFAULT 0,
    stock_qty REAL NOT NULL DEFAULT 0,
    barcode TEXT,
    qr_code TEXT,
    image_path TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS stock_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inventory_item_id INTEGER NOT NULL REFERENCES inventory_items(id),
    change_qty REAL NOT NULL,
    reason TEXT NOT NULL,
    reference_type TEXT,
    reference_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT,
    address TEXT,
    bike_reg_no TEXT,
    bike_model TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sales_invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_no TEXT UNIQUE NOT NULL,
    customer_id INTEGER REFERENCES customers(id),
    invoice_date TEXT NOT NULL,
    subtotal REAL NOT NULL DEFAULT 0,
    cgst_amount REAL NOT NULL DEFAULT 0,
    sgst_amount REAL NOT NULL DEFAULT 0,
    gst_amount REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL DEFAULT 0,
    amount_paid REAL NOT NULL DEFAULT 0,
    payment_status TEXT NOT NULL DEFAULT 'unpaid',
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sales_invoice_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sales_invoice_id INTEGER NOT NULL REFERENCES sales_invoices(id),
    inventory_item_id INTEGER REFERENCES inventory_items(id),
    description TEXT NOT NULL,
    part_no TEXT,
    qty REAL NOT NULL DEFAULT 1,
    rate REAL NOT NULL DEFAULT 0,
    gst_percent REAL NOT NULL DEFAULT 0,
    line_subtotal REAL NOT NULL DEFAULT 0,
    line_gst_amount REAL NOT NULL DEFAULT 0,
    line_total REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    action TEXT NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Google-authenticated logins. Any Google account can request access; an
-- admin must approve it in Settings before it can be used to log in.
CREATE TABLE IF NOT EXISTS google_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    google_sub TEXT,
    is_approved INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    approved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_inventory_part_no ON inventory_items(part_no);
CREATE INDEX IF NOT EXISTS idx_google_accounts_email ON google_accounts(email);
CREATE INDEX IF NOT EXISTS idx_purchase_invoice_items_invoice ON purchase_invoice_items(purchase_invoice_id);
CREATE INDEX IF NOT EXISTS idx_sales_invoice_items_invoice ON sales_invoice_items(sales_invoice_id);
CREATE INDEX IF NOT EXISTS idx_sales_invoices_customer ON sales_invoices(customer_id);
CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(name);
