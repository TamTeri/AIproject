// Event card gestures (catalog-004 / catalog-008):
// - single click on a card opens the event page;
// - double click buys one ticket in the saved currency (Quick Buy) through the
//   normal server-side purchase path (the hidden form posts with a CSRF token).
// A short delay tells a single click apart from the first half of a double click.
(function () {
  "use strict";
  var DOUBLE_CLICK_WINDOW_MS = 250;

  document.querySelectorAll(".event-card[data-event-url]").forEach(function (card) {
    var timer = null;

    card.addEventListener("click", function (event) {
      if (event.target.closest("a, button, input, select, form")) {
        return; // real links/buttons keep their normal behaviour
      }
      if (timer) {
        return;
      }
      timer = window.setTimeout(function () {
        timer = null;
        window.location.assign(card.dataset.eventUrl);
      }, DOUBLE_CLICK_WINDOW_MS);
    });

    card.addEventListener("dblclick", function (event) {
      event.preventDefault();
      if (timer) {
        window.clearTimeout(timer);
        timer = null;
      }
      var form = card.querySelector("form.quick-buy-form");
      if (form) {
        form.submit();
      }
    });
  });
})();

// purchase-014 (Call 5): an impatient second click on a purchase button is not
// sent. The server is the real guarantee (one-time form keys), because a slow
// page, a script or a retry can still send a form twice.
(function () {
  "use strict";
  var UNLOCK_AFTER_MS = 4000;
  document.querySelectorAll("form[data-single-submit]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (form.dataset.submitted === "1") {
        event.preventDefault();
        return;
      }
      form.dataset.submitted = "1";
      form.querySelectorAll("button[type=submit]").forEach(function (button) {
        button.setAttribute("aria-disabled", "true");
      });
      // If the page never changes (Stop pressed, network error), let the buyer try again.
      window.setTimeout(function () { unlock(form); }, UNLOCK_AFTER_MS);
    });
  });
  // A page shown again from the back/forward cache starts unlocked.
  window.addEventListener("pageshow", function () {
    document.querySelectorAll("form[data-single-submit]").forEach(unlock);
  });

  function unlock(form) {
    delete form.dataset.submitted;
    form.querySelectorAll("button[type=submit]").forEach(function (button) {
      button.removeAttribute("aria-disabled");
    });
  }
})();
