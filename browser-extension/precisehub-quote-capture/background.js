const PRECISEHUB_MATCH_PATTERNS = [
  "https://cards-project-kappa.vercel.app/*",
  "https://precisehub-git-main-precise-hub.vercel.app/*",
];

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "ADD_QUOTE_TO_PRECISEHUB") return undefined;

  addQuoteToPreciseHub(message.capture)
    .then(sendResponse)
    .catch((error) => sendResponse({ success: false, message: error?.message || "Could not add the quote." }));
  return true;
});

async function addQuoteToPreciseHub(capture) {
  const tabs = await chrome.tabs.query({ url: PRECISEHUB_MATCH_PATTERNS });
  if (!tabs.length) {
    return { success: false, message: "Open PreciseHub and start a flight or hotel booking first." };
  }

  const target = tabs.find((tab) => tab.active) || tabs[0];
  const [result] = await chrome.scripting.executeScript({
    target: { tabId: target.id },
    args: [capture],
    func: (quote) => {
      const vendorIdsByPlatform = {
        makemytrip: ["amex_mmt_flight_voucher", "amex_mmt_hotel_voucher"],
        cleartrip: ["amex_cleartrip_generic_voucher", "amex_cleartrip_hotel_voucher"],
        goibibo: ["amex_goibibo_hotel_voucher"],
        easemytrip: ["amex_easemytrip_hotel_voucher"],
        hdfc_smartbuy: ["hdfc_smartbuy_flight", "hdfc_smartbuy_hotel"],
        icici_ishop: ["icici_ishop_flight", "icici_ishop_hotel"],
      };
      const vendorId = (vendorIdsByPlatform[quote.vendor_key] || []).find((id) =>
        document.querySelector(`[data-vendor-amount="${id}"]`)
      );
      if (!vendorId) {
        return { success: false, message: "Open the matching flight or hotel booking in PreciseHub Step 2 first." };
      }

      const amountInput = document.querySelector(`[data-vendor-amount="${vendorId}"]`);
      const linkInput = document.querySelector(`[data-vendor-link="${vendorId}"]`);
      if (!amountInput || !linkInput) {
        return { success: false, message: "The matching vendor is not active in this PreciseHub booking." };
      }

      amountInput.value = Number(quote.amount).toFixed(2);
      linkInput.value = quote.url;
      for (const input of [amountInput, linkInput]) {
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }
      amountInput.closest(".vendor-row")?.scrollIntoView({ behavior: "smooth", block: "center" });
      return { success: true, vendorId };
    },
  });

  if (!result?.result?.success) {
    return { success: false, message: result?.result?.message || "PreciseHub could not accept this quote." };
  }

  await chrome.tabs.update(target.id, { active: true });
  return { success: true };
}
