// Vent til DOM er indlæst
document.addEventListener("DOMContentLoaded", function () {
  const navToggle = document.querySelector(".nav-toggle");
  const siteNav = document.querySelector(".site-nav");

  if (!navToggle || !siteNav) return;

  // Hjælpefunktioner
  const openNav = () => {
    siteNav.classList.add("open");
    navToggle.setAttribute("aria-expanded", "true");
    navToggle.setAttribute("aria-label", "Luk menu");
  };

  const closeNav = () => {
    siteNav.classList.remove("open");
    navToggle.setAttribute("aria-expanded", "false");
    navToggle.setAttribute("aria-label", "Åbn menu");
  };

  const isOpen = () => siteNav.classList.contains("open");

  // Toggle ved klik
  navToggle.addEventListener("click", function () {
    if (isOpen()) closeNav();
    else openNav();
  });

  // Luk hvis man klikker på et link i menuen (bedre UX på mobil)
  siteNav.addEventListener("click", function (e) {
    const target = e.target;
    if (target && target.tagName === "A" && isOpen()) {
      closeNav();
    }
  });

  // Luk ved klik udenfor menuen (mobil)
  document.addEventListener("click", function (e) {
    if (!isOpen()) return;

    const clickedInsideNav = siteNav.contains(e.target);
    const clickedToggle = navToggle.contains(e.target);

    if (!clickedInsideNav && !clickedToggle) {
      closeNav();
    }
  });

  // Luk ved ESC
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && isOpen()) {
      closeNav();
    }
  });

  // Luk hvis man går til desktop (fx rotation)
  window.addEventListener("resize", function () {
    if (window.matchMedia("(min-width: 768px)").matches && isOpen()) {
      closeNav();
    }
  });
});
