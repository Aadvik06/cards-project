# PreciseHub Quote Capture (private pilot)

This Chrome/Edge extension captures a reviewed vendor quote into an already-open PreciseHub booking. It does not store employee credentials, purchase anything, or collect data in the background.

## Employee workflow

1. Open PreciseHub in Chrome or Edge and start a **flight** or **hotel** booking through Step 2.
2. In another tab, search the supported travel platform as normal.
3. Highlight the final displayed price.
4. Click the **PreciseHub Quote Capture** extension icon.
5. Check the detected platform, price and link, then click **Add to open PreciseHub booking**.
6. Return to PreciseHub and choose **Add quote** in the review panel.
7. Check GST and voucher value before calculating the recommendation.

The current link is captured automatically and is passed through to the existing PDF link section.

## Private installation

1. Open `chrome://extensions` in Chrome, or `edge://extensions` in Edge.
2. Turn on **Developer mode**.
3. Choose **Load unpacked**.
4. Select this `precisehub-quote-capture` folder.
5. Pin the extension from the browser extensions menu.

The production PreciseHub address in `manifest.json` and `popup.js` is:

```text
https://precisehub-git-main-precise-hub.vercel.app/
```

If the company switches to a custom domain, update both files before loading the extension.

## Supported platforms in this pilot

- MakeMyTrip
- Cleartrip
- Goibibo
- EaseMyTrip
- HDFC SmartBuy
- ICICI iShop

The popup recognises the domain and captures the highlighted total plus the current link. It intentionally asks the employee to confirm the amount in PreciseHub before changing the booking.
