// Asset-resolver: gør billedstier robuste på både forside og undersider
const __SCRIPT_SRC__ = (() => {
  try {
    // Under parsing er document.currentScript typisk sat
    if (document.currentScript && document.currentScript.src) return document.currentScript.src;

    // Fallback: find seneste script-tag der peger på script.js
    const scripts = document.getElementsByTagName("script");
    for (let i = scripts.length - 1; i >= 0; i--) {
      const src = scripts[i].getAttribute("src") || "";
      if (src && src.includes("script.js")) return new URL(src, document.baseURI).toString();
    }
  } catch (e) {}
  return null;
})();

function resolveAssetPath(path) {
  if (!path) return path;

  // Eksterne/data-URL'er bruges som de er
  if (/^(https?:)?\/\//i.test(path) || path.startsWith("data:")) return path;

  // Normalisér til "site-root relativ" sti (uden indledende /)
  const clean = path.replace(/^\//, "").replace(/^\.\//, "");

  // Hvis vi kender scriptets placering (…/js/script.js), så kan vi altid gå op til site-roden
  if (__SCRIPT_SRC__) {
    return new URL("../" + clean, __SCRIPT_SRC__).toString();
  }

  // Sidste udvej: returnér som relativ sti
  return clean;
}

// Mobilmenu + dropdown (Ydelser): åbn/luk + luk ved klik udenfor og ESC
document.addEventListener("DOMContentLoaded", function () {
  const navToggle = document.querySelector(".nav-toggle");
  const siteNav = document.querySelector(".site-nav");

  // Dropdown (Ydelser)
  const servicesDropdown = document.querySelector(".site-nav .has-dropdown");
  const dropdownBtn = servicesDropdown ? servicesDropdown.querySelector(".dropdown-toggle") : null;
  const dropdownMenu = servicesDropdown ? servicesDropdown.querySelector(".dropdown-menu") : null;

  // Markér aktiv side i menuen (gør link bold via CSS)
  (function setActiveNavLink(){
    const links = Array.from(document.querySelectorAll(".site-nav a[href]"));
    if (!links.length) return;
  
    const normalize = (p) => {
      if (!p) return "/";
      p = p.replace(/\/index\.html$/i, "/");
      p = p.split("?")[0].split("#")[0];
      if (p.length > 1) p = p.replace(/\/+$/g, "");
      return p || "/";
    };
  
    // Aktuel sti (kan være /schier/ydelser/... eller /ydelser/...)
    const current = normalize(window.location.pathname);
  
    // Ryd tidligere markering
    links.forEach(a => a.removeAttribute("aria-current"));
  
    // Vælg bedste match (eksakt eller "samme sti i undermappe")
    let best = null;
    let bestLen = -1;
  
    links.forEach(a => {
      const href = a.getAttribute("href") || "";
      if (!href || href.startsWith("tel:") || href.startsWith("mailto:") || href.startsWith("#")) return;
  
      let linkPath = "/";
      try {
        // Brug location.href for robust parsing (lokalt/produktionen/undermapper)
        linkPath = normalize(new URL(a.getAttribute("href"), window.location.href).pathname);
      } catch (e) {
        return;
      }
  
      // Undgå at "/" (forside) matcher "alt"
      if (linkPath === "/") return;
  
      // Match-strategier (host-agnostisk):
      // 1) Eksakt: /ydelser/kontorrengoring == /ydelser/kontorrengoring
      // 2) Prefix: /ydelser matcher /ydelser/kontorrengoring
      // 3) Suffix: /ydelser/kontorrengoring matcher /schier/ydelser/kontorrengoring
      // 4) Contained: /ydelser/ matcher /schier/ydelser/...
      const isExact = (linkPath === current);
      const isPrefix = current.startsWith(linkPath + "/");
      const isSuffix = current.endsWith(linkPath);
      const isContained = current.includes(linkPath + "/");
  
      if (isExact || isPrefix || isSuffix || isContained) {
        if (linkPath.length > bestLen) {
          best = a;
          bestLen = linkPath.length;
        }
      }
    });
  
    if (best) best.setAttribute("aria-current", "page");
  
    // Hvis aktivt link er i dropdown, markér også parent ("Ydelser")
    if (best) {
      const dropdownParent = best.closest(".dropdown-menu")?.closest(".has-dropdown");
      if (dropdownParent) {
        const parentLink = dropdownParent.querySelector(".dropdown-link");
        if (parentLink && !parentLink.hasAttribute("aria-current")) {
          parentLink.setAttribute("aria-current", "true");
        }
      }
    }
  })();
  
  function isDesktop() {
    return window.matchMedia("(min-width: 768px)").matches;
  }

  function setMobileMenuOpen(open) {
    if (!navToggle || !siteNav) return;

    siteNav.classList.toggle("open", open);
    navToggle.setAttribute("aria-expanded", String(open));
    navToggle.setAttribute("aria-label", open ? "Luk menu" : "Åbn menu");

    // Når mobilmenu lukkes, skal dropdown også lukkes
    if (!open) setDropdownOpen(false);
  }

  let dropdownOpenedAutomatically = false;

  function setDropdownOpen(open, automatic = false) {
    if (!servicesDropdown || !dropdownBtn) return;

    if (!open) dropdownOpenedAutomatically = false;
    else if (!servicesDropdown.classList.contains("dropdown-open")) {
      dropdownOpenedAutomatically = automatic;
    }
    servicesDropdown.classList.toggle("dropdown-open", open);
    dropdownBtn.setAttribute("aria-expanded", String(open));
  }

  // Mobilmenu toggle
  if (navToggle && siteNav) {
    navToggle.addEventListener("click", function () {
      const open = !siteNav.classList.contains("open");
      setMobileMenuOpen(open);
    });
  }

  // Dropdown toggle (klik på pilen)
  if (servicesDropdown && dropdownBtn) {
    dropdownBtn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();

      // Hover/focus can open the panel before the first click is delivered.
      // Treat that first activation as an explicit open; a second closes it.
      const open = !servicesDropdown.classList.contains("dropdown-open") ||
        (isDesktop() && dropdownOpenedAutomatically);
      setDropdownOpen(open);
      dropdownOpenedAutomatically = false;
    });
   
    // Desktop: åbn ved hover/fokus
    servicesDropdown.addEventListener("mouseenter", function () {
      if (isDesktop()) setDropdownOpen(true, true);
    });

    servicesDropdown.addEventListener("mouseleave", function () {
      if (isDesktop() && !servicesDropdown.contains(document.activeElement)) {
        setDropdownOpen(false);
      }
    });

    servicesDropdown.addEventListener("focusin", function () {
      if (isDesktop()) setDropdownOpen(true, true);
    });

    servicesDropdown.addEventListener("focusout", function () {
      if (!isDesktop()) return;

      // Luk kun når fokus forlader dropdown'en helt
      setTimeout(() => {
        if (servicesDropdown && !servicesDropdown.contains(document.activeElement)) {
          setDropdownOpen(false);
        }
      }, 0);
    });
  }

  // Klik udenfor: luk dropdown og/eller mobilmenu
  document.addEventListener("click", function (e) {
    const target = e.target;

    // Luk mobilmenu hvis åben og der klikkes udenfor
    if (navToggle && siteNav && siteNav.classList.contains("open")) {
      const clickedInsideNav = siteNav.contains(target);
      const clickedToggle = navToggle.contains(target);

      if (!clickedInsideNav && !clickedToggle) {
        setMobileMenuOpen(false);
        return;
      }
    }

    // Luk dropdown hvis der klikkes udenfor dropdown'en
    if (servicesDropdown && servicesDropdown.classList.contains("dropdown-open")) {
      const clickedInsideDropdown = servicesDropdown.contains(target);
      if (!clickedInsideDropdown) setDropdownOpen(false);
    }
  });

  // ESC: luk alt (dropdown først)
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;

    if (servicesDropdown && servicesDropdown.classList.contains("dropdown-open")) {
      if (servicesDropdown.contains(document.activeElement)) dropdownBtn.focus();
      setDropdownOpen(false);
    }

    if (siteNav && siteNav.classList.contains("open")) {
      if (siteNav.contains(document.activeElement)) navToggle.focus();
      setMobileMenuOpen(false);
    }
  });

  // Klik på undermenu-link: luk dropdown (og mobilmenu på mobil)
  if (dropdownMenu) {
    dropdownMenu.addEventListener("click", function (e) {
      const a = e.target.closest("a");
      if (!a) return;

      setDropdownOpen(false);

      if (!isDesktop()) {
        setMobileMenuOpen(false);
      }
    });
  }

  // Keep the accessible fallback until the menu handlers are ready.
  document.documentElement.classList.remove("no-js");
  document.documentElement.classList.add("js");
});

document.addEventListener("DOMContentLoaded", () => {
  // Anmeldelser (data)
  const REVIEWS = [
    {
      name: "Laura Aagaard",
      avatar: "images/reviews/laura.avif",
      stars: 5,
      text: "Vi er virkelig glade for Schier rengøring…",
      source: "Google",
      url: "https://share.google/TOX8MqLccJ88ZGPAW"
    },
    {
      name: "zoob77",
      avatar: "images/reviews/zoob.avif",
      stars: 5,
      text: "Intet at udsætte…",
      source: "Google",
      url: "https://share.google/8fw9UN9i1ZvmhguR7"
    },
    {
      name: "Joachim Rehder",
      avatar: "images/reviews/joachim.avif",
      stars: 5,
      text: " ",
      source: "Google",
      url: "https://share.google/SJxXz1nYu3l2ArTK2"
    },
    {
      name: "Hanne Bruhn",
      avatar: "images/reviews/hanneb.avif",
      stars: 5,
      text: "rengøring i top, altid sød og venlig betjening…",
      source: "Google",
      url: "https://share.google/EyA3NZ7IDHXbZSpTA"
    },
    {
      name: "Rene Dissing",
      avatar: "images/reviews/rene.avif",
      stars: 5,
      text: "Bestilte en \"total\" rengøring af mit hus (3 etager)…",
      source: "Google",
      url: "https://share.google/Bn9jRVgWNd77TIrpz"
    },
    {
      name: "Hanne Jørgensen",
      avatar: "images/reviews/hanne.avif",
      stars: 4,
      text: " ",
      source: "Google",
      url: "https://maps.app.goo.gl/owZijKgQfCmGVFgj8"
    },
    {
      name: "Jonas Schnack Krog",
      avatar: "images/reviews/jonas.avif",
      stars: 5,
      text: "God og solid rengøring med god kommunikation…",
      source: "Google",
      url: "https://share.google/2zHZMIzgZwcFuGmT6"
    },
    {
      name: "Tina Katja Lund Andersen",
      avatar: "images/reviews/tina.avif",
      stars: 5,
      text: "Super god oplevelse, både før, under og efter…",
      source: "Trustpilot",
      url: "https://dk.trustpilot.com/reviews/605db2ccf85d75087035fcec"
    },
    {
      name: "Lotte Nielsen",
      avatar: "images/reviews/lotte.avif",
      stars: 5,
      text: "Bestilte en fllytteflytterengøring…",
      source: "Trustpilot",
      url: "https://dk.trustpilot.com/reviews/689f0fc9f2fd65a1267fde75"
    }
  ];

  // Elementer
  const card = document.querySelector("[data-reviews-card]");
  const avatar = document.querySelector("[data-reviews-avatar]");
  const nameEl = document.querySelector("[data-reviews-name]");
  const starsEl = document.querySelector("[data-reviews-stars]");
  const textEl = document.querySelector("[data-reviews-text]");
  const srcEl = document.querySelector("[data-reviews-source]");
  const prevBtn = document.querySelector("[data-reviews-prev]");
  const nextBtn = document.querySelector("[data-reviews-next]");
  const dotsEl = document.querySelector("[data-reviews-dots]");

  if (!card || !avatar || !nameEl || !starsEl || !textEl || !srcEl || !prevBtn || !nextBtn || !dotsEl) return;
  if (!Array.isArray(REVIEWS) || REVIEWS.length === 0) return;

  // State
  let index = 0;
  let timer = null;
  const INTERVAL_MS = 6500;

  function starsString(n) {
    const full = Math.max(0, Math.min(5, Number(n) || 0));
    return "★".repeat(full) + "☆".repeat(5 - full);
  }

  const dotButtons = [];

  function renderDots() {
    // Create controls once: updating a review must not remove the focused button.
    if (!dotButtons.length) {
      dotsEl.innerHTML = "";
      REVIEWS.forEach((_, i) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "reviews__dot";
        b.setAttribute("aria-label", `Gå til anmeldelse ${i + 1}`);
        b.addEventListener("click", () => {
          index = i;
          render();
          restartAuto();
        });
        dotsEl.appendChild(b);
        dotButtons.push(b);
      });
    }
    dotButtons.forEach((button, i) => {
      button.classList.toggle("is-active", i === index);
      button.setAttribute("aria-current", i === index ? "true" : "false");
    });
  }

  function render() {
    const r = REVIEWS[index];

    card.href = r.url || "#";

    avatar.src = resolveAssetPath(r.avatar || "");
    avatar.alt = r.name ? `Billede af ${r.name}` : "Anmelder";

    nameEl.textContent = r.name || "";

    const s = starsString(r.stars);
    starsEl.textContent = s;
    starsEl.setAttribute("aria-label", `${Math.max(0, Math.min(5, Number(r.stars) || 0))} ud af 5 stjerner`);

    const txt = (r.text || "").trim();
    textEl.style.display = "";
    textEl.textContent = txt.length ? txt : "\u00A0";

    srcEl.textContent = r.source ? `Anmeldelse fra: ${r.source}` : "";

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

  // Tastatur (kun når fokus er i reviews)
  const reviewsSection = card.closest(".reviews") || card;
  let pointerInsideReviews = false;

  document.addEventListener("keydown", (e) => {
    const active = document.activeElement;

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

  // Swipe
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

    if (Math.abs(dx) < 40) return;

    if (dx < 0) {
      next();
      restartAuto();
    } else {
      prev();
      restartAuto();
    }
  }, { passive: true });

  // Auto-skift
  function startAuto() {
    stopAuto();
    if (document.hidden || pointerInsideReviews ||
        reviewsSection.contains(document.activeElement)) return;
    timer = setInterval(() => next(), INTERVAL_MS);
  }

  function stopAuto() {
    if (timer) clearInterval(timer);
    timer = null;
  }

  function restartAuto() {
    startAuto();
  }

  reviewsSection.addEventListener("mouseenter", () => {
    pointerInsideReviews = true;
    stopAuto();
  });
  reviewsSection.addEventListener("mouseleave", () => {
    pointerInsideReviews = false;
    startAuto();
  });
  reviewsSection.addEventListener("focusin", stopAuto);
  reviewsSection.addEventListener("focusout", () => {
    // Wait until the browser has moved focus, then recheck the entire section.
    setTimeout(startAuto, 0);
  });

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopAuto();
    else startAuto();
  });

  render();
  startAuto();
});

  (function () {
    const user = "my";
    const domain = "schier";
    const tld = "dk";
    const email = `${user}@${domain}.${tld}`;

    const links = document.querySelectorAll(".email-link");

    links.forEach(function (link) {
      link.href = `mailto:${email}`;
      link.textContent = email;
      link.hidden = false;
      const fallback = link.nextElementSibling;
      if (fallback?.classList.contains("email-fallback")) fallback.hidden = true;
    });
  })();
