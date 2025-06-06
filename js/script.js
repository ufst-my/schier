// Vent til DOM er indlæst
document.addEventListener("DOMContentLoaded", function() {
  const navToggle = document.querySelector(".nav-toggle");
  const siteNav = document.querySelector(".site-nav");

  navToggle.addEventListener("click", function() {
    // Toggler klassen 'open' på nav-elementet
    siteNav.classList.toggle("open");
  });
});
