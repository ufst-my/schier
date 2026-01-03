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
  // 1) UDFYLD ANMELDELSER HER
  // =========================
  const REVIEWS = [
    {
      name: "Laura Aagaard",
      avatar: "images/reviews/laura.avif",     // dit billede (læg i /images eller hvor du vil)
      stars: 5,                                // 1-5
      text: "Vi er virkelig glade for Schier rengøring…", // kan være tom: " "
      source: "Google",
      url: "https://share.google/TOX8MqLccJ88ZGPAW"    // vælg del under anmeldelser
    },
    {
      name: "zoob77",    
      avatar: "images/reviews/zoob.avif",     // brugers billede
      stars: 5,                                // 1-5
      text: "Intet at udsætte…", // kan være tom: " "
      source: "Google",
      url: "https://share.google/8fw9UN9i1ZvmhguR7"    // vælg del under anmeldelser
    },
    {
      name: "Joachim Rehder",
      avatar: "images/reviews/joachim.avif",     // brugers billede
      stars: 5,                                // 1-5
      text: " ", // kan være tom: " "
      source: "Google",
      url: "https://share.google/SJxXz1nYu3l2ArTK2"    // vælg del under anmeldelser

    },
    {
      name: "Hanne Bruhn",
      avatar: "images/reviews/hanneb.avif",     // brugers billede
      stars: 5,                                // 1-5
      text: "rengøring i top, altid sød og venlig betjening…", // kan være tom: " "
      source: "Google",
      url: "https://share.google/EyA3NZ7IDHXbZSpTA"    // vælg del under anmeldelser
    },
    {
      name: "Rene Dissing",
      avatar: "images/reviews/rene.avif",     // brugers billede
      stars: 5,                                // 1-5
      text: "Bestilte en \"total\" rengøring af mit hus (3 etager)…", // kan være tom: " "
      source: "Google",
      url: "https://share.google/Bn9jRVgWNd77TIrpz"    // vælg del under anmeldelser
    },
    {
      name: "Hanne Jørgensen",
      avatar: "images/reviews/hanne.avif",     // brugers billede
      stars: 4,                                // 1-5
      text: " ", // kan være tom: " "
      source: "Google",
      url: "https://www.google.com/search?sa=X&sca_esv=21a016e0095234e7&sxsrf=AE3TifOEgnrjS0W1IVIML42CZn4LbGVAwQ:1767396192285&q=Schier+Reng%C3%B8ring+Anmeldelser&rflfq=1&num=20&stick=H4sIAAAAAAAAAONgkxIxNDQ3MDY0Mzc0NzW1tDA3sDAystjAyPiKUTY4OSMztUghKDUv_fCOosy8dAXHvNzUnJTUnOLUokWs-OUBjmeNplsAAAA&rldimm=11703167175598708228&tbm=lcl&hl=da-DK&ved=2ahUKEwiPxt_x_-2RAxWGRPEDHVu6Gx8Q9fQKegQIRxAG&biw=1680&bih=881&dpr=1#lkt=LocalPoiReviews"
    },
    {
      name: "Jonas Schnack Krog",
      avatar: "images/reviews/jonas.avif",     // brugers billede
      stars: 5,                                // 1-5
      text: "God og solid rengøring med god kommunikation…", // kan være tom: " "
      source: "Google",
      url: "https://share.google/2zHZMIzgZwcFuGmT6"    // vælg del under anmeldelser
    },
    {
      name: "Tina Katja Lund Andersen",
      avatar: "images/reviews/tina.avif",     // brugers billede
      stars: 5,                                // 1-5
      text: "Super god oplevelse, både før, under og efter…", // kan være tom: " "
      source: "Trustpilot",
      url: "https://dk.trustpilot.com/reviews/605db2ccf85d75087035fcec"    // vælg del under anmeldelser
    },
    {
      name: "Lotte Nielsen",
      avatar: "images/reviews/lotte.avif",     // brugers billede
      stars: 5,                                // 1-5
      text: "Bestilte en fllytteflytterengøring…", // kan være tom: " "
      source: "Trustpilot",
      url: "https://dk.trustpilot.com/reviews/689f0fc9f2fd65a1267fde75"    // vælg del under anmeldelser
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
    srcEl.textContent = r.source ? `Anmeldelse fra: ${r.source}` : "";

    // dots
    renderDots();
  }

  // =========================
  // 4) NAVIGATION
  // =========================
    
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
  
  // --- Keyboard support ---
  // Løsning: lyt på document, men kun når fokus er inde i reviews-området
  // (så du ikke “stjæler” piletaster når man fx scroller andre steder).
  const reviewsSection = card.closest(".reviews");
  
  document.addEventListener("keydown", (e) => {
    const active = document.activeElement;
  
    // Kør kun hvis fokus er på kortet eller inde i reviews-sektionen
    const focusInsideReviews =
      (active && (active === card || (reviewsSection && reviewsSection.contains(active))));
  
    if (!focusInsideReviews) return;
  
    if (e.key === "ArrowRight") {
      e.preventDefault();
      next();
      restartAuto();
    }
  
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      prev();
      restartAuto();
    }
  });
  
  // --- Touch swipe (iOS/Android) ---
  let startX = null;
  
  card.addEventListener("touchstart", (e) => {
    if (!e.touches || e.touches.length === 0) return;
    startX = e.touches[0].clientX;
  }, { passive: true });
  
  card.addEventListener("touchend", (e) => {
    if (startX === null) return;
  
    const endX =
      (e.changedTouches && e.changedTouches.length)
        ? e.changedTouches[0].clientX
        : startX;
  
    const dx = endX - startX;
    startX = null;
  
    if (Math.abs(dx) < 40) return; // ignorer små bevægelser
  
    if (dx < 0) { // swipe venstre -> næste
      next();
      restartAuto();
    } else {      // swipe højre -> forrige
      prev();
      restartAuto();
    }
  }, { passive: true });

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
