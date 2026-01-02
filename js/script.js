// Mobilmenu-toggle (åbn/luk) + klik-udenfor (bevarer dit nuværende setup)
document.addEventListener("DOMContentLoaded", function () {
  const navToggle = document.querySelector(".nav-toggle");
  const siteNav = document.querySelector(".site-nav");

  if (!navToggle || !siteNav) return;

  navToggle.addEventListener("click", function () {
    // Toggle menu-elementet
    siteNav.classList.toggle("open");

    // Opdater aria-expanded for tilgængelighed
    const isOpen = siteNav.classList.contains("open");
    navToggle.setAttribute("aria-expanded", String(isOpen));
    navToggle.setAttribute("aria-label", isOpen ? "Luk menu" : "Åbn menu");
  });

  // Luk ved klik udenfor
  document.addEventListener("click", function (e) {
    if (!siteNav.classList.contains("open")) return;

    const clickedInsideNav = siteNav.contains(e.target);
    const clickedToggle = navToggle.contains(e.target);

    if (!clickedInsideNav && !clickedToggle) {
      siteNav.classList.remove("open");
      navToggle.setAttribute("aria-expanded", "false");
      navToggle.setAttribute("aria-label", "Åbn menu");
    }
  });

  // Luk ved ESC
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && siteNav.classList.contains("open")) {
      siteNav.classList.remove("open");
      navToggle.setAttribute("aria-expanded", "false");
      navToggle.setAttribute("aria-label", "Åbn menu");
    }
  });
});
