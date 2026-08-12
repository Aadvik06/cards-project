const vendorsByType = {
  flight: [
    { id: "amex_mmt_flight_voucher", name: "MakeMyTrip Gift Voucher", card: "American Express" },
    { id: "amex_cleartrip_generic_voucher", name: "Cleartrip E-Gift Voucher", card: "American Express" },
    { id: "hdfc_smartbuy_flight", name: "HDFC SmartBuy", card: "HDFC Infinia" },
    { id: "icici_ishop_flight", name: "ICICI iShop", card: "ICICI Times Black" },
  ],
  hotel: [
    { id: "amex_goibibo_hotel_voucher", name: "Goibibo Hotel E-Gift Voucher", card: "American Express" },
    { id: "amex_easemytrip_hotel_voucher", name: "Easemytrip Hotel E-Gift Voucher", card: "American Express" },
    { id: "amex_mmt_hotel_voucher", name: "MakeMyTrip Hotel E-Gift Voucher", card: "American Express" },
    { id: "amex_cleartrip_hotel_voucher", name: "Cleartrip E-Gift Voucher", card: "American Express" },
    { id: "hdfc_smartbuy_hotel", name: "HDFC SmartBuy", card: "HDFC Infinia" },
    { id: "icici_ishop_hotel", name: "ICICI iShop", card: "ICICI Times Black" },
    { id: "amex_fine_hotels", name: "American Express Fine Hotels", card: "American Express" },
  ],
};

const state = {
  travelType: null,
  recommendation: null,
  selectedOption: null,
  pendingDeclineOption: null,
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

function showPanel(name) {
  Object.values(panels).forEach((panel) => panel.classList.add("is-hidden"));
  panels[name].classList.remove("is-hidden");

  const stepMap = { trip: 1, prices: 2, recommendation: 3, finalize: 4, done: 4 };
  $$(".step").forEach((step) => {
    step.classList.toggle("is-active", Number(step.dataset.step) === stepMap[name]);
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

function formatMoney(value) {
  return Number(value).toLocaleString("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  });
}

function formatNumber(value) {
  return Number(value).toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

function setupTripChoices() {
  $$(".choice-card").forEach((button) => {
    button.addEventListener("click", () => {
      state.travelType = button.dataset.travelType;
      $("#priceTitle").textContent =
        state.travelType === "flight" ? "Enter flight prices" : "Enter hotel prices";
      $("#travelDate").value = today();
      renderVendorRows();
      showPanel("prices");
    });
  });
}

function renderVendorRows() {
  const vendorList = $("#vendorList");
  vendorList.innerHTML = "";

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
        <input inputmode="decimal" min="0" max="100" step="0.01" type="number" data-vendor-discount="${vendor.id}" placeholder="0" />
      </label>
    `;
    vendorList.appendChild(row);
  });
}

function collectQuotes() {
  const quotes = [];
  vendorsByType[state.travelType].forEach((vendor) => {
    const amountInput = document.querySelector(`[data-vendor-amount="${vendor.id}"]`);
    const discountInput = document.querySelector(`[data-vendor-discount="${vendor.id}"]`);
    const amount = Number(amountInput.value);
    const discountPercent = Number(discountInput.value || 0);

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

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Something went wrong.");
  }
  return data;
}

function setupQuoteForm() {
  $("#backToTrip").addEventListener("click", () => showPanel("trip"));

  $("#quoteForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const quotes = collectQuotes();
    if (quotes.length === 0) {
      showToast("Enter at least one price.", true);
      return;
    }

    try {
      setStatus("Calculating");
      const recommendation = await postJson("/recommendations", {
        employee_id: $("#employeeId").value.trim() || null,
        travel_type: state.travelType,
        travel_date: $("#travelDate").value || null,
        quotes,
      });
      state.recommendation = recommendation;
      renderRecommendation();
      setStatus("Ready");
      showPanel("recommendation");
    } catch (error) {
      setStatus("Ready");
      showToast(error.message, true);
    }
  });
}

function renderRecommendation() {
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
  const button = isBest
    ? `<button class="primary" type="button" data-accept-option="${option.id}">Use this card</button>`
    : `<button class="secondary" type="button" data-decline-option="${option.id}">Choose this instead</button>`;

  return `
    <article class="option-card ${isBest ? "best" : ""}">
      <div class="option-top">
        <div>
          <span class="rank-badge">Rank ${option.rank}</span>
          <h3>${option.card_name}</h3>
          <p>${option.vendor_name}</p>
        </div>
        ${button}
      </div>
      <div class="metric-grid">
        <div class="metric">
          <span>Net cost</span>
          <strong>${formatMoney(option.net_cost)}</strong>
        </div>
        <div class="metric">
          <span>Pay after discount</span>
          <strong>${formatMoney(option.price_after_discount)}</strong>
        </div>
        <div class="metric">
          <span>Total points</span>
          <strong>${formatNumber(option.total_points)}</strong>
        </div>
        <div class="metric">
          <span>Point value</span>
          <strong>${formatMoney(option.points_value_rupees)}</strong>
        </div>
      </div>
    </article>
  `;
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
    showPanel("finalize");
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
      showPanel("finalize");
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
    <span>Estimated net cost: ${formatMoney(option.net_cost)}</span>
  `;
  $("#finalAmount").value = Number(option.price_after_discount).toFixed(2);
}

function setupFinalForm() {
  $("#finalForm").addEventListener("submit", async (event) => {
    event.preventDefault();

    try {
      setStatus("Saving");
      const paidAt = $("#paidAt").value ? new Date($("#paidAt").value).toISOString() : null;
      const transaction = await postJson(`/recommendations/${state.recommendation.id}/finalize`, {
        selected_option_id: state.selectedOption.id,
        final_amount_paid: $("#finalAmount").value,
        paid_at: paidAt,
      });
      renderDone(transaction);
      setStatus("Saved");
      showPanel("done");
    } catch (error) {
      setStatus("Ready");
      showToast(error.message, true);
    }
  });
}

function renderDone(transaction) {
  $("#savedDetails").innerHTML = `
    <div class="metric-grid">
      <div class="metric">
        <span>Final amount</span>
        <strong>${formatMoney(transaction.final_amount_paid)}</strong>
      </div>
      <div class="metric">
        <span>Points</span>
        <strong>${formatNumber(transaction.total_points)}</strong>
      </div>
      <div class="metric">
        <span>Net cost</span>
        <strong>${formatMoney(transaction.net_cost)}</strong>
      </div>
      <div class="metric">
        <span>Status</span>
        <strong>Logged</strong>
      </div>
    </div>
  `;
}

function setupStartOver() {
  $("#startOver").addEventListener("click", () => {
    state.travelType = null;
    state.recommendation = null;
    state.selectedOption = null;
    state.pendingDeclineOption = null;
    $("#quoteForm").reset();
    $("#finalForm").reset();
    setStatus("Ready");
    showPanel("trip");
  });
}

setupTripChoices();
setupQuoteForm();
setupDeclineActions();
setupFinalForm();
setupStartOver();

