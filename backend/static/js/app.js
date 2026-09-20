/* Enfield Lab - frontend application (vanilla JS, no build step). */
(() => {
  "use strict";

  /* ============================== API helper ============================== */
  async function api(path, opts = {}) {
    const finalOpts = Object.assign({ credentials: "same-origin" }, opts);
    finalOpts.headers = Object.assign({}, opts.headers);
    if (opts.json !== undefined) {
      finalOpts.headers["Content-Type"] = "application/json";
      finalOpts.body = JSON.stringify(opts.json);
    }
    const res = await fetch(path, finalOpts);
    let data = null;
    const contentType = res.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      data = await res.json().catch(() => null);
    }
    if (!res.ok) {
      const message = (data && (data.message || data.error)) || `Request failed (${res.status})`;
      const err = new Error(message);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  const fmtMoney = (n) => "₹" + (Number(n) || 0).toLocaleString("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
  const fmtNum = (n) => {
    const num = Number(n) || 0;
    return Number.isInteger(num) ? String(num) : num.toFixed(2);
  };
  const escapeHtml = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const todayISO = () => new Date().toISOString().slice(0, 10);

  function showToast(msg, isError) {
    const el = document.getElementById("toast");
    el.textContent = msg;
    el.style.background = isError ? "#d92d20" : "#1a1a1a";
    el.hidden = false;
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => { el.hidden = true; }, 3500);
  }

  /* ============================== Auth / bootstrap ============================== */
  const loginScreen = document.getElementById("login-screen");
  const appShell = document.getElementById("app-shell");

  async function boot() {
    try {
      await api("/api/me");
      showApp();
    } catch (e) {
      showLogin();
    }
  }

  function showLogin() {
    loginScreen.hidden = false;
    appShell.hidden = true;
  }

  function showApp() {
    loginScreen.hidden = true;
    appShell.hidden = false;
    if (!location.hash) location.hash = "#/dashboard";
    router();
  }

  document.getElementById("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("login-username").value.trim();
    const password = document.getElementById("login-password").value;
    const errBox = document.getElementById("login-error");
    errBox.hidden = true;
    try {
      await api("/api/login", { method: "POST", json: { username, password } });
      showApp();
    } catch (err) {
      errBox.textContent = err.message;
      errBox.hidden = false;
    }
  });

  document.getElementById("logout-btn").addEventListener("click", async () => {
    await api("/api/logout", { method: "POST" }).catch(() => {});
    location.hash = "";
    showLogin();
  });

  /* ============================== Drawer (swipe + burger) ============================== */
  const drawer = document.getElementById("drawer");
  const backdrop = document.getElementById("drawer-backdrop");
  const EDGE_ZONE = 28; // px from left edge that starts a swipe-open gesture
  const drawerWidth = () => drawer.offsetWidth || 260;
  let drawerOpen = false;
  let dragging = false;
  let dragStartX = 0;
  let dragCurrentX = 0;
  let dragEdgeStart = false;
  let dragFromOpen = false;

  function setDrawerTransform(px, animate) {
    drawer.classList.toggle("animate", !!animate);
    drawer.classList.toggle("dragging", !animate);
    drawer.style.transform = `translateX(${px}px)`;
  }

  function openDrawer(animate = true) {
    drawerOpen = true;
    setDrawerTransform(0, animate);
    backdrop.classList.add("visible");
  }
  function closeDrawer(animate = true) {
    drawerOpen = false;
    setDrawerTransform(-drawerWidth(), animate);
    backdrop.classList.remove("visible");
  }

  document.getElementById("burger-btn").addEventListener("click", () => {
    drawerOpen ? closeDrawer() : openDrawer();
  });
  backdrop.addEventListener("click", () => closeDrawer());

  // Touch handling for smooth, native-feeling swipe. Uses transform only
  // (no layout thrashing) and passive listeners where possible so it never
  // janks the main thread.
  document.addEventListener("touchstart", (e) => {
    const x = e.touches[0].clientX;
    if (!drawerOpen && x <= EDGE_ZONE) {
      dragging = true; dragEdgeStart = true; dragFromOpen = false;
      dragStartX = x; dragCurrentX = x;
      setDrawerTransform(-drawerWidth(), false);
      backdrop.classList.add("visible");
      backdrop.style.opacity = "0";
    } else if (drawerOpen) {
      dragging = true; dragEdgeStart = false; dragFromOpen = true;
      dragStartX = x; dragCurrentX = x;
    }
  }, { passive: true });

  document.addEventListener("touchmove", (e) => {
    if (!dragging) return;
    dragCurrentX = e.touches[0].clientX;
    const delta = dragCurrentX - dragStartX;
    const w = drawerWidth();
    let px;
    if (dragEdgeStart) {
      px = Math.min(0, Math.max(-w, -w + delta));
      backdrop.style.opacity = String(Math.min(1, Math.max(0, (delta / w))));
    } else if (dragFromOpen) {
      px = Math.min(0, Math.max(-w, delta));
      backdrop.style.opacity = String(Math.min(1, Math.max(0, 1 + px / w)));
    }
    if (px !== undefined) setDrawerTransform(px, false);
  }, { passive: true });

  document.addEventListener("touchend", () => {
    if (!dragging) return;
    dragging = false;
    const delta = dragCurrentX - dragStartX;
    const w = drawerWidth();
    backdrop.style.opacity = "";
    if (dragEdgeStart) {
      if (delta > w * 0.28) openDrawer(true); else closeDrawer(true);
    } else if (dragFromOpen) {
      if (delta < -w * 0.28) closeDrawer(true); else openDrawer(true);
    }
  });

  // Initialize closed off-screen.
  setDrawerTransform(-drawerWidth(), false);
  window.addEventListener("resize", () => { if (!drawerOpen) setDrawerTransform(-drawerWidth(), false); });

  /* ============================== Router ============================== */
  const routeTitles = {
    dashboard: "Dashboard", billing: "Billing", inventory: "Inventory",
    customers: "Customers", reports: "Reports", settings: "Settings",
  };
  const routeLoaders = {
    dashboard: loadDashboard, billing: loadBilling, inventory: loadInventory,
    customers: loadCustomers, reports: loadReports, settings: loadSettings,
  };

  function router() {
    const hash = location.hash.replace("#/", "") || "dashboard";
    const route = routeTitles[hash] ? hash : "dashboard";
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    document.getElementById(`view-${route}`).classList.add("active");
    document.getElementById("topbar-title").textContent = routeTitles[route];
    document.querySelectorAll(".drawer-nav a").forEach((a) => a.classList.toggle("active", a.dataset.route === route));
    closeDrawer(true);
    routeLoaders[route] && routeLoaders[route]();
  }
  window.addEventListener("hashchange", router);

  /* ============================== Generic modal helper ============================== */
  function openModal({ title, bodyHtml, footerHtml, onMount, wide }) {
    const root = document.getElementById("modal-root");
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.innerHTML = `
      <div class="modal" style="${wide ? "max-width:760px" : ""}">
        <div class="modal-header"><h3>${title}</h3><button class="modal-close" aria-label="Close">&times;</button></div>
        <div class="modal-body">${bodyHtml}</div>
        ${footerHtml ? `<div class="modal-footer">${footerHtml}</div>` : ""}
      </div>`;
    root.appendChild(overlay);
    const close = () => overlay.remove();
    overlay.querySelector(".modal-close").addEventListener("click", close);
    overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
    if (onMount) onMount(overlay, close);
    return { overlay, close };
  }

  /* ============================== Barcode / QR scanner ============================== */
  function openScanner(onDecode, hint) {
    const { overlay, close } = openModal({
      title: "Scan Barcode / QR",
      bodyHtml: `
        <div class="scanner-wrap"><video id="scanner-video" playsinline muted></video><div class="scan-frame"></div></div>
        <p class="scanner-hint">${hint || "Point the camera at the part's barcode or QR code."}</p>
        <div class="field"><label>Or type the code manually</label>
          <div style="display:flex;gap:8px;">
            <input type="text" id="manual-code" class="input" placeholder="e.g. RAN00043/C">
            <button class="btn btn-outline" id="manual-code-go">Use</button>
          </div>
        </div>`,
    });
    let codeReader = null;
    let stopped = false;
    const stop = () => {
      if (stopped) return;
      stopped = true;
      try { codeReader && codeReader.reset(); } catch (e) {}
    };
    const finish = (code) => { stop(); close(); onDecode(code); };

    overlay.querySelector(".modal-close").addEventListener("click", stop);
    overlay.querySelector("#manual-code-go").addEventListener("click", () => {
      const v = overlay.querySelector("#manual-code").value.trim();
      if (v) finish(v);
    });
    overlay.querySelector("#manual-code").addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); overlay.querySelector("#manual-code-go").click(); }
    });

    try {
      if (typeof ZXing === "undefined") throw new Error("Scanner library not loaded");
      codeReader = new ZXing.BrowserMultiFormatReader();
      const videoEl = overlay.querySelector("#scanner-video");
      codeReader.decodeFromVideoDevice(undefined, videoEl, (result, err) => {
        if (stopped) return;
        if (result) finish(result.getText());
      }).catch((e) => {
        showToast("Camera unavailable - type the code instead", true);
      });
    } catch (e) {
      showToast("Scanner unavailable on this device - type the code instead", true);
    }
  }

  /* ============================== WhatsApp share ============================== */
  async function shareInvoice(invoiceId, invoiceNo) {
    try {
      const pdfRes = await fetch(`/api/invoices/${invoiceId}/pdf`, { credentials: "same-origin" });
      const blob = await pdfRes.blob();
      const file = new File([blob], `${invoiceNo || "invoice"}.pdf`, { type: "application/pdf" });
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        await navigator.share({ files: [file], title: invoiceNo, text: `Invoice ${invoiceNo}` });
        return;
      }
    } catch (e) { /* fall through to link-based share */ }
    try {
      const link = await api(`/api/invoices/${invoiceId}/share-link`);
      window.open(link.whatsapp_url, "_blank");
    } catch (e) {
      showToast("Could not create share link: " + e.message, true);
    }
  }

  function downloadInvoicePdf(invoiceId) {
    window.open(`/api/invoices/${invoiceId}/pdf`, "_blank");
  }

  function invoiceActionsHtml(inv) {
    return `<div style="display:flex;gap:6px;flex-wrap:wrap;">
      <button class="btn btn-outline btn-sm" data-pdf="${inv.id}">PDF</button>
      <button class="btn btn-outline btn-sm" data-share="${inv.id}" data-invno="${escapeHtml(inv.invoice_no)}">WhatsApp</button>
    </div>`;
  }
  function bindInvoiceActionButtons(container) {
    container.querySelectorAll("[data-pdf]").forEach((b) => b.addEventListener("click", () => downloadInvoicePdf(b.dataset.pdf)));
    container.querySelectorAll("[data-share]").forEach((b) => b.addEventListener("click", () => shareInvoice(b.dataset.share, b.dataset.invno)));
  }

  function statusBadge(status) {
    const cls = status === "paid" ? "badge-paid" : status === "partial" ? "badge-partial" : "badge-unpaid";
    return `<span class="badge ${cls}">${status}</span>`;
  }

  /* ============================== DASHBOARD ============================== */
  async function loadDashboard() {
    const d = await api("/api/dashboard");
    document.getElementById("tile-sales").textContent = fmtMoney(d.sales_this_month);
    document.getElementById("tile-outstanding").textContent = fmtMoney(d.outstanding_receivables);
    document.getElementById("tile-lowstock").textContent = d.low_stock_items;
    document.getElementById("tile-customers").textContent = d.total_customers;

    const tbody = document.querySelector("#recent-invoices-table tbody");
    tbody.innerHTML = "";
    d.recent_invoices.forEach((inv) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${escapeHtml(inv.invoice_no)}</td><td>${escapeHtml(inv.customer_name || "-")}</td>
        <td>${escapeHtml(inv.invoice_date)}</td><td>${fmtMoney(inv.total)}</td><td>${statusBadge(inv.payment_status)}</td>
        <td>${invoiceActionsHtml(inv)}</td>`;
      tbody.appendChild(tr);
    });
    bindInvoiceActionButtons(tbody);
  }

  /* ============================== BILLING ============================== */
  let invoicesCache = [];
  let inventoryCache = [];
  let customersCache = [];

  async function loadBilling() {
    const data = await api("/api/invoices?limit=100");
    invoicesCache = data.invoices;
    renderInvoicesTable(invoicesCache);
  }
  function renderInvoicesTable(list) {
    const tbody = document.querySelector("#invoices-table tbody");
    tbody.innerHTML = "";
    list.forEach((inv) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${escapeHtml(inv.invoice_no)}</td><td>${escapeHtml(inv.customer_name || "-")}</td>
        <td>${escapeHtml(inv.invoice_date)}</td><td>${fmtMoney(inv.total)}</td><td>${fmtMoney(inv.amount_paid)}</td>
        <td>${statusBadge(inv.payment_status)}</td><td>${invoiceActionsHtml(inv)}</td>`;
      tbody.appendChild(tr);
    });
    bindInvoiceActionButtons(tbody);
  }
  document.getElementById("invoice-search").addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase();
    renderInvoicesTable(invoicesCache.filter((i) =>
      (i.invoice_no || "").toLowerCase().includes(q) || (i.customer_name || "").toLowerCase().includes(q)));
  });

  document.getElementById("new-invoice-btn").addEventListener("click", openNewInvoiceModal);

  async function openNewInvoiceModal() {
    const [invData, custData] = await Promise.all([
      inventoryCache.length ? Promise.resolve({ items: inventoryCache }) : api("/api/inventory"),
      api("/api/customers"),
    ]);
    inventoryCache = invData.items;
    customersCache = custData.customers;

    let selectedCustomer = null;
    let lineItems = []; // { inventory_item_id, description, part_no, qty, rate, gst_percent }

    openModal({
      title: "New Invoice",
      wide: true,
      bodyHtml: `
        <div class="field">
          <label>Customer</label>
          <div class="combobox" id="customer-combobox">
            <div style="display:flex;gap:8px;">
              <input type="text" class="input" id="customer-input" placeholder="Search customer by name or phone...">
              <button class="btn btn-outline" id="add-customer-inline-btn" type="button">+ Add</button>
            </div>
            <div class="combobox-list" id="customer-list" hidden></div>
          </div>
        </div>
        <div class="field-row">
          <div class="field"><label>Invoice Date</label><input type="date" class="input" id="invoice-date" value="${todayISO()}"></div>
          <div class="field"><label>Amount Paid Now</label><input type="number" class="input" id="amount-paid" value="0" min="0" step="0.01"></div>
        </div>

        <div class="field">
          <label>Add Item / Service</label>
          <div style="display:flex;gap:8px;">
            <div class="combobox" id="item-combobox" style="flex:1;">
              <input type="text" class="input" id="item-input" placeholder="Search inventory by part no or description...">
              <div class="combobox-list" id="item-list" hidden></div>
            </div>
            <button class="btn btn-outline" id="scan-line-item-btn" type="button">Scan Barcode</button>
          </div>
        </div>

        <table class="line-items-table" id="line-items-table">
          <thead><tr><th>Description</th><th>Part No</th><th>Qty</th><th>Rate</th><th>GST%</th><th>Total</th><th></th></tr></thead>
          <tbody></tbody>
        </table>

        <div class="totals-box">
          <div><span>Subtotal</span><span id="calc-subtotal">${fmtMoney(0)}</span></div>
          <div><span>CGST</span><span id="calc-cgst">${fmtMoney(0)}</span></div>
          <div><span>SGST</span><span id="calc-sgst">${fmtMoney(0)}</span></div>
          <div class="grand"><span>Total</span><span id="calc-total">${fmtMoney(0)}</span></div>
        </div>
      `,
      footerHtml: `<button class="btn btn-outline" id="cancel-invoice">Cancel</button><button class="btn btn-primary" id="save-invoice">Save Invoice</button>`,
      onMount(modal, close) {
        const custInput = modal.querySelector("#customer-input");
        const custList = modal.querySelector("#customer-list");
        function renderCustomerList(filter) {
          const q = (filter || "").toLowerCase();
          const matches = customersCache.filter((c) => !q || c.name.toLowerCase().includes(q) || (c.phone || "").includes(q));
          custList.innerHTML = matches.length
            ? matches.slice(0, 30).map((c) => `<div data-id="${c.id}">${escapeHtml(c.name)} ${c.phone ? "- " + escapeHtml(c.phone) : ""}</div>`).join("")
            : `<div class="empty">No matches - click "+ Add" to create one</div>`;
          custList.hidden = false;
          custList.querySelectorAll("[data-id]").forEach((div) => div.addEventListener("click", () => {
            const c = customersCache.find((x) => String(x.id) === div.dataset.id);
            selectedCustomer = c;
            custInput.value = `${c.name}${c.phone ? " - " + c.phone : ""}`;
            custList.hidden = true;
          }));
        }
        custInput.addEventListener("focus", () => renderCustomerList(custInput.value));
        custInput.addEventListener("input", () => { selectedCustomer = null; renderCustomerList(custInput.value); });
        document.addEventListener("click", (e) => { if (!modal.contains(e.target)) return; if (!e.target.closest("#customer-combobox")) custList.hidden = true; });

        modal.querySelector("#add-customer-inline-btn").addEventListener("click", () => {
          openAddCustomerModal((newCust) => {
            customersCache.unshift(newCust);
            selectedCustomer = newCust;
            custInput.value = `${newCust.name}${newCust.phone ? " - " + newCust.phone : ""}`;
          });
        });

        const itemInput = modal.querySelector("#item-input");
        const itemList = modal.querySelector("#item-list");
        function renderItemList(filter) {
          const q = (filter || "").toLowerCase();
          const matches = inventoryCache.filter((it) => !q || it.part_no.toLowerCase().includes(q) || it.description.toLowerCase().includes(q));
          itemList.innerHTML = matches.length
            ? matches.slice(0, 30).map((it) => `<div data-id="${it.id}">${escapeHtml(it.part_no)} - ${escapeHtml(it.description)} <span style="color:#888">(stock ${fmtNum(it.stock_qty)})</span></div>`).join("")
            : `<div class="empty">No matching parts</div>`;
          itemList.hidden = false;
        }
        itemInput.addEventListener("focus", () => renderItemList(itemInput.value));
        itemInput.addEventListener("input", () => renderItemList(itemInput.value));
        itemList.addEventListener("click", (e) => {
          const div = e.target.closest("[data-id]");
          if (!div) return;
          const it = inventoryCache.find((x) => String(x.id) === div.dataset.id);
          addLine({ inventory_item_id: it.id, description: it.description, part_no: it.part_no, qty: 1, rate: it.rate, gst_percent: it.gst_percent });
          itemInput.value = ""; itemList.hidden = true;
        });
        document.addEventListener("click", (e) => { if (!modal.contains(e.target)) return; if (!e.target.closest("#item-combobox")) itemList.hidden = true; });

        modal.querySelector("#scan-line-item-btn").addEventListener("click", () => {
          openScanner(async (code) => {
            try {
              const result = await api(`/api/inventory/lookup?code=${encodeURIComponent(code)}`);
              if (result.found) {
                addLine({ inventory_item_id: result.item.id, description: result.item.description, part_no: result.item.part_no, qty: 1, rate: result.item.rate, gst_percent: result.item.gst_percent });
                showToast(`Added ${result.item.part_no} to invoice`);
              } else {
                showToast(`Code "${code}" not found in inventory - add it from the Inventory screen first`, true);
              }
            } catch (e) { showToast(e.message, true); }
          });
        });

        function addLine(line) {
          lineItems.push(line);
          renderLines();
        }
        function renderLines() {
          const tbody = modal.querySelector("#line-items-table tbody");
          tbody.innerHTML = "";
          lineItems.forEach((line, idx) => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
              <td><input class="li-desc" value="${escapeHtml(line.description)}"></td>
              <td>${escapeHtml(line.part_no || "-")}</td>
              <td><input type="number" class="li-qty num" value="${line.qty}" min="0.01" step="0.01"></td>
              <td><input type="number" class="li-rate num" value="${line.rate}" min="0" step="0.01"></td>
              <td><input type="number" class="li-gst num" value="${line.gst_percent}" min="0" step="0.01"></td>
              <td class="li-total">${fmtMoney(line.qty * line.rate * (1 + line.gst_percent / 100))}</td>
              <td><button type="button" class="remove-line" data-idx="${idx}">&times;</button></td>`;
            tbody.appendChild(tr);
            tr.querySelector(".li-desc").addEventListener("input", (e) => { line.description = e.target.value; });
            tr.querySelector(".li-qty").addEventListener("input", (e) => { line.qty = parseFloat(e.target.value) || 0; recalc(); });
            tr.querySelector(".li-rate").addEventListener("input", (e) => { line.rate = parseFloat(e.target.value) || 0; recalc(); });
            tr.querySelector(".li-gst").addEventListener("input", (e) => { line.gst_percent = parseFloat(e.target.value) || 0; recalc(); });
            tr.querySelector(".remove-line").addEventListener("click", () => { lineItems.splice(idx, 1); renderLines(); });
          });
          recalc();
        }
        function recalc() {
          const tbody = modal.querySelector("#line-items-table tbody");
          let subtotal = 0, gstTotal = 0;
          lineItems.forEach((line, idx) => {
            const lineSub = line.qty * line.rate;
            const lineGst = lineSub * line.gst_percent / 100;
            subtotal += lineSub; gstTotal += lineGst;
            const cell = tbody.children[idx] && tbody.children[idx].querySelector(".li-total");
            if (cell) cell.textContent = fmtMoney(lineSub + lineGst);
          });
          modal.querySelector("#calc-subtotal").textContent = fmtMoney(subtotal);
          modal.querySelector("#calc-cgst").textContent = fmtMoney(gstTotal / 2);
          modal.querySelector("#calc-sgst").textContent = fmtMoney(gstTotal / 2);
          modal.querySelector("#calc-total").textContent = fmtMoney(subtotal + gstTotal);
        }

        modal.querySelector("#cancel-invoice").addEventListener("click", close);
        modal.querySelector("#save-invoice").addEventListener("click", async () => {
          if (!selectedCustomer) { showToast("Please select or add a customer", true); return; }
          if (!lineItems.length) { showToast("Add at least one item", true); return; }
          const payload = {
            customer_id: selectedCustomer.id,
            invoice_date: modal.querySelector("#invoice-date").value || todayISO(),
            amount_paid: parseFloat(modal.querySelector("#amount-paid").value) || 0,
            items: lineItems,
          };
          try {
            const invoice = await api("/api/invoices", { method: "POST", json: payload });
            showToast(`Invoice ${invoice.invoice_no} created`);
            close();
            loadBilling();
            loadDashboard();
            inventoryCache = []; // stock changed - force refresh next time it's needed
            openInvoiceCreatedModal(invoice);
          } catch (e) {
            showToast(e.message, true);
          }
        });
      },
    });
  }

  function openInvoiceCreatedModal(invoice) {
    openModal({
      title: `Invoice ${invoice.invoice_no} saved`,
      bodyHtml: `<p>Total: <b>${fmtMoney(invoice.total)}</b> &middot; Balance due: <b>${fmtMoney(invoice.total - invoice.amount_paid)}</b></p>
        <p>Share this invoice with the customer:</p>`,
      footerHtml: `<button class="btn btn-outline" id="ic-pdf">Download PDF</button><button class="btn btn-primary" id="ic-whatsapp">Share on WhatsApp</button>`,
      onMount(modal) {
        modal.querySelector("#ic-pdf").addEventListener("click", () => downloadInvoicePdf(invoice.id));
        modal.querySelector("#ic-whatsapp").addEventListener("click", () => shareInvoice(invoice.id, invoice.invoice_no));
      },
    });
  }

  /* ============================== ADD CUSTOMER (shared modal) ============================== */
  function openAddCustomerModal(onCreated) {
    openModal({
      title: "Add Customer",
      bodyHtml: `
        <div class="field"><label>Name *</label><input type="text" class="input" id="c-name" required></div>
        <div class="field-row">
          <div class="field"><label>Phone</label><input type="text" class="input" id="c-phone"></div>
          <div class="field"><label>Bike Registration No.</label><input type="text" class="input" id="c-reg"></div>
        </div>
        <div class="field-row">
          <div class="field"><label>Bike Model</label><input type="text" class="input" id="c-model"></div>
          <div class="field"><label>Address</label><input type="text" class="input" id="c-address"></div>
        </div>`,
      footerHtml: `<button class="btn btn-outline" id="c-cancel">Cancel</button><button class="btn btn-primary" id="c-save">Save Customer</button>`,
      onMount(modal, close) {
        modal.querySelector("#c-cancel").addEventListener("click", close);
        modal.querySelector("#c-save").addEventListener("click", async () => {
          const name = modal.querySelector("#c-name").value.trim();
          if (!name) { showToast("Name is required", true); return; }
          try {
            const customer = await api("/api/customers", {
              method: "POST",
              json: {
                name,
                phone: modal.querySelector("#c-phone").value.trim(),
                bike_reg_no: modal.querySelector("#c-reg").value.trim(),
                bike_model: modal.querySelector("#c-model").value.trim(),
                address: modal.querySelector("#c-address").value.trim(),
              },
            });
            showToast(`Customer ${customer.name} added`);
            close();
            onCreated && onCreated(customer);
          } catch (e) { showToast(e.message, true); }
        });
      },
    });
  }

  /* ============================== INVENTORY ============================== */
  let inventorySearchTimer = null;
  async function loadInventory(query) {
    const q = query != null ? query : document.getElementById("inventory-search").value;
    const data = await api(`/api/inventory${q ? "?q=" + encodeURIComponent(q) : ""}`);
    inventoryCache = data.items;
    const tbody = document.querySelector("#inventory-table tbody");
    tbody.innerHTML = "";
    data.items.forEach((it) => {
      const low = it.stock_qty <= data.low_stock_threshold;
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${escapeHtml(it.part_no)}</td><td class="wrap">${escapeHtml(it.description)}</td>
        <td>${escapeHtml(it.re_model || "-")}</td><td>${fmtMoney(it.mrp)}</td><td>${fmtMoney(it.rate)}</td>
        <td>${fmtNum(it.gst_percent)}%</td>
        <td>${low ? `<span class="badge badge-low">${fmtNum(it.stock_qty)}</span>` : fmtNum(it.stock_qty)}</td>
        <td><button class="btn btn-outline btn-sm" data-edit="${it.id}">Edit</button></td>`;
      tbody.appendChild(tr);
    });
    tbody.querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => openEditItemModal(b.dataset.edit)));
  }
  document.getElementById("inventory-search").addEventListener("input", () => {
    clearTimeout(inventorySearchTimer);
    inventorySearchTimer = setTimeout(() => loadInventory(), 300);
  });

  function openAddItemModal(prefill) {
    const p = prefill || {};
    openModal({
      title: "Add Inventory Item",
      bodyHtml: `
        <div class="field-row">
          <div class="field"><label>Part No *</label><input type="text" class="input" id="i-partno" value="${escapeHtml(p.part_no || "")}"></div>
          <div class="field"><label>RE Model</label><input type="text" class="input" id="i-model" value="${escapeHtml(p.re_model || "")}"></div>
        </div>
        <div class="field"><label>Description *</label><input type="text" class="input" id="i-desc" value="${escapeHtml(p.description || "")}"></div>
        <div class="field-row">
          <div class="field"><label>MRP</label><input type="number" step="0.01" class="input" id="i-mrp" value="${p.mrp || 0}"></div>
          <div class="field"><label>Rate (selling)</label><input type="number" step="0.01" class="input" id="i-rate" value="${p.rate || p.mrp || 0}"></div>
        </div>
        <div class="field-row">
          <div class="field"><label>GST %</label><input type="number" step="0.01" class="input" id="i-gst" value="${p.gst_percent || 0}"></div>
          <div class="field"><label>Opening Stock</label><input type="number" step="0.01" class="input" id="i-stock" value="${p.stock_qty || 0}"></div>
        </div>
        <div class="field"><label>Barcode / QR (optional)</label><input type="text" class="input" id="i-barcode" value="${escapeHtml(p.barcode || "")}"></div>
        ${p.raw_text_hint ? `<p style="font-size:12px;color:#888;">Auto-filled from label photo - please double-check before saving.</p>` : ""}
      `,
      footerHtml: `<button class="btn btn-outline" id="i-cancel">Cancel</button><button class="btn btn-primary" id="i-save">Save Item</button>`,
      onMount(modal, close) {
        modal.querySelector("#i-cancel").addEventListener("click", close);
        modal.querySelector("#i-save").addEventListener("click", async () => {
          const part_no = modal.querySelector("#i-partno").value.trim();
          const description = modal.querySelector("#i-desc").value.trim();
          if (!part_no || !description) { showToast("Part No and Description are required", true); return; }
          try {
            await api("/api/inventory", {
              method: "POST",
              json: {
                part_no, description,
                re_model: modal.querySelector("#i-model").value.trim(),
                mrp: parseFloat(modal.querySelector("#i-mrp").value) || 0,
                rate: parseFloat(modal.querySelector("#i-rate").value) || 0,
                gst_percent: parseFloat(modal.querySelector("#i-gst").value) || 0,
                stock_qty: parseFloat(modal.querySelector("#i-stock").value) || 0,
                barcode: modal.querySelector("#i-barcode").value.trim(),
                source: prefill ? "scan_ocr" : "manual",
              },
            });
            showToast(`${part_no} added to inventory`);
            close();
            loadInventory();
          } catch (e) { showToast(e.message, true); }
        });
      },
    });
  }

  function openEditItemModal(id) {
    const it = inventoryCache.find((x) => String(x.id) === String(id));
    if (!it) return;
    openModal({
      title: `Edit ${it.part_no}`,
      bodyHtml: `
        <div class="field"><label>Description</label><input type="text" class="input" id="e-desc" value="${escapeHtml(it.description)}"></div>
        <div class="field-row">
          <div class="field"><label>RE Model</label><input type="text" class="input" id="e-model" value="${escapeHtml(it.re_model || "")}"></div>
          <div class="field"><label>Stock Qty</label><input type="number" step="0.01" class="input" id="e-stock" value="${it.stock_qty}"></div>
        </div>
        <div class="field-row">
          <div class="field"><label>MRP</label><input type="number" step="0.01" class="input" id="e-mrp" value="${it.mrp}"></div>
          <div class="field"><label>Rate</label><input type="number" step="0.01" class="input" id="e-rate" value="${it.rate}"></div>
        </div>
        <div class="field"><label>GST %</label><input type="number" step="0.01" class="input" id="e-gst" value="${it.gst_percent}"></div>`,
      footerHtml: `<button class="btn btn-outline" id="e-cancel">Cancel</button><button class="btn btn-primary" id="e-save">Save Changes</button>`,
      onMount(modal, close) {
        modal.querySelector("#e-cancel").addEventListener("click", close);
        modal.querySelector("#e-save").addEventListener("click", async () => {
          try {
            await api(`/api/inventory/${it.id}`, {
              method: "PUT",
              json: {
                description: modal.querySelector("#e-desc").value.trim(),
                re_model: modal.querySelector("#e-model").value.trim(),
                stock_qty: parseFloat(modal.querySelector("#e-stock").value) || 0,
                mrp: parseFloat(modal.querySelector("#e-mrp").value) || 0,
                rate: parseFloat(modal.querySelector("#e-rate").value) || 0,
                gst_percent: parseFloat(modal.querySelector("#e-gst").value) || 0,
              },
            });
            showToast("Item updated");
            close();
            loadInventory();
          } catch (e) { showToast(e.message, true); }
        });
      },
    });
  }

  document.getElementById("add-item-btn").addEventListener("click", () => openAddItemModal());

  document.getElementById("scan-add-btn").addEventListener("click", () => {
    openScanner(async (code) => {
      try {
        const result = await api(`/api/inventory/lookup?code=${encodeURIComponent(code)}`);
        if (result.found) {
          openModal({
            title: "Part Found",
            bodyHtml: `<p><b>${escapeHtml(result.item.part_no)}</b> - ${escapeHtml(result.item.description)}</p>
              <p>Current stock: <b>${fmtNum(result.item.stock_qty)}</b></p>
              <div class="field"><label>Add to stock</label><input type="number" class="input" id="add-qty" value="1" min="0.01" step="0.01"></div>`,
            footerHtml: `<button class="btn btn-primary" id="add-qty-save">Add Stock</button>`,
            onMount(modal, close) {
              modal.querySelector("#add-qty-save").addEventListener("click", async () => {
                const qty = parseFloat(modal.querySelector("#add-qty").value) || 0;
                await api(`/api/inventory/${result.item.id}`, { method: "PUT", json: { stock_qty: result.item.stock_qty + qty } });
                showToast("Stock updated");
                close();
                loadInventory();
              });
            },
          });
        } else {
          openOcrCaptureModal(code);
        }
      } catch (e) { showToast(e.message, true); }
    }, "This part isn't a match to a known code yet? We'll help you add it from the label photo.");
  });

  function openOcrCaptureModal(scannedCode) {
    openModal({
      title: "New Part - Capture Label",
      bodyHtml: `<p>Code <b>${escapeHtml(scannedCode)}</b> isn't in inventory yet. Take a clear photo of the label
        (the side printed with PART NO / MRP) and we'll try to auto-fill the details.</p>
        <input type="file" accept="image/*" capture="environment" id="ocr-photo" class="input">
        <p id="ocr-status" style="font-size:13px;color:#888;margin-top:8px;"></p>`,
      footerHtml: `<button class="btn btn-outline" id="ocr-skip">Enter Manually</button>`,
      onMount(modal, close) {
        modal.querySelector("#ocr-skip").addEventListener("click", () => { close(); openAddItemModal({ barcode: scannedCode }); });
        modal.querySelector("#ocr-photo").addEventListener("change", async (e) => {
          const file = e.target.files[0];
          if (!file) return;
          modal.querySelector("#ocr-status").textContent = "Reading label...";
          const fd = new FormData();
          fd.append("photo", file);
          try {
            const result = await api("/api/inventory/scan-ocr", { method: "POST", body: fd });
            close();
            openAddItemModal({
              part_no: result.part_no || scannedCode,
              description: result.description || "",
              mrp: result.mrp || 0,
              barcode: scannedCode,
              raw_text_hint: true,
            });
          } catch (err) {
            modal.querySelector("#ocr-status").textContent = "Couldn't read the label - please enter details manually.";
          }
        });
      },
    });
  }

  document.getElementById("upload-invoice-btn").addEventListener("click", () => {
    document.getElementById("purchase-invoice-file").click();
  });
  document.getElementById("purchase-invoice-file").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    const banner = document.getElementById("upload-result");
    banner.hidden = false;
    banner.className = "banner";
    banner.textContent = "Uploading and extracting parts...";
    const fd = new FormData();
    fd.append("file", file);
    try {
      const result = await api("/api/purchase-invoices/upload", { method: "POST", body: fd });
      banner.className = "banner banner-success";
      banner.textContent = `Invoice ${result.invoice_no}: parsed ${result.line_items_parsed} line items - `
        + `${result.inventory_items_created} new parts added, ${result.inventory_items_updated} existing parts restocked `
        + `(+${fmtNum(result.total_qty_added)} units total).`;
      loadInventory();
    } catch (err) {
      banner.className = "banner banner-error";
      banner.textContent = err.message;
    }
  });

  /* ============================== CUSTOMERS ============================== */
  async function loadCustomers() {
    const data = await api("/api/customers");
    customersCache = data.customers;
    renderCustomersTable(customersCache);
  }
  function renderCustomersTable(list) {
    const tbody = document.querySelector("#customers-table tbody");
    tbody.innerHTML = "";
    list.forEach((c) => {
      const tr = document.createElement("tr");
      tr.style.cursor = "pointer";
      tr.innerHTML = `<td>${escapeHtml(c.name)}</td><td>${escapeHtml(c.phone || "-")}</td>
        <td>${escapeHtml(c.bike_model || "-")} ${c.bike_reg_no ? "(" + escapeHtml(c.bike_reg_no) + ")" : ""}</td>
        <td>${c.invoice_count}</td><td>${fmtMoney(c.outstanding)}</td>`;
      tr.addEventListener("click", () => openCustomerDetail(c.id));
      tbody.appendChild(tr);
    });
  }
  document.getElementById("customer-search").addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase();
    renderCustomersTable(customersCache.filter((c) =>
      c.name.toLowerCase().includes(q) || (c.phone || "").includes(q) || (c.bike_reg_no || "").toLowerCase().includes(q)));
  });
  document.getElementById("add-customer-btn").addEventListener("click", () => openAddCustomerModal(() => loadCustomers()));

  async function openCustomerDetail(id) {
    const c = await api(`/api/customers/${id}`);
    const rows = c.invoices.map((inv) => `<tr>
        <td>${escapeHtml(inv.invoice_no)}</td><td>${escapeHtml(inv.invoice_date)}</td>
        <td>${fmtMoney(inv.total)}</td><td>${statusBadge(inv.payment_status)}</td>
        <td>${invoiceActionsHtml(inv)}</td></tr>`).join("");
    const { overlay } = openModal({
      title: c.name,
      wide: true,
      bodyHtml: `
        <p>${c.phone ? "Phone: " + escapeHtml(c.phone) + "<br>" : ""}${c.address ? escapeHtml(c.address) + "<br>" : ""}
        ${c.bike_model ? "Vehicle: " + escapeHtml(c.bike_model) + (c.bike_reg_no ? " / " + escapeHtml(c.bike_reg_no) : "") : ""}</p>
        <h4 style="margin-bottom:6px;">Service History</h4>
        <div class="table-wrap"><table class="data-table">
          <thead><tr><th>Invoice</th><th>Date</th><th>Total</th><th>Status</th><th></th></tr></thead>
          <tbody>${rows || '<tr><td colspan="5" style="color:#888;">No invoices yet</td></tr>'}</tbody>
        </table></div>`,
    });
    bindInvoiceActionButtons(overlay);
  }

  /* ============================== REPORTS ============================== */
  function setReportRange(preset) {
    const to = new Date();
    let from = new Date();
    if (preset === "30") from.setDate(to.getDate() - 30);
    else if (preset === "month") from = new Date(to.getFullYear(), to.getMonth(), 1);
    else if (preset === "year") from = new Date(to.getFullYear(), 0, 1);
    document.getElementById("report-from").value = from.toISOString().slice(0, 10);
    document.getElementById("report-to").value = to.toISOString().slice(0, 10);
    loadReports();
  }
  document.querySelectorAll("[data-preset]").forEach((b) => b.addEventListener("click", () => setReportRange(b.dataset.preset)));
  document.getElementById("report-from").addEventListener("change", loadReports);
  document.getElementById("report-to").addEventListener("change", loadReports);

  async function loadReports() {
    if (!document.getElementById("report-from").value) {
      const to = new Date(); const from = new Date(); from.setDate(to.getDate() - 30);
      document.getElementById("report-from").value = from.toISOString().slice(0, 10);
      document.getElementById("report-to").value = to.toISOString().slice(0, 10);
    }
    const from = document.getElementById("report-from").value;
    const to = document.getElementById("report-to").value;
    const data = await api(`/api/reports/sales?from=${from}&to=${to}`);

    document.getElementById("rep-total-sales").textContent = fmtMoney(data.summary.total);
    document.getElementById("rep-invoice-count").textContent = data.summary.invoice_count;
    document.getElementById("rep-gst").textContent = fmtMoney(data.summary.gst_amount);
    document.getElementById("rep-collected").textContent = fmtMoney(data.summary.amount_paid);

    const chart = document.getElementById("sales-chart");
    if (!data.by_day.length) {
      chart.innerHTML = `<div class="chart-empty">No sales in this range</div>`;
    } else {
      const max = Math.max(...data.by_day.map((d) => d.total), 1);
      chart.innerHTML = data.by_day.map((d) => `
        <div class="chart-bar" style="height:${Math.max(4, (d.total / max) * 130)}px">
          <div class="chart-tip">${fmtMoney(d.total)}</div>
        </div>`).join("");
    }

    const topPartsBody = document.querySelector("#top-parts-table tbody");
    topPartsBody.innerHTML = data.top_parts.map((p) => `<tr><td>${escapeHtml(p.description)}</td><td>${fmtNum(p.qty_sold)}</td><td>${fmtMoney(p.revenue)}</td></tr>`).join("")
      || '<tr><td colspan="3" style="color:#888;">No data</td></tr>';

    const topCustBody = document.querySelector("#top-customers-table tbody");
    topCustBody.innerHTML = data.top_customers.map((c) => `<tr><td>${escapeHtml(c.name)}</td><td>${c.invoice_count}</td><td>${fmtMoney(c.revenue)}</td></tr>`).join("")
      || '<tr><td colspan="3" style="color:#888;">No data</td></tr>';
  }

  /* ============================== SETTINGS ============================== */
  async function loadSettings() {
    const profile = await api("/api/settings/profile");
    const form = document.getElementById("profile-form");
    Object.keys(profile).forEach((k) => {
      const field = form.elements[k];
      if (field) field.value = profile[k] != null ? profile[k] : "";
    });

    const activity = await api("/api/settings/activity?limit=50");
    const tbody = document.querySelector("#activity-table tbody");
    tbody.innerHTML = activity.activity.map((a) => `<tr>
        <td>${escapeHtml((a.created_at || "").replace("T", " ").slice(0, 19))}</td>
        <td>${escapeHtml(a.entity_type)}</td><td>${escapeHtml(a.action)}</td></tr>`).join("")
      || '<tr><td colspan="3" style="color:#888;">No activity yet</td></tr>';
  }

  document.getElementById("profile-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const payload = {};
    ["business_name", "tagline", "address", "phone", "email", "gstin", "invoice_prefix", "bank_name", "bank_account_no", "bank_ifsc"].forEach((k) => { payload[k] = form.elements[k].value; });
    payload.default_gst_percent = parseFloat(form.elements.default_gst_percent.value) || 0;
    payload.low_stock_threshold = parseInt(form.elements.low_stock_threshold.value) || 0;
    try {
      await api("/api/settings/profile", { method: "PUT", json: payload });
      showToast("Business profile saved");
    } catch (err) { showToast(err.message, true); }
  });

  document.getElementById("password-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    try {
      await api("/api/change-password", {
        method: "POST",
        json: { current_password: form.elements.current_password.value, new_password: form.elements.new_password.value },
      });
      showToast("Password updated");
      form.reset();
    } catch (err) { showToast(err.message, true); }
  });

  /* ============================== Start ============================== */
  boot();
})();
