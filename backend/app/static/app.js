const vendorsByType = {
  flight: [
    { id: "amex_mmt_flight_voucher", name: "MakeMyTrip Gift Voucher", card: "American Express" },
    { id: "amex_cleartrip_generic_voucher", name: "Cleartrip E-Gift Voucher", card: "American Express" },
    { id: "hdfc_smartbuy_flight", name: "HDFC SmartBuy", card: "HDFC Infinia" },
    { id: "icici_ishop_flight", name: "ICICI iShop", card: "ICICI Times Black" },
    { id: "travel_agent_flight", name: "Travel Agent", card: "Bank transfer", isAgent: true },
  ],
  hotel: [
    { id: "amex_goibibo_hotel_voucher", name: "Goibibo Hotel E-Gift Voucher", card: "American Express" },
    { id: "amex_easemytrip_hotel_voucher", name: "Easemytrip Hotel E-Gift Voucher", card: "American Express" },
    { id: "amex_mmt_hotel_voucher", name: "MakeMyTrip Hotel E-Gift Voucher", card: "American Express" },
    { id: "amex_cleartrip_hotel_voucher", name: "Cleartrip E-Gift Voucher", card: "American Express" },
    { id: "hdfc_smartbuy_hotel", name: "HDFC SmartBuy", card: "HDFC Infinia" },
    { id: "icici_ishop_hotel", name: "ICICI iShop", card: "ICICI Times Black" },
    { id: "amex_fine_hotels", name: "American Express Fine Hotels", card: "American Express" },
    { id: "travel_agent_hotel", name: "Travel Agent", card: "Bank transfer", isAgent: true },
  ],
};

const draftKey = "cardsProjectDraft";
const state = {
  travelType: null,
  recommendation: null,
  selectedOption: null,
  pendingDeclineOption: null,
  highestStep: 1,
};

const auth = {
  enabled: false,
  client: null,
  session: null,
  factorId: null,
  challengeId: null,
};

const cardNames = {
  amex: "American Express",
  hdfc_infinia: "HDFC Infinia",
  icici_times_black: "ICICI Times Black",
  bank_transfer: "Bank Transfer",
};

const cardImages = {
  amex: "/static/assets/american-express.webp",
  hdfc_infinia: "/static/assets/hdfc-infinia.webp",
  icici_times_black: "/static/assets/icici-times-black.webp",
  bank_transfer: "/static/assets/precisehub-logo.png",
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const panels = {
  trip: $("#stepTrip"),
  prices: $("#stepPrices"),
  recommendation: $("#stepRecommendation"),
  finalize: $("#stepFinalize"),
  done: $("#donePanel"),
};

const stepNumber = { trip: 1, prices: 2, recommendation: 3, finalize: 4, done: 4 };

function showBookingPanel(name) {
  $("#bookingView").classList.remove("is-hidden");
  $("#transactionsView").classList.add("is-hidden");
  $("#bookingTab").classList.add("is-active");
  $("#transactionsTab").classList.remove("is-active");

  Object.values(panels).forEach((panel) => panel.classList.add("is-hidden"));
  panels[name].classList.remove("is-hidden");
  state.highestStep = Math.max(state.highestStep, stepNumber[name]);

  $$(".step").forEach((step) => {
    const target = step.dataset.stepTarget;
    const isCurrent = target === name;
    step.classList.toggle("is-active", isCurrent);
    step.disabled = stepNumber[target] > state.highestStep;
  });
}

function setStatus(text) {
  $("#saveStatus").textContent = text;
}

function showToast(message, isError = false) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.remove("is-hidden");
  window.setTimeout(() => toast.classList.add("is-hidden"), 3600);
}

function setAuthMessage(message, isError = false) {
  const messageBox = $("#authMessage");
  messageBox.textContent = message || "";
  messageBox.classList.toggle("error", isError);
}

function setAuthRequired(required) {
  document.body.classList.remove("auth-pending");
  document.body.classList.toggle("auth-required", required);
  $("#authGate").classList.toggle("is-hidden", !required);
  $("#logoutButton").classList.toggle("is-hidden", required || !auth.enabled);
}

function decodeJwt(token) {
  try {
    const payload = token.split(".")[1].replaceAll("-", "+").replaceAll("_", "/");
    return JSON.parse(atob(payload.padEnd(Math.ceil(payload.length / 4) * 4, "=")));
  } catch {
    return {};
  }
}

function qrImageSource(qrCode) {
  if (!qrCode) return "";
  if (qrCode.startsWith("data:")) return qrCode;
  if (qrCode.trim().startsWith("<svg")) {
    return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(qrCode)}`;
  }
  return qrCode;
}

async function setupAuth() {
  let config;
  try {
    const response = await fetch("/auth/config");
    config = await response.json();
  } catch {
    document.body.classList.remove("auth-pending");
    setAuthMessage("Unable to load login settings.", true);
    return;
  }

  auth.enabled = Boolean(config.enabled);
  if (!auth.enabled) {
    setAuthRequired(false);
    return;
  }

  if (!window.supabase?.createClient) {
    setAuthRequired(true);
    setAuthMessage("Unable to load Supabase login library.", true);
    return;
  }

  auth.client = window.supabase.createClient(config.supabase_url, config.supabase_anon_key);
  setupAuthForms();

  const { data } = await auth.client.auth.getSession();
  if (data?.session) {
    await continueAuth(data.session);
  } else {
    showLogin();
  }
}

function setupAuthForms() {
  $("#loginForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    setAuthMessage("Signing in...");
    const email = $("#authEmail").value.trim();
    const password = $("#authPassword").value;
    const { data, error } = await auth.client.auth.signInWithPassword({ email, password });
    if (error) {
      setAuthMessage(error.message, true);
      return;
    }
    await continueAuth(data.session);
  });

  $("#mfaForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const code = $("#mfaCode").value.trim();
    if (!auth.factorId || !auth.challengeId) {
      setAuthMessage("MFA challenge is not ready. Please log in again.", true);
      return;
    }
    setAuthMessage("Verifying...");
    const { data, error } = await auth.client.auth.mfa.verify({
      factorId: auth.factorId,
      challengeId: auth.challengeId,
      code,
    });
    if (error) {
      setAuthMessage(error.message, true);
      return;
    }
    const session = data?.session || (await auth.client.auth.getSession()).data?.session;
    await continueAuth(session);
  });

  $("#logoutButton").addEventListener("click", async () => {
    await auth.client.auth.signOut();
    auth.session = null;
    showLogin();
  });
}

function showLogin() {
  $("#loginForm").classList.remove("is-hidden");
  $("#mfaForm").classList.add("is-hidden");
  $("#mfaSetup").classList.add("is-hidden");
  $("#mfaCode").value = "";
  setAuthMessage("");
  setAuthRequired(true);
}

async function continueAuth(session) {
  if (!session?.access_token) {
    showLogin();
    return;
  }

  auth.session = session;
  const claims = decodeJwt(session.access_token);
  if (claims.aal === "aal2") {
    setAuthRequired(false);
    setAuthMessage("");
    return;
  }

  const { data, error } = await auth.client.auth.mfa.listFactors();
  if (error) {
    setAuthMessage(error.message, true);
    setAuthRequired(true);
    return;
  }

  const verifiedFactor = data?.totp?.find((factor) => factor.status === "verified");
  if (verifiedFactor) {
    await startMfaChallenge(verifiedFactor.id, false);
  } else {
    await startMfaEnrollment();
  }
}

async function startMfaEnrollment() {
  setAuthRequired(true);
  $("#loginForm").classList.add("is-hidden");
  $("#mfaForm").classList.remove("is-hidden");
  $("#mfaSetup").classList.remove("is-hidden");
  setAuthMessage("Set up two-factor authentication.");

  const { data, error } = await auth.client.auth.mfa.enroll({
    factorType: "totp",
    friendlyName: "PreciseHub",
  });
  if (error) {
    setAuthMessage(error.message, true);
    return;
  }

  auth.factorId = data.id;
  $("#mfaQr").src = qrImageSource(data.totp?.qr_code);
  $("#mfaSecret").textContent = data.totp?.secret ? `Secret: ${data.totp.secret}` : "";
  await startMfaChallenge(data.id, true);
}

async function startMfaChallenge(factorId, keepSetupVisible) {
  setAuthRequired(true);
  $("#loginForm").classList.add("is-hidden");
  $("#mfaForm").classList.remove("is-hidden");
  $("#mfaSetup").classList.toggle("is-hidden", !keepSetupVisible);
  $("#mfaCode").value = "";
  setAuthMessage(keepSetupVisible ? "Scan the QR code, then enter the 6-digit code." : "Enter your authenticator code.");

  const { data, error } = await auth.client.auth.mfa.challenge({ factorId });
  if (error) {
    setAuthMessage(error.message, true);
    return;
  }
  auth.factorId = factorId;
  auth.challengeId = data.id;
  $("#mfaCode").focus();
}

async function authHeaders(baseHeaders = {}) {
  if (!auth.enabled) return baseHeaders;
  const { data } = await auth.client.auth.getSession();
  const token = data?.session?.access_token;
  if (!token) throw new Error("Please log in again.");
  return {
    ...baseHeaders,
    Authorization: `Bearer ${token}`,
  };
}

function formatMoney(value) {
  return Number(value || 0).toLocaleString("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  });
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

function formatCardName(cardIdOrName) {
  return cardNames[cardIdOrName] || cardIdOrName || "";
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function cardImageFor(cardIdOrName) {
  if (cardImages[cardIdOrName]) return cardImages[cardIdOrName];
  const name = String(cardIdOrName || "").toLowerCase();
  if (name.includes("american express")) return cardImages.amex;
  if (name.includes("hdfc")) return cardImages.hdfc_infinia;
  if (name.includes("icici")) return cardImages.icici_times_black;
  if (name.includes("bank transfer") || name.includes("travel agent")) return cardImages.bank_transfer;
  return cardImages.amex;
}

function formatDate(value) {
  if (!value) return "";
  return new Date(value).toLocaleDateString("en-IN", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function formatMonth(value = new Date()) {
  return new Date(value).toLocaleDateString("en-IN", {
    year: "numeric",
    month: "long",
  });
}

function detailValue(value) {
  const text = String(value || "").trim();
  return text ? escapeHtml(text) : "Not entered";
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

function setupTabs() {
  $("#bookingTab").addEventListener("click", () => showBookingPanel("trip"));
  $("#transactionsTab").addEventListener("click", loadTransactions);
}

function setupStepNavigation() {
  $$(".step").forEach((step) => {
    step.addEventListener("click", () => {
      const target = step.dataset.stepTarget;
      if (stepNumber[target] <= state.highestStep) {
        showBookingPanel(target);
      }
    });
  });
  $$("[data-step-back]").forEach((button) => {
    button.addEventListener("click", () => showBookingPanel(button.dataset.stepBack));
  });
}

function setupTripChoices() {
  $$(".choice-card").forEach((button) => {
    button.addEventListener("click", () => {
      state.travelType = button.dataset.travelType;
      $("#travelDate").value = today();
      $("#priceTitle").textContent = titleForType();
      renderTripDetails();
      renderVendorRows();
      showBookingPanel("prices");
    });
  });
}

function titleForType() {
  if (state.travelType === "flight") return "Enter flight details";
  if (state.travelType === "hotel") return "Enter hotel details";
  return "Enter voucher details";
}

function renderTripDetails() {
  const details = $("#tripDetails");
  if (state.travelType === "flight") {
    details.innerHTML = `
      <label>From<input id="fromCity" placeholder="Example: Mumbai" /></label>
      <label>To<input id="toCity" placeholder="Example: Delhi" /></label>
      <label>Flight date<input id="detailDate" type="date" /></label>
    `;
  } else if (state.travelType === "hotel") {
    details.innerHTML = `
      <label>City<input id="hotelCity" placeholder="Example: Delhi" /></label>
      <label>Check-in<input id="checkIn" type="date" /></label>
      <label>Check-out<input id="checkOut" type="date" /></label>
    `;
  } else {
    details.innerHTML = `
      <label>Voucher vendor<input id="voucherVendor" placeholder="Example: Office Supply Voucher" /></label>
      <label>Purchase date<input id="voucherDate" type="date" /></label>
    `;
  }
}

function renderVendorRows() {
  const vendorList = $("#vendorList");
  vendorList.innerHTML = "";

  if (state.travelType === "voucher") {
    vendorList.innerHTML = `
      <div class="vendor-row simple">
        <div class="vendor-title">
          <strong>American Express voucher purchase</strong>
          <span>This only tracks Amex points and cap usage. It does not optimize vendors.</span>
        </div>
        <label>
          Amount
          <input id="voucherAmount" inputmode="decimal" min="1" step="0.01" type="number" placeholder="0" />
        </label>
      </div>
    `;
    return;
  }

  vendorsByType[state.travelType].forEach((vendor) => {
    const row = document.createElement("div");
    row.className = "vendor-row";
    row.innerHTML = `
      <div class="vendor-title">
        <strong>${vendor.name}</strong>
        <span>${vendor.card}</span>
      </div>
      <label>
        Price
        <input inputmode="decimal" min="0" step="0.01" type="number" data-vendor-amount="${vendor.id}" placeholder="0" />
      </label>
      <label>
        Discount %
        <input
          inputmode="decimal"
          min="0"
          max="100"
          step="0.01"
          type="number"
          data-vendor-discount="${vendor.id}"
          placeholder="0"
          ${vendor.isAgent ? "value=\"0\" disabled" : ""}
        />
      </label>
      ${vendorDetailFields(vendor)}
    `;
    vendorList.appendChild(row);
  });
}

function vendorDetailFields(vendor) {
  if (state.travelType === "flight") {
    return `
      <label>
        Airline on this platform
        <input id="${vendor.id}_airline" placeholder="Example: Indigo" />
      </label>
      <label>
        Flight timing
        <input id="${vendor.id}_flight_time" placeholder="Example: 10:30 AM - 12:45 PM" />
      </label>
      <label>
        Class
        <select id="${vendor.id}_flight_class">
          <option value="">Select class</option>
          <option value="Economy">Economy</option>
          <option value="Premium Economy">Premium Economy</option>
          <option value="Business">Business</option>
          <option value="First Class">First Class</option>
        </select>
      </label>
    `;
  }
  if (state.travelType === "hotel") {
    return `
      <label>
        Hotel on this platform
        <input id="${vendor.id}_hotel" placeholder="Example: Taj Palace" />
      </label>
    `;
  }
  return "";
}

function collectQuotes() {
  const quotes = [];
  vendorsByType[state.travelType].forEach((vendor) => {
    const amountInput = document.querySelector(`[data-vendor-amount="${vendor.id}"]`);
    const discountInput = document.querySelector(`[data-vendor-discount="${vendor.id}"]`);
    const amount = Number(amountInput.value);
    const discountPercent = Number(discountInput?.value || 0);

    if (amount > 0) {
      quotes.push({
        vendor_id: vendor.id,
        amount: String(amount),
        discount_rate: String(discountPercent / 100),
      });
    }
  });
  return quotes;
}

function collectDetails() {
  const selectedVendorId = state.selectedOption?.vendor_id;
  const common = {
    employee_name: $("#employeeName").value.trim(),
    booking_for: $("#bookingFor").value.trim(),
    booking_date: $("#travelDate").value,
    description: $("#finalDescription").value.trim(),
  };
  if (state.travelType === "flight") {
    return {
      ...common,
      airline: selectedVendorId ? $(`#${selectedVendorId}_airline`)?.value.trim() || "" : "",
      flight_time: selectedVendorId ? $(`#${selectedVendorId}_flight_time`)?.value.trim() || "" : "",
      flight_class: selectedVendorId ? $(`#${selectedVendorId}_flight_class`)?.value || "" : "",
      from: $("#fromCity")?.value.trim() || "",
      to: $("#toCity")?.value.trim() || "",
      flight_date: $("#detailDate")?.value || "",
    };
  }
  if (state.travelType === "hotel") {
    return {
      ...common,
      hotel_name: selectedVendorId ? $(`#${selectedVendorId}_hotel`)?.value.trim() || "" : "",
      city: $("#hotelCity")?.value.trim() || "",
      check_in: $("#checkIn")?.value || "",
      check_out: $("#checkOut")?.value || "",
    };
  }
  return {
    ...common,
    vendor_name: $("#voucherVendor")?.value.trim() || "",
    purchase_date: $("#voucherDate")?.value || $("#travelDate").value,
  };
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: await authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  const data = await readResponseBody(response);
  if (!response.ok) throw new Error(data.detail || "Something went wrong.");
  return data;
}

async function deleteJson(url) {
  const response = await fetch(url, {
    method: "DELETE",
    headers: await authHeaders(),
  });
  const data = await readResponseBody(response);
  if (!response.ok) throw new Error(data.detail || "Something went wrong.");
  return data;
}

async function readResponseBody(response) {
  const text = await response.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

function setupQuoteForm() {
  $("#backToTrip").addEventListener("click", () => showBookingPanel("trip"));

  $("#quoteForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (state.travelType === "voucher") {
      prepareVoucherReview();
      return;
    }

    const quotes = collectQuotes();
    if (quotes.length === 0) {
      showToast("Enter at least one price.", true);
      return;
    }

    try {
      setStatus("Calculating");
      const recommendation = await postJson("/recommendations", {
        employee_name: $("#employeeName").value.trim() || null,
        travel_type: state.travelType,
        travel_date: $("#travelDate").value || null,
        quotes,
      });
      state.recommendation = recommendation;
      renderRecommendation();
      setStatus("Ready");
      showBookingPanel("recommendation");
    } catch (error) {
      setStatus("Ready");
      showToast(error.message, true);
    }
  });
}

function prepareVoucherReview() {
  const amount = Number($("#voucherAmount").value);
  if (!amount) {
    showToast("Enter the voucher amount.", true);
    return;
  }
  state.selectedOption = {
    id: "voucher",
    card_name: "American Express",
    vendor_name: $("#voucherVendor").value.trim() || "Other voucher",
    price_after_discount: String(amount),
    net_cost: String(amount),
  };
  $("#recommendationTitle").textContent = "Voucher tracking";
  $("#bestOption").innerHTML = `
    <article class="option-card best">
      <div class="option-top">
        <img class="option-card-image" src="${cardImageFor("amex")}" alt="American Express card" />
        <div>
          <span class="rank-badge">Track only</span>
          <h3>American Express</h3>
          <p>${state.selectedOption.vendor_name}</p>
        </div>
        <button class="primary" id="continueVoucher" type="button">Continue</button>
      </div>
      <p>This voucher will be logged for Amex point and cap tracking. No card optimization is needed.</p>
      <div class="metric-grid">
        <div class="metric feature"><span>Cash to pay</span><strong>${formatMoney(state.selectedOption.price_after_discount)}</strong></div>
      </div>
    </article>
  `;
  $("#rankList").innerHTML = "";
  $("#continueVoucher").addEventListener("click", () => {
    renderFinalize();
    showBookingPanel("finalize");
  });
  showBookingPanel("recommendation");
}

function renderRecommendation() {
  $("#recommendationTitle").textContent = "Recommended card";
  const best = state.recommendation.ranked_options[0];
  $("#bestOption").innerHTML = optionCard(best, true);

  const rankList = $("#rankList");
  rankList.innerHTML = "<h3>Other choices</h3>";
  state.recommendation.ranked_options.slice(1).forEach((option) => {
    const wrapper = document.createElement("div");
    wrapper.innerHTML = optionCard(option, false);
    rankList.appendChild(wrapper.firstElementChild);
  });

  $("[data-accept-option]").addEventListener("click", () => acceptOption(best));
  $$("[data-decline-option]").forEach((button) => {
    button.addEventListener("click", () => openDecline(button.dataset.declineOption));
  });
}

function optionCard(option, isBest) {
  const isBankTransfer = option.card_id === "bank_transfer";
  const button = isBest
    ? `<button class="primary" type="button" data-accept-option="${option.id}">${isBankTransfer ? "Use this option" : "Use this card"}</button>`
    : `<button class="secondary" type="button" data-decline-option="${option.id}">Choose this instead</button>`;
  const netCostLabel = isBankTransfer ? "Net cost" : "Net cost after points";

  return `
    <article class="option-card ${isBest ? "best" : ""} ${isBankTransfer ? "bank-transfer-option" : ""}">
      <div class="option-top">
        <img class="option-card-image ${isBankTransfer ? "logo-image" : ""}" src="${cardImageFor(option.card_id)}" alt="${escapeHtml(option.card_name)} ${isBankTransfer ? "logo" : "card"}" />
        <div>
          <span class="rank-badge">Rank ${option.rank}</span>
          <h3>${escapeHtml(option.card_name)}</h3>
          <p>${escapeHtml(option.vendor_name)}</p>
        </div>
        ${button}
      </div>
      ${optionDecisionDetails(option)}
      <div class="metric-grid">
        <div class="metric feature"><span>Cash to pay</span><strong>${formatMoney(option.price_after_discount)}</strong></div>
        <div class="metric"><span>${netCostLabel}</span><strong>${formatMoney(option.net_cost)}</strong></div>
        <div class="metric"><span>Total points</span><strong>${formatNumber(option.total_points)}</strong></div>
        <div class="metric"><span>Point value</span><strong>${formatMoney(option.points_value_rupees)}</strong></div>
      </div>
    </article>
  `;
}

function optionDecisionDetails(option) {
  if (state.travelType === "flight") {
    const airline = $(`#${option.vendor_id}_airline`)?.value;
    const timing = $(`#${option.vendor_id}_flight_time`)?.value;
    const flightClass = $(`#${option.vendor_id}_flight_class`)?.value;
    return `
      <div class="option-detail-grid">
        <div class="option-detail"><span>Employee</span><strong>${detailValue($("#employeeName")?.value)}</strong></div>
        <div class="option-detail"><span>Booking for</span><strong>${detailValue($("#bookingFor")?.value)}</strong></div>
        <div class="option-detail"><span>Route</span><strong>${detailValue($("#fromCity")?.value)} to ${detailValue($("#toCity")?.value)}</strong></div>
        <div class="option-detail"><span>Flight date</span><strong>${detailValue($("#detailDate")?.value)}</strong></div>
        <div class="option-detail"><span>Airline</span><strong>${detailValue(airline)}</strong></div>
        <div class="option-detail"><span>Flight time</span><strong>${detailValue(timing)}</strong></div>
        <div class="option-detail"><span>Class</span><strong>${detailValue(flightClass)}</strong></div>
      </div>
    `;
  }

  if (state.travelType === "hotel") {
    const hotelName = $(`#${option.vendor_id}_hotel`)?.value;
    return `
      <div class="option-detail-grid">
        <div class="option-detail"><span>Employee</span><strong>${detailValue($("#employeeName")?.value)}</strong></div>
        <div class="option-detail"><span>Booking for</span><strong>${detailValue($("#bookingFor")?.value)}</strong></div>
        <div class="option-detail"><span>City</span><strong>${detailValue($("#hotelCity")?.value)}</strong></div>
        <div class="option-detail"><span>Hotel</span><strong>${detailValue(hotelName)}</strong></div>
        <div class="option-detail"><span>Check-in</span><strong>${detailValue($("#checkIn")?.value)}</strong></div>
        <div class="option-detail"><span>Check-out</span><strong>${detailValue($("#checkOut")?.value)}</strong></div>
      </div>
    `;
  }

  return "";
}

function personalInfoRows() {
  if (state.travelType === "flight") {
    return [
      ["Employee", $("#employeeName")?.value],
      ["Booking for", $("#bookingFor")?.value],
      ["Route", `${$("#fromCity")?.value || ""} to ${$("#toCity")?.value || ""}`],
      ["Flight date", $("#detailDate")?.value],
    ];
  }
  if (state.travelType === "hotel") {
    return [
      ["Employee", $("#employeeName")?.value],
      ["Booking for", $("#bookingFor")?.value],
      ["City", $("#hotelCity")?.value],
      ["Check-in", $("#checkIn")?.value],
      ["Check-out", $("#checkOut")?.value],
    ];
  }
  return [];
}

function comparisonRowValue(option, rowKey) {
  if (rowKey === "Rank") return option.rank;
  if (rowKey === "Vendor") return option.vendor_name;
  if (rowKey === "Airline") return $(`#${option.vendor_id}_airline`)?.value;
  if (rowKey === "Flight time") return $(`#${option.vendor_id}_flight_time`)?.value;
  if (rowKey === "Class") return $(`#${option.vendor_id}_flight_class`)?.value;
  if (rowKey === "Hotel") return $(`#${option.vendor_id}_hotel`)?.value;
  if (rowKey === "Cash to pay") return formatMoney(option.price_after_discount);
  if (rowKey === "Net cost") return formatMoney(option.net_cost);
  if (rowKey === "Total points") return formatNumber(option.total_points);
  if (rowKey === "Point value") return formatMoney(option.points_value_rupees);
  return "";
}

function setupChoicePdf() {
  $("#printCeoChoices").addEventListener("click", () => {
    if (!state.recommendation?.ranked_options?.length) {
      showToast("Generate recommendations first.", true);
      return;
    }
    const printWindow = window.open("", "_blank");
    if (!printWindow) {
      showToast("Allow pop-ups to generate the PDF.", true);
      return;
    }

    const options = state.recommendation.ranked_options;
    const personalRows = personalInfoRows().map(([label, value]) => `
      <tr><th>${escapeHtml(label)}</th><td>${detailValue(value)}</td></tr>
    `).join("");
    const comparisonRows = [
      "Rank",
      "Vendor",
      ...(state.travelType === "flight" ? ["Airline", "Flight time", "Class"] : []),
      ...(state.travelType === "hotel" ? ["Hotel"] : []),
      "Cash to pay",
      "Net cost",
      "Total points",
      "Point value",
    ].map((label) => `
      <tr>
        <th>${escapeHtml(label)}</th>
        ${options.map((option) => `<td>${detailValue(comparisonRowValue(option, label))}</td>`).join("")}
      </tr>
    `).join("");
    const cardHeaders = options.map((option) => {
      const isBankTransfer = option.card_id === "bank_transfer";
      return `
      <th class="card-head ${isBankTransfer ? "logo-card-head" : ""}">
        <img src="${cardImageFor(option.card_id)}" alt="${escapeHtml(option.card_name)} ${isBankTransfer ? "logo" : "card"}" />
        <strong>${escapeHtml(option.card_name)}</strong>
      </th>
    `;
    }).join("");

    printWindow.document.write(`
      <!doctype html>
      <html>
        <head>
          <title>PreciseHub Travel Choices</title>
          <style>
            @page { size: A4 portrait; margin: 9mm; }
            * { box-sizing: border-box; }
            body {
              background: #ffffff;
              color: #17211c;
              font-family: Arial, sans-serif;
              font-size: 9px;
              margin: 0;
            }
            header {
              align-items: center;
              border-bottom: 2px solid #0a4d3f;
              display: flex;
              justify-content: space-between;
              margin-bottom: 8px;
              padding-bottom: 6px;
            }
            .logo-left { height: 28px; object-fit: contain; object-position: left center; width: 128px; }
            .logo-right { height: 34px; object-fit: contain; object-position: right center; width: 124px; }
            .title { text-align: center; }
            h1 { color: #0a4d3f; font-size: 15px; line-height: 1.1; margin: 0 0 2px; }
            .muted { color: #5f6d64; font-size: 8px; margin: 0; }
            .section-title {
              align-items: center;
              color: #0a4d3f;
              display: flex;
              font-size: 10px;
              font-weight: 700;
              letter-spacing: 0;
              margin: 7px 0 4px;
            }
            .section-title::after {
              background: #dce4dc;
              content: "";
              flex: 1;
              height: 1px;
              margin-left: 8px;
            }
            table {
              border-collapse: separate;
              border-spacing: 0;
              overflow: hidden;
              table-layout: fixed;
              width: 100%;
            }
            .info-table,
            .compare-table {
              border: 1px solid #dce4dc;
              border-radius: 7px;
            }
            th,
            td {
              border-bottom: 1px solid #e5ebe5;
              border-right: 1px solid #e5ebe5;
              line-height: 1.2;
              padding: 5px 6px;
              text-align: left;
              vertical-align: middle;
              word-break: break-word;
            }
            tr:last-child th,
            tr:last-child td { border-bottom: 0; }
            th:last-child,
            td:last-child { border-right: 0; }
            .info-table th {
              background: #f4faf7;
              color: #5f6d64;
              font-weight: 700;
              width: 28%;
            }
            .compare-table th:first-child {
              background: #f4faf7;
              color: #5f6d64;
              font-weight: 700;
              width: 24%;
            }
            .compare-table td {
              text-align: center;
            }
            .compare-table thead th {
              background: #0a4d3f;
              color: #ffffff;
              text-align: center;
            }
            .compare-table thead th:first-child {
              background: #0a4d3f;
              color: #ffffff;
            }
            .card-head {
              padding: 5px;
            }
            .card-head img {
              border-radius: 5px;
              display: block;
              height: 34px;
              margin: 0 auto 3px;
              object-fit: contain;
              width: 76px;
            }
            .logo-card-head img {
              background: #ffffff;
              border: 1px solid #dce4dc;
              padding: 4px;
              width: 96px;
            }
            .card-head strong {
              display: block;
              font-size: 8px;
              line-height: 1.15;
            }
          </style>
        </head>
        <body>
          <header>
            <img class="logo-left" src="/static/assets/precisehub-logo.png" alt="PreciseHub" />
            <div class="title">
              <h1>Travel Choice Report</h1>
              <p class="muted">Generated ${new Date().toLocaleString("en-IN")} before final transaction logging.</p>
            </div>
            <img class="logo-right" src="/static/assets/precise-logo-transparent.png" alt="Precise Biopharma Pvt. Ltd." />
          </header>
          <section>
            <div class="section-title">Personal Information</div>
            <table class="info-table"><tbody>${personalRows}</tbody></table>
          </section>
          <section>
            <div class="section-title">Card Comparison</div>
            <table class="compare-table">
              <thead>
                <tr><th>Detail</th>${cardHeaders}</tr>
              </thead>
              <tbody>${comparisonRows}</tbody>
            </table>
          </section>
          <script>
            window.onload = () => {
              const images = Array.from(document.images);
              Promise.all(images.map((image) => image.complete ? Promise.resolve() : new Promise((resolve) => {
                image.onload = resolve;
                image.onerror = resolve;
              }))).then(() => window.print());
            };
          </script>
        </body>
      </html>
    `);
    printWindow.document.close();
  });
}

async function acceptOption(option) {
  try {
    setStatus("Saving");
    await postJson(`/recommendations/${state.recommendation.id}/decision`, {
      accepted: true,
      selected_option_id: option.id,
    });
    state.selectedOption = option;
    renderFinalize();
    setStatus("Ready");
    showBookingPanel("finalize");
  } catch (error) {
    setStatus("Ready");
    showToast(error.message, true);
  }
}

function openDecline(optionId) {
  state.pendingDeclineOption = state.recommendation.ranked_options.find((option) => option.id === optionId);
  $("#declineReason").value = "";
  $("#declineBox").classList.remove("is-hidden");
  $("#declineReason").focus();
}

function setupDeclineActions() {
  $("#cancelDecline").addEventListener("click", () => {
    state.pendingDeclineOption = null;
    $("#declineBox").classList.add("is-hidden");
  });

  $("#confirmDecline").addEventListener("click", async () => {
    const reason = $("#declineReason").value.trim();
    if (!reason) {
      showToast("Enter the reason for choosing a different card.", true);
      return;
    }

    try {
      setStatus("Saving");
      const option = state.pendingDeclineOption;
      await postJson(`/recommendations/${state.recommendation.id}/decision`, {
        accepted: false,
        selected_option_id: option.id,
        decline_reason: reason,
      });
      state.selectedOption = option;
      $("#declineBox").classList.add("is-hidden");
      renderFinalize();
      setStatus("Ready");
      showBookingPanel("finalize");
    } catch (error) {
      setStatus("Ready");
      showToast(error.message, true);
    }
  });
}

function renderFinalize() {
  const option = state.selectedOption;
  $("#selectedSummary").innerHTML = `
    <strong>${option.card_name}</strong>
    <span>${option.vendor_name}</span>
    <span>Expected amount: ${formatMoney(option.price_after_discount)}</span>
  `;
  $("#finalAmount").value = Number(option.price_after_discount).toFixed(2);
}

function setupFinalForm() {
  $("#finalForm").addEventListener("submit", async (event) => {
    event.preventDefault();

    const details = collectDetails();
    if (!details.description) {
      showToast("Add a short description before saving.", true);
      return;
    }

    try {
      setStatus("Saving");
      const paidAt = $("#paidAt").value ? new Date($("#paidAt").value).toISOString() : null;
      const transaction = state.travelType === "voucher"
        ? await postJson("/vouchers", {
            employee_name: details.employee_name || null,
            vendor_name: details.vendor_name || "Other voucher",
            final_amount_paid: $("#finalAmount").value,
            paid_at: paidAt,
            description: details.description,
          })
        : await postJson(`/recommendations/${state.recommendation.id}/finalize`, {
            selected_option_id: state.selectedOption.id,
            final_amount_paid: $("#finalAmount").value,
            paid_at: paidAt,
            details,
          });
      renderDone(transaction);
      localStorage.removeItem(draftKey);
      setStatus("Saved");
      showBookingPanel("done");
    } catch (error) {
      setStatus("Ready");
      showToast(error.message, true);
    }
  });
}

function renderDone(transaction) {
  $("#savedDetails").innerHTML = `
    <div class="metric-grid">
      <div class="metric"><span>Final amount</span><strong>${formatMoney(transaction.final_amount_paid)}</strong></div>
      <div class="metric"><span>Points</span><strong>${formatNumber(transaction.total_points)}</strong></div>
      <div class="metric"><span>Net cost</span><strong>${formatMoney(transaction.net_cost)}</strong></div>
      <div class="metric"><span>Status</span><strong>Logged</strong></div>
    </div>
  `;
}

function setupDraftsAndCancel() {
  $$("[data-save-draft]").forEach((button) => {
    button.addEventListener("click", () => {
      localStorage.setItem(draftKey, JSON.stringify({
        travelType: state.travelType,
        highestStep: state.highestStep,
        values: collectFormValues(),
      }));
      showToast("Draft saved on this computer.");
    });
  });

  $$("[data-cancel-flow]").forEach((button) => {
    button.addEventListener("click", cancelFlow);
  });
}

function collectFormValues() {
  const values = {};
  $$("input, select, textarea").forEach((field) => {
    const key = field.id ||
      (field.dataset.vendorAmount ? `amount:${field.dataset.vendorAmount}` : "") ||
      (field.dataset.vendorDiscount ? `discount:${field.dataset.vendorDiscount}` : "");
    if (key) values[key] = field.value;
  });
  return values;
}

function fillFormValues(values) {
  Object.entries(values || {}).forEach(([key, value]) => {
    const field =
      document.getElementById(key) ||
      (key.startsWith("amount:") ? document.querySelector(`[data-vendor-amount="${key.slice(7)}"]`) : null) ||
      (key.startsWith("discount:") ? document.querySelector(`[data-vendor-discount="${key.slice(9)}"]`) : null);
    if (field) field.value = value;
  });
}

function setupDraftLoading() {
  $("#loadDraft").addEventListener("click", () => {
    const rawDraft = localStorage.getItem(draftKey);
    if (!rawDraft) {
      showToast("No saved draft found.", true);
      return;
    }
    const draft = JSON.parse(rawDraft);
    state.travelType = draft.travelType;
    state.highestStep = Math.max(2, draft.highestStep || 2);
    $("#priceTitle").textContent = titleForType();
    renderTripDetails();
    renderVendorRows();
    fillFormValues(draft.values);
    showBookingPanel("prices");
    showToast("Draft loaded.");
  });
}

function cancelFlow() {
  state.travelType = null;
  state.recommendation = null;
  state.selectedOption = null;
  state.pendingDeclineOption = null;
  state.highestStep = 1;
  $("#quoteForm").reset();
  $("#finalForm").reset();
  $("#tripDetails").innerHTML = "";
  $("#vendorList").innerHTML = "";
  localStorage.removeItem(draftKey);
  setStatus("Ready");
  showBookingPanel("trip");
}

function setupStartOver() {
  $("#startOver").addEventListener("click", cancelFlow);
}

function setupReports() {
  const now = new Date();
  $("#reportMonth").value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  $("#reportYear").value = String(now.getFullYear());

  $("#currentMonthReport").addEventListener("click", () => {
    downloadReport("/reports/current-month.pdf");
  });

  $("#pastMonthReport").addEventListener("click", () => {
    const value = $("#reportMonth").value;
    if (!value) {
      showToast("Select a month first.", true);
      return;
    }
    const [year, month] = value.split("-");
    downloadReport(`/reports/monthly/${year}/${Number(month)}.pdf`);
  });

  $("#yearReport").addEventListener("click", () => {
    const year = Number($("#reportYear").value);
    if (!year) {
      showToast("Enter a year first.", true);
      return;
    }
    downloadReport(`/reports/ytd/${year}.pdf`);
  });
}

async function downloadReport(url) {
  const reportWindow = window.open("", "_blank");
  if (!reportWindow) {
    showToast("Allow pop-ups to generate the report.", true);
    return;
  }
  reportWindow.document.write("<p>Generating report...</p>");
  try {
    const response = await fetch(url, { headers: await authHeaders() });
    if (!response.ok) throw new Error("Could not generate report.");
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    reportWindow.location.href = objectUrl;
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
  } catch (error) {
    reportWindow.close();
    showToast(error.message, true);
  }
}

async function loadTransactions() {
  $("#bookingView").classList.add("is-hidden");
  $("#transactionsView").classList.remove("is-hidden");
  $("#transactionsTab").classList.add("is-active");
  $("#bookingTab").classList.remove("is-active");

  try {
    setStatus("Loading");
    const headers = await authHeaders();
    const [summaryResponse, transactionsResponse] = await Promise.all([
      fetch("/logs/summary", { headers }),
      fetch("/transactions", { headers }),
    ]);
    const summary = await summaryResponse.json();
    const transactions = await transactionsResponse.json();
    renderSummary(summary);
    renderTransactions(transactions);
    setStatus("Ready");
  } catch (error) {
    setStatus("Ready");
    showToast("Could not load past transactions.", true);
  }
}

function renderSummary(summary) {
  const monthName = formatMonth();
  $("#summaryCards").innerHTML = `
    <div class="metric feature"><span>${monthName} reward points</span><strong>${formatNumber(summary.month.total_points)}</strong></div>
    <div class="metric"><span>${monthName} bonus points</span><strong>${formatNumber(summary.month.bonus_points)}</strong></div>
    <div class="metric"><span>Year to date points</span><strong>${formatNumber(summary.year_to_date.total_points)}</strong></div>
    <div class="metric"><span>Year to date spend</span><strong>${formatMoney(summary.year_to_date.final_amount_paid)}</strong></div>
  `;
  $("#cardSplit").innerHTML = `
    <h3>${monthName} card wise points</h3>
    <div class="card-split-list">
      ${(summary.cards || []).map((card) => `
        <article class="card-split-row">
          <strong>${formatCardName(card.card_id)}</strong>
          <span>Total points: ${formatNumber(card.total_points)}</span>
          <span>Bonus remaining: ${formatNumber(card.bonus_points_remaining)} / ${formatNumber(card.cycle_bonus_cap)}</span>
        </article>
      `).join("")}
    </div>
  `;
}

function renderTransactions(transactions) {
  const list = $("#transactionList");
  if (!transactions.length) {
    list.innerHTML = `<p class="empty-state">No transactions logged yet.</p>`;
    return;
  }
  list.innerHTML = "";

  const oldestFirstTransactions = [...transactions].sort((first, second) => (
    new Date(first.paid_at) - new Date(second.paid_at)
  ));
  const transactionNumbers = new Map(
    oldestFirstTransactions.map((item, index) => [item.id, index + 1])
  );
  const sortedTransactions = [...transactions].sort((first, second) => (
    new Date(second.paid_at) - new Date(first.paid_at)
  ));
  const groups = groupTransactionsByMonth(sortedTransactions);
  groups.forEach((group) => {
    const section = document.createElement("section");
    section.className = "month-group";
    section.innerHTML = `
      <div class="month-heading">
        <h3>${group.label}</h3>
      </div>
      <div class="month-metrics">
        <span>Reward points: <strong>${formatNumber(group.totalPoints)}</strong></span>
        <span>Bonus points: <strong>${formatNumber(group.bonusPoints)}</strong></span>
        <span>Total spend: <strong>${formatMoney(group.totalSpend)}</strong></span>
      </div>
    `;
    group.items.forEach((item) => {
      const transactionNumber = transactionNumbers.get(item.id);
      section.appendChild(transactionRow(item, transactionNumber));
    });
    list.appendChild(section);
  });

  $$("[data-delete-transaction]").forEach((button) => {
    button.addEventListener("click", async () => {
      const confirmed = window.confirm("Delete this transaction?");
      if (!confirmed) return;
      try {
        setStatus("Deleting");
        await deleteJson(`/transactions/${button.dataset.deleteTransaction}`);
        await loadTransactions();
        showToast("Transaction deleted.");
      } catch (error) {
        setStatus("Ready");
        showToast(error.message, true);
      }
    });
  });
}

function groupTransactionsByMonth(transactions) {
  const groups = [];
  transactions.forEach((item) => {
    const paidAt = new Date(item.paid_at);
    const key = `${paidAt.getFullYear()}-${String(paidAt.getMonth() + 1).padStart(2, "0")}`;
    let group = groups.find((entry) => entry.key === key);
    if (!group) {
      group = {
        key,
        label: formatMonth(paidAt),
        totalPoints: 0,
        bonusPoints: 0,
        totalSpend: 0,
        items: [],
      };
      groups.push(group);
    }
    group.totalPoints += Number(item.total_points || 0);
    group.bonusPoints += Number(item.bonus_points || 0);
    group.totalSpend += Number(item.final_amount_paid || 0);
    group.items.push(item);
  });
  return groups;
}

function transactionRow(item, transactionNumber) {
    const details = item.details || {};
    const card = formatCardName(item.card_id);
    const isBankTransfer = item.card_id === "bank_transfer";
    const row = document.createElement("article");
    row.className = "transaction-row";
    row.innerHTML = `
      <img class="transaction-card-image ${isBankTransfer ? "logo-image" : ""}" src="${cardImageFor(item.card_id)}" alt="${card} ${isBankTransfer ? "logo" : "card"}" />
      <div>
        <strong>${transactionNumber}. ${card}</strong>
        <span>${formatDate(item.paid_at)} - ${item.travel_type} - ${details.vendor_name || item.vendor_id}</span>
        <small>${details.description || ""}</small>
      </div>
      <div><span>Paid</span><strong>${formatMoney(item.final_amount_paid)}</strong></div>
      <div><span>Points</span><strong>${formatNumber(item.total_points)}</strong></div>
      <button class="danger-button compact" data-delete-transaction="${item.id}" type="button">Delete</button>
    `;
    return row;
}

setupTabs();
setupStepNavigation();
setupTripChoices();
setupQuoteForm();
setupDeclineActions();
setupFinalForm();
setupDraftsAndCancel();
setupDraftLoading();
setupStartOver();
setupReports();
setupChoicePdf();
setupAuth();
