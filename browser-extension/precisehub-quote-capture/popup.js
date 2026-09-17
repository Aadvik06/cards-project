const supportedPlatforms = [
  { key: "makemytrip", name: "MakeMyTrip", domains: ["makemytrip.com"] },
  { key: "cleartrip", name: "Cleartrip", domains: ["cleartrip.com"] },
  { key: "goibibo", name: "Goibibo", domains: ["goibibo.com"] },
  { key: "easemytrip", name: "EaseMyTrip", domains: ["easemytrip.com"] },
  { key: "hdfc_smartbuy", name: "HDFC SmartBuy", domains: ["hdfcbank.com"] },
  { key: "icici_ishop", name: "ICICI iShop", domains: ["icicibank.com"] },
];

const vendorName = document.querySelector("#vendorName");
const linkStatus = document.querySelector("#linkStatus");
const priceInput = document.querySelector("#price");
const priceHint = document.querySelector("#priceHint");
const captureButton = document.querySelector("#captureButton");
const status = document.querySelector("#status");
let activeCapture = null;

function setStatus(message, error = false) {
  status.textContent = message;
  status.classList.toggle("error", error);
}

function platformForUrl(rawUrl) {
  try {
    const hostname = new URL(rawUrl).hostname.toLowerCase();
    return supportedPlatforms.find((platform) => platform.domains.some((domain) => hostname === domain || hostname.endsWith(`.${domain}`)));
  } catch {
    return null;
  }
}

function parseAmount(rawValue) {
  const text = String(rawValue || "").replace(/\s+/g, " ");
  const match = text.match(/(?:₹|INR|Rs\.?)[\s:]*([0-9][0-9,]*(?:\.\d{1,2})?)/i)
    || text.match(/\b([0-9][0-9,]*(?:\.\d{1,2})?)\b/);
  if (!match) return null;
  const value = Number(match[1].replace(/,/g, ""));
  return Number.isFinite(value) && value > 0 ? value : null;
}

async function extractActivePage(tabId) {
  const [result] = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => ({
      url: window.location.href,
      title: document.title,
      selectedText: window.getSelection()?.toString() || "",
    }),
  });
  return result?.result;
}

function refreshCaptureButton() {
  captureButton.disabled = !activeCapture || !(Number(priceInput.value) > 0);
}

async function initialise() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url) {
    setStatus("Could not read this browser tab.", true);
    return;
  }
  const platform = platformForUrl(tab.url);
  if (!platform) {
    vendorName.textContent = "Unsupported platform";
    linkStatus.textContent = "Open a supported travel website first";
    setStatus("This first release supports MakeMyTrip, Cleartrip, Goibibo, EaseMyTrip, SmartBuy and iShop.", true);
    return;
  }
  try {
    const page = await extractActivePage(tab.id);
    activeCapture = { vendor_key: platform.key, url: page.url, title: page.title };
    vendorName.textContent = platform.name;
    linkStatus.textContent = "Current page link ready";
    const selectedAmount = parseAmount(page.selectedText);
    if (selectedAmount) {
      priceInput.value = selectedAmount.toFixed(2);
      priceHint.textContent = "Price taken from the text you selected on the page.";
    } else {
      priceHint.textContent = "For accuracy, highlight the final price on the page before opening this extension. You may also type it here.";
    }
    refreshCaptureButton();
  } catch {
    setStatus("The page could not be read. Refresh the travel page and try again.", true);
  }
}

priceInput.addEventListener("input", refreshCaptureButton);

captureButton.addEventListener("click", async () => {
  if (!activeCapture) return;
  const amount = Number(priceInput.value);
  if (!Number.isFinite(amount) || amount <= 0) return;
  captureButton.disabled = true;
  setStatus("Sending quote to PreciseHub…");
  try {
    const response = await chrome.runtime.sendMessage({
      type: "ADD_QUOTE_TO_PRECISEHUB",
      capture: { ...activeCapture, amount },
    });
    if (!response?.success) {
      throw new Error(response?.message || "PreciseHub could not accept this quote.");
    }
    setStatus("Quote added. Review GST and voucher value in PreciseHub.");
  } catch (error) {
    setStatus(
      error?.message || "Could not add the quote. Keep PreciseHub open on the matching Step 2 booking and try again.",
      true,
    );
    refreshCaptureButton();
  }
});

initialise();
