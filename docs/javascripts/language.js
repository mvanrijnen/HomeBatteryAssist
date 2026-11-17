// Open the documentation in the reader's own language (Dutch or English).
//
// On the first visit the browser's language decides; a language picked in
// the language menu is remembered and always wins after that.
(function () {
  const KEY = "hba-docs-language";
  const current = document.documentElement.lang || "en";
  let chosen = null;
  try {
    chosen = localStorage.getItem(KEY);
  } catch (e) {
    chosen = null;
  }

  // Remember a choice from the language menu.
  document.addEventListener("click", (event) => {
    const link = event.target.closest && event.target.closest("a[hreflang]");
    if (!link) return;
    try {
      localStorage.setItem(KEY, link.getAttribute("hreflang"));
    } catch (e) {
      /* private window: nothing to remember */
    }
  });

  const wanted =
    chosen ||
    ((navigator.languages || [navigator.language || ""]).some((l) => /^nl\b/i.test(l)) ? "nl" : "en");
  if (wanted === current) return;
  const target = document.querySelector(`a[hreflang="${wanted}"]`);
  if (target && target.href && target.href !== location.href) {
    location.replace(target.href + location.hash);
  }
})();
