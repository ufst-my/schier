const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.resolve(__dirname, "..");
const source = fs.readFileSync(path.join(root, "js/script.js"), "utf8");

function page({ desktop = true, pathname = "/ydelser/kontorrengoring/" } = {}) {
  let document;
  const intervals = new Map(), timeouts = [], ready = [];
  let sequence = 0;
  function element(name, className = "") {
    const listeners = {}, attributes = {};
    let classes = new Set(className.split(/\s+/).filter(Boolean));
    const el = {
      name, listeners, attributes, children: [], parent: null, style: {}, hidden: false,
      addEventListener(type, fn) { (listeners[type] ||= []).push(fn); },
      appendChild(child) { child.parent = this; this.children.push(child); },
      contains(child) { return child === this || this.children.some(c => c.contains(child)); },
      setAttribute(key, value) { attributes[key] = String(value); },
      getAttribute(key) { return attributes[key] ?? null; },
      hasAttribute(key) { return Object.hasOwn(attributes, key); },
      removeAttribute(key) { delete attributes[key]; },
      closest(selector) {
        const cls = selector.slice(1);
        for (let item = this; item; item = item.parent) {
          if (item.classList.contains(cls)) return item;
        }
        return null;
      },
      querySelector(selector) {
        const cls = selector.slice(1);
        const visit = node => {
          for (const child of node.children) {
            if (child.classList.contains(cls)) return child;
            const found = visit(child); if (found) return found;
          }
          return null;
        };
        return visit(this);
      },
      emit(type, event = {}, bubble = false) {
        const e = Object.assign({ target: this, preventDefault() {}, stopPropagation() {} }, event);
        for (const fn of listeners[type] || []) fn(e);
        if (bubble && this.parent) this.parent.emit(type, e, true);
      },
      focus() {
        const previous = document.activeElement;
        if (previous === this) return;
        document.activeElement = this;
        if (previous) previous.emit("focusout", { relatedTarget: this }, true);
        this.emit("focusin", { relatedTarget: previous }, true);
      },
    };
    el.classList = {
      contains(cls) { return classes.has(cls); },
      add(cls) { classes.add(cls); },
      remove(cls) { classes.delete(cls); },
      toggle(cls, enabled = !classes.has(cls)) {
        enabled ? classes.add(cls) : classes.delete(cls); return enabled;
      },
    };
    Object.defineProperty(el, "className", {
      get() { return [...classes].join(" "); },
      set(value) { classes = new Set(value.split(/\s+/).filter(Boolean)); },
    });
    Object.defineProperty(el, "innerHTML", {
      set() {
        if (this.contains(document.activeElement)) document.activeElement = body;
        this.children = [];
      },
      get() { return ""; },
    });
    return el;
  }
  const body = element("body"), html = element("html", "no-js");
  const nav = element("nav", "site-nav"), navToggle = element("nav-toggle", "nav-toggle");
  const dropdown = element("services", "has-dropdown");
  const dropdownBtn = element("dropdown-btn", "dropdown-toggle");
  const parentLink = element("services-link", "dropdown-link");
  const submenu = element("submenu", "dropdown-menu"), serviceLink = element("service-link");
  nav.appendChild(dropdown); dropdown.appendChild(parentLink);
  dropdown.appendChild(dropdownBtn); dropdown.appendChild(submenu); submenu.appendChild(serviceLink);
  parentLink.setAttribute("href", "../"); serviceLink.setAttribute("href", "./");
  const contactLink = element("contact-link"); contactLink.setAttribute("href", "../../kontakt/");
  const section = element("reviews", "reviews");
  const reviews = Object.fromEntries(["card","avatar","name","stars","text","source","prev","next","dots"]
    .map(name => [name, element(name)]));
  for (const el of Object.values(reviews)) section.appendChild(el);
  const email = element("email", "email-link"), fallback = element("fallback", "email-fallback");
  email.hidden = true; email.nextElementSibling = fallback;
  const documentListeners = {};
  document = {
    currentScript: { src: "https://preview.invalid/js/script.js" },
    baseURI: "https://preview.invalid" + pathname,
    documentElement: html, activeElement: body, hidden: false,
    querySelector(selector) {
      if (selector === ".nav-toggle") return navToggle;
      if (selector === ".site-nav") return nav;
      if (selector === ".site-nav .has-dropdown") return dropdown;
      const name = selector.match(/^\[data-reviews-(.+)\]$/)?.[1];
      return reviews[name] || null;
    },
    querySelectorAll(selector) {
      if (selector === ".email-link") return [email];
      if (selector === ".site-nav a[href]") return [parentLink, serviceLink, contactLink];
      return [];
    },
    createElement(tag) { return element(tag); },
    addEventListener(type, fn) {
      if (type === "DOMContentLoaded") ready.push(fn);
      else (documentListeners[type] ||= []).push(fn);
    },
  };
  const context = {
    document, URL,
    window: {
      location: { pathname, href: "https://preview.invalid" + pathname },
      matchMedia() { return { matches: desktop }; },
    },
    setInterval(fn) { const id = ++sequence; intervals.set(id, fn); return id; },
    clearInterval(id) { intervals.delete(id); },
    setTimeout(fn) { timeouts.push(fn); },
  };
  vm.runInNewContext(source, context);
  for (const init of ready) init();
  return {
    document, html, body, nav, navToggle, dropdown, dropdownBtn, submenu, serviceLink,
    parentLink, contactLink, section, reviews, email, fallback, intervals,
    flush() { while (timeouts.length) timeouts.shift()(); },
    event(type, data = {}) {
      const e = Object.assign({ key: "", target: body, preventDefault() {} }, data);
      for (const fn of documentListeners[type] || []) fn(e);
    },
  };
}

test("desktop Escape closes the dropdown and returns focus to its button", () => {
  const p = page();
  p.serviceLink.focus();
  assert.equal(p.dropdownBtn.getAttribute("aria-expanded"), "true");
  p.event("keydown", { key: "Escape" }); p.flush();
  assert.equal(p.document.activeElement, p.dropdownBtn);
  assert.equal(p.dropdownBtn.getAttribute("aria-expanded"), "false");
  assert.equal(p.dropdown.classList.contains("dropdown-open"), false);
  const css = fs.readFileSync(path.join(root, "css/style.css"), "utf8");
  assert.match(css, /\.no-js \.site-nav \.has-dropdown:focus-within/);
  assert.doesNotMatch(css, /(?:^|\n)\s*\.site-nav \.has-dropdown:(?:hover|focus-within)/);
});

test("mobile Escape closes the navigation and preserves a visible focus target", () => {
  const p = page({ desktop: false });
  p.navToggle.emit("click");
  assert.equal(p.nav.classList.contains("open"), true);
  p.dropdownBtn.focus(); p.dropdownBtn.emit("click");
  p.serviceLink.focus();
  p.event("keydown", { key: "Escape" }); p.flush();
  assert.equal(p.nav.classList.contains("open"), false);
  assert.equal(p.document.activeElement, p.navToggle);
  assert.equal(p.navToggle.getAttribute("aria-expanded"), "false");
});

test("menu enhancement is enabled after initialization and identifies the current service", () => {
  const p = page();
  assert.equal(p.html.classList.contains("no-js"), false);
  assert.equal(p.html.classList.contains("js"), true);
  assert.equal(p.serviceLink.getAttribute("aria-current"), "page");
  assert.equal(p.parentLink.getAttribute("aria-current"), "true");
  assert.equal(p.contactLink.getAttribute("aria-current"), null);
});

test("review navigation and returning to the tab do not restart autoplay while focused", () => {
  const p = page();
  assert.equal(p.intervals.size, 1);
  p.reviews.card.focus();
  assert.equal(p.intervals.size, 0);
  p.event("keydown", { key: "ArrowRight" });
  assert.equal(p.intervals.size, 0);
  p.document.hidden = true; p.event("visibilitychange");
  p.document.hidden = false; p.event("visibilitychange");
  assert.equal(p.intervals.size, 0);
  p.body.focus(); p.flush();
  assert.equal(p.intervals.size, 1);
});

test("the whole review section pauses autoplay, including previous/next controls", () => {
  const p = page();
  p.section.emit("mouseenter"); p.reviews.next.emit("click");
  assert.equal(p.intervals.size, 0);
  p.reviews.prev.focus(); p.section.emit("mouseleave");
  assert.equal(p.intervals.size, 0);
  p.body.focus(); p.flush();
  assert.equal(p.intervals.size, 1);
});

test("dot buttons keep their identity and keyboard focus when selected", () => {
  const p = page(), oldButtons = [...p.reviews.dots.children], dot = oldButtons[2];
  dot.focus(); dot.emit("click");
  assert.equal(p.document.activeElement, dot);
  assert.equal(p.reviews.dots.children[2], dot);
  assert.deepEqual(p.reviews.dots.children, oldButtons);
  assert.equal(dot.getAttribute("aria-current"), "true");
  assert.equal(oldButtons[0].getAttribute("aria-current"), "false");
  assert.equal(p.intervals.size, 0);
});

test("email is assembled by JavaScript and only then replaces the phone fallback", () => {
  const p = page();
  assert.equal(p.email.hidden, false);
  assert.equal(p.fallback.hidden, true);
  assert.equal(p.email.textContent, ["my", "schier", "dk"].slice(0, 2).join("@") + ".dk");
  assert.equal(p.email.href, "mailto:" + p.email.textContent);
});
