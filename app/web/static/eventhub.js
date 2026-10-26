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
