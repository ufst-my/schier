document.addEventListener("DOMContentLoaded", function () {
  // =========================
  // Mobilmenu-toggle
  // =========================
  const navToggle = document.querySelector(".nav-toggle");
  const siteNav = document.querySelector(".site-nav");

  if (navToggle && siteNav) {
    navToggle.addEventListener("click", function () {
      siteNav.classList.toggle("open");
      const isOpen = siteNav.classList.contains("open");
      navToggle.setAttribute("aria-expanded", String(isOpen));
      navToggle.setAttribute("aria-label", isOpen ? "Luk menu" : "Åbn menu");
    });

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

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && siteNav.classList.contains("open")) {
        siteNav.classList.remove("open");
        navToggle.setAttribute("aria-expanded", "false");
        navToggle.setAttribute("aria-label", "Åbn menu");
      }
    });
  }

  // =========================
  // Reviews slider
  // =========================
  const REVIEWS = [
    // UDFYLD/BEHOLD DINE EGENE HER (eksempel)
    // {
    //   name: "Navn",
    //   avatar: "images/reviews/navn.avif",
    //   stars: 5,
    //   text: "",
    //   source: "Trustpilot",
    //   url: "https://dk.trustpilot.com/review/www.schier.dk"
    // }
  ];

  const card    = document.querySelector("[data-reviews-card]");
  const avatar  = document.querySelector("[data-reviews-avatar]");
  const nameEl  = document.querySelector("[data-reviews-name]");
  const starsEl = document.querySelector("[data-reviews-stars]");
  const textEl  = document.querySelector("[data-reviews-text]");
  const srcEl   = document.querySelector("[data-reviews-source]");
  const prevBtn = document.querySelector("[data-reviews-prev]");
  const nextBtn = document.querySelector("[data-reviews-next]");
  const dotsEl  = document.querySelector("[data-reviews-dots]");

  // Hvis der ikke er reviews på siden, eller du ikke har udfyldt listen, gør vi ingenting.
  if (!card || !avatar || !nameEl || !starsEl || !textEl || !srcEl || !prevBtn || !nextBtn || !dotsEl) return;
  if (!Array.isArray(REVIEWS) || REVIEWS.length === 0) return;

  let index = 0;
  let timer = null;
  const INTERVAL_MS = 6500;

  function starsString(n) {
    const full = Math.max(0, Math.min(5, Number(n) || 0));
    return "★".repeat(full) + "☆".repeat(5 - full);
  }

  function renderDots() {
    dotsEl.innerHTML = "";
    REVIEWS.forEach((_, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "reviews__dot" + (i === index ? " is-active" : "");
      b.setAttribute("aria-label", `Gå til anmeldelse ${i + 1}`);
      b.addEventListener("click", () => {
        index = i;
        render();
        restartAuto();
      });
      dotsEl.appendChild(b);
    });
  }

  function render() {
    const r = REVIEWS[index];

    // Link til kilden
    card.href = r.url || "#";

    // Avatar
    avatar.src = r.avatar || "";
    avatar.alt = r.name ? `Billede af ${r.name}` : "Anmelder";

    // Navn
    nameEl.textContent = r.name || "";

    // Stjerner
    const s = starsString(r.stars);
    starsEl.textContent = s;
    const sr = Math.max(0, Math.min(5, Number(r.stars) || 0));
    starsEl.setAttribute("aria-label", `${sr} ud af 5 stjerner`);

    // Tekst: behold altid linjen (blank hvis tom)
    const txt = (r.text || "").trim();
    textEl.textContent = txt.length ? txt : "\u00A0";

    // Kilde
    srcEl.textContent = r.source ? `Kilde: ${r.source}` : "";

    renderDots();
  }

  // Navigation
  function next() {
    index = (index + 1) % REVIEWS.length;
    render();
  }

  function prev() {
    index = (index - 1 + REVIEWS.length) % REVIEWS.length;
    render();
  }

  nextBtn.addEventListener("click", () => { next(); restartAuto(); });
  prevBtn.addEventListener("click", () => { prev(); restartAuto(); });

  // Keyboard: pil venstre/højre når fokus er i reviews
  const reviewsSection = card.closest(".reviews");
  document.addEventListener("keydown", (e) => {
    const active = document.activeElement;
    const focusInside =
      active && (active === card || (reviewsSection && reviewsSection.contains(active)));
    if (!focusInside) return;

    if (e.key === "ArrowRight") { e.preventDefault(); next(); restartAuto(); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); prev(); restartAuto(); }
  });

  // Touch swipe (undgå at swipe utilsigtet klikker link)
  let startX = null;
  let isSwiping = false;

  card.addEventListener("touchstart", (e) => {
    if (!e.touches || e.touches.length === 0) return;
    startX = e.touches[0].clientX;
    isSwiping = false;
  }, { passive: true });

  card.addEventListener("touchmove", (e) => {
    if (startX === null || !e.touches || e.touches.length === 0) return;
    const dx = e.touches[0].clientX - startX;
    if (Math.abs(dx) > 10) isSwiping = true;
  }, { passive: true });

  card.addEventListener("touchend", (e) => {
    if (startX === null) return;

    const endX = (e.changedTouches && e.changedTouches.length)
      ? e.changedTouches[0].clientX
      : startX;

    const dx = endX - startX;
    startX = null;

    if (Math.abs(dx) < 40) return;

    // Marker som swipe så click kan ignoreres
    isSwiping = true;

    if (dx < 0) { next(); restartAuto(); }
    else { prev(); restartAuto(); }
  }, { passive: true });

  // Ignorér klik hvis det var swipe (så man ikke ryger ud på Trustpilot/Google ved swipe)
  card.addEventListener("click", (e) => {
    if (isSwiping) {
      e.preventDefault();
      isSwiping = false;
    }
  });

  // Auto-skift
  function startAuto() {
    stopAuto();
    timer = setInterval(() => next(), INTERVAL_MS);
  }
  function stopAuto() {
    if (timer) clearInterval(timer);
    timer = null;
  }
  function restartAuto() {
    startAuto();
  }

  card.addEventListener("mouseenter", stopAuto);
  card.addEventListener("mouseleave", startAuto);
  card.addEventListener("focusin", stopAuto);
  card.addEventListener("focusout", startAuto);

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopAuto();
    else startAuto();
  });

  // Init
  render();
  startAuto();
});
