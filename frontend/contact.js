/* Shared support-contact widget.
 * - Injects a floating WhatsApp "Chat with us" button (bottom-right).
 * - Fills any element with class "js-support-email" / "js-support-whatsapp".
 * Config comes from config.js (window.SUPPORT_WHATSAPP / window.SUPPORT_EMAIL). */
(function () {
  var wa = (window.SUPPORT_WHATSAPP || "").replace(/[^0-9]/g, "");
  var email = window.SUPPORT_EMAIL || "";
  var greeting = encodeURIComponent("Hi! I need help with the AI Research Assistant.");
  var waLink = wa ? "https://wa.me/" + wa + "?text=" + greeting : null;

  // Fill inline contact links (footers, policy pages).
  document.querySelectorAll(".js-support-email").forEach(function (el) {
    if (!email) return;
    el.textContent = email;
    if (el.tagName === "A") el.href = "mailto:" + email;
  });
  document.querySelectorAll(".js-support-whatsapp").forEach(function (el) {
    if (!waLink) return;
    el.textContent = "WhatsApp";
    if (el.tagName === "A") { el.href = waLink; el.target = "_blank"; el.rel = "noopener"; }
  });

  // Floating WhatsApp button.
  if (!waLink) return;
  var a = document.createElement("a");
  a.href = waLink;
  a.target = "_blank";
  a.rel = "noopener";
  a.className = "wa-fab";
  a.setAttribute("aria-label", "Chat with us on WhatsApp");
  a.innerHTML =
    '<svg viewBox="0 0 32 32" width="24" height="24" aria-hidden="true">' +
    '<path fill="currentColor" d="M16 3C9.4 3 4 8.4 4 15c0 2.1.6 4.1 1.6 5.9L4 29l8.3-1.6c1.7.9 3.7 1.4 5.7 1.4 6.6 0 12-5.4 12-12S22.6 3 16 3zm0 21.8c-1.8 0-3.5-.5-5-1.4l-.4-.2-4.9 1 .9-4.8-.3-.5c-1-1.6-1.5-3.4-1.5-5.3C4.8 9.9 9.9 4.8 16 4.8S27.2 9.9 27.2 16 22.1 24.8 16 24.8zm6.1-6.3c-.3-.2-2-1-2.3-1.1-.3-.1-.5-.2-.8.2-.2.3-.9 1.1-1.1 1.3-.2.2-.4.2-.7.1-1.8-.9-3-1.6-4.2-3.6-.3-.5.3-.5.9-1.6.1-.2 0-.4 0-.6-.1-.2-.8-1.9-1.1-2.5-.3-.7-.6-.6-.8-.6h-.7c-.2 0-.6.1-.9.4-.3.3-1.2 1.2-1.2 2.9s1.2 3.3 1.4 3.6c.2.2 2.4 3.7 5.9 5.2 2.2.9 3 1 4.1.9.7-.1 2-.8 2.3-1.6.3-.8.3-1.4.2-1.6-.1-.1-.3-.2-.6-.3z"/>' +
    '</svg><span>Chat with us</span>';
  document.body.appendChild(a);
})();
