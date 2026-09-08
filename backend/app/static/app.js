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

const state = {
  travelType: null,
  recommendation: null,
  selectedOption: null,
  pendingDeclineOption: null,
  currentDraftId: null,
  highestStep: 1,
  removedVendorIds: new Set(),
};

let toastTimer;

const noDiscountVendors = new Set([
  "hdfc_smartbuy_flight",
  "hdfc_smartbuy_hotel",
  "icici_ishop_flight",
  "icici_ishop_hotel",
  "travel_agent_flight",
  "travel_agent_hotel",
]);

const amexTravelVoucherVendors = new Set([
  "amex_mmt_flight_voucher",
  "amex_cleartrip_generic_voucher",
  "amex_goibibo_hotel_voucher",
  "amex_easemytrip_hotel_voucher",
  "amex_mmt_hotel_voucher",
  "amex_cleartrip_hotel_voucher",
]);

const indianStates = [
  "Andhra Pradesh",
  "Arunachal Pradesh",
  "Assam",
  "Bihar",
  "Chhattisgarh",
  "Goa",
  "Gujarat",
  "Haryana",
  "Himachal Pradesh",
  "Jharkhand",
  "Karnataka",
  "Kerala",
  "Madhya Pradesh",
  "Maharashtra",
  "Manipur",
  "Meghalaya",
  "Mizoram",
  "Nagaland",
  "Odisha",
  "Punjab",
  "Rajasthan",
  "Sikkim",
  "Tamil Nadu",
  "Telangana",
  "Tripura",
  "Uttar Pradesh",
  "Uttarakhand",
  "West Bengal",
  "Andaman and Nicobar Islands",
  "Chandigarh",
  "Dadra and Nagar Haveli and Daman and Diu",
  "Daman",
  "Delhi",
  "Jammu and Kashmir",
  "Ladakh",
  "Lakshadweep",
  "Puducherry",
  "Outside India",
];

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

function timePicker(id) {
  return splitPicker(id, 23, "Hour", "Min");
}

function durationPicker(id) {
  return splitPicker(id, 48, "Hours", "Minutes");
}

function splitPicker(id, maxHours, hourLabel, minuteLabel) {
  return `
    <input id="${id}" type="hidden" />
    <div class="split-picker" data-picker-target="${id}">
      <select data-picker-hour aria-label="${hourLabel}">
        ${numberOptions(0, maxHours, hourLabel)}
      </select>
      <select data-picker-minute aria-label="${minuteLabel}">
        ${numberOptions(0, 59, minuteLabel)}
      </select>
    </div>
  `;
}

function numberOptions(start, end, emptyLabel) {
  const options = [`<option value="">${emptyLabel}</option>`];
  for (let value = start; value <= end; value += 1) {
    const text = String(value).padStart(2, "0");
    options.push(`<option value="${text}">${text}</option>`);
  }
  return options.join("");
}

function cabinClassSelect(id) {
  return `
    <select id="${id}">
      <option value="Economy" selected>Economy</option>
      <option value="Premium Economy">Premium Economy</option>
      <option value="Business">Business</option>
      <option value="First Class">First Class</option>
    </select>
  `;
}

function stateSelect(id) {
  return `
    <select id="${id}">
      <option value="">Select state/province</option>
      ${indianStates.map((stateName) => `<option value="${stateName}">${stateName}</option>`).join("")}
    </select>
  `;
}

function formatDurationValue(value) {
  if (!value) return "";
  const [hoursText, minutesText] = value.split(":");
  const hours = Number(hoursText);
  const minutes = Number(minutesText);
  if (Number.isNaN(hours) || Number.isNaN(minutes)) return value;
  return [
    hours ? `${hours}h` : "",
    minutes ? `${minutes}m` : "",
  ].filter(Boolean).join(" ") || "0m";
}

function flightLegValues(vendorId, prefix = "") {
  const fieldPrefix = prefix ? `${prefix}_` : "";
  const labelPrefix = prefix === "return" ? "Inbound" : "Outbound";
  const layover = $(`#${vendorId}_${fieldPrefix}layover`)?.value || "No";
  const layoverDuration = formatDurationValue($(`#${vendorId}_${fieldPrefix}layover_duration`)?.value);
  return {
    departure_time: $(`#${vendorId}_${prefix ? `${prefix}_flight_time` : "flight_time"}`)?.value || "",
    arrival_time: $(`#${vendorId}_${prefix ? `${prefix}_arrival_time` : "outbound_arrival_time"}`)?.value || "",
    flight_1_duration: formatDurationValue($(`#${vendorId}_${prefix ? `${prefix}_flight_duration` : "flight_duration"}`)?.value),
    layover,
    layover_duration: layover === "Yes" ? layoverDuration : "",
    connecting_flight_time: $(`#${vendorId}_${prefix ? `${prefix}_connection_time` : "outbound_connection_time"}`)?.value || "",
    flight_2_duration: formatDurationValue($(`#${vendorId}_${prefix ? `${prefix}_connection_duration` : "outbound_connection_duration"}`)?.value),
    cabin_class: $(`#${vendorId}_${prefix ? `${prefix}_cabin_class` : "outbound_cabin_class"}`)?.value || "",
    label: labelPrefix,
  };
}

function flightLegSummary(leg) {
  const hasLegDetails = Boolean(
    leg.departure_time ||
    leg.arrival_time ||
    leg.flight_1_duration ||
    leg.connecting_flight_time ||
    leg.flight_2_duration ||
    leg.cabin_class
  );
  const parts = [
    leg.departure_time ? `Departure: ${leg.departure_time}` : "",
    leg.arrival_time ? `Arrival: ${leg.arrival_time}` : "",
    leg.flight_1_duration ? `Flight 1: ${leg.flight_1_duration}` : "",
    leg.layover === "Yes" ? `Layover: ${leg.layover_duration || "Yes"}` : (hasLegDetails ? "Layover: No" : ""),
    leg.connecting_flight_time ? `Connecting flight: ${leg.connecting_flight_time}` : "",
    leg.flight_2_duration ? `Flight 2: ${leg.flight_2_duration}` : "",
    leg.cabin_class ? `Cabin class: ${leg.cabin_class}` : "",
  ];
  return parts.filter(Boolean).join(" | ");
}

function savedFlightLegSummary(details, prefix = "outbound") {
  const isReturn = prefix === "return";
  return flightLegSummary({
    departure_time: details[`${prefix}_departure_time`] || (isReturn ? details.return_flight_time : details.flight_time),
    arrival_time: details[`${prefix}_arrival_time`] || "",
    flight_1_duration: details[`${prefix}_flight_1_duration`] || (!isReturn ? details.flight_duration : ""),
    layover: details[`${prefix}_layover`] || (!isReturn ? details.layover : "No"),
    layover_duration: details[`${prefix}_layover_duration`] || (!isReturn ? details.layover_duration : ""),
    connecting_flight_time: details[`${prefix}_connection_time`] || "",
    flight_2_duration: details[`${prefix}_flight_2_duration`] || "",
    cabin_class: details[`${prefix}_cabin_class`] || (!isReturn ? details.flight_class : ""),
  });
}

function updateLayoverControls(select) {
  const targetIds = (select.dataset.layoverTargets || "").split(",").filter(Boolean);
  const disabled = select.value !== "Yes";
  targetIds.forEach((id) => {
    const field = document.getElementById(id);
    if (!field) return;
    field.disabled = disabled;
    setSplitPickerDisabled(id, disabled);
    if (disabled) field.value = "";
  });
  refreshSplitPickers();
}

function setupLayoverControls() {
  $$("[data-layover-targets]").forEach((select) => {
    updateLayoverControls(select);
    select.addEventListener("change", () => updateLayoverControls(select));
  });
}

function refreshLayoverControls() {
  $$("[data-layover-targets]").forEach((select) => updateLayoverControls(select));
}

function syncSplitPicker(picker) {
  const target = document.getElementById(picker.dataset.pickerTarget);
  const hour = picker.querySelector("[data-picker-hour]")?.value || "";
  const minute = picker.querySelector("[data-picker-minute]")?.value || "";
  if (!target) return;
  target.value = hour && minute ? `${hour}:${minute}` : "";
}

function setSplitPickerDisabled(targetId, disabled) {
  const picker = document.querySelector(`[data-picker-target="${targetId}"]`);
  if (!picker) return;
  picker.querySelectorAll("select").forEach((field) => {
    field.disabled = disabled;
    if (disabled) field.value = "";
  });
}

function refreshSplitPicker(picker) {
  const target = document.getElementById(picker.dataset.pickerTarget);
  const [hour = "", minute = ""] = String(target?.value || "").split(":");
  const hourField = picker.querySelector("[data-picker-hour]");
  const minuteField = picker.querySelector("[data-picker-minute]");
  if (hourField) hourField.value = hour;
  if (minuteField) minuteField.value = minute;
}

function setupSplitPickers() {
  $$("[data-picker-target]").forEach((picker) => {
    refreshSplitPicker(picker);
    picker.querySelectorAll("select").forEach((field) => {
      field.addEventListener("change", () => syncSplitPicker(picker));
    });
  });
}

function refreshSplitPickers() {
  $$("[data-picker-target]").forEach((picker) => refreshSplitPicker(picker));
}

function updateTripTypeControls() {
  if (state.travelType !== "flight") return;
  const isOneWay = $("#flightTripType")?.value === "One way";
  $$(".inbound-only").forEach((field) => {
    field.disabled = isOneWay;
    if (isOneWay) field.value = "";
  });
  $$("[data-inbound-section]").forEach((section) => {
    section.classList.toggle("is-disabled", isOneWay);
    section.querySelectorAll("input, select").forEach((field) => {
      field.disabled = isOneWay;
      setSplitPickerDisabled(field.id, isOneWay);
      if (isOneWay) field.value = "";
    });
  });
  refreshSplitPickers();
  refreshLayoverControls();
}

function setupTripTypeControls() {
  const tripType = $("#flightTripType");
  if (!tripType) return;
  tripType.addEventListener("change", updateTripTypeControls);
  updateTripTypeControls();
}

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
  $("#draftsView").classList.add("is-hidden");
  $("#bookingTab").classList.add("is-active");
  $("#transactionsTab").classList.remove("is-active");
  $("#draftsTab").classList.remove("is-active");

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

function showToast(message, isError = false, action = null) {
  const toast = $("#toast");
  toast.replaceChildren();
  const text = document.createElement("span");
  text.textContent = message;
  toast.appendChild(text);
  if (action) {
    const button = document.createElement("button");
    button.className = "toast-action";
    button.type = "button";
    button.textContent = action.label;
    button.addEventListener("click", () => {
      action.onClick();
      toast.classList.add("is-hidden");
    });
    toast.appendChild(button);
  }
  toast.classList.toggle("error", isError);
  toast.classList.remove("is-hidden");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => toast.classList.add("is-hidden"), 5000);
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

function formatPercent(value) {
  return `${Number(value || 0) * 100}%`;
}

function formatCardName(cardIdOrName) {
  return cardNames[cardIdOrName] || cardIdOrName || "";
}

function formatTravelType(value) {
  return String(value || "").replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
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
  $("#draftsTab").addEventListener("click", loadDrafts);
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
      state.recommendation = null;
      state.selectedOption = null;
      state.pendingDeclineOption = null;
      state.currentDraftId = null;
      state.highestStep = 1;
      state.removedVendorIds = new Set();
      $("#travelDate").value = today();
      $("#priceTitle").textContent = titleForType();
      updateFlightOnlyFields();
      renderTripDetails();
      renderVendorRows();
      showBookingPanel("prices");
    });
  });
}

function updateFlightOnlyFields() {
  $$(".flight-only").forEach((field) => {
    field.classList.toggle("is-hidden", state.travelType !== "flight");
  });
  $$(".hotel-only").forEach((field) => {
    field.classList.toggle("is-hidden", state.travelType !== "hotel");
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
      <label>From<input id="fromCity" /></label>
      <label>From state/province${stateSelect("fromState")}</label>
      <label class="outside-location is-hidden" data-outside-location="fromState">
        Country / state outside India
        <input id="fromOutsideLocation" placeholder="For example, Ontario, Canada" />
      </label>
      <label>To<input id="toCity" /></label>
      <label>To state/province${stateSelect("toState")}</label>
      <label class="outside-location is-hidden" data-outside-location="toState">
        Country / state outside India
        <input id="toOutsideLocation" placeholder="For example, California, USA" />
      </label>
      <label>Flight date<input id="detailDate" type="date" /></label>
      <label>Return flight date<input id="returnFlightDate" class="inbound-only" type="date" /></label>
      <label>
        Trip type
        <select id="flightTripType">
          <option value="One way">One way</option>
          <option value="Return">Return</option>
        </select>
      </label>
    `;
  } else if (state.travelType === "hotel") {
    details.innerHTML = `
      <label>Hotel state/province${stateSelect("hotelState")}</label>
      <label class="outside-location is-hidden" data-outside-location="hotelState">
        Country / state outside India
        <input id="hotelOutsideLocation" placeholder="For example, Dubai, UAE" />
      </label>
      <label>Check-in<input id="checkIn" type="date" /></label>
      <label>Check-out<input id="checkOut" type="date" /></label>
    `;
  } else {
    details.innerHTML = `
      <label>Voucher vendor<input id="voucherVendor" /></label>
      <label>Purchase date<input id="voucherDate" type="date" /></label>
    `;
  }
  setupOutsideIndiaPrompts();
}

function setupOutsideIndiaPrompts() {
  $$('[data-outside-location]').forEach((container) => {
    const stateField = document.getElementById(container.dataset.outsideLocation);
    const textField = container.querySelector("input");
    const refresh = () => {
      const isOutsideIndia = stateField?.value === "Outside India";
      container.classList.toggle("is-hidden", !isOutsideIndia);
      textField.required = isOutsideIndia;
      if (!isOutsideIndia) textField.value = "";
    };
    stateField?.addEventListener("change", refresh);
    refresh();
  });
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
    const isVoucherVendor = isAmexTravelVoucherVendor(vendor.id);
    const priceLabel = state.travelType === "flight" ? "Flight price" : "Hotel price";
    row.className = `vendor-row ${state.travelType === "flight" ? "flight-vendor-row" : ""} ${state.travelType === "hotel" ? "hotel-vendor-row" : ""}`;
    row.innerHTML = `
      <button class="remove-vendor" data-remove-vendor="${vendor.id}" type="button" aria-label="Remove ${escapeHtml(vendor.name)}" title="Remove this vendor">×</button>
      <div class="vendor-title">
        <strong>${vendor.name}</strong>
        <span>${vendor.card}</span>
      </div>
      <div class="vendor-fields ${state.travelType === "flight" ? "flight-fields" : ""} ${state.travelType === "hotel" ? "hotel-fields" : ""}">
        <label>
          ${isVoucherVendor ? priceLabel : "Price"}
          <input inputmode="decimal" min="0" step="0.01" type="number" data-vendor-amount="${vendor.id}" placeholder="0" />
        </label>
        ${isVoucherVendor ? `
          <label>
            Voucher value
            <input inputmode="decimal" min="0" step="0.01" type="number" data-vendor-voucher="${vendor.id}" placeholder="0" />
          </label>
        ` : ""}
        <label>
          ${isVoucherVendor ? "Voucher discount %" : "Discount %"}
          <input
            inputmode="decimal"
            min="0"
            max="100"
            step="0.01"
            type="number"
            data-vendor-discount="${vendor.id}"
            placeholder="0"
            ${noDiscountVendors.has(vendor.id) ? "value=\"0\" disabled" : ""}
          />
        </label>
        <label class="checkbox-label">
          <input type="checkbox" data-vendor-gst="${vendor.id}" />
          GST invoice can be created
        </label>
        <label class="wide-detail booking-link-field">
          Booking / listing link <span>Optional · included at the bottom of the PDF</span>
          <input type="url" data-vendor-link="${vendor.id}" placeholder="https://..." />
        </label>
        ${vendorDetailFields(vendor)}
      </div>
    `;
    vendorList.appendChild(row);
  });
  $$('[data-remove-vendor]').forEach((button) => {
    button.addEventListener("click", () => {
      const vendorId = button.dataset.removeVendor;
      const row = button.closest(".vendor-row");
      if (!vendorId || !row) return;
      state.removedVendorIds.add(vendorId);
      row.classList.add("is-hidden");
      const vendor = vendorsByType[state.travelType].find((item) => item.id === vendorId);
      showToast(`${vendor?.name || "Vendor"} removed.`, false, {
        label: "Undo",
        onClick: () => {
          state.removedVendorIds.delete(vendorId);
          row.classList.remove("is-hidden");
        },
      });
    });
  });
  setupSplitPickers();
  setupLayoverControls();
  setupTripTypeControls();
}

function vendorDetailFields(vendor) {
  if (state.travelType === "flight") {
    return `
      <label>
        Airline on this platform
        <input id="${vendor.id}_airline" />
      </label>
      <div class="field-section">
        <h3>Outbound flight</h3>
        <div class="field-section-grid">
          <label>
            Departure time
            ${timePicker(`${vendor.id}_flight_time`)}
          </label>
          <label>
            Arrival time
            ${timePicker(`${vendor.id}_outbound_arrival_time`)}
          </label>
          <label>
            Flight 1 duration
            ${durationPicker(`${vendor.id}_flight_duration`)}
          </label>
          <label>
            Layover
            <select id="${vendor.id}_layover" data-layover-targets="${vendor.id}_layover_duration,${vendor.id}_outbound_connection_time,${vendor.id}_outbound_connection_duration">
              <option value="No">No</option>
              <option value="Yes">Yes</option>
            </select>
          </label>
          <label>
            Layover duration
            ${durationPicker(`${vendor.id}_layover_duration`)}
          </label>
          <label>
            Connecting flight time
            ${timePicker(`${vendor.id}_outbound_connection_time`)}
          </label>
          <label>
            Flight 2 duration
            ${durationPicker(`${vendor.id}_outbound_connection_duration`)}
          </label>
          <label>
            Cabin class
            ${cabinClassSelect(`${vendor.id}_outbound_cabin_class`)}
          </label>
        </div>
      </div>
      <div class="field-section" data-inbound-section>
        <h3>Inbound flight</h3>
        <div class="field-section-grid">
          <label>
            Departure time
            ${timePicker(`${vendor.id}_return_flight_time`)}
          </label>
          <label>
            Arrival time
            ${timePicker(`${vendor.id}_return_arrival_time`)}
          </label>
          <label>
            Flight 1 duration
            ${durationPicker(`${vendor.id}_return_flight_duration`)}
          </label>
          <label>
            Layover
            <select id="${vendor.id}_return_layover" data-layover-targets="${vendor.id}_return_layover_duration,${vendor.id}_return_connection_time,${vendor.id}_return_connection_duration">
              <option value="No">No</option>
              <option value="Yes">Yes</option>
            </select>
          </label>
          <label>
            Layover duration
            ${durationPicker(`${vendor.id}_return_layover_duration`)}
          </label>
          <label>
            Connecting flight time
            ${timePicker(`${vendor.id}_return_connection_time`)}
          </label>
          <label>
            Flight 2 duration
            ${durationPicker(`${vendor.id}_return_connection_duration`)}
          </label>
          <label>
            Cabin class
            ${cabinClassSelect(`${vendor.id}_return_cabin_class`)}
          </label>
        </div>
      </div>
    `;
  }
  if (state.travelType === "hotel") {
    return `
      <label>
        Hotel on this platform
        <input id="${vendor.id}_hotel" />
      </label>
      <label>
        Check-in time
        ${timePicker(`${vendor.id}_check_in_time`)}
      </label>
      <label>
        Check-out time
        ${timePicker(`${vendor.id}_check_out_time`)}
      </label>
    `;
  }
  return "";
}

function collectQuotes() {
  const quotes = [];
  vendorsByType[state.travelType].forEach((vendor) => {
    if (state.removedVendorIds.has(vendor.id)) return;
    const amountInput = document.querySelector(`[data-vendor-amount="${vendor.id}"]`);
    const discountInput = document.querySelector(`[data-vendor-discount="${vendor.id}"]`);
    const voucherInput = document.querySelector(`[data-vendor-voucher="${vendor.id}"]`);
    const gstInput = document.querySelector(`[data-vendor-gst="${vendor.id}"]`);
    const amount = Number(amountInput?.value || 0);
    const discountPercent = noDiscountVendors.has(vendor.id) ? 0 : Number(discountInput?.value || 0);
    const voucherFaceValue = Number(voucherInput?.value || 0);

    if (amount > 0) {
      if (state.travelType === "flight" && (!$("#fromState")?.value || !$("#toState")?.value)) {
        throw new Error("Select from and to state/province before calculating flight recommendations.");
      }
      if (state.travelType === "flight" && $("#fromState")?.value === "Outside India" && !$("#fromOutsideLocation")?.value.trim()) {
        throw new Error("Enter the origin country or state outside India.");
      }
      if (state.travelType === "flight" && $("#toState")?.value === "Outside India" && !$("#toOutsideLocation")?.value.trim()) {
        throw new Error("Enter the destination country or state outside India.");
      }
      if (state.travelType === "hotel" && !$("#hotelState")?.value) {
        throw new Error("Select the hotel state/province before calculating hotel recommendations.");
      }
      if (state.travelType === "hotel" && $("#hotelState")?.value === "Outside India" && !$("#hotelOutsideLocation")?.value.trim()) {
        throw new Error("Enter the hotel country or state outside India.");
      }
      if (isAmexTravelVoucherVendor(vendor.id) && voucherFaceValue <= 0) {
        throw new Error("Enter the voucher value for each Amex voucher option with a price.");
      }
      if (isAmexTravelVoucherVendor(vendor.id) && voucherFaceValue > amount) {
        throw new Error("Voucher value cannot be higher than the booking price.");
      }
      quotes.push({
        vendor_id: vendor.id,
        amount: String(amount),
        discount_rate: String(discountPercent / 100),
        voucher_face_value: isAmexTravelVoucherVendor(vendor.id) ? String(voucherFaceValue) : null,
        gst_invoice_available: Boolean(gstInput?.checked),
        origin_state: state.travelType === "flight" ? $("#fromState")?.value || null : null,
        destination_state: state.travelType === "flight" ? $("#toState")?.value || null : null,
        hotel_state: state.travelType === "hotel" ? $("#hotelState")?.value || null : null,
        flight_class: state.travelType === "flight"
          ? $(`#${vendor.id}_outbound_cabin_class`)?.value || "Economy"
          : null,
        flight_sector_count: state.travelType === "flight" ? flightSectorCount(vendor.id) : 1,
      });
    }
  });
  return quotes;
}

function flightSectorCount(vendorId) {
  const outboundSegments = $(`#${vendorId}_layover`)?.value === "Yes" ? 2 : 1;
  if ($("#flightTripType")?.value === "One way") return outboundSegments;
  const inboundSegments = $(`#${vendorId}_return_layover`)?.value === "Yes" ? 2 : 1;
  return outboundSegments + inboundSegments;
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
    const outboundLeg = selectedVendorId ? flightLegValues(selectedVendorId) : {};
    const returnLeg = selectedVendorId ? flightLegValues(selectedVendorId, "return") : {};
    return {
      ...common,
      airline: selectedVendorId ? $(`#${selectedVendorId}_airline`)?.value.trim() || "" : "",
      flight_time: outboundLeg.departure_time || "",
      return_flight_time: returnLeg.departure_time || "",
      flight_duration: outboundLeg.flight_1_duration || "",
      layover: outboundLeg.layover || "No",
      layover_duration: outboundLeg.layover_duration || "",
      outbound_departure_time: outboundLeg.departure_time || "",
      outbound_arrival_time: outboundLeg.arrival_time || "",
      outbound_flight_1_duration: outboundLeg.flight_1_duration || "",
      outbound_layover: outboundLeg.layover || "No",
      outbound_layover_duration: outboundLeg.layover_duration || "",
      outbound_connection_time: outboundLeg.connecting_flight_time || "",
      outbound_flight_2_duration: outboundLeg.flight_2_duration || "",
      outbound_cabin_class: outboundLeg.cabin_class || "",
      return_departure_time: returnLeg.departure_time || "",
      return_arrival_time: returnLeg.arrival_time || "",
      return_flight_1_duration: returnLeg.flight_1_duration || "",
      return_layover: returnLeg.layover || "No",
      return_layover_duration: returnLeg.layover_duration || "",
      return_connection_time: returnLeg.connecting_flight_time || "",
      return_flight_2_duration: returnLeg.flight_2_duration || "",
      return_cabin_class: returnLeg.cabin_class || "",
      flight_class: outboundLeg.cabin_class || "",
      trip_region: $("#tripRegion")?.value || "",
      trip_type: $("#flightTripType")?.value || "",
      from: $("#fromCity")?.value.trim() || "",
      from_state: $("#fromState")?.value || "",
      from_outside_location: $("#fromOutsideLocation")?.value.trim() || "",
      to: $("#toCity")?.value.trim() || "",
      to_state: $("#toState")?.value || "",
      to_outside_location: $("#toOutsideLocation")?.value.trim() || "",
      flight_date: $("#detailDate")?.value || "",
      return_flight_date: $("#returnFlightDate")?.value || "",
      gst_invoice_available: selectedVendorId ? document.querySelector(`[data-vendor-gst="${selectedVendorId}"]`)?.checked || false : false,
    };
  }
  if (state.travelType === "hotel") {
    return {
      ...common,
      hotel_name: selectedVendorId ? $(`#${selectedVendorId}_hotel`)?.value.trim() || "" : "",
      city: $("#hotelCity")?.value.trim() || "",
      hotel_state: $("#hotelState")?.value || "",
      hotel_outside_location: $("#hotelOutsideLocation")?.value.trim() || "",
      check_in: $("#checkIn")?.value || "",
      check_in_time: selectedVendorId ? $(`#${selectedVendorId}_check_in_time`)?.value || "" : "",
      check_out: $("#checkOut")?.value || "",
      check_out_time: selectedVendorId ? $(`#${selectedVendorId}_check_out_time`)?.value || "" : "",
      gst_invoice_available: selectedVendorId ? document.querySelector(`[data-vendor-gst="${selectedVendorId}"]`)?.checked || false : false,
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

async function putJson(url, body) {
  const response = await fetch(url, {
    method: "PUT",
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

    try {
      const quotes = collectQuotes();
      if (quotes.length === 0) {
        showToast("Enter at least one price.", true);
        return;
      }
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
  const netCostLabel = "Net cost after points, GST, and tax";
  const voucherMath = voucherMathDetails(option);

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
      ${voucherMath}
      <div class="metric-grid">
        <div class="metric"><span>Total booking cost</span><strong>${formatMoney(option.listed_amount)}</strong></div>
        <div class="metric feature"><span>Cash to pay</span><strong>${formatMoney(option.price_after_discount)}</strong></div>
        <div class="metric"><span>${netCostLabel}</span><strong>${formatMoney(option.net_cost)}</strong></div>
        <div class="metric"><span>Total points</span><strong>${formatNumber(option.total_points)}</strong></div>
        <div class="metric"><span>Point value</span><strong>${formatMoney(option.points_value_rupees)}</strong></div>
        <div class="metric"><span>GST itinerary rate</span><strong>${formatPercent(option.gst_rate)}</strong></div>
        <div class="metric"><span>Estimated GST credit</span><strong>${formatMoney(option.gst_credit || 0)}</strong></div>
        <div class="metric"><span>Tax benefit (27.5%)</span><strong>${formatMoney(option.tax_benefit || 0)}</strong></div>
      </div>
      <p class="gst-estimate-note">${escapeHtml(option.gst_note || "Invoice will confirm GST treatment.")}</p>
    </article>
  `;
}

function voucherMathDetails(option) {
  if (!isAmexTravelVoucherOption(option)) return "";
  const voucherFaceValue = Number(option.eligible_amount || 0);
  const directCardBalance = Number(option.cash_component || 0);
  const voucherPurchaseCost = Math.max(Number(option.price_after_discount || 0) - directCardBalance, 0);
  return `
    <div class="option-detail-grid voucher-math-grid">
      <div class="option-detail"><span>Voucher value used</span><strong>${formatMoney(voucherFaceValue)}</strong></div>
      <div class="option-detail"><span>Voucher purchase cost</span><strong>${formatMoney(voucherPurchaseCost)}</strong></div>
      <div class="option-detail"><span>Direct card balance</span><strong>${formatMoney(directCardBalance)}</strong></div>
    </div>
  `;
}

function optionDecisionDetails(option) {
  if (state.travelType === "flight") {
    const airline = $(`#${option.vendor_id}_airline`)?.value;
    const outboundLeg = flightLegValues(option.vendor_id);
    const returnLeg = flightLegValues(option.vendor_id, "return");
    return `
      <div class="option-detail-grid">
        <div class="option-detail"><span>Employee</span><strong>${detailValue($("#employeeName")?.value)}</strong></div>
        <div class="option-detail"><span>Booking for</span><strong>${detailValue($("#bookingFor")?.value)}</strong></div>
        <div class="option-detail"><span>Trip region</span><strong>${detailValue($("#tripRegion")?.value)}</strong></div>
        <div class="option-detail"><span>Trip type</span><strong>${detailValue($("#flightTripType")?.value)}</strong></div>
        <div class="option-detail"><span>Route</span><strong>${detailValue($("#fromCity")?.value)} to ${detailValue($("#toCity")?.value)}</strong></div>
        <div class="option-detail"><span>Flight date</span><strong>${detailValue($("#detailDate")?.value)}</strong></div>
        <div class="option-detail"><span>Return flight date</span><strong>${detailValue($("#returnFlightDate")?.value)}</strong></div>
        <div class="option-detail"><span>Airline</span><strong>${detailValue(airline)}</strong></div>
        <div class="option-detail"><span>GST</span><strong>${option.gst_claimable ? "Claimable" : "Not claimable"}</strong></div>
        <div class="option-detail wide-detail"><span>Outbound flight</span><strong>${detailValue(flightLegSummary(outboundLeg))}</strong></div>
        <div class="option-detail wide-detail"><span>Inbound flight</span><strong>${detailValue(flightLegSummary(returnLeg))}</strong></div>
      </div>
    `;
  }

  if (state.travelType === "hotel") {
    const hotelName = $(`#${option.vendor_id}_hotel`)?.value;
    const checkInTime = $(`#${option.vendor_id}_check_in_time`)?.value;
    const checkOutTime = $(`#${option.vendor_id}_check_out_time`)?.value;
    return `
      <div class="option-detail-grid">
        <div class="option-detail"><span>Employee</span><strong>${detailValue($("#employeeName")?.value)}</strong></div>
        <div class="option-detail"><span>Booking for</span><strong>${detailValue($("#bookingFor")?.value)}</strong></div>
        <div class="option-detail"><span>City</span><strong>${detailValue($("#hotelCity")?.value)}</strong></div>
        <div class="option-detail"><span>Hotel</span><strong>${detailValue(hotelName)}</strong></div>
        <div class="option-detail"><span>Check-in</span><strong>${detailValue($("#checkIn")?.value)}</strong></div>
        <div class="option-detail"><span>Check-out</span><strong>${detailValue($("#checkOut")?.value)}</strong></div>
        <div class="option-detail"><span>Check-in time</span><strong>${detailValue(checkInTime)}</strong></div>
        <div class="option-detail"><span>Check-out time</span><strong>${detailValue(checkOutTime)}</strong></div>
        <div class="option-detail"><span>GST</span><strong>${option.gst_claimable ? "Claimable" : "Not claimable"}</strong></div>
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
      ["Trip region", $("#tripRegion")?.value],
      ["Trip type", $("#flightTripType")?.value],
      ["Route", `${$("#fromCity")?.value || ""} to ${$("#toCity")?.value || ""}`],
      ["Flight date", $("#detailDate")?.value],
      ["Return flight date", $("#returnFlightDate")?.value],
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
  if (rowKey === "Outbound flight") return flightLegSummary(flightLegValues(option.vendor_id));
  if (rowKey === "Inbound flight") return flightLegSummary(flightLegValues(option.vendor_id, "return"));
  if (rowKey === "Hotel") return $(`#${option.vendor_id}_hotel`)?.value;
  if (rowKey === "Check-in time") return $(`#${option.vendor_id}_check_in_time`)?.value;
  if (rowKey === "Check-out time") return $(`#${option.vendor_id}_check_out_time`)?.value;
  if (rowKey === "Voucher value") return isAmexTravelVoucherOption(option) ? formatMoney(option.eligible_amount) : "-";
  if (rowKey === "Voucher purchase cost") {
    return isAmexTravelVoucherOption(option)
      ? formatMoney(Math.max(Number(option.price_after_discount || 0) - Number(option.cash_component || 0), 0))
      : "-";
  }
  if (rowKey === "Direct card balance") return isAmexTravelVoucherOption(option) ? formatMoney(option.cash_component) : "-";
  if (rowKey === "Total booking cost") return formatMoney(option.listed_amount);
  if (rowKey === "Cash to pay") return formatMoney(option.price_after_discount);
  if (rowKey === "GST rate") return formatPercent(option.gst_rate);
  if (rowKey === "GST credit") return formatMoney(option.gst_credit || 0);
  if (rowKey === "Tax benefit" || rowKey === "Tax benefit (27.5%)") return formatMoney(option.tax_benefit || 0);
  if (rowKey === "GST status") return option.gst_claimable ? "Claimable" : "Not claimable";
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
      ...(state.travelType === "flight" ? ["Airline", "Outbound flight", "Inbound flight"] : []),
      ...(state.travelType === "hotel" ? ["Hotel", "Check-in time", "Check-out time"] : []),
      "Total booking cost",
      "Cash to pay",
      "Total points",
      "Point value",
      "GST credit",
      "GST rate",
      "Tax benefit (27.5%)",
      "GST status",
      "Net cost",
    ].map((label) => `
      <tr class="${label === "Net cost" ? "net-cost-row" : ""}">
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
    const bookingLinks = bookingLinksForPdf(options);
    const bookingLinksMarkup = bookingLinks.length ? `
      <section class="booking-links">
        <div class="section-title">Booking Links</div>
        <ul>${bookingLinks.map((link) => `<li><strong>${escapeHtml(link.vendor)}</strong><a href="${escapeHtml(link.url)}" target="_blank" rel="noopener noreferrer">Open booking link</a></li>`).join("")}</ul>
      </section>
    ` : "";

    printWindow.document.write(`
      <!doctype html>
      <html>
        <head>
          <title>PreciseHub Travel Choices</title>
          <style>
            @page { size: A4 landscape; margin: 8mm; }
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
            .net-cost-row td {
              color: #0a4d3f;
              font-weight: 700;
            }
            .booking-links { margin-top: 10px; }
            .booking-links ul { list-style: none; margin: 0; padding: 0; }
            .booking-links li { border-bottom: 1px solid #e5ebe5; display: flex; gap: 10px; justify-content: space-between; padding: 5px 2px; }
            .booking-links a { color: #0a4d3f; font-weight: 700; text-decoration: underline; }
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
          ${bookingLinksMarkup}
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

function bookingLinksForPdf(options) {
  const byVendor = new Map();
  options.forEach((option) => {
    if (byVendor.has(option.vendor_id)) return;
    const input = document.querySelector(`[data-vendor-link="${option.vendor_id}"]`);
    const url = safeBookingUrl(input?.value);
    if (url) byVendor.set(option.vendor_id, { vendor: option.vendor_name, url });
  });
  return [...byVendor.values()];
}

function safeBookingUrl(value) {
  const trimmed = String(value || "").trim();
  if (!trimmed) return "";
  try {
    const url = new URL(trimmed);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
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
  const usesVoucherSplit = isAmexTravelVoucherOption(option);
  const allowsPointsRedemption = isPointRedemptionCard(option);
  $("#selectedSummary").innerHTML = `
    <strong>${option.card_name}</strong>
    <span>${option.vendor_name}</span>
    <span>Expected amount: ${formatMoney(option.price_after_discount)}</span>
  `;
  $("#finalAmount").value = Number(option.price_after_discount).toFixed(2);
  $("#finalAmountLabel").textContent = allowsPointsRedemption ? "Final booking total before points" : "Final amount paid";
  $("#pointsRedemptionBox").classList.toggle("is-hidden", !allowsPointsRedemption);
  if (!allowsPointsRedemption) $("#rewardPointsUsed").value = "0";
  $("#amexSplitBox").classList.toggle("is-hidden", !usesVoucherSplit);
  ["#voucherFaceValueUsed", "#voucherPurchaseAmountPaid", "#cardBalancePaid"].forEach((selector) => {
    $(selector).required = usesVoucherSplit;
    if (!usesVoucherSplit) $(selector).value = "";
  });
  if (usesVoucherSplit) {
    const voucherFaceValue = Number(option.eligible_amount || 0);
    const cardBalance = Number(option.cash_component || 0);
    const voucherPurchaseAmount = Math.max(Number(option.price_after_discount || 0) - cardBalance, 0);
    $("#voucherFaceValueUsed").value = voucherFaceValue.toFixed(2);
    $("#voucherPurchaseAmountPaid").value = voucherPurchaseAmount.toFixed(2);
    $("#cardBalancePaid").value = cardBalance.toFixed(2);
  }
}

function isAmexTravelVoucherOption(option) {
  return Boolean(option?.card_id === "amex" && amexTravelVoucherVendors.has(option.vendor_id));
}

function isPointRedemptionCard(option) {
  return Boolean(option && ["hdfc_infinia", "icici_times_black"].includes(option.card_id));
}

function isAmexTravelVoucherVendor(vendorId) {
  return amexTravelVoucherVendors.has(vendorId);
}

function setupFinalForm() {
  $("#finalForm").addEventListener("submit", async (event) => {
    event.preventDefault();

    const details = collectDetails();
    if (!details.description) {
      showToast("Add a short description before saving.", true);
      return;
    }
    const pointsUsed = isPointRedemptionCard(state.selectedOption)
      ? Number($("#rewardPointsUsed").value || 0)
      : 0;
    if (pointsUsed < 0 || !Number.isFinite(pointsUsed)) {
      showToast("Enter a valid number of reward points used.", true);
      return;
    }
    if (isAmexTravelVoucherOption(state.selectedOption)) {
      const voucherFaceValue = Number($("#voucherFaceValueUsed").value || 0);
      const voucherPurchaseAmount = Number($("#voucherPurchaseAmountPaid").value || 0);
      const cardBalance = Number($("#cardBalancePaid").value || 0);
      const finalAmount = Number($("#finalAmount").value || 0);
      if (Math.abs((voucherPurchaseAmount + cardBalance) - finalAmount) > 0.01) {
        showToast("Voucher purchase cost and direct card balance must add up to the final amount paid.", true);
        return;
      }
      details.voucher_face_value_used = $("#voucherFaceValueUsed").value || "0";
      details.voucher_purchase_amount_paid = $("#voucherPurchaseAmountPaid").value || "0";
      details.card_balance_paid = $("#cardBalancePaid").value || "0";
      details.checkout_value = (voucherFaceValue + cardBalance).toFixed(2);
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
            points_used: String(pointsUsed),
            details,
          });
      renderDone(transaction);
      if (state.currentDraftId) {
        deleteJson(`/drafts/${state.currentDraftId}`).catch(() => {});
        state.currentDraftId = null;
      }
      setStatus("Saved");
      showBookingPanel("done");
    } catch (error) {
      setStatus("Ready");
      showToast(error.message, true);
    }
  });
}

function renderDone(transaction) {
  const details = transaction.details || {};
  const splitLine = details.voucher_purchase_amount_paid || details.card_balance_paid || details.voucher_amount_paid || details.cash_amount_paid
    ? `<div class="metric"><span>Voucher/card split</span><strong>${formatMoney(details.voucher_purchase_amount_paid || details.voucher_amount_paid || 0)} / ${formatMoney(details.card_balance_paid || details.cash_amount_paid || 0)}</strong></div>`
    : "";
  $("#savedDetails").innerHTML = `
    <div class="metric-grid">
      <div class="metric"><span>Final amount</span><strong>${formatMoney(transaction.final_amount_paid)}</strong></div>
      <div class="metric"><span>Points</span><strong>${formatNumber(transaction.total_points)}</strong></div>
      ${Number(transaction.points_used || 0) ? `<div class="metric"><span>Points used</span><strong>${formatNumber(transaction.points_used)}</strong></div>` : ""}
      <div class="metric"><span>GST credit</span><strong>${formatMoney(transaction.gst_credit || 0)}</strong></div>
      <div class="metric"><span>Tax benefit</span><strong>${formatMoney(transaction.tax_benefit || 0)}</strong></div>
      <div class="metric"><span>Net cost</span><strong>${formatMoney(transaction.net_cost)}</strong></div>
      <div class="metric"><span>Status</span><strong>Logged</strong></div>
      ${splitLine}
    </div>
  `;
  renderInvoiceUpload(transaction.id, null, "#completedInvoicePanel");
}

function currentPanelName() {
  return Object.entries(panels).find(([, panel]) => !panel.classList.contains("is-hidden"))?.[0] || "trip";
}

function draftTitle() {
  if (state.travelType === "flight") {
    const route = [$("#fromCity")?.value, $("#toCity")?.value].filter(Boolean).join(" to ");
    return route ? `Flight - ${route}` : "Flight booking";
  }
  if (state.travelType === "hotel") {
    const city = $("#hotelCity")?.value;
    const checkIn = $("#checkIn")?.value;
    const checkOut = $("#checkOut")?.value;
    const stayDates = [checkIn, checkOut].filter(Boolean).join(" to ");
    const titleParts = [city, stayDates].filter(Boolean);
    return titleParts.length ? `Hotel - ${titleParts.join(" - ")}` : "Hotel booking";
  }
  if (state.travelType === "voucher") {
    return `Voucher - ${$("#voucherVendor")?.value || "Untitled"}`;
  }
  return "Untitled draft";
}

function draftPayload() {
  return {
    id: state.currentDraftId,
    title: draftTitle(),
    travel_type: state.travelType || "unknown",
    current_step: Math.min(state.highestStep || 1, 4),
    data: {
      travelType: state.travelType,
      highestStep: state.highestStep,
      panel: currentPanelName(),
      values: collectFormValues(),
      recommendation: state.recommendation,
      selectedOption: state.selectedOption,
    },
  };
}

function setupDraftsAndCancel() {
  $$("[data-save-draft]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!state.travelType) {
        showToast("Start a booking before saving a draft.", true);
        return;
      }
      try {
        setStatus("Saving draft");
        const draft = await postJson("/drafts", draftPayload());
        state.currentDraftId = draft.id;
        setStatus("Ready");
        showToast("Draft saved.");
      } catch (error) {
        setStatus("Ready");
        showToast(error.message, true);
      }
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
      (field.dataset.vendorDiscount ? `discount:${field.dataset.vendorDiscount}` : "") ||
      (field.dataset.vendorVoucher ? `voucher:${field.dataset.vendorVoucher}` : "") ||
      (field.dataset.vendorGst ? `gst:${field.dataset.vendorGst}` : "") ||
      (field.dataset.vendorLink ? `link:${field.dataset.vendorLink}` : "");
    if (key) values[key] = field.type === "checkbox" ? field.checked : field.value;
  });
  return values;
}

function fillFormValues(values) {
  Object.entries(values || {}).forEach(([key, value]) => {
    const field =
      document.getElementById(key) ||
      (key.startsWith("amount:") ? document.querySelector(`[data-vendor-amount="${key.slice(7)}"]`) : null) ||
      (key.startsWith("discount:") ? document.querySelector(`[data-vendor-discount="${key.slice(9)}"]`) : null) ||
      (key.startsWith("voucher:") ? document.querySelector(`[data-vendor-voucher="${key.slice(8)}"]`) : null) ||
      (key.startsWith("gst:") ? document.querySelector(`[data-vendor-gst="${key.slice(4)}"]`) : null) ||
      (key.startsWith("link:") ? document.querySelector(`[data-vendor-link="${key.slice(5)}"]`) : null);
    if (field) {
      if (field.type === "checkbox") field.checked = Boolean(value);
      else field.value = value;
    }
  });
}

function cancelFlow() {
  state.travelType = null;
  state.recommendation = null;
  state.selectedOption = null;
  state.pendingDeclineOption = null;
  state.currentDraftId = null;
  state.highestStep = 1;
  state.removedVendorIds = new Set();
  $("#quoteForm").reset();
  $("#finalForm").reset();
  $("#tripDetails").innerHTML = "";
  $("#vendorList").innerHTML = "";
  updateFlightOnlyFields();
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
  try {
    setStatus("Generating report");
    const reportWindow = window.open("", "_blank");
    if (!reportWindow) throw new Error("Allow pop-ups to open the report in a full browser tab.");
    const response = await fetch(url, { headers: await authHeaders() });
    if (!response.ok) throw new Error("Could not generate report.");
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    reportWindow.location.replace(objectUrl);
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 300000);
    setStatus("Ready");
  } catch (error) {
    setStatus("Ready");
    showToast(error.message, true);
  }
}

async function loadTransactions() {
  $("#bookingView").classList.add("is-hidden");
  $("#draftsView").classList.add("is-hidden");
  $("#transactionsView").classList.remove("is-hidden");
  $("#transactionsTab").classList.add("is-active");
  $("#bookingTab").classList.remove("is-active");
  $("#draftsTab").classList.remove("is-active");

  try {
    setStatus("Loading");
    const headers = await authHeaders();
    const [summaryResponse, transactionsResponse, storageResponse] = await Promise.all([
      fetch("/logs/summary", { headers }),
      fetch("/transactions", { headers }),
      fetch("/invoices/storage-summary", { headers }),
    ]);
    if (!summaryResponse.ok || !transactionsResponse.ok || !storageResponse.ok) {
      throw new Error("Could not load transaction history.");
    }
    const summary = await summaryResponse.json();
    const transactions = await transactionsResponse.json();
    const storage = await storageResponse.json();
    renderSummary(summary);
    renderInvoiceStorage(storage);
    renderTransactions(transactions);
    setStatus("Ready");
  } catch (error) {
    setStatus("Ready");
    showToast("Could not load past transactions.", true);
  }
}

function renderInvoiceStorage(storage) {
  const used = Number(storage.used_bytes || 0);
  const allocation = Number(storage.allocation_bytes || 1);
  const percent = Math.min((used / allocation) * 100, 100);
  const tone = percent >= 95 ? "is-critical" : percent >= 80 ? "is-warning" : "";
  const message = percent >= 95
    ? "Archive invoices to your computer, then delete them here to keep the system working."
    : percent >= 80
      ? "Archive older invoices soon so there is room for new bookings."
      : "Invoices can be downloaded and removed after you archive them locally.";
  $("#invoiceStoragePanel").innerHTML = `
    <div class="invoice-storage-copy">
      <p class="eyebrow">Invoice archive</p>
      <h3>${formatFileSize(used)} used of ${formatFileSize(allocation)} reserved</h3>
      <p>${formatNumber(storage.invoice_count || 0)} invoice${Number(storage.invoice_count || 0) === 1 ? "" : "s"} stored · ${formatFileSize(storage.remaining_bytes || 0)} remaining</p>
    </div>
    <div class="storage-meter ${tone}" aria-label="${percent.toFixed(0)} percent of invoice storage used"><span style="width: ${percent}%"></span></div>
    <p class="storage-note ${tone}">${message}</p>
  `;
}

async function loadDrafts() {
  $("#bookingView").classList.add("is-hidden");
  $("#transactionsView").classList.add("is-hidden");
  $("#draftsView").classList.remove("is-hidden");
  $("#bookingTab").classList.remove("is-active");
  $("#transactionsTab").classList.remove("is-active");
  $("#draftsTab").classList.add("is-active");

  try {
    setStatus("Loading");
    const response = await fetch("/drafts", { headers: await authHeaders() });
    if (!response.ok) throw new Error("Could not load drafts.");
    const drafts = await response.json();
    renderDrafts(drafts);
    setStatus("Ready");
  } catch (error) {
    setStatus("Ready");
    showToast(error.message, true);
  }
}

function renderDrafts(drafts) {
  const list = $("#draftList");
  if (!drafts.length) {
    list.innerHTML = `<p class="empty-state">No drafts saved yet.</p>`;
    return;
  }
  list.innerHTML = drafts.map((draft) => `
    <article class="draft-row">
      <div>
        <strong>${escapeHtml(draft.title)}</strong>
        <span>${escapeHtml(formatTravelType(draft.travel_type))} - Step ${draft.current_step} - Updated ${formatDate(draft.updated_at)}</span>
      </div>
      <div class="draft-actions">
        <button class="primary compact" data-resume-draft="${draft.id}" type="button">Resume</button>
        <button class="danger-button compact" data-delete-draft="${draft.id}" type="button">Delete</button>
      </div>
    </article>
  `).join("");

  $$("[data-resume-draft]").forEach((button) => {
    button.addEventListener("click", async () => {
      const response = await fetch(`/drafts/${button.dataset.resumeDraft}`, { headers: await authHeaders() });
      if (!response.ok) {
        showToast("Could not load draft.", true);
        return;
      }
      resumeDraft(await response.json());
    });
  });

  $$("[data-delete-draft]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!window.confirm("Delete this draft?")) return;
      try {
        setStatus("Deleting");
        await deleteJson(`/drafts/${button.dataset.deleteDraft}`);
        await loadDrafts();
        showToast("Draft deleted.");
      } catch (error) {
        setStatus("Ready");
        showToast(error.message, true);
      }
    });
  });
}

function resumeDraft(draft) {
  const data = draft.data || {};
  state.currentDraftId = draft.id;
  state.travelType = data.travelType || draft.travel_type;
  state.highestStep = Math.max(2, data.highestStep || draft.current_step || 2);
  state.recommendation = data.recommendation || null;
  state.selectedOption = data.selectedOption || null;
  state.pendingDeclineOption = null;
  $("#quoteForm").reset();
  $("#finalForm").reset();
  $("#priceTitle").textContent = titleForType();
  updateFlightOnlyFields();
  renderTripDetails();
  renderVendorRows();
  fillFormValues(data.values || {});
  refreshSplitPickers();
  refreshLayoverControls();
  updateTripTypeControls();
  if (state.recommendation?.ranked_options?.length) renderRecommendation();
  if (state.selectedOption) renderFinalize();
  showBookingPanel(data.panel || "prices");
  showToast("Draft loaded.");
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

  const oldestFirstTransactions = [...transactions].sort((first, second) => compareTransactions(first, second));
  const transactionNumbers = new Map(
    oldestFirstTransactions.map((item, index) => [item.id, index + 1])
  );
  const sortedTransactions = [...transactions].sort((first, second) => compareTransactions(second, first));
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
    groupTransactionCategories(group.items).forEach((category) => {
      const categoryBlock = document.createElement("div");
      categoryBlock.className = "transaction-category";
      categoryBlock.innerHTML = `<h4>${category.label}</h4>`;
      category.items.forEach((item) => {
        const transactionNumber = transactionNumbers.get(item.id);
        categoryBlock.appendChild(transactionRow(item, transactionNumber));
      });
      section.appendChild(categoryBlock);
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
  $$('[data-open-edit]').forEach((button) => {
    button.addEventListener("click", () => {
      const editor = document.querySelector(`#transaction-edit-${button.dataset.openEdit}`);
      if (!editor) return;
      editor.classList.remove("is-hidden");
      editor.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  });
  $$('[data-cancel-edit]').forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelector(`#transaction-edit-${button.dataset.cancelEdit}`)?.classList.add("is-hidden");
    });
  });
  $$('[data-edit-transaction]').forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const details = {};
      form.querySelectorAll("[data-edit-field]").forEach((input) => {
        details[input.dataset.editField] = input.value.trim();
      });
      try {
        setStatus("Saving details");
        await putJson(`/transactions/${form.dataset.editTransaction}/details`, { details });
        await loadTransactions();
        showToast("Booking details updated.");
      } catch (error) {
        setStatus("Ready");
        showToast(error.message, true);
      }
    });
  });
  setupInvoiceActions();
}

function compareTransactions(first, second) {
  const firstTime = new Date(first.paid_at || first.created_at).getTime();
  const secondTime = new Date(second.paid_at || second.created_at).getTime();
  if (firstTime !== secondTime) return firstTime - secondTime;
  return new Date(first.created_at || first.paid_at).getTime() - new Date(second.created_at || second.paid_at).getTime();
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

function groupTransactionCategories(transactions) {
  const labels = { flight: "Flights", hotel: "Hotels", voucher: "Vouchers" };
  return ["flight", "hotel", "voucher"].map((type) => ({
    type,
    label: labels[type],
    items: transactions.filter((item) => item.travel_type === type),
  })).filter((group) => group.items.length);
}

function transactionRow(item, transactionNumber) {
  const details = item.details || {};
  const card = formatCardName(item.card_id);
  const isBankTransfer = item.card_id === "bank_transfer";
  const summary = transactionSummary(item);
  const row = document.createElement("article");
  row.className = "transaction-row";
  row.innerHTML = `
    <div class="transaction-overview">
      <img class="transaction-card-image ${isBankTransfer ? "logo-image" : ""}" src="${cardImageFor(item.card_id)}" alt="${card} ${isBankTransfer ? "logo" : "card"}" />
      <div class="transaction-copy">
        <div class="transaction-title-row">
          <strong>${transactionNumber}. ${escapeHtml(card)}</strong>
        </div>
        <h4>${escapeHtml(summary.title)}</h4>
        <p>${escapeHtml(summary.metadata)}</p>
        <div class="transaction-tags">${summary.tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")}</div>
        ${details.description ? `<p class="transaction-note">${escapeHtml(details.description)}</p>` : ""}
      </div>
    </div>
    <div class="transaction-stat"><span>Paid</span><strong>${formatMoney(item.final_amount_paid)}</strong></div>
    <div class="transaction-stat"><span>Points</span><strong>${formatNumber(item.total_points)}</strong></div>
    <div class="transaction-actions">
      ${transactionInvoicePanel(item)}
      <button class="secondary compact transaction-edit-action" data-open-edit="${item.id}" type="button">Edit details</button>
      <button class="transaction-delete-action" data-delete-transaction="${item.id}" type="button">Delete transaction</button>
    </div>
    <details class="transaction-details">
      <summary><span>View booking details</span><span class="details-chevron" aria-hidden="true">⌄</span></summary>
      <div class="transaction-detail-grid">${transactionDetailsMarkup(item)}</div>
    </details>
    ${transactionEditMarkup(item)}
  `;
  return row;
}

function transactionEditMarkup(item) {
  const details = item.details || {};
  return `
    <section class="transaction-edit-details is-hidden" id="transaction-edit-${item.id}">
      <form data-edit-transaction="${item.id}">
        <p>Only descriptive booking information can be changed. Amounts, points, taxes, and card details remain locked.</p>
        <div class="transaction-edit-grid">${transactionEditFields(item.travel_type, details)}</div>
        <div class="transaction-edit-actions">
          <button class="primary compact" type="submit">Save details</button>
          <button class="secondary compact" data-cancel-edit="${item.id}" type="button">Cancel</button>
        </div>
      </form>
    </section>
  `;
}

function transactionEditFields(travelType, details) {
  const field = (label, key, type = "text") => `
    <label>${escapeHtml(label)}
      <input data-edit-field="${key}" type="${type}" value="${escapeHtml(details[key] || "")}" />
    </label>
  `;
  const note = () => `
    <label class="transaction-edit-note">Notes
      <textarea data-edit-field="description" rows="2">${escapeHtml(details.description || "")}</textarea>
    </label>
  `;
  if (travelType === "flight") {
    return [
      field("From", "from"), field("To", "to"), field("Airline", "airline"),
      field("Outbound date", "flight_date", "date"), field("Return date", "return_flight_date", "date"), field("Trip type", "trip_type"),
      field("Outbound departure", "outbound_departure_time", "time"), field("Outbound arrival", "outbound_arrival_time", "time"),
      field("Inbound departure", "return_departure_time", "time"), field("Inbound arrival", "return_arrival_time", "time"), note(),
    ].join("");
  }
  if (travelType === "hotel") {
    return [
      field("Hotel", "hotel_name"), field("City", "city"), field("State / location", "hotel_state"),
      field("Check-in", "check_in", "date"), field("Check-out", "check_out", "date"), note(),
    ].join("");
  }
  return [field("Voucher vendor", "vendor_name"), field("Purchase date", "purchase_date", "date"), note()].join("");
}

function transactionInvoicePanel(item) {
  const uploaded = item.invoice_status === "uploaded";
  const invoice = item.invoice;
  return `
    <section class="transaction-invoice-panel ${uploaded ? "is-uploaded" : "is-pending"}" aria-label="Invoice record">
      <div class="transaction-invoice-heading">
        <span class="invoice-panel-status ${uploaded ? "is-uploaded" : ""}">Invoice ${uploaded ? "uploaded" : "pending"}</span>
        <small>${uploaded ? escapeHtml(invoice?.filename || "Invoice saved for audit") : "Optional audit record"}</small>
      </div>
      ${uploaded ? `
        <div class="invoice-panel-actions">
          <button class="secondary compact" data-view-invoice="${item.id}" type="button">View</button>
          <button class="secondary compact" data-download-invoice="${item.id}" data-invoice-name="${escapeHtml(invoice?.filename || "invoice")}" type="button">Download</button>
          <button class="invoice-text-action" data-delete-invoice="${item.id}" type="button">Remove invoice</button>
        </div>
      ` : ""}
      <div class="invoice-panel-upload">${invoiceUploadControl(item.id, invoice)}</div>
    </section>
  `;
}

function transactionSummary(item) {
  const details = item.details || {};
  const vendor = vendorDisplayName(item.vendor_id, item.travel_type, details);
  if (item.travel_type === "flight") {
    return {
      title: [details.from, details.to].filter(Boolean).join(" → ") || "Flight booking",
      metadata: [vendor, details.airline, details.flight_date ? formatDate(details.flight_date) : formatDate(item.paid_at)].filter(Boolean).join(" · "),
      tags: [details.trip_region, details.trip_type, details.outbound_cabin_class || details.flight_class].filter(Boolean),
    };
  }
  if (item.travel_type === "hotel") {
    return {
      title: details.hotel_name || details.city || "Hotel booking",
      metadata: [vendor, details.city, details.check_in ? `Check-in ${formatDate(details.check_in)}` : formatDate(item.paid_at)].filter(Boolean).join(" · "),
      tags: [details.hotel_state].filter(Boolean),
    };
  }
  return {
    title: voucherVendorName(details, item.vendor_id, vendor),
    metadata: `American Express voucher purchase · ${formatDate(item.paid_at)}`,
    tags: [],
  };
}

function vendorDisplayName(vendorId, travelType, details = {}) {
  const configuredVendor = vendorsByType[travelType]?.find((vendor) => vendor.id === vendorId)?.name;
  if (configuredVendor) return configuredVendor;
  if (vendorId === "amex_other_voucher") return "Other American Express Voucher";
  if (travelType === "voucher" && details.vendor_name) return details.vendor_name;
  return humanizeVendorId(vendorId) || "Booking platform";
}

function voucherVendorName(details, vendorId, fallback) {
  const enteredName = String(details.vendor_name || "").trim();
  if (!enteredName || enteredName === vendorId || enteredName.toLowerCase() === "other voucher") return fallback;
  return enteredName;
}

function humanizeVendorId(vendorId) {
  if (!vendorId) return "";
  const abbreviations = { amex: "American Express", hdfc: "HDFC", icici: "ICICI", mmt: "MakeMyTrip", goibibo: "Goibibo", easemytrip: "EaseMyTrip" };
  return String(vendorId)
    .split("_")
    .filter(Boolean)
    .map((part) => abbreviations[part.toLowerCase()] || `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(" ");
}

function transactionDetailsMarkup(item) {
  const details = item.details || {};
  const rows = [];
  const add = (label, value) => {
    if (value !== undefined && value !== null && value !== "") {
      rows.push(`<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value))}</strong></div>`);
    }
  };
  add("Booking platform", vendorDisplayName(item.vendor_id, item.travel_type, details));
  add("Booking date", formatDate(item.paid_at));
  if (item.travel_type === "flight") {
    add("Route", [details.from, details.to].filter(Boolean).join(" → "));
    add("Airline", details.airline);
    add("Trip type", details.trip_type);
    add("Cabin", details.outbound_cabin_class || details.flight_class);
    add("Flight date", details.flight_date ? formatDate(details.flight_date) : "");
    add("Outbound flight", savedFlightLegSummary(details, "outbound"));
    add("Inbound flight", savedFlightLegSummary(details, "return"));
  } else if (item.travel_type === "hotel") {
    add("Hotel", details.hotel_name);
    add("City", details.city);
    add("Check-in", details.check_in ? formatDate(details.check_in) : "");
    add("Check-out", details.check_out ? formatDate(details.check_out) : "");
  }
  if (details.checkout_value || details.voucher_purchase_amount_paid || details.voucher_amount_paid || details.card_balance_paid || details.cash_amount_paid) {
    add("Booking value", details.checkout_value ? formatMoney(details.checkout_value) : "");
    add("Voucher value used", details.voucher_face_value_used ? formatMoney(details.voucher_face_value_used) : "");
    add("Voucher purchase cost", formatMoney(details.voucher_purchase_amount_paid || details.voucher_amount_paid || 0));
    add("Direct card balance", formatMoney(details.card_balance_paid || details.cash_amount_paid || 0));
  }
  add("GST credit", formatMoney(item.gst_credit || 0));
  add("Tax benefit", formatMoney(item.tax_benefit || 0));
  if (Number(item.points_used || 0)) add("Points used", formatNumber(item.points_used));
  return rows.join("");
}

function invoiceUploadControl(transactionId, invoice) {
  return `
    <div class="invoice-upload-control">
      <label class="invoice-file-input">
        <input data-invoice-file="${transactionId}" type="file" accept="application/pdf,image/jpeg,image/png,image/webp" />
        <span class="invoice-file-icon" aria-hidden="true">↑</span>
        <span class="invoice-file-copy">
          <strong>${invoice ? "Choose a replacement" : "Choose invoice"}</strong>
          <small data-invoice-file-label="${transactionId}">PDF, JPG, PNG or WEBP · up to 10 MB</small>
        </span>
      </label>
      <button class="primary compact" data-save-invoice="${transactionId}" type="button">${invoice ? "Replace invoice" : "Upload invoice"}</button>
    </div>
  `;
}

function renderInvoiceUpload(transactionId, invoice, targetSelector) {
  const target = $(targetSelector);
  target.innerHTML = `
    <div class="invoice-upload-copy">
      <strong>Invoice ${invoice ? "uploaded" : "pending"}</strong>
      <span>${invoice ? escapeHtml(invoice.filename) : "Optional: upload a PDF or image for the audit record."}</span>
    </div>
    <div class="invoice-upload-actions">
      ${invoice ? `<button class="secondary compact" data-view-invoice="${transactionId}" type="button">View invoice</button>` : ""}
      ${invoice ? `<button class="secondary compact" data-download-invoice="${transactionId}" data-invoice-name="${escapeHtml(invoice.filename)}" type="button">Download</button><button class="danger-button compact" data-delete-invoice="${transactionId}" type="button">Delete invoice</button>` : ""}
      ${invoiceUploadControl(transactionId, invoice)}
    </div>
  `;
  setupInvoiceActions();
}

function setupInvoiceActions() {
  $$("[data-invoice-file]").forEach((input) => {
    if (input.dataset.bound) return;
    input.dataset.bound = "true";
    input.addEventListener("change", () => {
      const label = document.querySelector(`[data-invoice-file-label="${input.dataset.invoiceFile}"]`);
      const file = input.files?.[0];
      if (label) label.textContent = file ? `${file.name} · ${formatFileSize(file.size)}` : "PDF, JPG, PNG or WEBP · up to 10 MB";
    });
  });
  $$("[data-save-invoice]").forEach((button) => {
    if (button.dataset.bound) return;
    button.dataset.bound = "true";
    button.addEventListener("click", async () => {
      const transactionId = button.dataset.saveInvoice;
      const file = document.querySelector(`[data-invoice-file="${transactionId}"]`)?.files?.[0];
      if (!file) {
        showToast("Choose an invoice file first.", true);
        return;
      }
      if (file.size > 10 * 1024 * 1024) {
        showToast("Invoice files must be 10 MB or smaller.", true);
        return;
      }
      try {
        setStatus("Uploading invoice");
        const formData = new FormData();
        formData.append("invoice", file);
        const response = await fetch(`/transactions/${transactionId}/invoice`, {
          method: "POST",
          headers: await authHeaders(),
          body: formData,
        });
        const data = await readResponseBody(response);
        if (!response.ok) throw new Error(data.detail || "Could not upload the invoice.");
        setStatus("Saved");
        showToast("Invoice uploaded.");
        if ($("#transactionsView").classList.contains("is-hidden")) {
          renderInvoiceUpload(transactionId, data, "#completedInvoicePanel");
        } else {
          await loadTransactions();
        }
      } catch (error) {
        setStatus("Ready");
        showToast(error.message, true);
      }
    });
  });
  $$("[data-view-invoice]").forEach((button) => {
    if (button.dataset.bound) return;
    button.dataset.bound = "true";
    button.addEventListener("click", () => viewInvoice(button.dataset.viewInvoice));
  });
  $$("[data-download-invoice]").forEach((button) => {
    if (button.dataset.bound) return;
    button.dataset.bound = "true";
    button.addEventListener("click", () => downloadInvoice(button.dataset.downloadInvoice, button.dataset.invoiceName));
  });
  $$("[data-delete-invoice]").forEach((button) => {
    if (button.dataset.bound) return;
    button.dataset.bound = "true";
    button.addEventListener("click", async () => {
      if (!window.confirm("Delete this invoice after you have downloaded and archived it? The transaction will remain.")) return;
      try {
        setStatus("Deleting invoice");
        await deleteJson(`/transactions/${button.dataset.deleteInvoice}/invoice`);
        showToast("Invoice deleted. The transaction was kept.");
        if ($("#transactionsView").classList.contains("is-hidden")) {
          renderInvoiceUpload(button.dataset.deleteInvoice, null, "#completedInvoicePanel");
        } else {
          await loadTransactions();
        }
      } catch (error) {
        setStatus("Ready");
        showToast(error.message, true);
      }
    });
  });
}

async function viewInvoice(transactionId) {
  try {
    const invoiceWindow = window.open("", "_blank");
    if (!invoiceWindow) throw new Error("Allow pop-ups to view the invoice.");
    const response = await fetch(`/transactions/${transactionId}/invoice`, { headers: await authHeaders() });
    if (!response.ok) throw new Error("Could not open the invoice.");
    const objectUrl = URL.createObjectURL(await response.blob());
    invoiceWindow.location.replace(objectUrl);
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 300000);
  } catch (error) {
    showToast(error.message, true);
  }
}

async function downloadInvoice(transactionId, filename = "invoice") {
  try {
    const response = await fetch(`/transactions/${transactionId}/invoice`, { headers: await authHeaders() });
    if (!response.ok) throw new Error("Could not download the invoice.");
    const objectUrl = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename || "invoice";
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 300000);
  } catch (error) {
    showToast(error.message, true);
  }
}

function formatFileSize(bytes) {
  const value = Number(bytes || 0);
  if (value < 1024 * 1024) return `${Math.max(0, Math.round(value / 1024))} KB`;
  return `${(value / (1024 * 1024)).toFixed(value >= 100 * 1024 * 1024 ? 0 : 1)} MB`;
}

setupTabs();
setupStepNavigation();
setupTripChoices();
setupQuoteForm();
setupDeclineActions();
setupFinalForm();
setupDraftsAndCancel();
setupStartOver();
setupReports();
setupChoicePdf();
setupAuth();
