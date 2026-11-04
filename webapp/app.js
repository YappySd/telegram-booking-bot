/* Mini App for online booking.
 * Inside Telegram it talks to the bot's HTTP API (authenticated with initData).
 * Opened in a plain browser it switches to a demo mode with generated data. */
(() => {
  "use strict";

  const tg = window.Telegram && window.Telegram.WebApp;
  const inTelegram = Boolean(tg && tg.initData);
  const $ = (sel) => document.querySelector(sel);
  const view = $("#view");

  // ---------------------------------------------------------------- helpers
  const DOW = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];
  const MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const parseISO = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const fmtLong = (s) => { const d = parseISO(s); return `${DOW[d.getDay()]}, ${d.getDate()} ${MONTHS[d.getMonth()]}`; };
  const haptic = (kind) => { try { kind === "ok" ? tg.HapticFeedback.notificationOccurred("success") : tg.HapticFeedback.impactOccurred("light"); } catch (_) {} };

  let toastTimer;
  function toast(message) {
    const el = $("#toast");
    el.textContent = message;
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
  }

  // ------------------------------------------------------------------- theme
  function applyTheme() {
    if (!inTelegram) return;
    const p = tg.themeParams || {};
    const root = document.documentElement;
    root.dataset.tg = "1";
    const set = (name, value) => value && root.style.setProperty(name, value);
    set("--bg", p.bg_color);
    set("--text", p.text_color);
    set("--muted", p.hint_color);
    set("--surface", p.secondary_bg_color || p.section_bg_color);
    root.style.setProperty("--surface2", "color-mix(in srgb, var(--surface) 86%, var(--text))");
    root.style.setProperty("--line", "color-mix(in srgb, var(--text) 10%, transparent)");
  }

  // --------------------------------------------------------------------- API
  const realApi = {
    async call(path, options = {}) {
      const response = await fetch(path, {
        ...options,
        headers: { "Content-Type": "application/json", "X-Telegram-Init-Data": tg.initData },
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw Object.assign(new Error(data.message || "Не удалось выполнить запрос"), { code: data.error });
      return data;
    },
    config: () => fetch("/api/config").then((r) => r.json()),
    days: (service) => realApi.call(`/api/days?service=${encodeURIComponent(service)}`).then((d) => d.days),
    slots: (service, date) => realApi.call(`/api/slots?service=${encodeURIComponent(service)}&date=${date}`).then((d) => d.slots),
    book: (payload) => realApi.call("/api/book", { method: "POST", body: JSON.stringify(payload) }).then((d) => d.booking),
    my: () => realApi.call("/api/my").then((d) => d.bookings),
    cancel: (id) => realApi.call("/api/cancel", { method: "POST", body: JSON.stringify({ id }) }),
  };

  const demoApi = (() => {
    const bookings = [];
    let nextId = 1;
    const wait = (ms = 220) => new Promise((r) => setTimeout(r, ms));
    const hash = (text) => [...text].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);
    const services = [
      { id: "cut", title: "Стрижка", minutes: 60, price: 500, emoji: "✂️" },
      { id: "beard", title: "Борода", minutes: 30, price: 300, emoji: "🧔" },
      { id: "combo", title: "Стрижка + борода", minutes: 90, price: 750, emoji: "💈" },
      { id: "kids", title: "Детская стрижка", minutes: 30, price: 350, emoji: "🧒" },
    ];
    const daySlots = (service, date) => {
      const day = parseISO(date);
      if (day.getDay() === 0) return [];
      const out = [];
      const last = day.getDay() === 6 ? 15.5 : 18.5;
      for (let h = 10; h <= last; h += 0.5) {
        if (h >= 13 && h < 14) continue;
        const label = `${String(Math.floor(h)).padStart(2, "0")}:${h % 1 ? "30" : "00"}`;
        const taken = hash(`${service}${date}${label}`) % 3 === 0;
        const mine = bookings.some((b) => b.date === date && b.time === label);
        const now = new Date();
        const past = iso(now) === date && h <= now.getHours() + 1 + now.getMinutes() / 60;
        if (!taken && !mine && !past) out.push(label);
      }
      return out;
    };
    return {
      async config() { await wait(); return { name: "Demo Studio", currency: "₴", services }; },
      async days(service) {
        await wait();
        const result = [];
        for (let i = 0; i < 14; i++) {
          const d = new Date(); d.setDate(d.getDate() + i);
          if (daySlots(service, iso(d)).length) result.push(iso(d));
        }
        return result;
      },
      async slots(service, date) { await wait(); return daySlots(service, date); },
      async book(p) {
        await wait(400);
        const service = services.find((s) => s.id === p.service);
        const booking = { id: nextId++, service: service.title, date: p.date, time: p.time, minutes: service.minutes };
        bookings.push(booking);
        return booking;
      },
      async my() { await wait(); return [...bookings].sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time)); },
      async cancel(id) { await wait(); const i = bookings.findIndex((b) => b.id === id); if (i >= 0) bookings.splice(i, 1); return { ok: true }; },
    };
  })();

  const api = inTelegram ? realApi : demoApi;

  // ------------------------------------------------------------------- state
  const state = {
    tab: "book",
    step: "service", // service -> time -> confirm -> done
    config: null,
    service: null,
    days: [],
    day: null,
    slots: null,
    time: null,
    name: (tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.first_name) || "",
    phone: "",
    my: null,
    done: null,
    busy: false,
    req: 0,
  };

  // --------------------------------------------------------------------- CTA
  let ctaAction = null;
  function setCta(text, action, { disabled = false, info = "" } = {}) {
    $("#cta").hidden = false;
    const button = $("#cta-btn");
    button.textContent = text;
    button.disabled = disabled || state.busy;
    $("#cta-info").textContent = info;
    ctaAction = action;
  }
  const hideCta = () => { $("#cta").hidden = true; ctaAction = null; };
  $("#cta-btn").addEventListener("click", () => ctaAction && ctaAction());

  // -------------------------------------------------------------- navigation
  function goBack() {
    if (state.step === "confirm") state.step = "time";
    else if (state.step === "time") { state.step = "service"; state.time = null; }
    haptic();
    render();
  }
  $("#back").addEventListener("click", goBack);
  if (inTelegram) tg.BackButton.onClick(goBack);

  document.querySelectorAll(".tabs button").forEach((button) =>
    button.addEventListener("click", () => {
      state.tab = button.dataset.tab;
      haptic();
      if (state.tab === "my") loadMy();
      render();
    })
  );

  // ------------------------------------------------------------------ screens
  const price = (n) => `${n} ${state.config.currency}`;

  function renderService() {
    hideCta();
    const cards = state.config.services.map((s) => `
      <button class="service${state.service && state.service.id === s.id ? " on" : ""}" data-id="${esc(s.id)}">
        <span class="ico">${esc(s.emoji)}</span>
        <span class="info"><span class="name">${esc(s.title)}</span><div class="meta">${s.minutes} мин</div></span>
        <span class="price">${price(s.price)}</span>
      </button>`).join("");
    view.innerHTML = `<div class="screen"><h2>Выберите услугу</h2>${cards}</div>`;
    view.querySelectorAll(".service").forEach((el) =>
      el.addEventListener("click", () => {
        state.service = state.config.services.find((s) => s.id === el.dataset.id);
        state.step = "time";
        state.day = null; state.time = null; state.slots = null; state.days = [];
        haptic();
        loadDays();
        render();
      })
    );
  }

  async function loadDays() {
    const token = ++state.req;
    try {
      const days = await api.days(state.service.id);
      if (token !== state.req) return;
      state.days = days;
      state.day = days[0] || null;
      state.slots = null;
      render();
      if (state.day) loadSlots();
    } catch (error) { toast(error.message); }
  }

  async function loadSlots() {
    const token = ++state.req;
    state.slots = null;
    try {
      const slots = await api.slots(state.service.id, state.day);
      if (token !== state.req) return;
      state.slots = slots;
      render();
    } catch (error) { toast(error.message); }
  }

  function renderTime() {
    const scroll = (view.querySelector(".days") || {}).scrollLeft || 0;
    let html = `<div class="screen"><h2>${esc(state.service.emoji)} ${esc(state.service.title)} · ${state.service.minutes} мин</h2>`;
    if (!state.days.length) {
      html += state.slots === null && !state.day
        ? `<div class="skeleton" style="height:78px"></div>`
        : `<div class="empty">Свободных дат пока нет.<br>Загляните позже.</div>`;
    } else {
      html += `<div class="days">${state.days.map((d) => {
        const date = parseISO(d);
        return `<button class="day${d === state.day ? " on" : ""}" data-day="${d}"><small>${DOW[date.getDay()]}</small><b>${date.getDate()}</b></button>`;
      }).join("")}</div><h2>Время</h2>`;
      if (state.slots === null) html += `<div class="slots">${'<div class="skeleton"></div>'.repeat(8)}</div>`;
      else if (!state.slots.length) html += `<div class="empty">На этот день всё занято.</div>`;
      else html += `<div class="slots">${state.slots.map((t) => `<button class="slot${t === state.time ? " on" : ""}" data-time="${t}">${t}</button>`).join("")}</div>`;
    }
    html += "</div>";
    view.innerHTML = html;
    const days = view.querySelector(".days");
    if (days) days.scrollLeft = scroll;

    view.querySelectorAll(".day").forEach((el) =>
      el.addEventListener("click", () => { state.day = el.dataset.day; state.time = null; haptic(); loadSlots(); render(); })
    );
    view.querySelectorAll(".slot").forEach((el) =>
      el.addEventListener("click", () => { state.time = el.dataset.time; haptic(); render(); })
    );

    if (state.time) setCta("Продолжить", () => { state.step = "confirm"; haptic(); render(); }, { info: `${fmtLong(state.day)} · ${state.time}` });
    else setCta("Выберите время", null, { disabled: true });
  }

  function summaryRows(rows) {
    return `<div class="summary">${rows.map(([k, v]) => `<div class="row"><span>${k}</span><b>${esc(v)}</b></div>`).join("")}</div>`;
  }

  function renderConfirm() {
    const s = state.service;
    view.innerHTML = `<div class="screen"><h2>Проверьте запись</h2>
      ${summaryRows([["Услуга", s.title], ["Дата", fmtLong(state.day)], ["Время", state.time], ["Длительность", `${s.minutes} мин`], ["Стоимость", price(s.price)]])}
      <h2>Ваши данные</h2>
      <label><span>Имя</span><input id="name" autocomplete="name" maxlength="60" value="${esc(state.name)}" placeholder="Как к вам обращаться"></label>
      <label><span>Телефон (необязательно)</span><input id="phone" inputmode="tel" autocomplete="tel" maxlength="20" value="${esc(state.phone)}" placeholder="+380 …"></label>
      <p class="hint">Телефон увидит только мастер. Напоминание придёт в этот чат.</p></div>`;
    $("#name").addEventListener("input", (e) => { state.name = e.target.value; });
    $("#phone").addEventListener("input", (e) => { state.phone = e.target.value.replace(/[^0-9+()\-\s]/g, ""); e.target.value = state.phone; });
    setCta(state.busy ? "Записываем…" : "Записаться", submit, { info: `К оплате на месте: ${price(s.price)}` });
  }

  async function submit() {
    if (state.busy) return;
    state.busy = true; render();
    try {
      state.done = await api.book({ service: state.service.id, date: state.day, time: state.time, name: state.name.trim(), phone: state.phone.trim() });
      state.step = "done"; haptic("ok");
    } catch (error) {
      toast(error.message);
      if (error.code === "slot_taken" || error.code === "slot_unavailable") { state.step = "time"; state.time = null; loadSlots(); }
    } finally { state.busy = false; render(); }
  }

  function renderDone() {
    const b = state.done;
    view.innerHTML = `<div class="screen done">
      <div class="check"><svg viewBox="0 0 44 44"><path d="M11 23l8 8 15-17"/></svg></div>
      <h2>Вы записаны</h2><p>Напомню за день и за пару часов до визита.</p>
      ${summaryRows([["Услуга", b.service], ["Дата", fmtLong(b.date)], ["Время", b.time]])}</div>`;
    setCta(inTelegram ? "Готово" : "Записаться ещё", () => {
      if (inTelegram) return tg.close();
      Object.assign(state, { step: "service", service: null, day: null, time: null, done: null });
      render();
    });
  }

  async function loadMy() {
    state.my = null;
    try { state.my = await api.my(); } catch (error) { toast(error.message); state.my = []; }
    if (state.tab === "my") render();
  }

  function renderMy() {
    hideCta();
    if (state.my === null) { view.innerHTML = `<div class="screen"><div class="skeleton" style="height:70px"></div></div>`; return; }
    if (!state.my.length) { view.innerHTML = `<div class="screen"><div class="empty">Предстоящих записей нет.</div></div>`; return; }
    view.innerHTML = `<div class="screen"><h2>Предстоящие записи</h2>${state.my.map((b) => `
      <div class="ticket"><div class="when"><b>${esc(b.service)}</b><span>${fmtLong(b.date)}, ${b.time}</span></div>
      <button class="ghost" data-id="${b.id}">Отменить</button></div>`).join("")}</div>`;
    view.querySelectorAll(".ghost").forEach((el) =>
      el.addEventListener("click", () => {
        const run = async (yes) => {
          if (!yes) return;
          try { await api.cancel(Number(el.dataset.id)); haptic("ok"); toast("Запись отменена"); } catch (error) { toast(error.message); }
          loadMy();
        };
        if (inTelegram) tg.showConfirm("Отменить запись?", run); else run(window.confirm("Отменить запись?"));
      })
    );
  }

  // ------------------------------------------------------------------ render
  function render() {
    document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === state.tab));
    const canGoBack = state.tab === "book" && (state.step === "time" || state.step === "confirm");
    $("#back").hidden = !canGoBack;
    if (inTelegram) canGoBack ? tg.BackButton.show() : tg.BackButton.hide();
    if (state.tab === "my") return renderMy();
    ({ service: renderService, time: renderTime, confirm: renderConfirm, done: renderDone })[state.step]();
  }

  // -------------------------------------------------------------------- init
  async function init() {
    if (tg) { tg.ready(); tg.expand(); }
    applyTheme();
    $("#demo").hidden = inTelegram;
    try {
      state.config = await api.config();
    } catch (_) {
      view.innerHTML = `<div class="empty">Не удалось загрузить данные. Откройте запись ещё раз.</div>`;
      return;
    }
    $("#biz").textContent = state.config.name;
    $("#subtitle").textContent = "Онлайн-запись";
    document.title = state.config.name;
    render();
  }
  init();
})();
