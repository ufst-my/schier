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

document.addEventListener("DOMContentLoaded", () => {
  // =========================
  // 1) UDFYLD DINE ANMELDELSER HER
  // =========================
  const REVIEWS = [
    {
      name: "Navn 1",
      avatar: "images/reviews/navn1.jpg",     // dit billede (læg i /images eller hvor du vil)
      stars: 5,                                // 1-5
      text: "Kort uddrag af anmeldelsen her…", // kan være tom: ""
      source: "Trustpilot",
      url: "https://dk.trustpilot.com/review/www.schier.dk"
    },
    {
      name: "Navn 2",
      avatar: "images/reviews/navn2.jpg",
      stars: 5,
      text: "Endnu et kort uddrag…",
      source: "Google",
      url: "INDSÆT-LINK-TIL-DEN-KONKRETE-ANMELDELSE-ELLER-PROFIL"
    }
  ];

  // =========================
  // 2) ELEMENTER
  // =========================
  const card   = document.querySelector("[data-reviews-card]");
  const avatar = document.querySelector("[data-reviews-avatar]");
  const nameEl = document.querySelector("[data-reviews-name]");
  const starsEl= document.querySelector("[data-reviews-stars]");
  const textEl = document.querySelector("[data-reviews-text]");
  const srcEl  = document.querySelector("[data-reviews-source]");
  const prevBtn= document.querySelector("[data-reviews-prev]");
  const nextBtn= document.querySelector("[data-reviews-next]");
  const dotsEl = document.querySelector("[data-reviews-dots]");

  if (!card || !avatar || !nameEl || !starsEl || !textEl || !srcEl || !prevBtn || !nextBtn || !dotsEl) return;
  if (!Array.isArray(REVIEWS) || REVIEWS.length === 0) return;

  // =========================
  // 3) RENDER
  // =========================
  let index = 0;
  let timer = null;
  const INTERVAL_MS = 6500;

  function starsString(n){
    const full = Math.max(0, Math.min(5, Number(n) || 0));
    return "★".repeat(full) + "☆".repeat(5 - full);
  }

  function renderDots(){
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

  function render(){
    const r = REVIEWS[index];

    // link
    card.href = r.url || "#";

    // billede
    avatar.src = r.avatar || "";
    avatar.alt = r.name ? `Billede af ${r.name}` : "Anmelder";

    // navn
    nameEl.textContent = r.name || "";

    // stjerner
    const s = starsString(r.stars);
    starsEl.textContent = s;
    starsEl.setAttribute("aria-label", `${Math.max(0, Math.min(5, Number(r.stars) || 0))} ud af 5 stjerner`);

    // tekst (valgfri)
    const txt = (r.text || "").trim();
    if (txt.length === 0){
      textEl.style.display = "none";
      textEl.textContent = "";
    } else {
      textEl.style.display = "";
      textEl.textContent = txt;
    }

    // kilde (valgfri)
    srcEl.textContent = r.source ? `Kilde: ${r.source}` : "";

    // dots
    renderDots();
  }

  // =========================
  // 4) NAVIGATION
  // =========================
  function next(){
    index = (index + 1) % REVIEWS.length;
    render();
  }

  function prev(){
    index = (index - 1 + REVIEWS.length) % REVIEWS.length;
    render();
  }

  nextBtn.addEventListener("click", () => { next(); restartAuto(); });
  prevBtn.addEventListener("click", () => { prev(); restartAuto(); });

  // Tastatur: pil venstre/højre når kortet/sektionen er i fokus
  card.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") { next(); restartAuto(); }
    if (e.key === "ArrowLeft")  { prev(); restartAuto(); }
  });

  // Swipe på touch (simpelt)
  let startX = null;
  card.addEventListener("pointerdown", (e) => {
    startX = e.clientX;
  });
  card.addEventListener("pointerup", (e) => {
    if (startX === null) return;
    const dx = e.clientX - startX;
    startX = null;

    if (Math.abs(dx) < 40) return; // lille bevægelse -> ignorer
    if (dx < 0) { next(); restartAuto(); } // swipe venstre -> næste
    else { prev(); restartAuto(); }        // swipe højre -> forrige
  });

  // =========================
  // 5) AUTO-SKIFT
  // =========================
  function startAuto(){
    stopAuto();
    timer = setInterval(() => next(), INTERVAL_MS);
  }

  function stopAuto(){
    if (timer) clearInterval(timer);
    timer = null;
  }

  function restartAuto(){
    startAuto();
  }

  // Pause når man “holder musen over” eller fokuserer (for læsbarhed)
  card.addEventListener("mouseenter", stopAuto);
  card.addEventListener("mouseleave", startAuto);
  card.addEventListener("focusin", stopAuto);
  card.addEventListener("focusout", startAuto);

  // Pause når fanen ikke er aktiv
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopAuto();
    else startAuto();
  });

  // Init
  render();
  startAuto();
});
