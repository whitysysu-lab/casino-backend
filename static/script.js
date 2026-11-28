const API_URL = "";
const tg = window.Telegram ? window.Telegram.WebApp : null;
if (tg) {
  tg.ready();
  tg.expand();
  try {
    tg.setHeaderColor("#070a12");
    tg.setBackgroundColor("#070a12");
    if (tg.BackButton) {
      tg.BackButton.onClick(() => switchTab("lobby"));
    }
  } catch {}
}

const GAMES = [
  { id: "crash", icon: "🚀", name: "Краш", desc: "Живой полёт и кэшаут", cat: "top", badge: "LIVE" },
  { id: "mines", icon: "💣", name: "Мины", desc: "Авто-ход • показ бомб", cat: "top", badge: "TOP" },
  { id: "plinko", icon: "⚪", name: "Плинко", desc: "Падающие шарики до 22x", cat: "top", badge: "NEW" },
  { id: "roulette", icon: "🎡", name: "Рулетка", desc: "Европейская 0–36 • 34x", cat: "table", badge: "0–36" },
  { id: "slots", icon: "🍒", name: "Слоты", desc: "3 барабана до 20x", cat: "top" },
  { id: "tower", icon: "🏰", name: "Башня", desc: "8 этажей вверх", cat: "arcade", badge: "NEW" },
  { id: "wheel", icon: "🎯", name: "Колесо Фортуны", desc: "12 секторов до 3x", cat: "arcade" },
  { id: "blackjack", icon: "🂡", name: "Блэкджек 21", desc: "Обыграй дилера", cat: "table", badge: "NEW" },
  { id: "dice", icon: "🎲", name: "Кости", desc: "Шанс 5–90%", cat: "arcade" },
  { id: "coinflip", icon: "🪙", name: "Монетка", desc: "3D бросок • 1.90x", cat: "arcade" },
  { id: "hilo", icon: "🃏", name: "Карты Hi-Lo", desc: "Выше или ниже с %", cat: "table" },
  { id: "limbo", icon: "⚡", name: "Лимбо", desc: "Цель до 1000x", cat: "top", badge: "NEW" },
  { id: "keno", icon: "🎱", name: "Кено", desc: "Угадай числа до 250x", cat: "arcade", badge: "NEW" },
  { id: "cases", icon: "🎁", name: "Кейсы", desc: "Выбей до 10x", cat: "top", badge: "NEW" },
  { id: "baccarat", icon: "💎", name: "Баккара", desc: "Игрок / Банкир / Ничья", cat: "table", badge: "NEW" },
  { id: "thimbles", icon: "🥤", name: "Напёрстки", desc: "Найди шарик • 2.8x", cat: "arcade", badge: "NEW" },
  { id: "rps", icon: "✊", name: "КНБ", desc: "Камень-Ножницы-Бумага", cat: "arcade", badge: "NEW" },
  { id: "penalty", icon: "⚽", name: "Пенальти", desc: "Забей гол вратарю", cat: "arcade", badge: "NEW" },
  { id: "scratch", icon: "🎫", name: "Скретч-карта", desc: "Сотри 3 одинаковых", cat: "arcade", badge: "NEW" },
  { id: "dice7", icon: "🎯", name: "2 Кубика", desc: "Больше / Меньше 7", cat: "table", badge: "NEW" }
];

const WHEEL_SECTORS = [0, 1.5, 0, 2, 0.5, 0, 1.2, 0, 2.5, 0, 0.5, 3];
const WHEEL_COLORS = ['#1e293b','#2563eb','#1e293b','#7c3aed','#475569','#1e293b','#10b981','#1e293b','#0284c7','#1e293b','#475569','#d97706'];
const ROUL_ORDER = [0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8,23,10,5,24,16,33,1,20,14,31,9,22,18,29,7,28,12,35,3,26];
const RED_NUMS = new Set([1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]);
const PLINKO_BUCKETS = {
  low: [4.0, 1.8, 1.1, 0.85, 0.6, 0.85, 1.1, 1.8, 4.0],
  medium: [10.0, 3.0, 1.4, 0.6, 0.35, 0.6, 1.4, 3.0, 10.0],
  high: [22.0, 4.5, 1.3, 0.3, 0.2, 0.3, 1.3, 4.5, 22.0]
};
const CASE_PRICES = { bronze: 1, silver: 5, gold: 20, royal: 50 };
const CASE_ITEMS = [
  { label: "0.2x", mult: 0.2, weight: 400, rarity: "common", icon: "🪙" },
  { label: "0.5x", mult: 0.5, weight: 260, rarity: "common", icon: "💵" },
  { label: "1.0x", mult: 1.0, weight: 150, rarity: "uncommon", icon: "💰" },
  { label: "1.5x", mult: 1.5, weight: 90, rarity: "rare", icon: "💍" },
  { label: "2.5x", mult: 2.5, weight: 55, rarity: "epic", icon: "💎" },
  { label: "5.0x", mult: 5.0, weight: 35, rarity: "legendary", icon: "👑" },
  { label: "10.0x", mult: 10.0, weight: 10, rarity: "mythic", icon: "🏆" }
];
const KENO_PAY = {
  1:{1:2.85}, 2:{1:0.5,2:7.4}, 3:{2:2.5,3:16.5}, 4:{2:1.5,3:4.5,4:25},
  5:{2:0.65,3:2.6,4:11.5,5:48}, 6:{2:0.25,3:1.75,4:5.8,5:23,6:90},
  7:{3:1.2,4:3.4,5:12.5,6:50,7:160}, 8:{3:0.85,4:2.2,5:6.5,6:24,7:80,8:250}
};
const WD_STATUS_RU = { pending: "Ожидает", approved: "Выплачено", rejected: "Отклонено" };

function loadJSON(key, fallback) {
  try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; } catch { return fallback; }
}
function saveJSON(key, val) {
  try { localStorage.setItem(key, JSON.stringify(val)); } catch {}
}

let state = {
  isDemo: false, demoBalance: 10000.00, realBalance: 0.00,
  userId: null, username: "Игрок", gamesPlayed: 0, totalWon: 0,
  limits: { max_bet: 100, max_win: 1000 },
  withdrawals: [], isAdmin: false, busy: false,
  currentTab: "lobby", currentGame: null, currentCat: "all",
  pendingBalance: null,
  activeMines: null, demoMines: null,
  activeCrash: null, demoCrash: null,
  activeTower: null, demoTower: null,
  activeBj: null, demoBj: null,
  hiloCard: 7,
  demoHiloCard: Math.floor(Math.random() * 11) + 3,
  wheelRotation: 0, coinAngle: 0,
  kenoPicks: [], scratchState: null,
  soundOn: loadJSON("tc_sound", true),
  favorites: loadJSON("tc_favs", []),
  recentGames: loadJSON("tc_recent", []),
  gameHistory: {},
  sessionBets: loadJSON("tc_session_bets", []),
  adminUsersCache: []
};

// ==================== ЗВУКОВЫЕ ЭФФЕКТЫ (Web Audio API) ====================
let audioCtx = null;
function getAudioCtx() {
  if (!audioCtx) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (Ctx) audioCtx = new Ctx();
  }
  if (audioCtx && audioCtx.state === "suspended") audioCtx.resume().catch(() => {});
  return audioCtx;
}

function playSFX(kind) {
  if (!state.soundOn) return;
  try {
    const ctx = getAudioCtx();
    if (!ctx) return;
    const now = ctx.currentTime;
    const beep = (freq, dur, type = "sine", vol = 0.08, delay = 0) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(freq, now + delay);
      gain.gain.setValueAtTime(vol, now + delay);
      gain.gain.exponentialRampToValueAtTime(0.001, now + delay + dur);
      osc.connect(gain); gain.connect(ctx.destination);
      osc.start(now + delay); osc.stop(now + delay + dur);
    };
    if (kind === "tap") beep(520, 0.05, "triangle", 0.06);
    else if (kind === "tick") beep(740, 0.035, "sine", 0.045);
    else if (kind === "win") {
      beep(523.25, 0.11, "triangle", 0.09, 0);
      beep(659.25, 0.11, "triangle", 0.09, 0.09);
      beep(783.99, 0.18, "triangle", 0.10, 0.18);
    } else if (kind === "bigwin") {
      [523.25, 659.25, 783.99, 1046.5].forEach((f, idx) => beep(f, 0.16, "triangle", 0.11, idx * 0.08));
    } else if (kind === "lose") {
      beep(260, 0.13, "sawtooth", 0.06, 0);
      beep(190, 0.18, "sawtooth", 0.06, 0.1);
    } else if (kind === "boom") {
      beep(140, 0.25, "sawtooth", 0.11, 0);
      beep(80, 0.30, "square", 0.09, 0.06);
    }
  } catch {}
}

function toggleSound() {
  state.soundOn = !state.soundOn;
  saveJSON("tc_sound", state.soundOn);
  updateSoundUI();
  if (state.soundOn) playSFX("tap");
  showToast(state.soundOn ? "Звук включён" : "Звук отключён", "info");
}

function updateSoundUI() {
  const btn = document.getElementById("soundToggle");
  if (!btn) return;
  btn.textContent = state.soundOn ? "🔊" : "🔇";
  btn.classList.toggle("muted", !state.soundOn);
}

// ==================== ТОСТЫ И 18+ ====================
function showToast(msg, type = "info") {
  const box = document.getElementById("toastContainer");
  if (!box) return;
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = msg;
  box.appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity 0.25s"; setTimeout(() => el.remove(), 260); }, 2800);
}

function initAgeGate() {
  if (!loadJSON("tc_age_ok", false)) {
    document.getElementById("ageModal")?.classList.add("open");
  }
}
function acceptAgeGate() {
  saveJSON("tc_age_ok", true);
  document.getElementById("ageModal")?.classList.remove("open");
  playSFX("tap");
}

// ==================== РЕЕСТР ТАЙМЕРОВ И ЖИЗНЕННЫЙ ЦИКЛ ====================
let screenToken = 0;
const timers = { timeouts: new Set(), intervals: new Set(), rafs: new Set() };

function safeTimeout(fn, ms) {
  const tok = screenToken;
  const id = setTimeout(() => {
    timers.timeouts.delete(id);
    if (tok === screenToken) fn();
  }, ms);
  timers.timeouts.add(id);
  return id;
}

function safeInterval(fn, ms) {
  const tok = screenToken;
  const id = setInterval(() => {
    if (tok !== screenToken) { clearInterval(id); timers.intervals.delete(id); return; }
    fn();
  }, ms);
  timers.intervals.add(id);
  return id;
}

function safeRAF(fn) {
  const tok = screenToken;
  const id = requestAnimationFrame((now) => {
    timers.rafs.delete(id);
    if (tok === screenToken) fn(now);
  });
  timers.rafs.add(id);
  return id;
}

function cleanupLoops() {
  screenToken += 1;
  timers.timeouts.forEach(id => clearTimeout(id));
  timers.timeouts.clear();
  timers.intervals.forEach(id => clearInterval(id));
  timers.intervals.clear();
  timers.rafs.forEach(id => cancelAnimationFrame(id));
  timers.rafs.clear();

  if (crashRuntime) {
    crashRuntime.flying = false;
    crashRuntime = null;
  }
  crashStarting = false;
  flushPlinkoOnExit();

  if (state.scratchState && state.scratchState.balance !== undefined) {
    const s = state.scratchState;
    state.scratchState = null;
    applyBalance(s.balance);
    recordSessionBet("scratch", s.bet, s.win, s.win_symbol ? `3x ${s.win_symbol} (${s.multiplier}x)` : "Билет завершён");
  }
  if (state.pendingBalance !== null) {
    applyBalance(state.pendingBalance);
    state.pendingBalance = null;
  }
  state.busy = false;
}

function haptic(type) {
  try {
    if (!tg || !tg.HapticFeedback) return;
    if (type === "win") tg.HapticFeedback.notificationOccurred("success");
    else if (type === "lose") tg.HapticFeedback.notificationOccurred("error");
    else tg.HapticFeedback.impactOccurred("light");
  } catch {}
}

function escHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, m => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[m]));
}

function parseCardRank(card) {
  const m = String(card || "").match(/^(10|[2-9JQKA])/);
  return m ? m[1] : "0";
}

function parseApiError(data, status) {
  if (!data) return `Ошибка сервера (${status})`;
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail.map(e => {
      if (typeof e === "string") return e;
      const field = Array.isArray(e.loc) ? e.loc[e.loc.length - 1] : "";
      return field ? `${field}: ${e.msg || "неверное значение"}` : (e.msg || "Ошибка данных");
    }).join("; ");
  }
  if (typeof data.detail === "object") return JSON.stringify(data.detail);
  return `Ошибка запроса (${status})`;
}

async function apiFetch(path, options = {}) {
  const initData = tg && tg.initData ? tg.initData : "";
  const res = await fetch(API_URL + path, {
    ...options,
    headers: { "Content-Type": "application/json", "X-Telegram-Init-Data": initData, ...(options.headers || {}) }
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(parseApiError(data, res.status));
  return data;
}

function getBal() { return state.isDemo ? state.demoBalance : state.realBalance; }

function applyBalance(newBal) {
  const val = Math.max(0, Math.round(Number(newBal) * 100) / 100);
  if (state.isDemo) state.demoBalance = val;
  else state.realBalance = val;
  updateBalanceUI(true);
}

function deductBetNow(bet) {
  const prev = getBal();
  applyBalance(prev - bet);
  return prev;
}

function updateBalanceUI(bump = false) {
  const balStr = getBal().toFixed(2);
  document.getElementById("balanceDisplay").textContent = balStr;
  document.querySelectorAll(".bet-bal-live").forEach(el => { el.textContent = `Баланс: $${balStr}`; });
  const pill = document.getElementById("demoToggle");
  pill.textContent = state.isDemo ? "ДЕМО ВКЛ" : "ДЕМО ВЫКЛ";
  pill.classList.toggle("active", state.isDemo);
  const mt = document.getElementById("gameModeTag");
  if (mt) {
    mt.textContent = state.isDemo ? "ДЕМО" : "РЕАЛ";
    mt.classList.toggle("demo", state.isDemo);
  }
  if (bump) {
    const b = document.getElementById("balanceBox");
    b.classList.add("bump");
    setTimeout(() => b.classList.remove("bump"), 180);
  }
}

function toggleDemo() {
  if (state.busy || plinkoState.balls.length > 0 || plinkoState.requesting) {
    showToast("Дождитесь окончания текущего раунда", "warn");
    return;
  }
  state.isDemo = !state.isDemo;
  if (state.isDemo && state.demoBalance < 10) state.demoBalance = 10000.00;
  updateBalanceUI(true);
  haptic("tap"); playSFX("tap");
  showToast(state.isDemo ? "Включён демо-режим ($10 000)" : "Включён реальный режим", state.isDemo ? "warn" : "success");
  if (state.currentTab === "game" && state.currentGame) {
    openGame(state.currentGame);
  } else {
    renderGamesGrid();
  }
}

function showBanner(elId, type, text) {
  const el = document.getElementById(elId);
  if (!el) return;
  el.className = "result-banner " + type;
  el.textContent = text;
}

function recordSessionBet(gameId, bet, win, extra = "") {
  const meta = GAMES.find(g => g.id === gameId);
  const entry = {
    ts: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    game: meta ? `${meta.icon} ${meta.name}` : gameId,
    bet: Number(bet),
    win: Number(win),
    demo: state.isDemo,
    extra
  };
  state.sessionBets.unshift(entry);
  if (state.sessionBets.length > 30) state.sessionBets.pop();
  saveJSON("tc_session_bets", state.sessionBets);
}

function renderSessionHistory() {
  const box = document.getElementById("sessionHistoryList");
  if (!box) return;
  if (!state.sessionBets.length) {
    box.innerHTML = '<div style="color:var(--muted);font-size:12.5px;">Ставок в этой сессии пока нет</div>';
    return;
  }
  box.innerHTML = state.sessionBets.map(item => {
    const diff = Math.round((item.win - item.bet) * 100) / 100;
    const col = diff > 0 ? "#34d399" : (diff < 0 ? "#f87171" : "#fbbf24");
    const sign = diff > 0 ? "+" : "";
    return `
      <div class="row-item">
        <div>
          <strong>${escHtml(item.game)}</strong>
          <span style="font-size:10px;color:var(--muted);margin-left:5px;">${item.demo ? "ДЕМО" : "РЕАЛ"} • ${escHtml(item.ts)}</span>
          <div style="font-size:11px;color:var(--muted);">Ставка $${item.bet.toFixed(2)}${item.extra ? " • " + escHtml(item.extra) : ""}</div>
        </div>
        <div style="color:${col};font-weight:900;">${sign}$${diff.toFixed(2)}</div>
      </div>
    `;
  }).join("");
}

function clearSessionHistory() {
  state.sessionBets = [];
  saveJSON("tc_session_bets", []);
  renderSessionHistory();
  showToast("История сессии очищена", "info");
}

function pushGameHistory(gameId, label, cls = "") {
  if (!state.gameHistory[gameId]) state.gameHistory[gameId] = [];
  state.gameHistory[gameId].unshift({ label, cls });
  if (state.gameHistory[gameId].length > 12) state.gameHistory[gameId].pop();
  renderGameHistory(gameId);
}

function renderGameHistory(gameId) {
  const strip = document.getElementById("gameHistStrip");
  if (!strip) return;
  const list = state.gameHistory[gameId] || [];
  if (!list.length) {
    strip.innerHTML = '<span style="font-size:10.5px;color:var(--muted);">История раундов появится здесь</span>';
    return;
  }
  strip.innerHTML = list.map(h => `<span class="hist-pill ${h.cls}">${escHtml(h.label)}</span>`).join("");
}

function showOutcome(elId, bet, win, extra = "", gameId = state.currentGame) {
  const profit = Math.round((win - bet) * 100) / 100;
  const prefix = extra ? extra + " • " : "";
  if (gameId) recordSessionBet(gameId, bet, win, extra);
  if (win > bet) {
    haptic("win");
    playSFX(win >= bet * 4 ? "bigwin" : "win");
    showBanner(elId, "win", `${prefix}Выигрыш $${win.toFixed(2)} (+$${profit.toFixed(2)})`);
  } else if (win === bet && bet > 0) {
    haptic("tap"); playSFX("tap");
    showBanner(elId, "warn", `${prefix}Возврат ставки $${win.toFixed(2)}`);
  } else if (win > 0 && win < bet) {
    haptic("lose"); playSFX("lose");
    showBanner(elId, "warn", `${prefix}Частичный возврат $${win.toFixed(2)} (-$${(bet - win).toFixed(2)})`);
  } else {
    haptic("lose"); playSFX("lose");
    showBanner(elId, "lose", `${prefix}Проигрыш -$${bet.toFixed(2)}`);
  }
}

function hasActiveSession(gameId) {
  if (gameId === "mines") return !!(state.isDemo ? state.demoMines : state.activeMines);
  if (gameId === "crash") return !!(state.isDemo ? state.demoCrash : state.activeCrash);
  if (gameId === "tower") return !!(state.isDemo ? state.demoTower : state.activeTower);
  if (gameId === "blackjack") return !!(state.isDemo ? state.demoBj : state.activeBj);
  return false;
}

function toggleFavorite(e, gameId) {
  e.stopPropagation();
  const idx = state.favorites.indexOf(gameId);
  if (idx >= 0) {
    state.favorites.splice(idx, 1);
    showToast("Убрано из избранного", "info");
  } else {
    state.favorites.push(gameId);
    showToast("Добавлено в избранное", "warn");
  }
  saveJSON("tc_favs", state.favorites);
  haptic("tap"); playSFX("tap");
  renderGamesGrid();
}

function renderGamesGrid() {
  const cat = state.currentCat || "all";
  const q = (document.getElementById("gameSearch")?.value || "").trim().toLowerCase();
  let list = GAMES;
  if (cat === "fav") list = GAMES.filter(g => state.favorites.includes(g.id));
  else if (cat === "recent") list = state.recentGames.map(id => GAMES.find(g => g.id === id)).filter(Boolean);
  else if (cat !== "all") list = GAMES.filter(g => g.cat === cat);

  if (q) {
    list = list.filter(g => g.name.toLowerCase().includes(q) || g.desc.toLowerCase().includes(q) || g.id.includes(q));
  }

  const grid = document.getElementById("gamesGrid");
  if (!list.length) {
    grid.innerHTML = `<div class="panel" style="grid-column:1/-1;text-align:center;color:var(--muted);font-size:13px;">Игры не найдены</div>`;
    return;
  }

  grid.innerHTML = list.map(g => {
    const isFav = state.favorites.includes(g.id);
    const isActive = hasActiveSession(g.id);
    const badgeHtml = isActive
      ? `<div class="game-badge live-session">▶ ИГРА</div>`
      : (g.badge ? `<div class="game-badge ${g.badge==='LIVE'||g.badge==='TOP'?'hot':''}">${g.badge}</div>` : "");
    return `
      <div class="game-card ${isActive ? 'has-active' : ''}" onclick="openGame('${g.id}')">
        <button class="fav-btn ${isFav ? 'is-fav' : ''}" onclick="toggleFavorite(event, '${g.id}')" title="В избранное">${isFav ? '★' : '☆'}</button>
        ${badgeHtml}
        <div class="game-icon">${g.icon}</div>
        <div class="game-name">${g.name}</div>
        <div class="game-desc">${g.desc}</div>
      </div>
    `;
  }).join("");
}

function filterGames(cat, btn) {
  state.currentCat = cat;
  document.querySelectorAll(".cat-btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  renderGamesGrid();
}

async function loadProfile() {
  try {
    const data = await apiFetch("/api/me");
    state.userId = data.user_id;
    state.username = data.username || "Игрок";
    state.realBalance = data.balance;
    state.gamesPlayed = data.games_played;
    state.totalWon = data.total_won;
    if (data.hilo_card) state.hiloCard = data.hilo_card;
    if (data.limits) state.limits = data.limits;
    state.activeMines = data.active_mines;
    state.activeCrash = data.active_crash;
    state.activeTower = data.active_tower;
    state.activeBj = data.active_blackjack;
    state.withdrawals = data.withdrawals || [];
    state.isAdmin = !!data.is_admin;

    document.getElementById("welcomeTitle").textContent = `Привет, ${state.username}!`;
    document.getElementById("welcomeAva").textContent = state.username.charAt(0).toUpperCase();
    document.getElementById("profName").textContent = state.username;
    document.getElementById("profId").textContent = state.userId;
    document.getElementById("profBal").textContent = Number(state.realBalance).toFixed(2);
    document.getElementById("profGames").textContent = state.gamesPlayed;
    document.getElementById("profWon").textContent = Number(state.totalWon).toFixed(2);
    renderWithdrawals();
    renderSessionHistory();
    renderGamesGrid();

    if (state.isAdmin) {
      document.getElementById("adminPanel").style.display = "block";
      if (!document.getElementById("adminTargetId").value) {
        document.getElementById("adminTargetId").value = state.userId;
      }
      loadAdminOverview();
    }
    updateBalanceUI();
  } catch {
    state.isDemo = true;
    document.getElementById("welcomeTitle").textContent = "Привет, Гость (Демо)!";
    document.getElementById("profName").textContent = "Гость (Демо)";
    renderWithdrawals();
    renderSessionHistory();
    updateBalanceUI();
  }
}

function renderWithdrawals() {
  const box = document.getElementById("withdrawList");
  if (!state.withdrawals.length) {
    box.innerHTML = '<div style="color:var(--muted);font-size:13px;">Заявок пока нет</div>';
    return;
  }
  box.innerHTML = state.withdrawals.map(w => `
    <div class="row-item">
      <div><strong>Заявка #${w.id}</strong> • $${Number(w.amount).toFixed(2)}</div>
      <span class="badge ${w.status}">${WD_STATUS_RU[w.status] || w.status}</span>
    </div>
  `).join("");
}

async function loadLeaderboard() {
  const box = document.getElementById("leadersList");
  box.innerHTML = '<div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div>';
  try {
    const data = await apiFetch("/api/leaderboard");
    if (!data.leaders || !data.leaders.length) {
      box.innerHTML = '<div style="color:var(--muted);font-size:13px;">Пока нет сыгранных партий</div>';
      return;
    }
    const medals = ["🥇", "🥈", "🥉"];
    box.innerHTML = data.leaders.map((u, i) => `
      <div class="row-item">
        <div>
          <strong>${medals[i] || (i + 1) + "."} ${escHtml(u.username)}</strong>
          <div style="font-size:11px;color:var(--muted);">Игр: ${u.games_played}</div>
        </div>
        <div style="color:var(--gold);font-weight:900;">$${Number(u.total_won).toFixed(2)}</div>
      </div>
    `).join("");
  } catch (e) {
    box.innerHTML = `<div style="color:var(--muted);font-size:13px;">${escHtml(e.message)}</div>`;
  }
}

function renderAdminUsers() {
  const uBox = document.getElementById("adminUsersList");
  if (!uBox) return;
  const q = (document.getElementById("adminUserSearch")?.value || "").trim().toLowerCase();
  const filtered = state.adminUsersCache.filter(u =>
    !q || String(u.user_id).includes(q) || String(u.username || "").toLowerCase().includes(q)
  );
  if (!filtered.length) {
    uBox.innerHTML = '<div style="color:var(--muted);font-size:12.5px;">Совпадений нет</div>';
    return;
  }
  uBox.innerHTML = filtered.map((u, idx) => `
    <div class="row-item" style="cursor:pointer;" onclick="pickAdminUser(${Number(u.user_id)})">
      <div>
        <strong>${idx + 1}. ${escHtml(u.username)}</strong>
        <div style="color:var(--muted);font-size:11px;">ID: ${u.user_id} • Игр: ${u.games_played}</div>
      </div>
      <div style="color:#34d399;font-weight:900;">$${Number(u.balance).toFixed(2)}</div>
    </div>
  `).join("");
}

function pickAdminUser(uid) {
  const user = state.adminUsersCache.find(u => Number(u.user_id) === Number(uid));
  const name = user ? (user.username || "Игрок") : "Игрок";
  document.getElementById("adminTargetId").value = uid;
  showToast(`Выбран игрок ${name} (${uid})`, "info");
}

async function loadAdminOverview() {
  if (!state.isAdmin) return;
  try {
    const data = await apiFetch("/api/admin/overview");
    const s = data.stats;
    document.getElementById("admUsersCount").textContent = s.users_count;
    document.getElementById("admTotalBal").textContent = "$" + Number(s.total_balance).toFixed(0);
    document.getElementById("admTotalGames").textContent = s.total_games;
    document.getElementById("admWagered").textContent = "$" + Number(s.total_wagered).toFixed(2);
    const pEl = document.getElementById("admProfit");
    pEl.textContent = (s.house_profit >= 0 ? "+" : "") + "$" + Number(s.house_profit).toFixed(2);
    pEl.className = "stat-val " + (s.house_profit >= 0 ? "green" : "red");
    document.getElementById("admStars").textContent = `${s.total_stars} ⭐ ($${Number(s.total_deposited).toFixed(2)})`;
    document.getElementById("admWithdrawn").textContent = `$${Number(s.total_withdrawn).toFixed(2)} / $${Number(s.pending_withdraw_sum).toFixed(2)}`;

    const pBox = document.getElementById("adminPendingList");
    if (!data.pending_withdrawals.length) {
      pBox.innerHTML = '<div style="color:var(--muted);font-size:13px;">Нет ожидающих заявок</div>';
    } else {
      pBox.innerHTML = data.pending_withdrawals.map(w => `
        <div class="row-item">
          <div>
            <strong>#${w.id} • $${Number(w.amount).toFixed(2)}</strong>
            <div style="font-size:11px;color:var(--muted);">${escHtml(w.username)} (${w.user_id})<br>${escHtml(w.details)}</div>
          </div>
          <div style="display:flex;gap:5px;">
            <button class="mini-btn ok" onclick="handleAdminWithdraw(${w.id}, 'approve')">✓</button>
            <button class="mini-btn no" onclick="handleAdminWithdraw(${w.id}, 'reject')">✕</button>
          </div>
        </div>
      `).join("");
    }

    state.adminUsersCache = data.users || [];
    renderAdminUsers();
  } catch {}
}

function switchTab(tab) {
  cleanupLoops();
  state.currentTab = tab;
  if (tab !== "game") state.currentGame = null;
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
  document.getElementById(`view-${tab}`).classList.add("active");
  const nav = document.getElementById(`nav-${tab}`);
  if (nav) nav.classList.add("active");

  try {
    if (tg && tg.BackButton) {
      if (tab === "game") tg.BackButton.show();
      else tg.BackButton.hide();
    }
  } catch {}

  if (tab === "lobby") {
    syncDemoCrashIfEnded();
    renderGamesGrid();
    if (!state.isDemo && state.activeCrash) {
      apiFetch("/api/play/crash/state").then(st => {
        if (st.status === "crashed" || st.status === "cashed_out" || st.status === "idle") {
          state.activeCrash = null;
          if (st.balance !== undefined) applyBalance(st.balance);
          if (state.currentTab === "lobby") renderGamesGrid();
        }
      }).catch(() => {});
    }
  }
  if (tab === "profile" || tab === "wallet") { loadProfile(); renderSessionHistory(); }
  if (tab === "leaders") loadLeaderboard();
}

function betControlsHTML(btnText, fnName, onBetInput = "checkCapHint()") {
  return `
    <div class="bet-row">
      <div class="bet-label">
        <span>Ставка ($) • макс $${state.limits.max_bet}</span>
        <span class="bet-bal-live">Баланс: $${getBal().toFixed(2)}</span>
      </div>
      <div class="bet-input-wrap">
        <input type="number" id="betInput" value="1" min="0.1" max="${state.limits.max_bet}" step="0.5" oninput="${onBetInput}" />
        <button class="chip-btn" onclick="multBet(0.5);${onBetInput}">½</button>
        <button class="chip-btn" onclick="multBet(2);${onBetInput}">2x</button>
        <button class="chip-btn" onclick="setBetMax();${onBetInput}">MAX</button>
      </div>
      <div id="capWarn" class="cap-warn"></div>
    </div>
    <button id="playBtn" class="action-btn" onclick="${fnName}()">${btnText}</button>
    <div id="gameResult" class="result-banner"></div>
  `;
}

function updateCapWarning(mult) {
  const el = document.getElementById("capWarn");
  const inp = document.getElementById("betInput");
  if (!el || !inp) return;
  const b = parseFloat(inp.value) || 0;
  if (b > 0 && mult > 0 && b * mult > state.limits.max_win) {
    el.textContent = `⚠️ Макс. выигрыш ограничен лимитом $${state.limits.max_win} (сейчас расчёт $${(b * mult).toFixed(0)})`;
    el.classList.add("show");
  } else {
    el.classList.remove("show");
  }
}

function checkCapHint() {
  const g = state.currentGame;
  if (g === "dice") {
    const t = parseInt(document.getElementById("diceSlider")?.value || 50);
    const chance = window._diceDir === "under" ? (t - 1) : (100 - t);
    updateCapWarning(93 / Math.max(1, chance));
  } else if (g === "limbo") {
    const target = parseFloat(document.getElementById("limboTarget")?.value || 2);
    updateCapWarning(target);
  } else if (g === "plinko") {
    const vals = PLINKO_BUCKETS[window._plinkoRisk || "medium"];
    const cnt = getPlinkoBallsCount();
    const betVal = parseFloat(document.getElementById("betInput")?.value) || 0;
    const el = document.getElementById("capWarn");
    if (el) {
      if (betVal * cnt > state.limits.max_bet) {
        el.textContent = `⚠️ Сумма (${cnt} × $${betVal.toFixed(2)} = $${(betVal * cnt).toFixed(2)}) превышает макс. ставку $${state.limits.max_bet}`;
        el.classList.add("show");
      } else {
        updateCapWarning(Math.max(...vals));
      }
    }
    updatePlinkoBtnLabel();
  } else if (g === "roulette") {
    const t = window._roulType;
    const m = (t === "green" || t === "number") ? 34 : (t.startsWith("dozen") ? 2.85 : 1.95);
    updateCapWarning(m);
  } else if (g === "slots") {
    updateCapWarning(20);
  } else if (g === "keno") {
    const map = KENO_PAY[state.kenoPicks.length] || {};
    const maxM = Math.max(0, ...Object.values(map));
    updateCapWarning(maxM);
  } else {
    updateCapWarning(0);
  }
}

function multBet(k) {
  const inp = document.getElementById("betInput");
  if (!inp || inp.disabled) return;
  const val = Math.min(state.limits.max_bet, Math.max(0.1, Math.round((parseFloat(inp.value || 1) * k) * 100) / 100));
  inp.value = val;
}
function setBetMax() {
  const inp = document.getElementById("betInput");
  if (!inp || inp.disabled) return;
  inp.value = Math.min(state.limits.max_bet, Math.max(0.1, Math.floor(getBal() * 100) / 100));
}

function getBet() {
  const b = parseFloat(document.getElementById("betInput").value);
  if (isNaN(b) || b <= 0) throw new Error("Введите корректную ставку");
  if (b > state.limits.max_bet) throw new Error(`Максимальная ставка — $${state.limits.max_bet}`);
  if (b > getBal()) throw new Error("Недостаточно средств на балансе");
  return Math.round(b * 100) / 100;
}

function setBtnDisabled(id, dis) {
  const el = document.getElementById(id);
  if (el) el.disabled = dis;
}

function capDemoWin(w) {
  return Math.min(Math.round(w * 100) / 100, state.limits.max_win);
}

// ==================== ОТКРЫТИЕ ВСЕХ 20 ИГР ====================
function openGame(game) {
  cleanupLoops();
  state.currentTab = "game";
  state.currentGame = game;

  state.recentGames = [game, ...state.recentGames.filter(id => id !== game)].slice(0, 8);
  saveJSON("tc_recent", state.recentGames);

  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.getElementById("view-game").classList.add("active");
  try { if (tg && tg.BackButton) tg.BackButton.show(); } catch {}

  const box = document.getElementById("gameContainer");
  const meta = GAMES.find(g => g.id === game);
  document.getElementById("activeGameTitle").textContent = meta ? `${meta.icon} ${meta.name}` : game;
  updateBalanceUI();

  const histHtml = `<div class="history-strip" id="gameHistStrip"></div>`;

  if (game === "slots") {
    box.innerHTML = `
      ${histHtml}
      <div class="slot-machine">
        <div class="reels">
          <div class="reel-window" id="rw0"><span id="r0">🍒</span></div>
          <div class="reel-window" id="rw1"><span id="r1">💎</span></div>
          <div class="reel-window" id="rw2"><span id="r2">7️⃣</span></div>
        </div>
        <div class="paytable"><span>7️⃣7️⃣7️⃣ <b>20x</b></span><span>💎💎💎 <b>12x</b></span><span>3 в ряд <b>6x</b></span><span>Пара <b>1.55x</b></span></div>
      </div>
      ${betControlsHTML("Крутить слоты", "playSlots")}
    `;
    renderGameHistory("slots");
  } else if (game === "mines") {
    let cells = "";
    for (let i = 0; i < 25; i++) cells += `<div class="mine-cell" id="mc-${i}" onclick="clickMine(${i})"></div>`;
    box.innerHTML = `
      <div class="bet-label"><span>Количество мин (1–24)</span><span id="minesMultLabel" style="color:var(--gold);">Множитель: 1.00x</span></div>
      <div class="bet-input-wrap" style="margin-bottom:6px;">
        <input type="number" id="minesCount" value="3" min="1" max="24" />
        <button class="chip-btn" onclick="setMinesPreset(1)">1</button>
        <button class="chip-btn" onclick="setMinesPreset(3)">3</button>
        <button class="chip-btn" onclick="setMinesPreset(5)">5</button>
        <button class="chip-btn" onclick="setMinesPreset(10)">10</button>
        <button class="chip-btn" onclick="setMinesPreset(20)">20</button>
      </div>
      <div class="mines-grid">${cells}</div>
      <div class="bet-row">
        <div class="bet-label"><span>Ставка ($) • макс $${state.limits.max_bet}</span><span class="bet-bal-live">Баланс: $${getBal().toFixed(2)}</span></div>
        <div class="bet-input-wrap">
          <input type="number" id="betInput" value="1" min="0.1" max="${state.limits.max_bet}" step="0.5" />
          <button class="chip-btn" onclick="multBet(0.5)">½</button>
          <button class="chip-btn" onclick="multBet(2)">2x</button>
          <button class="chip-btn" onclick="setBetMax()">MAX</button>
        </div>
      </div>
      <div class="btn-row">
        <button id="minesMainBtn" class="action-btn" onclick="startOrCashoutMines()">Начать игру</button>
        <button id="minesAutoBtn" class="action-btn primary" style="display:none;max-width:44%;" onclick="clickMine(-1)">🎲 Авто</button>
      </div>
      <div id="gameResult" class="result-banner"></div>
    `;
    restoreMinesUI();
  } else if (game === "dice") {
    window._diceDir = "under";
    box.innerHTML = `
      ${histHtml}
      <div class="choice-group">
        <button class="choice-btn selected" id="diceUnder" onclick="setDiceDir('under')">⬇️ Меньше</button>
        <button class="choice-btn" id="diceOver" onclick="setDiceDir('over')">⬆️ Больше</button>
      </div>
      <div class="dice-track-wrap">
        <div class="dice-pin" id="dicePin">50</div>
        <div class="dice-track">
          <div class="dice-fill" id="diceFillWin" style="background:var(--success);"></div>
          <div class="dice-fill" id="diceFillLose" style="background:var(--danger);"></div>
        </div>
      </div>
      <div class="bet-label"><span>Цель: <b id="diceTargetVal">50</b></span><span id="diceInfo" style="color:var(--gold);">Шанс: 49% • 1.90x</span></div>
      <input type="range" id="diceSlider" min="6" max="91" value="50" style="width:100%;" oninput="updateDiceUI()" />
      ${betControlsHTML("Бросить кубик", "playDice")}
    `;
    renderGameHistory("dice");
    updateDiceUI();
  } else if (game === "coinflip") {
    window._coinSide = "heads";
    box.innerHTML = `
      ${histHtml}
      <div class="coin-stage">
        <div class="coin-3d" id="coin3d">
          <div class="coin-face coin-front">🦅<small>Орёл</small></div>
          <div class="coin-face coin-back">👑<small>Решка</small></div>
        </div>
      </div>
      <div class="choice-group">
        <button class="choice-btn selected" id="cfHeads" onclick="setCoin('heads')">🦅 Орёл (1.90x)</button>
        <button class="choice-btn" id="cfTails" onclick="setCoin('tails')">👑 Решка (1.90x)</button>
      </div>
      ${betControlsHTML("Подбросить монету", "playCoinflip")}
    `;
    renderGameHistory("coinflip");
  } else if (game === "crash") {
    box.innerHTML = `
      ${histHtml}
      <div class="crash-canvas-wrap">
        <canvas id="crashCanvas" width="480" height="185"></canvas>
        <div class="crash-overlay">
          <div class="crash-mult" id="crashMult" style="color:var(--gold);">1.00x</div>
          <div class="crash-sub" id="crashSub">Готов к запуску</div>
        </div>
      </div>
      <div class="bet-label"><span>Авто-вывод (0 = ручной вывод)</span><span>Лимит: $${state.limits.max_win}</span></div>
      <input type="number" id="crashAuto" value="0" min="0" max="1000" step="0.1" placeholder="0 (отключён)" />
      <div class="bet-row">
        <div class="bet-label"><span>Ставка ($)</span><span class="bet-bal-live">Баланс: $${getBal().toFixed(2)}</span></div>
        <div class="bet-input-wrap">
          <input type="number" id="betInput" value="1" min="0.1" max="${state.limits.max_bet}" step="0.5" />
          <button class="chip-btn" onclick="multBet(0.5)">½</button>
          <button class="chip-btn" onclick="multBet(2)">2x</button>
          <button class="chip-btn" onclick="setBetMax()">MAX</button>
        </div>
      </div>
      <button id="crashBtn" class="action-btn" onclick="crashAction()">🚀 Запустить ракету</button>
      <div id="gameResult" class="result-banner"></div>
    `;
    renderGameHistory("crash");
    drawCrashGraph(1.0, false);
    restoreCrashUI();
  } else if (game === "roulette") {
    window._roulType = "red";
    box.innerHTML = `
      ${histHtml}
      <div class="roul-viewport">
        <div class="roul-pointer"></div>
        <div class="roul-strip" id="roulStrip"></div>
      </div>
      <div class="choice-group">
        <button class="choice-btn red selected" id="rt-red" onclick="setRoulType('red')">🔴 Красн. 1.95x</button>
        <button class="choice-btn green" id="rt-green" onclick="setRoulType('green')">🟢 Зеро 34x</button>
        <button class="choice-btn" id="rt-black" onclick="setRoulType('black')">⚫ Чёрн. 1.95x</button>
      </div>
      <div class="choice-group">
        <button class="choice-btn" id="rt-even" onclick="setRoulType('even')">Чёт 1.95x</button>
        <button class="choice-btn" id="rt-odd" onclick="setRoulType('odd')">Нечет 1.95x</button>
        <button class="choice-btn" id="rt-low" onclick="setRoulType('low')">1–18</button>
        <button class="choice-btn" id="rt-high" onclick="setRoulType('high')">19–36</button>
      </div>
      <div class="choice-group">
        <button class="choice-btn" id="rt-dozen1" onclick="setRoulType('dozen1')">1–12 (2.85x)</button>
        <button class="choice-btn" id="rt-dozen2" onclick="setRoulType('dozen2')">13–24 (2.85x)</button>
        <button class="choice-btn" id="rt-dozen3" onclick="setRoulType('dozen3')">25–36 (2.85x)</button>
        <button class="choice-btn" id="rt-number" onclick="setRoulType('number')">Число 34x</button>
      </div>
      <div id="roulNumWrap" style="display:none;margin-top:8px;">
        <div class="bet-label"><span>Точное число (0–36)</span></div>
        <input type="number" id="roulNumber" value="7" min="0" max="36" />
      </div>
      ${betControlsHTML("Крутить рулетку", "playRoulette")}
    `;
    renderGameHistory("roulette");
    initRouletteStrip();
  } else if (game === "wheel") {
    box.innerHTML = `
      ${histHtml}
      <div class="wheel-wrap">
        <div class="wheel-pointer">▼</div>
        <div class="wheel-center">T</div>
        <canvas id="wheelCanvas" width="266" height="266"></canvas>
      </div>
      ${betControlsHTML("Крутить колесо", "playWheel")}
    `;
    renderGameHistory("wheel");
    let blink = false;
    drawWheel(blink);
    safeInterval(() => { blink = !blink; drawWheel(blink); }, 450);
  } else if (game === "hilo") {
    window._hiloDir = "high";
    const curCard = state.isDemo ? state.demoHiloCard : state.hiloCard;
    box.innerHTML = `
      <div style="text-align:center;margin:8px 0;">
        <div style="font-size:11px;color:var(--muted);">Текущая карта (равная карта = проигрыш)</div>
        <div id="hiloCardDisplay" style="font-size:52px;font-weight:900;margin:6px 0;">${cardLabel(curCard)}</div>
      </div>
      <div class="choice-group">
        <button class="choice-btn selected" id="hlHigh" onclick="setHilo('high')">⬆️ Выше</button>
        <button class="choice-btn" id="hlLow" onclick="setHilo('low')">⬇️ Ниже</button>
      </div>
      ${betControlsHTML("Открыть карту", "playHilo")}
    `;
    updateHiloButtons();
  } else if (game === "plinko") {
    window._plinkoRisk = window._plinkoRisk || "medium";
    window._plinkoBalls = window._plinkoBalls || 1;
    box.innerHTML = `
      ${histHtml}
      <div class="choice-group">
        <button class="choice-btn ${window._plinkoRisk==='low'?'selected':''}" id="pr-low" onclick="setPlinkoRisk('low')">Низкий (до 4x)</button>
        <button class="choice-btn ${window._plinkoRisk==='medium'?'selected':''}" id="pr-medium" onclick="setPlinkoRisk('medium')">Средний (до 10x)</button>
        <button class="choice-btn ${window._plinkoRisk==='high'?'selected':''}" id="pr-high" onclick="setPlinkoRisk('high')">Высокий (до 22x)</button>
      </div>
      <div class="plinko-wrap">
        <div class="plinko-hud">
          <span class="pill-live" id="plinkoInFlight">⚪ В полёте: 0</span>
          <span id="plinkoLastHit">Добавляй шарики прямо в полёте</span>
        </div>
        <canvas id="plinkoCanvas" width="440" height="240"></canvas>
        <div class="plinko-buckets" id="plinkoBuckets"></div>
      </div>
      <div class="bet-row" style="margin-top:6px;">
        <div class="bet-label"><span>Количество шариков (1–50)</span><span style="color:var(--gold);" id="plinkoTotalCostLbl">Итого: $1.00</span></div>
        <div class="plinko-balls-row">
          <input type="number" id="plinkoBallsInput" value="${window._plinkoBalls}" min="1" max="50" step="1" oninput="onPlinkoBallsInput()" />
          <button class="chip-btn ${window._plinkoBalls===1?'active':''}" id="pb-cnt-1" onclick="setPlinkoBalls(1)">1</button>
          <button class="chip-btn ${window._plinkoBalls===3?'active':''}" id="pb-cnt-3" onclick="setPlinkoBalls(3)">3</button>
          <button class="chip-btn ${window._plinkoBalls===5?'active':''}" id="pb-cnt-5" onclick="setPlinkoBalls(5)">5</button>
          <button class="chip-btn ${window._plinkoBalls===10?'active':''}" id="pb-cnt-10" onclick="setPlinkoBalls(10)">10</button>
          <button class="chip-btn ${window._plinkoBalls===20?'active':''}" id="pb-cnt-20" onclick="setPlinkoBalls(20)">20</button>
        </div>
      </div>
      ${betControlsHTML("⚪ Бросить шарик ($1.00)", "playPlinko", "checkCapHint()")}
    `;
    renderGameHistory("plinko");
    initPlinkoBoard();
    updatePlinkoBtnLabel();
  } else if (game === "tower") {
    window._towerDiff = "medium";
    box.innerHTML = `
      <div class="choice-group" id="towerDiffGroup">
        <button class="choice-btn" id="td-easy" onclick="setTowerDiff('easy')">Легко (4 кол.)</button>
        <button class="choice-btn selected" id="td-medium" onclick="setTowerDiff('medium')">Средне (3 кол.)</button>
        <button class="choice-btn" id="td-hard" onclick="setTowerDiff('hard')">Хард (2 лов.)</button>
      </div>
      <div class="bet-label"><span>Этаж: <b id="towerFloorLbl">0 / 8</b></span><span id="towerMultLbl" style="color:var(--gold);">1.00x</span></div>
      <div class="tower-grid" id="towerGrid"></div>
      <div class="bet-row">
        <div class="bet-label"><span>Ставка ($)</span><span class="bet-bal-live">Баланс: $${getBal().toFixed(2)}</span></div>
        <div class="bet-input-wrap">
          <input type="number" id="betInput" value="1" min="0.1" max="${state.limits.max_bet}" step="0.5" />
          <button class="chip-btn" onclick="multBet(0.5)">½</button>
          <button class="chip-btn" onclick="multBet(2)">2x</button>
          <button class="chip-btn" onclick="setBetMax()">MAX</button>
        </div>
      </div>
      <div class="btn-row">
        <button id="towerMainBtn" class="action-btn" onclick="startOrCashoutTower()">Начать подъём</button>
        <button id="towerAutoBtn" class="action-btn primary" style="display:none;max-width:42%;" onclick="climbTower(-1)">🎲 Авто</button>
      </div>
      <div id="gameResult" class="result-banner"></div>
    `;
    restoreTowerUI();
  } else if (game === "limbo") {
    box.innerHTML = `
      ${histHtml}
      <div style="text-align:center;font-size:46px;font-weight:900;margin:12px 0;color:var(--gold);" id="limboVal">1.00x</div>
      <div class="bet-label"><span>Целевой множитель (1.05x – 1000x)</span><span id="limboChance" style="color:var(--muted);">Шанс: 47.0%</span></div>
      <input type="number" id="limboTarget" value="2.0" min="1.05" max="1000" step="0.1" oninput="updateLimboChance()" />
      ${betControlsHTML("Запустить Лимбо", "playLimbo")}
    `;
    renderGameHistory("limbo");
    updateLimboChance();
  } else if (game === "keno") {
    state.kenoPicks = [3, 7, 13, 19];
    let cells = "";
    for (let i = 1; i <= 25; i++) cells += `<div class="keno-cell" id="kc-${i}" onclick="toggleKeno(${i})">${i}</div>`;
    box.innerHTML = `
      <div class="bet-label">
        <span>Выберите 1–8 чисел (<b id="kenoCount">4</b>/8)</span>
        <div style="display:flex;gap:5px;">
          <button class="chip-btn" style="padding:3px 8px;" onclick="randomKeno()">🎲 Авто</button>
          <button class="chip-btn" style="padding:3px 8px;" onclick="clearKeno()">✕ Сброс</button>
        </div>
      </div>
      <div class="keno-grid">${cells}</div>
      <div class="keno-paybar" id="kenoPaybar"></div>
      ${betControlsHTML("Сыграть в Кено", "playKeno")}
    `;
    renderKenoPicks();
  } else if (game === "cases") {
    window._caseTier = "bronze";
    box.innerHTML = `
      <div class="choice-group">
        <button class="choice-btn selected" id="ct-bronze" onclick="setCaseTier('bronze')">🥉 $1</button>
        <button class="choice-btn" id="ct-silver" onclick="setCaseTier('silver')">🥈 $5</button>
        <button class="choice-btn" id="ct-gold" onclick="setCaseTier('gold')">🥇 $20</button>
        <button class="choice-btn" id="ct-royal" onclick="setCaseTier('royal')">👑 $50</button>
      </div>
      <div class="case-strip-wrap">
        <div class="roul-pointer"></div>
        <div class="roul-strip" id="caseStrip"></div>
      </div>
      <div style="font-size:11px;color:var(--muted);text-align:center;margin-bottom:6px;">Дроп: 0.2x • 0.5x • 1x • 1.5x • 2.5x • 5x • 10x</div>
      <button id="playBtn" class="action-btn" onclick="playCase()">🎁 Открыть кейс ($1)</button>
      <div id="gameResult" class="result-banner"></div>
    `;
    initCaseStrip();
  } else if (game === "blackjack") {
    box.innerHTML = `
      <div style="text-align:center;">
        <div style="font-size:11px;color:var(--muted);">Дилер (<b id="bjDealerScore">0</b>)</div>
        <div class="cards-row" id="bjDealerCards"></div>
        <div style="font-size:11px;color:var(--muted);margin-top:8px;">Ваши карты (<b id="bjPlayerScore">0</b>)</div>
        <div class="cards-row" id="bjPlayerCards"></div>
      </div>
      <div class="bet-row" id="bjBetWrap">
        <div class="bet-label"><span>Ставка ($)</span><span class="bet-bal-live">Баланс: $${getBal().toFixed(2)}</span></div>
        <div class="bet-input-wrap">
          <input type="number" id="betInput" value="1" min="0.1" max="${state.limits.max_bet}" step="0.5" />
          <button class="chip-btn" onclick="multBet(0.5)">½</button>
          <button class="chip-btn" onclick="multBet(2)">2x</button>
          <button class="chip-btn" onclick="setBetMax()">MAX</button>
        </div>
      </div>
      <button id="bjStartBtn" class="action-btn" onclick="bjStart()">Раздать карты</button>
      <div class="btn-row" id="bjActionBtns" style="display:none;">
        <button class="action-btn primary" onclick="bjHit()">➕ Взять</button>
        <button class="action-btn success" onclick="bjStand()">✋ Хватит</button>
      </div>
      <div id="gameResult" class="result-banner"></div>
    `;
    restoreBjUI();
  } else if (game === "baccarat") {
    window._bacChoice = "player";
    box.innerHTML = `
      ${histHtml}
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;text-align:center;margin-bottom:10px;">
        <div class="stat-card"><div style="font-size:11px;color:var(--muted);">Игрок (<b id="bacPScore">0</b>)</div><div class="cards-row" id="bacPCards"></div></div>
        <div class="stat-card"><div style="font-size:11px;color:var(--muted);">Банкир (<b id="bacBScore">0</b>)</div><div class="cards-row" id="bacBCards"></div></div>
      </div>
      <div class="choice-group">
        <button class="choice-btn selected" id="bc-player" onclick="setBac('player')">Игрок 1.95x</button>
        <button class="choice-btn green" id="bc-tie" onclick="setBac('tie')">Ничья 8x</button>
        <button class="choice-btn red" id="bc-banker" onclick="setBac('banker')">Банкир 1.90x</button>
      </div>
      ${betControlsHTML("Раздать Баккара", "playBaccarat")}
    `;
    renderGameHistory("baccarat");
  } else if (game === "thimbles") {
    window._thCup = 1; window._thBalls = 1;
    box.innerHTML = `
      <div class="choice-group">
        <button class="choice-btn selected" id="tb-1" onclick="setThBalls(1)">1 шарик (2.80x)</button>
        <button class="choice-btn" id="tb-2" onclick="setThBalls(2)">2 шарика (1.40x)</button>
      </div>
      <div class="cups-row">
        <button class="cup-btn" id="cup-0" onclick="setThCup(0)">🥤</button>
        <button class="cup-btn selected" id="cup-1" onclick="setThCup(1)">🥤</button>
        <button class="cup-btn" id="cup-2" onclick="setThCup(2)">🥤</button>
      </div>
      ${betControlsHTML("Открыть стакан", "playThimbles")}
    `;
  } else if (game === "rps") {
    window._rpsChoice = "rock";
    box.innerHTML = `
      <div style="display:flex;justify-content:space-around;align-items:center;font-size:44px;margin:14px 0;">
        <div id="rpsYou">✊</div>
        <div style="font-size:16px;font-weight:900;color:var(--muted);">VS</div>
        <div id="rpsBot">❔</div>
      </div>
      <div class="choice-group">
        <button class="choice-btn selected" id="rps-rock" onclick="setRps('rock')">✊ Камень</button>
        <button class="choice-btn" id="rps-scissors" onclick="setRps('scissors')">✌️ Ножницы</button>
        <button class="choice-btn" id="rps-paper" onclick="setRps('paper')">✋ Бумага</button>
      </div>
      ${betControlsHTML("Сыграть (1.85x)", "playRps")}
    `;
  } else if (game === "penalty") {
    window._penZone = 0; window._penDiff = "normal";
    box.innerHTML = `
      <div class="choice-group">
        <button class="choice-btn selected" id="pd-normal" onclick="setPenDiff('normal')">Обычный (1.55x)</button>
        <button class="choice-btn" id="pd-hard" onclick="setPenDiff('hard')">Сложный (2.30x)</button>
      </div>
      <div class="goal-box">
        <div class="goal-zone selected" id="pz-0" onclick="setPenZone(0)">↖️ Верх Л</div>
        <div class="goal-zone" id="pz-2" onclick="setPenZone(2)">⬆️ Центр</div>
        <div class="goal-zone" id="pz-1" onclick="setPenZone(1)">↗️ Верх П</div>
        <div class="goal-zone" id="pz-3" onclick="setPenZone(3)">↙️ Низ Л</div>
        <div style="display:flex;align-items:center;justify-content:center;font-size:28px;" id="penKeeper">🧤</div>
        <div class="goal-zone" id="pz-4" onclick="setPenZone(4)">↘️ Низ П</div>
      </div>
      ${betControlsHTML("Пробить пенальти", "playPenalty")}
    `;
  } else if (game === "scratch") {
    state.scratchState = null;
    let cells = "";
    for (let i = 0; i < 9; i++) cells += `<div class="scratch-cell" id="sc-${i}" onclick="scratchCell(${i})">?</div>`;
    box.innerHTML = `
      <div style="font-size:11.5px;color:var(--muted);text-align:center;">Собери 3 одинаковых символа — до 10x!</div>
      <div class="scratch-grid">${cells}</div>
      <div class="bet-row">
        <div class="bet-label"><span>Цена билета ($)</span><span class="bet-bal-live">Баланс: $${getBal().toFixed(2)}</span></div>
        <div class="bet-input-wrap">
          <input type="number" id="betInput" value="1" min="0.1" max="${state.limits.max_bet}" step="0.5" />
          <button class="chip-btn" onclick="multBet(0.5)">½</button>
          <button class="chip-btn" onclick="multBet(2)">2x</button>
          <button class="chip-btn" onclick="setBetMax()">MAX</button>
        </div>
      </div>
      <div class="btn-row">
        <button id="playBtn" class="action-btn" onclick="buyScratch()">🎫 Купить билет</button>
        <button id="scratchAllBtn" class="action-btn primary" style="display:none;" onclick="scratchAll()">✨ Стереть всё</button>
      </div>
      <div id="gameResult" class="result-banner"></div>
    `;
  } else if (game === "dice7") {
    window._d7Choice = "under";
    box.innerHTML = `
      ${histHtml}
      <div style="display:flex;justify-content:center;gap:18px;font-size:48px;margin:12px 0;">
        <span id="d7a">🎲</span><span id="d7b">🎲</span>
      </div>
      <div style="text-align:center;font-size:14px;font-weight:800;color:var(--gold);margin-bottom:8px;" id="d7Sum">Сумма: —</div>
      <div class="choice-group">
        <button class="choice-btn selected" id="d7-under" onclick="setD7('under')">&lt; 7 (2.20x)</button>
        <button class="choice-btn" id="d7-exact7" onclick="setD7('exact7')">= 7 (5.50x)</button>
        <button class="choice-btn" id="d7-over" onclick="setD7('over')">&gt; 7 (2.20x)</button>
        <button class="choice-btn" id="d7-double" onclick="setD7('double')">Дубль 5.5x</button>
      </div>
      ${betControlsHTML("Бросить 2 кубика", "playDice7")}
    `;
    renderGameHistory("dice7");
  }
  checkCapHint();
}

// ==================== 1. СЛОТЫ ====================
async function playSlots() {
  if (state.busy) return;
  let prev = null;
  try {
    const bet = getBet();
    state.busy = true; setBtnDisabled("playBtn", true);
    prev = deductBetNow(bet); haptic("tap"); playSFX("tap");
    document.getElementById("gameResult").style.display = "none";
    for (let i = 0; i < 3; i++) {
      const w = document.getElementById(`rw${i}`);
      w.classList.remove("win-glow"); w.classList.add("spinning");
    }

    let data;
    if (state.isDemo) {
      const syms = ["🍒", "🍋", "🍇", "🔔", "💎", "7️⃣"];
      const reels = [0,1,2].map(() => syms[Math.floor(Math.random()*syms.length)]);
      let mult = 0;
      if (reels[0]===reels[1] && reels[1]===reels[2]) mult = reels[0]==="7️⃣"?20:(reels[0]==="💎"?12:6);
      else if (reels[0]===reels[1] || reels[1]===reels[2] || reels[0]===reels[2]) mult = 1.55;
      const win = capDemoWin(bet * mult);
      data = { reels, multiplier: mult, win, balance: prev - bet + win };
    } else {
      data = await apiFetch("/api/play/slots", { method: "POST", body: JSON.stringify({ bet }) });
    }

    state.pendingBalance = data.balance;
    const syms = ["🍒", "🍋", "🍇", "🔔", "💎", "7️⃣"];
    const tickId = safeInterval(() => {
      for (let i = 0; i < 3; i++) {
        if (document.getElementById(`rw${i}`)?.classList.contains("spinning")) {
          document.getElementById(`r${i}`).textContent = syms[Math.floor(Math.random()*syms.length)];
        }
      }
    }, 70);

    [420, 760, 1100].forEach((ms, i) => {
      safeTimeout(() => {
        const w = document.getElementById(`rw${i}`);
        if (!w) return;
        w.classList.remove("spinning");
        document.getElementById(`r${i}`).textContent = data.reels[i];
        haptic("tap"); playSFX("tick");
        if (i === 2) {
          clearInterval(tickId); timers.intervals.delete(tickId);
          if (data.win > bet) for (let k = 0; k < 3; k++) document.getElementById(`rw${k}`)?.classList.add("win-glow");
          state.pendingBalance = null;
          applyBalance(data.balance);
          pushGameHistory("slots", data.multiplier ? `${data.multiplier}x` : "0x", data.win > bet ? "win" : "lose");
          showOutcome("gameResult", bet, data.win, data.multiplier ? `${data.multiplier}x` : "", "slots");
          state.busy = false; setBtnDisabled("playBtn", false);
        }
      }, ms);
    });
  } catch (e) {
    if (prev !== null) applyBalance(prev);
    state.pendingBalance = null;
    for (let i = 0; i < 3; i++) document.getElementById(`rw${i}`)?.classList.remove("spinning");
    state.busy = false; setBtnDisabled("playBtn", false);
    showBanner("gameResult", "lose", e.message);
  }
}

// ==================== 2. МИНЫ ====================
function setMinesPreset(n) {
  const inp = document.getElementById("minesCount");
  if (inp && !inp.disabled) inp.value = n;
}

function setMinesControlsLocked(locked) {
  const mc = document.getElementById("minesCount");
  const bi = document.getElementById("betInput");
  if (mc) mc.disabled = locked;
  if (bi) bi.disabled = locked;
  const ab = document.getElementById("minesAutoBtn");
  if (ab) ab.style.display = locked ? "block" : "none";
}

function restoreMinesUI() {
  const m = state.isDemo ? state.demoMines : state.activeMines;
  if (!m) { setMinesControlsLocked(false); return; }
  document.getElementById("minesCount").value = m.mines_count;
  document.getElementById("betInput").value = m.bet;
  setMinesControlsLocked(true);
  (m.revealed || []).forEach(c => {
    const el = document.getElementById(`mc-${c}`);
    if (el) { el.classList.add("safe"); el.textContent = "💎"; }
  });
  document.getElementById("minesMultLabel").textContent = `Множитель: ${(m.multiplier || 1).toFixed(2)}x`;
  const btn = document.getElementById("minesMainBtn");
  btn.textContent = m.potential_win ? `Забрать $${Number(m.potential_win).toFixed(2)}` : "Забрать выигрыш";
  btn.classList.add("success");
}

function revealRemainingBombs(minesArr, explodedCell = -1) {
  (minesArr || []).forEach(m => {
    const c = document.getElementById(`mc-${m}`);
    if (!c || c.classList.contains("safe")) return;
    if (m === explodedCell) { c.classList.add("boom"); c.textContent = "💥"; }
    else { c.classList.add("bomb-reveal"); c.textContent = "💣"; }
  });
}

async function startOrCashoutMines() {
  if (state.busy) return;
  const active = state.isDemo ? state.demoMines : state.activeMines;
  let prev = null;
  try {
    state.busy = true;
    if (active) {
      if (state.isDemo) {
        if (!active.revealed.length) throw new Error("Откройте хотя бы одну клетку");
        const win = capDemoWin(active.bet * active.multiplier);
        revealRemainingBombs(Array.from(active.mineSet));
        applyBalance(state.demoBalance + win);
        showOutcome("gameResult", active.bet, win, `${active.multiplier}x`, "mines");
        state.demoMines = null;
      } else {
        const data = await apiFetch("/api/play/mines/cashout", { method: "POST" });
        revealRemainingBombs(data.mines);
        applyBalance(data.balance);
        showOutcome("gameResult", active.bet, data.win, `${data.multiplier}x`, "mines");
        state.activeMines = null;
      }
      const btn = document.getElementById("minesMainBtn");
      btn.textContent = "Начать игру"; btn.classList.remove("success");
      setMinesControlsLocked(false);
      state.busy = false;
      return;
    }

    const bet = getBet();
    const mines_count = parseInt(document.getElementById("minesCount").value || 3);
    if (mines_count < 1 || mines_count > 24) throw new Error("Мин должно быть от 1 до 24");
    for (let i = 0; i < 25; i++) {
      const el = document.getElementById(`mc-${i}`);
      el.className = "mine-cell"; el.textContent = "";
    }
    prev = deductBetNow(bet); haptic("tap"); playSFX("tap");

    if (state.isDemo) {
      const all = Array.from({length: 25}, (_, i) => i).sort(() => Math.random() - 0.5);
      state.demoMines = { bet, mines_count, multiplier: 1.0, revealed: [], mineSet: new Set(all.slice(0, mines_count)) };
    } else {
      const data = await apiFetch("/api/play/mines/start", { method: "POST", body: JSON.stringify({ bet, mines_count }) });
      applyBalance(data.balance);
      state.activeMines = { bet: data.bet, mines_count: data.mines_count, multiplier: 1.0, revealed: [] };
    }
    setMinesControlsLocked(true);
    document.getElementById("minesMultLabel").textContent = "Множитель: 1.00x";
    const btn = document.getElementById("minesMainBtn");
    btn.textContent = "Забрать выигрыш"; btn.classList.add("success");
    document.getElementById("gameResult").style.display = "none";
  } catch (e) {
    if (prev !== null) applyBalance(prev);
    showBanner("gameResult", "lose", e.message);
  } finally {
    state.busy = false;
  }
}

async function clickMine(cell) {
  const active = state.isDemo ? state.demoMines : state.activeMines;
  if (!active || state.busy) return;
  if (cell >= 0 && document.getElementById(`mc-${cell}`)?.classList.contains("safe")) return;

  state.busy = true;
  try {
    if (state.isDemo) {
      let chosen = cell;
      if (chosen === -1) {
        const unopened = [];
        for (let i = 0; i < 25; i++) if (!active.revealed.includes(i)) unopened.push(i);
        chosen = unopened[Math.floor(Math.random() * unopened.length)];
      }
      const el = document.getElementById(`mc-${chosen}`);
      if (active.mineSet.has(chosen)) {
        revealRemainingBombs(Array.from(active.mineSet), chosen);
        playSFX("boom");
        showOutcome("gameResult", active.bet, 0, "Подрыв на мине", "mines");
        state.demoMines = null;
        document.getElementById("minesMainBtn").textContent = "Начать игру";
        document.getElementById("minesMainBtn").classList.remove("success");
        setMinesControlsLocked(false);
      } else {
        el.classList.add("safe"); el.textContent = "💎"; haptic("tap"); playSFX("tick");
        active.revealed.push(chosen);
        let prob = 1.0;
        for (let i = 0; i < active.revealed.length; i++) prob *= (25 - active.mines_count - i) / (25 - i);
        active.multiplier = Math.max(1.02, Math.round((0.94 / prob) * 100) / 100);
        const pot = capDemoWin(active.bet * active.multiplier);
        active.potential_win = pot;
        if (active.revealed.length === 25 - active.mines_count || pot >= state.limits.max_win) {
          revealRemainingBombs(Array.from(active.mineSet));
          applyBalance(state.demoBalance + pot);
          showOutcome("gameResult", active.bet, pot, `Макс. выигрыш (${active.multiplier}x)`, "mines");
          state.demoMines = null;
          document.getElementById("minesMainBtn").textContent = "Начать игру";
          document.getElementById("minesMainBtn").classList.remove("success");
          setMinesControlsLocked(false);
        } else {
          document.getElementById("minesMultLabel").textContent = `Множитель: ${active.multiplier}x`;
          document.getElementById("minesMainBtn").textContent = `Забрать $${pot.toFixed(2)}`;
        }
      }
      return;
    }

    const data = await apiFetch("/api/play/mines/reveal", { method: "POST", body: JSON.stringify({ cell }) });
    const el = document.getElementById(`mc-${data.cell}`);
    if (data.status === "boom") {
      revealRemainingBombs(data.mines, data.cell);
      playSFX("boom");
      showOutcome("gameResult", active.bet, 0, "Подрыв на мине", "mines");
      state.activeMines = null;
      document.getElementById("minesMainBtn").textContent = "Начать игру";
      document.getElementById("minesMainBtn").classList.remove("success");
      setMinesControlsLocked(false);
    } else if (data.status === "win_all") {
      if (el) { el.classList.add("safe"); el.textContent = "💎"; }
      revealRemainingBombs(data.mines);
      applyBalance(data.balance);
      showOutcome("gameResult", active.bet, data.win, `Победа (${data.multiplier}x)`, "mines");
      state.activeMines = null;
      document.getElementById("minesMainBtn").textContent = "Начать игру";
      document.getElementById("minesMainBtn").classList.remove("success");
      setMinesControlsLocked(false);
    } else {
      if (el) { el.classList.add("safe"); el.textContent = "💎"; }
      haptic("tap"); playSFX("tick");
      state.activeMines.multiplier = data.multiplier;
      state.activeMines.potential_win = data.potential_win;
      state.activeMines.revealed = data.revealed;
      document.getElementById("minesMultLabel").textContent = `Множитель: ${data.multiplier}x`;
      document.getElementById("minesMainBtn").textContent = `Забрать $${Number(data.potential_win).toFixed(2)}`;
    }
  } catch (e) {
    showBanner("gameResult", "lose", e.message);
  } finally {
    state.busy = false;
  }
}

// ==================== 3. КОСТИ (93% RTP) ====================
function setDiceDir(d) {
  window._diceDir = d;
  document.getElementById("diceUnder").classList.toggle("selected", d === "under");
  document.getElementById("diceOver").classList.toggle("selected", d === "over");
  const sl = document.getElementById("diceSlider");
  if (d === "under") { sl.min = 6; sl.max = 91; if (sl.value > 91) sl.value = 91; if (sl.value < 6) sl.value = 6; }
  else { sl.min = 10; sl.max = 95; if (sl.value < 10) sl.value = 10; if (sl.value > 95) sl.value = 95; }
  updateDiceUI();
}

function updateDiceUI() {
  const t = parseInt(document.getElementById("diceSlider").value);
  document.getElementById("diceTargetVal").textContent = t;
  const under = window._diceDir === "under";
  const chance = under ? (t - 1) : (100 - t);
  const mult = (93 / chance).toFixed(2);
  document.getElementById("diceInfo").textContent = `Шанс: ${chance}% • ${mult}x`;
  const fWin = document.getElementById("diceFillWin");
  const fLose = document.getElementById("diceFillLose");
  if (under) {
    fWin.style.left = "0%"; fWin.style.width = `${t}%`;
    fLose.style.left = `${t}%`; fLose.style.width = `${100 - t}%`;
  } else {
    fLose.style.left = "0%"; fLose.style.width = `${t}%`;
    fWin.style.left = `${t}%`; fWin.style.width = `${100 - t}%`;
  }
  checkCapHint();
}

async function playDice() {
  if (state.busy) return;
  let prev = null;
  try {
    const bet = getBet();
    const target = parseInt(document.getElementById("diceSlider").value);
    const direction = window._diceDir;
    state.busy = true; setBtnDisabled("playBtn", true);
    prev = deductBetNow(bet); haptic("tap"); playSFX("tap");

    let data;
    if (state.isDemo) {
      const roll = Math.floor(Math.random() * 100) + 1;
      const chance = direction === "under" ? (target - 1) : (100 - target);
      const mult = Math.round((93 / chance) * 100) / 100;
      const is_win = direction === "under" ? roll < target : roll > target;
      const win = is_win ? capDemoWin(bet * mult) : 0;
      data = { roll, is_win, multiplier: mult, win, balance: prev - bet + win };
    } else {
      data = await apiFetch("/api/play/dice", { method: "POST", body: JSON.stringify({ bet, target, direction }) });
    }

    state.pendingBalance = data.balance;
    const pin = document.getElementById("dicePin");
    pin.style.display = "block";
    pin.className = "dice-pin";
    pin.style.left = "2%";
    pin.textContent = "🎲";
    safeRAF(() => {
      pin.style.left = `${Math.max(4, Math.min(96, data.roll))}%`;
      pin.textContent = data.roll;
    });

    safeTimeout(() => {
      pin.className = "dice-pin " + (data.is_win ? "win" : "lose");
      state.pendingBalance = null;
      applyBalance(data.balance);
      pushGameHistory("dice", String(data.roll), data.is_win ? "win" : "lose");
      showOutcome("gameResult", bet, data.win, `Выпало ${data.roll}`, "dice");
      state.busy = false; setBtnDisabled("playBtn", false);
    }, 580);
  } catch (e) {
    if (prev !== null) applyBalance(prev);
    state.pendingBalance = null;
    state.busy = false; setBtnDisabled("playBtn", false);
    showBanner("gameResult", "lose", e.message);
  }
}

// ==================== 4. МОНЕТКА (3D) ====================
function setCoin(s) {
  window._coinSide = s;
  document.getElementById("cfHeads").classList.toggle("selected", s === "heads");
  document.getElementById("cfTails").classList.toggle("selected", s === "tails");
}

async function playCoinflip() {
  if (state.busy) return;
  let prev = null;
  try {
    const bet = getBet();
    const choice = window._coinSide;
    state.busy = true; setBtnDisabled("playBtn", true);
    prev = deductBetNow(bet); haptic("tap"); playSFX("tap");

    let data;
    if (state.isDemo) {
      const result = Math.random() < 0.5 ? "heads" : "tails";
      const win = result === choice ? capDemoWin(bet * 1.90) : 0;
      data = { result, win, balance: prev - bet + win };
    } else {
      data = await apiFetch("/api/play/coinflip", { method: "POST", body: JSON.stringify({ bet, choice }) });
    }

    state.pendingBalance = data.balance;
    const wantMod = data.result === "heads" ? 0 : 180;
    const curMod = state.coinAngle % 360;
    state.coinAngle += 1440 + ((wantMod - curMod + 360) % 360);
    document.getElementById("coin3d").style.transform = `rotateY(${state.coinAngle}deg)`;

    safeTimeout(() => {
      state.pendingBalance = null;
      applyBalance(data.balance);
      pushGameHistory("coinflip", data.result === "heads" ? "🦅 Орёл" : "👑 Решка", data.win > 0 ? "win" : "lose");
      showOutcome("gameResult", bet, data.win, data.result === "heads" ? "Выпал Орёл" : "Выпала Решка", "coinflip");
      state.busy = false; setBtnDisabled("playBtn", false);
    }, 1450);
  } catch (e) {
    if (prev !== null) applyBalance(prev);
    state.pendingBalance = null;
    state.busy = false; setBtnDisabled("playBtn", false);
    showBanner("gameResult", "lose", e.message);
  }
}

// ==================== 5. ЖИВОЙ КРАШ ====================
let crashRuntime = null;
let crashStarting = false;

function syncDemoCrashIfEnded() {
  const dc = state.demoCrash;
  if (!dc || !dc.startedAt) return;
  const elapsed = (performance.now() - dc.startedAt) / 1000;
  const mult = Math.round(Math.exp(0.12 * elapsed) * 100) / 100;
  if (dc.auto_cashout >= 1.05 && mult >= dc.auto_cashout && dc.auto_cashout <= dc.crash_point) {
    const win = capDemoWin(dc.bet * dc.auto_cashout);
    state.demoCrash = null;
    applyBalance(state.demoBalance + win);
    recordSessionBet("crash", dc.bet, win, `Авто ${dc.auto_cashout}x`);
  } else if (mult >= dc.crash_point) {
    state.demoCrash = null;
    recordSessionBet("crash", dc.bet, 0, `Краш ${dc.crash_point}x`);
  }
}

function drawCrashGraph(mult, crashed) {
  const c = document.getElementById("crashCanvas");
  if (!c) return;
  const ctx = c.getContext("2d");
  const W = c.width, H = c.height;
  ctx.clearRect(0, 0, W, H);

  ctx.strokeStyle = "rgba(255,255,255,0.06)"; ctx.lineWidth = 1;
  for (let i = 1; i < 4; i++) {
    ctx.beginPath(); ctx.moveTo(0, (H / 4) * i); ctx.lineTo(W, (H / 4) * i); ctx.stroke();
  }

  const t = Math.min(1, Math.log(Math.max(1, mult)) / 2.2);
  const endX = 24 + t * (W - 60);
  const endY = H - 22 - Math.pow(t, 1.35) * (H - 52);

  const grad = ctx.createLinearGradient(0, H, 0, 0);
  grad.addColorStop(0, crashed ? "rgba(239,68,68,0.05)" : "rgba(245,185,66,0.04)");
  grad.addColorStop(1, crashed ? "rgba(239,68,68,0.35)" : "rgba(16,185,129,0.32)");

  ctx.beginPath();
  ctx.moveTo(24, H - 22);
  ctx.quadraticCurveTo(24 + (endX - 24) * 0.65, H - 22, endX, endY);
  ctx.lineTo(endX, H - 22);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  ctx.beginPath();
  ctx.moveTo(24, H - 22);
  ctx.quadraticCurveTo(24 + (endX - 24) * 0.65, H - 22, endX, endY);
  ctx.strokeStyle = crashed ? "#ef4444" : "#34d399";
  ctx.lineWidth = 4;
  ctx.stroke();

  ctx.font = "22px sans-serif";
  ctx.fillText(crashed ? "💥" : "🚀", endX - 11, endY + 8);
}

function restoreCrashUI() {
  if (state.isDemo) syncDemoCrashIfEnded();
  const c = state.isDemo ? state.demoCrash : state.activeCrash;
  if (!c) return;
  const localStart = (state.isDemo && c.startedAt)
    ? c.startedAt
    : (performance.now() - (Math.log(Math.max(1, c.multiplier || 1)) / 0.12) * 1000);
  startCrashLoop(c.bet, c.auto_cashout || 0, localStart, c.crash_point || null);
}

function startCrashLoop(bet, autoC, localStart, demoCrashPoint) {
  cleanupLoops();
  state.busy = true;
  crashRuntime = { bet, autoC, localStart, demoCrashPoint, flying: true, cashing: false };
  const btn = document.getElementById("crashBtn");
  btn.className = "action-btn success";
  document.getElementById("betInput").disabled = true;
  document.getElementById("crashAuto").disabled = true;
  document.getElementById("crashSub").textContent = "Ракета в полёте — забирай!";

  const tick = () => {
    if (!crashRuntime || !crashRuntime.flying) return;
    const elapsed = (performance.now() - crashRuntime.localStart) / 1000;
    const mult = Math.round(Math.exp(0.12 * elapsed) * 100) / 100;

    if (state.isDemo && crashRuntime.demoCrashPoint) {
      if (crashRuntime.autoC >= 1.05 && mult >= crashRuntime.autoC && crashRuntime.autoC <= crashRuntime.demoCrashPoint) {
        const win = capDemoWin(bet * crashRuntime.autoC);
        finishCrash(true, crashRuntime.autoC, win, state.demoBalance + win);
        return;
      }
      if (mult >= crashRuntime.demoCrashPoint) {
        finishCrash(false, crashRuntime.demoCrashPoint, 0, state.demoBalance);
        return;
      }
    }

    const mEl = document.getElementById("crashMult");
    if (mEl) { mEl.textContent = mult.toFixed(2) + "x"; mEl.style.color = "#34d399"; }
    drawCrashGraph(mult, false);
    const pot = Math.min(bet * mult, state.limits.max_win).toFixed(2);
    const bEl = document.getElementById("crashBtn");
    if (bEl && !crashRuntime.cashing) bEl.textContent = `💰 Забрать $${pot} (${mult.toFixed(2)}x)`;

    safeRAF(tick);
  };
  safeRAF(tick);

  if (!state.isDemo) {
    safeInterval(async () => {
      if (!crashRuntime || !crashRuntime.flying || crashRuntime.cashing) return;
      try {
        const st = await apiFetch("/api/play/crash/state");
        if (!crashRuntime || !crashRuntime.flying) return;
        if (st.status === "crashed") {
          finishCrash(false, st.crash_point, 0, st.balance);
        } else if (st.status === "cashed_out") {
          finishCrash(true, st.multiplier, st.win, st.balance);
        }
      } catch {}
    }, 420);
  }
}

function finishCrash(isWin, mult, win, newBal) {
  const bet = crashRuntime ? crashRuntime.bet : 0;
  if (crashRuntime) crashRuntime.flying = false;
  crashRuntime = null;
  state.activeCrash = null; state.demoCrash = null;
  cleanupLoops();

  const mEl = document.getElementById("crashMult");
  if (mEl) { mEl.textContent = Number(mult).toFixed(2) + "x"; mEl.style.color = isWin ? "#34d399" : "#ef4444"; }
  const sEl = document.getElementById("crashSub");
  if (sEl) sEl.textContent = isWin ? "Успешный вывод!" : "ВЗРЫВ!";
  drawCrashGraph(mult, !isWin);
  if (!isWin) playSFX("boom");

  applyBalance(newBal);
  pushGameHistory("crash", `${Number(mult).toFixed(2)}x`, isWin ? "win" : "lose");
  showOutcome("gameResult", bet, win, isWin ? `Забрали на ${Number(mult).toFixed(2)}x` : `Краш на ${Number(mult).toFixed(2)}x`, "crash");
  const btn = document.getElementById("crashBtn");
  if (btn) { btn.className = "action-btn"; btn.textContent = "🚀 Запустить ракету"; btn.disabled = false; }
  const bi = document.getElementById("betInput"); if (bi) bi.disabled = false;
  const ca = document.getElementById("crashAuto"); if (ca) ca.disabled = false;
}

async function crashAction() {
  if (crashRuntime && crashRuntime.flying) {
    if (crashRuntime.cashing) return;
    crashRuntime.cashing = true;
    if (state.isDemo) {
      const elapsed = (performance.now() - crashRuntime.localStart) / 1000;
      const mult = Math.max(1.01, Math.round(Math.exp(0.12 * elapsed) * 100) / 100);
      if (mult >= crashRuntime.demoCrashPoint) {
        finishCrash(false, crashRuntime.demoCrashPoint, 0, state.demoBalance);
      } else {
        const win = capDemoWin(crashRuntime.bet * mult);
        finishCrash(true, mult, win, state.demoBalance + win);
      }
      return;
    }
    try {
      const data = await apiFetch("/api/play/crash/cashout", { method: "POST" });
      finishCrash(data.status === "cashed_out", data.multiplier, data.win, data.balance);
    } catch (e) {
      if (crashRuntime) crashRuntime.cashing = false;
      showBanner("gameResult", "lose", e.message);
    }
    return;
  }

  if (crashStarting || state.busy) return;
  crashStarting = true;
  setBtnDisabled("crashBtn", true);
  let prev = null;
  try {
    const bet = getBet();
    const auto_cashout = parseFloat(document.getElementById("crashAuto").value || 0);
    if (auto_cashout !== 0 && auto_cashout < 1.05) throw new Error("Авто-вывод от 1.05x или 0");
    prev = deductBetNow(bet); haptic("tap"); playSFX("tap");
    document.getElementById("gameResult").style.display = "none";

    if (state.isDemo) {
      const r = (Math.floor(Math.random() * 999999) + 1) / 1000000;
      const cp = 0.94 / r < 1.01 ? 1.0 : Math.round(Math.min(0.94 / r, 1000) * 100) / 100;
      if (cp <= 1.0) {
        crashRuntime = { bet };
        finishCrash(false, 1.0, 0, prev - bet);
        return;
      }
      const nowPerf = performance.now();
      state.demoCrash = { bet, auto_cashout, crash_point: cp, multiplier: 1.0, startedAt: nowPerf };
      setBtnDisabled("crashBtn", false);
      startCrashLoop(bet, auto_cashout, nowPerf, cp);
      return;
    }

    const data = await apiFetch("/api/play/crash/start", { method: "POST", body: JSON.stringify({ bet, auto_cashout }) });
    applyBalance(data.balance);
    if (data.status === "crashed") {
      crashRuntime = { bet };
      finishCrash(false, data.crash_point, 0, data.balance);
    } else {
      state.activeCrash = { bet, auto_cashout, multiplier: 1.0 };
      setBtnDisabled("crashBtn", false);
      startCrashLoop(bet, auto_cashout, performance.now(), null);
    }
  } catch (e) {
    if (prev !== null) applyBalance(prev);
    setBtnDisabled("crashBtn", false);
    showBanner("gameResult", "lose", e.message);
  } finally {
    crashStarting = false;
  }
}

// ==================== 6. ЕВРОПЕЙСКАЯ РУЛЕТКА (0–36) ====================
function roulColor(n) { return n === 0 ? "green" : (RED_NUMS.has(n) ? "red" : "black"); }

function initRouletteStrip() {
  const strip = document.getElementById("roulStrip");
  if (!strip) return;
  const seq = [...ROUL_ORDER, ...ROUL_ORDER, ...ROUL_ORDER, ...ROUL_ORDER];
  strip.innerHTML = seq.map(n => `<div class="roul-tile ${roulColor(n)}">${n}</div>`).join("");
  strip.style.transition = "none";
  strip.style.transform = "translateX(0px)";
}

function setRoulType(t) {
  window._roulType = t;
  document.querySelectorAll('[id^="rt-"]').forEach(b => b.classList.remove("selected"));
  document.getElementById(`rt-${t}`)?.classList.add("selected");
  document.getElementById("roulNumWrap").style.display = t === "number" ? "block" : "none";
  checkCapHint();
}

async function playRoulette() {
  if (state.busy) return;
  let prev = null;
  try {
    const bet = getBet();
    const bet_type = window._roulType;
    const number = bet_type === "number" ? parseInt(document.getElementById("roulNumber").value) : null;
    if (bet_type === "number" && (isNaN(number) || number < 0 || number > 36)) throw new Error("Число от 0 до 36");

    state.busy = true; setBtnDisabled("playBtn", true);
    prev = deductBetNow(bet); haptic("tap"); playSFX("tap");

    let data;
    if (state.isDemo) {
      const landed = Math.floor(Math.random() * 37);
      const col = roulColor(landed);
      let is_win = false, mult = 0;
      if (bet_type === "green") { is_win = landed === 0; mult = 34; }
      else if (bet_type === "number") { is_win = landed === number; mult = 34; }
      else if (bet_type === "red") { is_win = col === "red"; mult = 1.95; }
      else if (bet_type === "black") { is_win = col === "black"; mult = 1.95; }
      else if (bet_type === "even") { is_win = landed !== 0 && landed % 2 === 0; mult = 1.95; }
      else if (bet_type === "odd") { is_win = landed % 2 === 1; mult = 1.95; }
      else if (bet_type === "low") { is_win = landed >= 1 && landed <= 18; mult = 1.95; }
      else if (bet_type === "high") { is_win = landed >= 19; mult = 1.95; }
      else if (bet_type === "dozen1") { is_win = landed >= 1 && landed <= 12; mult = 2.85; }
      else if (bet_type === "dozen2") { is_win = landed >= 13 && landed <= 24; mult = 2.85; }
      else if (bet_type === "dozen3") { is_win = landed >= 25; mult = 2.85; }
      const win = is_win ? capDemoWin(bet * mult) : 0;
      data = { number: landed, color: col, is_win, multiplier: is_win ? mult : 0, win, balance: prev - bet + win };
    } else {
      data = await apiFetch("/api/play/roulette", { method: "POST", body: JSON.stringify({ bet, bet_type, number }) });
    }

    state.pendingBalance = data.balance;
    const strip = document.getElementById("roulStrip");
    const vpW = strip.parentElement.clientWidth;
    const tileW = 60;
    const baseIdx = ROUL_ORDER.indexOf(data.number);
    const targetIdx = ROUL_ORDER.length * 2 + baseIdx;
    const jitter = (Math.random() - 0.5) * 28;
    const offset = -(targetIdx * tileW + tileW / 2 - vpW / 2) + jitter;

    strip.style.transition = "none";
    strip.style.transform = "translateX(0px)";
    strip.offsetHeight;
    strip.style.transition = "transform 3.1s cubic-bezier(0.1, 0.85, 0.15, 1)";
    strip.style.transform = `translateX(${offset}px)`;

    safeTimeout(() => {
      const ico = data.color === "green" ? "🟢" : (data.color === "red" ? "🔴" : "⚫");
      state.pendingBalance = null;
      applyBalance(data.balance);
      pushGameHistory("roulette", String(data.number), data.color);
      showOutcome("gameResult", bet, data.win, `${ico} Выпало ${data.number}`, "roulette");
      state.busy = false; setBtnDisabled("playBtn", false);
    }, 3150);
  } catch (e) {
    if (prev !== null) applyBalance(prev);
    state.pendingBalance = null;
    state.busy = false; setBtnDisabled("playBtn", false);
    showBanner("gameResult", "lose", e.message);
  }
}

// ==================== 7. КОЛЕСО ФОРТУНЫ ====================
function drawWheel(blinkPhase = false) {
  const c = document.getElementById("wheelCanvas");
  if (!c) return;
  const ctx = c.getContext("2d");
  const cx = 133, cy = 133, outerR = 130, wheelR = 115;
  const n = WHEEL_SECTORS.length;
  const arc = (2 * Math.PI) / n;
  ctx.clearRect(0, 0, 266, 266);

  ctx.beginPath(); ctx.arc(cx, cy, outerR, 0, 2 * Math.PI);
  const rim = ctx.createLinearGradient(0, 0, 266, 266);
  rim.addColorStop(0, "#ffe082"); rim.addColorStop(0.5, "#d48817"); rim.addColorStop(1, "#fef08a");
  ctx.fillStyle = rim; ctx.fill();

  for (let i = 0; i < n; i++) {
    const a = i * arc - Math.PI / 2;
    ctx.beginPath(); ctx.moveTo(cx, cy); ctx.arc(cx, cy, wheelR, a, a + arc);
    ctx.fillStyle = WHEEL_COLORS[i % WHEEL_COLORS.length]; ctx.fill();
    ctx.strokeStyle = "#070a12"; ctx.lineWidth = 2; ctx.stroke();

    ctx.save(); ctx.translate(cx, cy); ctx.rotate(a + arc / 2);
    ctx.fillStyle = WHEEL_SECTORS[i] >= 2 ? "#fef08a" : "#fff";
    ctx.font = "900 13px sans-serif"; ctx.textAlign = "right";
    ctx.fillText(WHEEL_SECTORS[i] + "x", wheelR - 12, 5);
    ctx.restore();
  }

  for (let i = 0; i < 24; i++) {
    const a = (i / 24) * Math.PI * 2;
    const lx = cx + Math.cos(a) * 122.5;
    const ly = cy + Math.sin(a) * 122.5;
    const lit = (i % 2 === 0) === blinkPhase;
    ctx.beginPath(); ctx.arc(lx, ly, 3.2, 0, Math.PI * 2);
    ctx.fillStyle = lit ? "#ffffff" : "#78350f";
    ctx.fill();
  }
}

async function playWheel() {
  if (state.busy) return;
  let prev = null;
  try {
    const bet = getBet();
    state.busy = true; setBtnDisabled("playBtn", true);
    prev = deductBetNow(bet); haptic("tap"); playSFX("tap");

    let data;
    if (state.isDemo) {
      const sector_index = Math.floor(Math.random() * WHEEL_SECTORS.length);
      const mult = WHEEL_SECTORS[sector_index];
      const win = capDemoWin(bet * mult);
      data = { sector_index, multiplier: mult, win, balance: prev - bet + win };
    } else {
      data = await apiFetch("/api/play/wheel", { method: "POST", body: JSON.stringify({ bet }) });
    }

    state.pendingBalance = data.balance;
    const seg = 360 / WHEEL_SECTORS.length;
    const targetAngle = 360 - (data.sector_index * seg + seg / 2);
    state.wheelRotation += 1800 + ((targetAngle - (state.wheelRotation % 360) + 360) % 360);
    document.getElementById("wheelCanvas").style.transform = `rotate(${state.wheelRotation}deg)`;

    safeTimeout(() => {
      state.pendingBalance = null;
      applyBalance(data.balance);
      pushGameHistory("wheel", `${data.multiplier}x`, data.multiplier >= 1.2 ? "win" : (data.multiplier > 0 ? "gold" : "lose"));
      showOutcome("gameResult", bet, data.win, `Сектор ${data.multiplier}x`, "wheel");
      state.busy = false; setBtnDisabled("playBtn", false);
    }, 3250);
  } catch (e) {
    if (prev !== null) applyBalance(prev);
    state.pendingBalance = null;
    state.busy = false; setBtnDisabled("playBtn", false);
    showBanner("gameResult", "lose", e.message);
  }
}

// ==================== 8. КАРТЫ HI-LO (СЕРВЕРНАЯ КАРТА) ====================
function cardLabel(v) {
  const map = { 11: "J", 12: "Q", 13: "K", 14: "A" };
  return (map[v] || v) + " ♠️";
}

function updateHiloButtons() {
  const c = state.isDemo ? state.demoHiloCard : state.hiloCard;
  const hiCnt = 14 - c;
  const loCnt = c - 2;
  const hiBtn = document.getElementById("hlHigh");
  const loBtn = document.getElementById("hlLow");
  if (!hiBtn || !loBtn) return;

  if (hiCnt > 0) {
    const hiPct = ((hiCnt / 13) * 100).toFixed(1);
    const hiMult = Math.max(1.03, Math.round((11.7 / hiCnt) * 100) / 100).toFixed(2);
    hiBtn.disabled = false;
    hiBtn.innerHTML = `⬆️ Выше<br><small>${hiPct}% • ${hiMult}x</small>`;
  } else {
    hiBtn.disabled = true; hiBtn.innerHTML = `⬆️ Выше<br><small>0%</small>`;
    window._hiloDir = "low";
  }

  if (loCnt > 0) {
    const loPct = ((loCnt / 13) * 100).toFixed(1);
    const loMult = Math.max(1.03, Math.round((11.7 / loCnt) * 100) / 100).toFixed(2);
    loBtn.disabled = false;
    loBtn.innerHTML = `⬇️ Ниже<br><small>${loPct}% • ${loMult}x</small>`;
  } else {
    loBtn.disabled = true; loBtn.innerHTML = `⬇️ Ниже<br><small>0%</small>`;
    window._hiloDir = "high";
  }
  hiBtn.classList.toggle("selected", window._hiloDir === "high");
  loBtn.classList.toggle("selected", window._hiloDir === "low");
}

function setHilo(d) {
  window._hiloDir = d;
  updateHiloButtons();
}

async function playHilo() {
  if (state.busy) return;
  let prev = null;
  try {
    const bet = getBet();
    const guess = window._hiloDir;
    state.busy = true; setBtnDisabled("playBtn", true);
    prev = deductBetNow(bet); haptic("tap"); playSFX("tap");

    let data;
    if (state.isDemo) {
      const cur = state.demoHiloCard;
      const count = guess === "high" ? (14 - cur) : (cur - 2);
      if (count <= 0) throw new Error("Невозможный ход для этой карты");
      const mult = Math.max(1.03, Math.round((11.7 / count) * 100) / 100);
      const next_card = Math.floor(Math.random() * 13) + 2;
      const is_win = guess === "high" ? next_card > cur : next_card < cur;
      const win = is_win ? capDemoWin(bet * mult) : 0;
      state.demoHiloCard = next_card;
      data = { next_card, is_win, win, multiplier: mult, balance: prev - bet + win };
    } else {
      data = await apiFetch("/api/play/hilo", { method: "POST", body: JSON.stringify({ bet, guess }) });
      state.hiloCard = data.next_card;
    }

    document.getElementById("hiloCardDisplay").textContent = cardLabel(data.next_card);
    updateHiloButtons();
    applyBalance(data.balance);
    showOutcome("gameResult", bet, data.win, `Выпала ${cardLabel(data.next_card)}`, "hilo");
  } catch (e) {
    if (prev !== null) applyBalance(prev);
    showBanner("gameResult", "lose", e.message);
  } finally {
    state.busy = false; setBtnDisabled("playBtn", false);
  }
}

// ==================== 9. ПЛИНКО (60 FPS, МУЛЬТИ-ШАРИКИ) ====================
const PLINKO_W = 440;
const PLINKO_H = 240;
const PLINKO_MAX_ACTIVE = 150;

const plinkoState = {
  balls: [],
  flashes: [],
  popups: [],
  batches: new Map(),
  nextBatchId: 1,
  animRunning: false,
  requesting: false,
  confirmedBalance: null,
  unsettledWin: 0,
  inFlightCost: 0,
  pegCache: null,
  dpr: 1,
  lastTickSfx: 0,
  lastLandSfx: 0,
  bucketTimers: new Array(9).fill(null)
};

function round2(v) {
  return Math.round(Number(v) * 100) / 100;
}

function getPlinkoBallsCount() {
  const inp = document.getElementById("plinkoBallsInput");
  const raw = inp ? parseInt(inp.value, 10) : (window._plinkoBalls || 1);
  if (isNaN(raw) || raw < 1) return 1;
  return Math.min(50, raw);
}

function setPlinkoBalls(n) {
  const val = Math.max(1, Math.min(50, parseInt(n, 10) || 1));
  window._plinkoBalls = val;
  const inp = document.getElementById("plinkoBallsInput");
  if (inp) inp.value = val;
  [1, 3, 5, 10, 20].forEach(k => {
    document.getElementById(`pb-cnt-${k}`)?.classList.toggle("active", k === val);
  });
  haptic("tap"); playSFX("tap");
  checkCapHint();
}

function onPlinkoBallsInput() {
  const inp = document.getElementById("plinkoBallsInput");
  let v = parseInt(inp?.value || "1", 10);
  if (!isNaN(v)) {
    if (v > 50) { v = 50; inp.value = 50; }
    window._plinkoBalls = Math.max(1, v);
  }
  [1, 3, 5, 10, 20].forEach(k => {
    document.getElementById(`pb-cnt-${k}`)?.classList.toggle("active", k === window._plinkoBalls);
  });
  checkCapHint();
}

function updatePlinkoBtnLabel() {
  if (state.currentGame !== "plinko") return;
  const cnt = getPlinkoBallsCount();
  const bet = parseFloat(document.getElementById("betInput")?.value) || 0;
  const total = round2(bet * cnt);
  const lbl = document.getElementById("plinkoTotalCostLbl");
  if (lbl) lbl.textContent = `Итого: $${total.toFixed(2)}`;
  const btn = document.getElementById("playBtn");
  if (btn) {
    const word = cnt === 1 ? "шарик" : (cnt >= 2 && cnt <= 4 ? "шарика" : "шариков");
    btn.textContent = cnt === 1
      ? `⚪ Бросить шарик ($${total.toFixed(2)})`
      : `⚪ Бросить ${cnt} ${word} ($${total.toFixed(2)})`;
  }
}

function setPlinkoRiskButtonsLocked(locked) {
  ["low", "medium", "high"].forEach(k => {
    const el = document.getElementById(`pr-${k}`);
    if (el) el.disabled = locked;
  });
}

function setPlinkoRisk(r) {
  if (plinkoState.balls.length > 0 || plinkoState.requesting) {
    showToast("Сменить риск можно после приземления шариков", "warn");
    return;
  }
  window._plinkoRisk = r;
  ["low", "medium", "high"].forEach(k => document.getElementById(`pr-${k}`)?.classList.toggle("selected", k === r));
  renderPlinkoBuckets();
  checkCapHint();
}

function plinkoPegPos(row, col) {
  const topY = 22, gapY = 26, gapX = 42;
  const pegsInRow = row + 3;
  const startX = PLINKO_W / 2 - ((pegsInRow - 1) * gapX) / 2;
  return { x: startX + col * gapX, y: topY + row * gapY };
}

function buildPlinkoPegCache(dpr) {
  const off = document.createElement("canvas");
  off.width = Math.round(PLINKO_W * dpr);
  off.height = Math.round(PLINKO_H * dpr);
  const octx = off.getContext("2d");
  octx.scale(dpr, dpr);

  // Лёгкая направляющая сетка
  octx.fillStyle = "rgba(255,255,255,0.03)";
  octx.beginPath();
  octx.moveTo(PLINKO_W / 2 - 48, 12);
  octx.lineTo(PLINKO_W / 2 + 48, 12);
  octx.lineTo(PLINKO_W - 14, PLINKO_H - 10);
  octx.lineTo(14, PLINKO_H - 10);
  octx.closePath();
  octx.fill();

  for (let r = 0; r < 8; r++) {
    for (let col = 0; col < r + 3; col++) {
      const p = plinkoPegPos(r, col);
      // Тёмный обод
      octx.beginPath();
      octx.arc(p.x, p.y, 4.8, 0, Math.PI * 2);
      octx.fillStyle = "rgba(15, 23, 42, 0.9)";
      octx.fill();
      // Светлый пин
      octx.beginPath();
      octx.arc(p.x, p.y, 3.6, 0, Math.PI * 2);
      octx.fillStyle = "#94a3b8";
      octx.fill();
      // Блик
      octx.beginPath();
      octx.arc(p.x - 1.1, p.y - 1.1, 1.1, 0, Math.PI * 2);
      octx.fillStyle = "rgba(255,255,255,0.55)";
      octx.fill();
    }
  }
  return off;
}

function renderPlinkoBuckets() {
  const bBox = document.getElementById("plinkoBuckets");
  if (!bBox) return;
  const vals = PLINKO_BUCKETS[window._plinkoRisk || "medium"];
  bBox.innerHTML = vals.map((m, i) => {
    const bg = m >= 4 ? "#ef4444" : (m >= 1.2 ? "#f59e0b" : "#38bdf8");
    return `<div class="plinko-b" id="pb-${i}" style="background:${bg}">${m}x</div>`;
  }).join("");
}

function initPlinkoBoard() {
  const c = document.getElementById("plinkoCanvas");
  if (!c) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  plinkoState.dpr = dpr;
  c.width = Math.round(PLINKO_W * dpr);
  c.height = Math.round(PLINKO_H * dpr);
  plinkoState.pegCache = buildPlinkoPegCache(dpr);
  renderPlinkoBuckets();
  drawPlinkoFrame(performance.now());
}

function syncPlinkoVisualBalance(bump = false) {
  if (plinkoState.confirmedBalance === null) return;
  const shown = Math.max(0, round2(plinkoState.confirmedBalance - plinkoState.unsettledWin - plinkoState.inFlightCost));
  if (state.isDemo) state.demoBalance = shown;
  else state.realBalance = shown;
  updateBalanceUI(bump);
}

function updatePlinkoHud(lastText = null) {
  const el = document.getElementById("plinkoInFlight");
  if (el) el.textContent = `⚪ В полёте: ${plinkoState.balls.length}`;
  if (lastText !== null) {
    const lt = document.getElementById("plinkoLastHit");
    if (lt) lt.textContent = lastText;
  }
}

function pulsePlinkoBucket(idx) {
  const el = document.getElementById(`pb-${idx}`);
  if (!el) return;
  el.classList.add("hit");
  if (plinkoState.bucketTimers[idx]) clearTimeout(plinkoState.bucketTimers[idx]);
  plinkoState.bucketTimers[idx] = setTimeout(() => {
    el.classList.remove("hit");
    plinkoState.bucketTimers[idx] = null;
  }, 150);
}

function flushPlinkoOnExit() {
  plinkoState.bucketTimers.forEach((t, i) => {
    if (t) { clearTimeout(t); plinkoState.bucketTimers[i] = null; }
  });
  if (plinkoState.batches.size > 0) {
    plinkoState.batches.forEach(batch => {
      const label = batch.count === 1 ? `Лунка ${batch.lastMult}x` : `${batch.count} шариков`;
      recordSessionBet("plinko", batch.totalBet, batch.totalWin, label);
    });
    plinkoState.batches.clear();
  }
  const finalBal = plinkoState.confirmedBalance;
  plinkoState.balls = [];
  plinkoState.flashes = [];
  plinkoState.popups = [];
  plinkoState.animRunning = false;
  plinkoState.requesting = false;
  plinkoState.confirmedBalance = null;
  plinkoState.unsettledWin = 0;
  plinkoState.inFlightCost = 0;
  if (finalBal !== null) applyBalance(finalBal);
}

function drawPlinkoFrame(now) {
  const c = document.getElementById("plinkoCanvas");
  if (!c) { plinkoState.animRunning = false; return; }
  const ctx = c.getContext("2d");
  const dpr = plinkoState.dpr || 1;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, PLINKO_W, PLINKO_H);

  // 1. Статичное поле из кэша за 1 вызов (0 лагов)
  if (plinkoState.pegCache) {
    ctx.drawImage(plinkoState.pegCache, 0, 0, PLINKO_W, PLINKO_H);
  }

  // 2. Вспышки на пинах (без shadowBlur)
  const flashes = plinkoState.flashes;
  for (let i = flashes.length - 1; i >= 0; i--) {
    const f = flashes[i];
    const age = now - f.start;
    if (age >= 220) {
      flashes.splice(i, 1);
      continue;
    }
    const p = age / 220;
    const alpha = 1 - p;
    ctx.beginPath();
    ctx.arc(f.x, f.y, 4.5 + p * 7, 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(245, 185, 66, ${(alpha * 0.85).toFixed(2)})`;
    ctx.lineWidth = 1.8;
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(f.x, f.y, 4.2, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(253, 224, 71, ${alpha.toFixed(2)})`;
    ctx.fill();
  }

  // 3. Активные шарики
  const balls = plinkoState.balls;
  for (let i = balls.length - 1; i >= 0; i--) {
    const b = balls[i];
    const elapsed = now - b.spawnAt;
    if (elapsed < 0) continue;

    const seg = Math.floor(elapsed / b.stepMs);
    const frac = (elapsed % b.stepMs) / b.stepMs;

    if (seg > b.lastSeg && seg > 0 && seg < b.nodes.length - 1) {
      b.lastSeg = seg;
      const hitNode = b.nodes[seg];
      if (plinkoState.flashes.length < 40) {
        plinkoState.flashes.push({ x: hitNode.px, y: hitNode.py, start: now });
      }
      if (now - plinkoState.lastTickSfx > 55) {
        plinkoState.lastTickSfx = now;
        playSFX("tick");
      }
    }

    if (seg >= b.nodes.length - 1) {
      balls.splice(i, 1);
      onPlinkoBallLanded(b, now);
      continue;
    }

    const a = b.nodes[seg];
    const nxt = b.nodes[seg + 1];
    // Плавный горизонтальный переход + гравитационный отскок по Y
    const x = a.x + (nxt.x - a.x) * frac;
    const y = a.y + (nxt.y - a.y) * (frac * frac) - Math.sin(frac * Math.PI) * 7.5;

    // Мягкий ореол + ядро + блик (без shadowBlur — быстро на мобильных GPU)
    ctx.beginPath();
    ctx.arc(x, y, 8.8, 0, Math.PI * 2);
    ctx.fillStyle = b.haloColor;
    ctx.fill();

    ctx.beginPath();
    ctx.arc(x, y, 5.6, 0, Math.PI * 2);
    ctx.fillStyle = b.coreColor;
    ctx.fill();

    ctx.beginPath();
    ctx.arc(x - 1.7, y - 1.7, 1.6, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(255,255,255,0.85)";
    ctx.fill();
  }

  // 4. Всплывающие множители
  const popups = plinkoState.popups;
  ctx.font = "900 11px sans-serif";
  ctx.textAlign = "center";
  for (let i = popups.length - 1; i >= 0; i--) {
    const pop = popups[i];
    const age = now - pop.start;
    if (age >= 520) {
      popups.splice(i, 1);
      continue;
    }
    const p = age / 520;
    ctx.globalAlpha = 1 - p;
    ctx.fillStyle = pop.color;
    ctx.fillText(pop.text, pop.x, pop.y - p * 22);
    ctx.globalAlpha = 1;
  }
}

function onPlinkoBallLanded(ball, now) {
  plinkoState.unsettledWin = Math.max(0, round2(plinkoState.unsettledWin - ball.win));
  pulsePlinkoBucket(ball.bucket);

  const isBig = ball.mult >= 4;
  const isWin = ball.mult >= 1.1;
  const popColor = isBig ? "#f87171" : (isWin ? "#34d399" : "#94a3b8");
  if (plinkoState.popups.length < 24) {
    plinkoState.popups.push({
      x: Math.max(24, Math.min(PLINKO_W - 24, ball.finalX)),
      y: PLINKO_H - 14,
      text: `${ball.mult}x`,
      color: popColor,
      start: now
    });
  }

  pushGameHistory("plinko", `${ball.mult}x`, isWin ? "win" : "lose");
  updatePlinkoHud(`Последняя лунка: ${ball.mult}x (+$${ball.win.toFixed(2)})`);

  if (now - plinkoState.lastLandSfx > 70) {
    plinkoState.lastLandSfx = now;
    if (isBig) { haptic("win"); playSFX("bigwin"); }
    else if (isWin) { haptic("win"); playSFX("win"); }
    else { playSFX("tap"); }
  }

  const batch = plinkoState.batches.get(ball.batchId);
  if (batch) {
    batch.landed += 1;
    batch.lastMult = ball.mult;
    if (batch.landed >= batch.count) {
      plinkoState.batches.delete(ball.batchId);
      const label = batch.count === 1
        ? `Лунка ${ball.mult}x`
        : `${batch.count} шариков`;
      const profit = round2(batch.totalWin - batch.totalBet);
      recordSessionBet("plinko", batch.totalBet, batch.totalWin, label);
      if (batch.totalWin > batch.totalBet) {
        showBanner("gameResult", "win", `${label} • Выигрыш $${batch.totalWin.toFixed(2)} (+$${profit.toFixed(2)})`);
      } else if (batch.totalWin === batch.totalBet) {
        showBanner("gameResult", "warn", `${label} • Возврат $${batch.totalWin.toFixed(2)}`);
      } else if (batch.totalWin > 0) {
        showBanner("gameResult", "warn", `${label} • Возврат $${batch.totalWin.toFixed(2)} (-$${round2(batch.totalBet - batch.totalWin).toFixed(2)})`);
      } else {
        showBanner("gameResult", "lose", `${label} • Проигрыш -$${batch.totalBet.toFixed(2)}`);
      }
    }
  }

  if (plinkoState.balls.length === 0 && !plinkoState.requesting && plinkoState.inFlightCost === 0) {
    const exact = plinkoState.confirmedBalance;
    plinkoState.confirmedBalance = null;
    plinkoState.unsettledWin = 0;
    if (exact !== null) applyBalance(exact);
    setPlinkoRiskButtonsLocked(false);
  } else {
    syncPlinkoVisualBalance(ball.win > 0);
  }
}

function startPlinkoLoop() {
  if (plinkoState.animRunning) return;
  plinkoState.animRunning = true;
  const loop = (now) => {
    if (!plinkoState.animRunning) return;
    drawPlinkoFrame(now);
    if (plinkoState.balls.length > 0 || plinkoState.flashes.length > 0 || plinkoState.popups.length > 0) {
      safeRAF(loop);
    } else {
      plinkoState.animRunning = false;
    }
  };
  safeRAF(loop);
}

function spawnPlinkoDrops(drops, risk, batchId, betPerBall) {
  const now = performance.now();
  const stagger = drops.length >= 15 ? 45 : (drops.length >= 6 ? 65 : 85);
  const coreColor = risk === "high" ? "#fbbf24" : (risk === "low" ? "#fef08a" : "#fde047");
  const haloColor = risk === "high" ? "rgba(239,68,68,0.28)" : "rgba(245,185,66,0.26)";

  drops.forEach((drop, idx) => {
    const jitter = (Math.random() - 0.5) * 4.5;
    const nodes = [{ x: PLINKO_W / 2 + jitter * 0.5, y: 6, px: PLINKO_W / 2, py: 6 }];
    let rightCount = 0;
    for (let r = 0; r < 8; r++) {
      const peg = plinkoPegPos(r, rightCount + 1);
      const stepJit = (Math.random() - 0.5) * 3.5;
      nodes.push({ x: peg.x + stepJit, y: peg.y - 7, px: peg.x, py: peg.y });
      rightCount += drop.path[r];
    }
    const finalX = PLINKO_W / 2 + (drop.bucket - 4) * 42;
    nodes.push({ x: finalX + jitter * 0.6, y: PLINKO_H - 8, px: finalX, py: PLINKO_H - 8 });

    plinkoState.balls.push({
      nodes,
      spawnAt: now + idx * stagger,
      stepMs: 118 + Math.random() * 14,
      lastSeg: -1,
      bucket: drop.bucket,
      mult: drop.multiplier,
      win: Number(drop.win),
      bet: betPerBall,
      finalX,
      batchId,
      coreColor,
      haloColor
    });
  });

  setPlinkoRiskButtonsLocked(true);
  updatePlinkoHud();
  startPlinkoLoop();
}

async function playPlinko() {
  if (plinkoState.requesting) return;
  let totalCost = 0;
  let hadConfirmed = plinkoState.confirmedBalance !== null;
  let prevBalSnapshot = getBal();

  try {
    const bet = parseFloat(document.getElementById("betInput").value);
    if (isNaN(bet) || bet <= 0) throw new Error("Введите корректную ставку");
    const betPerBall = round2(bet);
    const count = getPlinkoBallsCount();
    totalCost = round2(betPerBall * count);

    if (betPerBall > state.limits.max_bet || totalCost > state.limits.max_bet) {
      throw new Error(`Сумма (${count} × $${betPerBall.toFixed(2)} = $${totalCost.toFixed(2)}) превышает лимит $${state.limits.max_bet}`);
    }
    if (plinkoState.balls.length + count > PLINKO_MAX_ACTIVE) {
      throw new Error(`Максимум ${PLINKO_MAX_ACTIVE} шариков в полёте одновременно`);
    }
    if (totalCost > getBal()) throw new Error("Недостаточно средств на балансе");

    const risk = window._plinkoRisk || "medium";
    plinkoState.requesting = true;
    haptic("tap"); playSFX("tap");

    // Мгновенно списываем визуально, сохраняя инвариант с уже летящими шариками
    if (!hadConfirmed) {
      plinkoState.confirmedBalance = prevBalSnapshot;
    }
    plinkoState.inFlightCost = round2(plinkoState.inFlightCost + totalCost);
    syncPlinkoVisualBalance(true);

    let data;
    if (state.isDemo) {
      const vals = PLINKO_BUCKETS[risk];
      const drops = [];
      let remCap = state.limits.max_win;
      let totalWin = 0;
      for (let i = 0; i < count; i++) {
        const path = Array.from({ length: 8 }, () => Math.random() < 0.5 ? 0 : 1);
        const bucket = path.reduce((a, b) => a + b, 0);
        const mult = vals[bucket];
        const rawW = round2(betPerBall * mult);
        const w = Math.min(rawW, remCap);
        remCap = Math.max(0, round2(remCap - w));
        totalWin = round2(totalWin + w);
        drops.push({ path, bucket, multiplier: mult, win: w });
      }
      const nextBal = round2(plinkoState.confirmedBalance - totalCost + totalWin);
      data = { balls: count, total_bet: totalCost, total_win: totalWin, drops, balance: nextBal };
    } else {
      data = await apiFetch("/api/play/plinko", {
        method: "POST",
        body: JSON.stringify({ bet: betPerBall, risk, balls: count })
      });
    }

    const drops = Array.isArray(data.drops) && data.drops.length
      ? data.drops
      : [{ path: data.path, bucket: data.bucket, multiplier: data.multiplier, win: data.win }];
    const batchWin = round2(drops.reduce((acc, d) => acc + Number(d.win || 0), 0));

    plinkoState.inFlightCost = Math.max(0, round2(plinkoState.inFlightCost - totalCost));
    plinkoState.confirmedBalance = Number(data.balance);
    plinkoState.unsettledWin = round2(plinkoState.unsettledWin + batchWin);
    syncPlinkoVisualBalance(false);

    const batchId = plinkoState.nextBatchId++;
    plinkoState.batches.set(batchId, {
      count: drops.length,
      landed: 0,
      totalBet: totalCost,
      totalWin: batchWin,
      lastMult: drops[0].multiplier
    });

    spawnPlinkoDrops(drops, risk, batchId, betPerBall);
  } catch (e) {
    if (totalCost > 0 && plinkoState.inFlightCost >= totalCost) {
      plinkoState.inFlightCost = Math.max(0, round2(plinkoState.inFlightCost - totalCost));
    }
    if (plinkoState.balls.length === 0 && plinkoState.inFlightCost === 0) {
      const restore = plinkoState.confirmedBalance !== null ? plinkoState.confirmedBalance : prevBalSnapshot;
      plinkoState.confirmedBalance = null;
      plinkoState.unsettledWin = 0;
      applyBalance(restore);
    } else {
      syncPlinkoVisualBalance(false);
    }
    showBanner("gameResult", "lose", e.message);
  } finally {
    plinkoState.requesting = false;
  }
}

// ==================== 10. БАШНЯ (TOWER) ====================
const TOWER_CFG = { easy: [4, 1], medium: [3, 1], hard: [3, 2] };

function setTowerDiff(d) {
  if (state.isDemo ? state.demoTower : state.activeTower) return;
  window._towerDiff = d;
  ["easy","medium","hard"].forEach(k => document.getElementById(`td-${k}`)?.classList.toggle("selected", k === d));
  drawTowerGrid(d, 0, null);
}

function drawTowerGrid(diff, curFloor, revealedTraps) {
  const [cols, traps] = TOWER_CFG[diff];
  const safeP = (cols - traps) / cols;
  const box = document.getElementById("towerGrid");
  if (!box) return;
  let html = "";
  for (let f = 0; f < 8; f++) {
    const mult = (0.94 / Math.pow(safeP, f + 1)).toFixed(2);
    const isActive = (state.isDemo ? state.demoTower : state.activeTower) && f === curFloor && !revealedTraps;
    html += `<div class="tower-row ${isActive ? 'active-floor' : ''}" style="grid-template-columns: repeat(${cols}, 1fr);">`;
    for (let c = 0; c < cols; c++) {
      let cls = "tower-cell", txt = `${mult}x`;
      if (revealedTraps) {
        if (revealedTraps[f]?.includes(c)) { cls += " trap"; txt = "💀"; }
        else if (f < curFloor) { cls += " safe"; txt = "💎"; }
      } else if (f < curFloor) {
        cls += " safe"; txt = "✓";
      }
      html += `<div class="${cls}" onclick="${isActive ? `climbTower(${c})` : ''}">${txt}</div>`;
    }
    html += `</div>`;
  }
  box.innerHTML = html;
}

function restoreTowerUI() {
  const t = state.isDemo ? state.demoTower : state.activeTower;
  const bi = document.getElementById("betInput");
  if (!t) {
    if (bi) bi.disabled = false;
    drawTowerGrid(window._towerDiff, 0, null);
    return;
  }
  if (bi) { bi.value = t.bet; bi.disabled = true; }
  window._towerDiff = t.difficulty;
  ["easy","medium","hard"].forEach(k => document.getElementById(`td-${k}`)?.classList.toggle("selected", k === t.difficulty));
  document.getElementById("towerFloorLbl").textContent = `${t.floor} / 8`;
  document.getElementById("towerMultLbl").textContent = `${(t.multiplier || 1).toFixed(2)}x`;
  document.getElementById("towerAutoBtn").style.display = "block";
  const btn = document.getElementById("towerMainBtn");
  btn.textContent = t.potential_win ? `Забрать $${Number(t.potential_win).toFixed(2)}` : "Забрать выигрыш";
  btn.classList.add("success");
  drawTowerGrid(t.difficulty, t.floor, null);
}

async function startOrCashoutTower() {
  if (state.busy) return;
  const active = state.isDemo ? state.demoTower : state.activeTower;
  let prev = null;
  state.busy = true;
  try {
    if (active) {
      if (state.isDemo) {
        if (active.floor <= 0) throw new Error("Пройдите хотя бы 1 этаж");
        const win = capDemoWin(active.bet * active.multiplier);
        drawTowerGrid(active.difficulty, active.floor, active.traps);
        applyBalance(state.demoBalance + win);
        showOutcome("gameResult", active.bet, win, `Этаж ${active.floor} (${active.multiplier}x)`, "tower");
        state.demoTower = null;
      } else {
        const data = await apiFetch("/api/play/tower/cashout", { method: "POST" });
        drawTowerGrid(active.difficulty, active.floor, data.traps);
        applyBalance(data.balance);
        showOutcome("gameResult", active.bet, data.win, `Этаж ${active.floor} (${data.multiplier}x)`, "tower");
        state.activeTower = null;
      }
      document.getElementById("towerMainBtn").textContent = "Начать подъём";
      document.getElementById("towerMainBtn").classList.remove("success");
      document.getElementById("towerAutoBtn").style.display = "none";
      const bi = document.getElementById("betInput"); if (bi) bi.disabled = false;
      return;
    }

    const bet = getBet();
    const difficulty = window._towerDiff;
    prev = deductBetNow(bet); haptic("tap"); playSFX("tap");
    document.getElementById("gameResult").style.display = "none";

    if (state.isDemo) {
      const [cols, trapsN] = TOWER_CFG[difficulty];
      const traps = [];
      for (let f = 0; f < 8; f++) {
        const arr = Array.from({length: cols}, (_, i) => i).sort(() => Math.random() - 0.5);
        traps.push(arr.slice(0, trapsN));
      }
      state.demoTower = { bet, difficulty, floor: 0, multiplier: 1.0, traps };
    } else {
      const data = await apiFetch("/api/play/tower/start", { method: "POST", body: JSON.stringify({ bet, difficulty }) });
      applyBalance(data.balance);
      state.activeTower = { bet: data.bet, difficulty, floor: 0, multiplier: 1.0 };
    }
    restoreTowerUI();
  } catch (e) {
    if (prev !== null) applyBalance(prev);
    showBanner("gameResult", "lose", e.message);
  } finally { state.busy = false; }
}

async function climbTower(col) {
  const active = state.isDemo ? state.demoTower : state.activeTower;
  if (!active || state.busy) return;
  state.busy = true;
  try {
    if (state.isDemo) {
      const [cols, trapsN] = TOWER_CFG[active.difficulty];
      const chosen = col === -1 ? Math.floor(Math.random() * cols) : col;
      if (active.traps[active.floor].includes(chosen)) {
        drawTowerGrid(active.difficulty, active.floor, active.traps);
        playSFX("boom");
        showOutcome("gameResult", active.bet, 0, `Ловушка на этаже ${active.floor + 1}`, "tower");
        state.demoTower = null;
        document.getElementById("towerMainBtn").textContent = "Начать подъём";
        document.getElementById("towerMainBtn").classList.remove("success");
        document.getElementById("towerAutoBtn").style.display = "none";
        const bi = document.getElementById("betInput"); if (bi) bi.disabled = false;
      } else {
        active.floor += 1;
        active.multiplier = Math.round((0.94 / Math.pow((cols - trapsN) / cols, active.floor)) * 100) / 100;
        active.potential_win = capDemoWin(active.bet * active.multiplier);
        haptic("tap"); playSFX("tick");
        if (active.floor >= 8 || active.potential_win >= state.limits.max_win) {
          drawTowerGrid(active.difficulty, active.floor, active.traps);
          applyBalance(state.demoBalance + active.potential_win);
          showOutcome("gameResult", active.bet, active.potential_win, "Вершина башни!", "tower");
          state.demoTower = null;
          document.getElementById("towerMainBtn").textContent = "Начать подъём";
          document.getElementById("towerMainBtn").classList.remove("success");
          document.getElementById("towerAutoBtn").style.display = "none";
          const bi = document.getElementById("betInput"); if (bi) bi.disabled = false;
        } else { restoreTowerUI(); }
      }
      return;
    }

    const data = await apiFetch("/api/play/tower/climb", { method: "POST", body: JSON.stringify({ col }) });
    if (data.status === "boom") {
      drawTowerGrid(active.difficulty, active.floor, data.traps);
      playSFX("boom");
      showOutcome("gameResult", active.bet, 0, `Ловушка на этаже ${data.floor + 1}`, "tower");
      state.activeTower = null;
      document.getElementById("towerMainBtn").textContent = "Начать подъём";
      document.getElementById("towerMainBtn").classList.remove("success");
      document.getElementById("towerAutoBtn").style.display = "none";
      const bi = document.getElementById("betInput"); if (bi) bi.disabled = false;
    } else if (data.status === "win_all") {
      drawTowerGrid(active.difficulty, data.floor, data.traps);
      applyBalance(data.balance);
      showOutcome("gameResult", active.bet, data.win, `Победа (${data.multiplier}x)`, "tower");
      state.activeTower = null;
      document.getElementById("towerMainBtn").textContent = "Начать подъём";
      document.getElementById("towerMainBtn").classList.remove("success");
      document.getElementById("towerAutoBtn").style.display = "none";
      const bi = document.getElementById("betInput"); if (bi) bi.disabled = false;
    } else {
      haptic("tap"); playSFX("tick");
      state.activeTower.floor = data.floor;
      state.activeTower.multiplier = data.multiplier;
      state.activeTower.potential_win = data.potential_win;
      restoreTowerUI();
    }
  } catch (e) { showBanner("gameResult", "lose", e.message); }
  finally { state.busy = false; }
}

// ==================== 11. ЛИМБО ====================
function updateLimboChance() {
  const t = Math.max(1.05, parseFloat(document.getElementById("limboTarget")?.value || 2));
  const ch = document.getElementById("limboChance");
  if (ch) ch.textContent = `Шанс: ${Math.min(94, 94 / t).toFixed(1)}%`;
  checkCapHint();
}

async function playLimbo() {
  if (state.busy) return;
  let prev = null;
  try {
    const bet = getBet();
    const target = parseFloat(document.getElementById("limboTarget").value);
    if (isNaN(target) || target < 1.05 || target > 1000) throw new Error("Цель от 1.05x до 1000x");
    state.busy = true; setBtnDisabled("playBtn", true);
    prev = deductBetNow(bet); haptic("tap"); playSFX("tap");

    let data;
    if (state.isDemo) {
      const r = (Math.floor(Math.random() * 999999) + 1) / 1000000;
      const result = 0.94 / r < 1.01 ? 1.0 : Math.round(Math.min(0.94 / r, 1000) * 100) / 100;
      const is_win = result >= target;
      const win = is_win ? capDemoWin(bet * target) : 0;
      data = { result, is_win, win, balance: prev - bet + win };
    } else {
      data = await apiFetch("/api/play/limbo", { method: "POST", body: JSON.stringify({ bet, target }) });
    }

    state.pendingBalance = data.balance;
    const el = document.getElementById("limboVal");
    const steps = 16;
    let i = 0;
    const iv = safeInterval(() => {
      i++;
      const cur = 1 + (data.result - 1) * (i / steps);
      if (el) el.textContent = cur.toFixed(2) + "x";
      if (i >= steps) {
        clearInterval(iv); timers.intervals.delete(iv);
        if (el) {
          el.textContent = data.result.toFixed(2) + "x";
          el.style.color = data.is_win ? "#34d399" : "#ef4444";
        }
        state.pendingBalance = null;
        applyBalance(data.balance);
        pushGameHistory("limbo", `${data.result.toFixed(2)}x`, data.is_win ? "win" : "lose");
        showOutcome("gameResult", bet, data.win, `Выпало ${data.result.toFixed(2)}x`, "limbo");
        state.busy = false; setBtnDisabled("playBtn", false);
      }
    }, 22);
  } catch (e) {
    if (prev !== null) applyBalance(prev);
    state.pendingBalance = null;
    state.busy = false; setBtnDisabled("playBtn", false);
    showBanner("gameResult", "lose", e.message);
  }
}

// ==================== 12. КЕНО ====================
function renderKenoPicks(drawn = [], hits = []) {
  const dSet = new Set(drawn), hSet = new Set(hits), pSet = new Set(state.kenoPicks);
  for (let i = 1; i <= 25; i++) {
    const el = document.getElementById(`kc-${i}`);
    if (!el) continue;
    el.className = "keno-cell";
    if (hSet.has(i)) el.classList.add("hit");
    else if (pSet.has(i)) el.classList.add("picked");
    else if (dSet.has(i)) el.classList.add("drawn");
  }
  const cnt = document.getElementById("kenoCount");
  if (cnt) cnt.textContent = state.kenoPicks.length;
  const pb = document.getElementById("kenoPaybar");
  if (pb) {
    const payMap = KENO_PAY[state.kenoPicks.length];
    if (!payMap) {
      pb.innerHTML = '<span>Выберите от 1 до 8 чисел</span>';
    } else {
      pb.innerHTML = Object.entries(payMap).map(([h, m]) => `<span>${h} совп: <b>${m}x</b></span>`).join("");
    }
  }
  checkCapHint();
}

function toggleKeno(n) {
  if (state.busy) return;
  const idx = state.kenoPicks.indexOf(n);
  if (idx >= 0) state.kenoPicks.splice(idx, 1);
  else if (state.kenoPicks.length < 8) state.kenoPicks.push(n);
  playSFX("tap");
  renderKenoPicks();
}

function randomKeno() {
  if (state.busy) return;
  const arr = Array.from({length: 25}, (_, i) => i + 1).sort(() => Math.random() - 0.5);
  state.kenoPicks = arr.slice(0, 5);
  playSFX("tap");
  renderKenoPicks();
}

function clearKeno() {
  if (state.busy) return;
  state.kenoPicks = [];
  renderKenoPicks();
}

async function playKeno() {
  if (state.busy) return;
  let prev = null;
  try {
    if (!state.kenoPicks.length) throw new Error("Выберите хотя бы 1 число");
    const bet = getBet();
    state.busy = true; setBtnDisabled("playBtn", true);
    prev = deductBetNow(bet); haptic("tap"); playSFX("tap");

    let data;
    if (state.isDemo) {
      const pool = Array.from({length: 25}, (_, i) => i + 1).sort(() => Math.random() - 0.5);
      const drawn = pool.slice(0, 8);
      const hits = state.kenoPicks.filter(n => drawn.includes(n));
      const mult = (KENO_PAY[state.kenoPicks.length] || {})[hits.length] || 0;
      const win = capDemoWin(bet * mult);
      data = { drawn, hits, multiplier: mult, win, balance: prev - bet + win };
    } else {
      data = await apiFetch("/api/play/keno", { method: "POST", body: JSON.stringify({ bet, picks: state.kenoPicks }) });
    }

    renderKenoPicks(data.drawn, data.hits);
    applyBalance(data.balance);
    showOutcome("gameResult", bet, data.win, `Совпадений: ${data.hits.length} (${data.multiplier}x)`, "keno");
  } catch (e) {
    if (prev !== null) applyBalance(prev);
    showBanner("gameResult", "lose", e.message);
  } finally { state.busy = false; setBtnDisabled("playBtn", false); }
}

// ==================== 13. КЕЙСЫ ====================
function setCaseTier(t) {
  if (state.busy) return;
  window._caseTier = t;
  ["bronze","silver","gold","royal"].forEach(k => document.getElementById(`ct-${k}`)?.classList.toggle("selected", k === t));
  document.getElementById("playBtn").textContent = `🎁 Открыть кейс ($${CASE_PRICES[t]})`;
}

function randomCaseItem() {
  let r = Math.floor(Math.random() * 1000), acc = 0;
  for (const it of CASE_ITEMS) { acc += it.weight; if (r < acc) return it; }
  return CASE_ITEMS[0];
}

function initCaseStrip(winItem = null) {
  const strip = document.getElementById("caseStrip");
  if (!strip) return;
  const arr = Array.from({length: 45}, () => randomCaseItem());
  if (winItem) arr[34] = winItem;
  strip.innerHTML = arr.map(it => `<div class="case-item rarity-${it.rarity}"><div style="font-size:24px;">${it.icon}</div><div>${it.label}</div></div>`).join("");
  strip.style.transition = "none";
  strip.style.transform = "translateX(0px)";
}

async function playCase() {
  if (state.busy) return;
  let prev = null;
  try {
    const tier = window._caseTier;
    const cost = CASE_PRICES[tier];
    if (cost > state.limits.max_bet) throw new Error(`Максимальная ставка — $${state.limits.max_bet}`);
    if (cost > getBal()) throw new Error("Недостаточно средств на балансе");
    state.busy = true; setBtnDisabled("playBtn", true);
    prev = deductBetNow(cost); haptic("tap"); playSFX("tap");

    let data;
    if (state.isDemo) {
      const item = randomCaseItem();
      const win = capDemoWin(cost * item.mult);
      data = { tier, cost, item, win, balance: prev - cost + win };
    } else {
      data = await apiFetch("/api/play/cases", { method: "POST", body: JSON.stringify({ tier }) });
    }

    state.pendingBalance = data.balance;
    initCaseStrip(data.item);
    const strip = document.getElementById("caseStrip");
    const vpW = strip.parentElement.clientWidth;
    const offset = -(34 * 78 + 39 - vpW / 2) + (Math.random() - 0.5) * 30;
    strip.offsetHeight;
    strip.style.transition = "transform 3.2s cubic-bezier(0.1, 0.85, 0.15, 1)";
    strip.style.transform = `translateX(${offset}px)`;

    safeTimeout(() => {
      state.pendingBalance = null;
      applyBalance(data.balance);
      showOutcome("gameResult", cost, data.win, `${data.item.icon} Дроп ${data.item.label}`, "cases");
      state.busy = false; setBtnDisabled("playBtn", false);
    }, 3250);
  } catch (e) {
    if (prev !== null) applyBalance(prev);
    state.pendingBalance = null;
    state.busy = false; setBtnDisabled("playBtn", false);
    showBanner("gameResult", "lose", e.message);
  }
}

// ==================== 14. БЛЭКДЖЕК 21 ====================
function renderCards(elId, cards) {
  const box = document.getElementById(elId);
  if (!box) return;
  box.innerHTML = cards.map(c => {
    if (c === "🂠") return `<div class="play-card back">🂠</div>`;
    const isRed = c.includes("♥") || c.includes("♦");
    return `<div class="play-card ${isRed ? 'red' : ''}">${escHtml(c)}</div>`;
  }).join("");
}

function demoDeck() {
  const r = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"], s = ["♠️","♥️","♦️","♣️"];
  return r.flatMap(x => s.map(y => x + y)).sort(() => Math.random() - 0.5);
}

function bjCalc(hand) {
  let tot = 0, aces = 0;
  for (const c of hand) {
    const rk = parseCardRank(c);
    if (["J","Q","K","10"].includes(rk)) tot += 10;
    else if (rk === "A") { tot += 11; aces++; }
    else tot += parseInt(rk, 10) || 0;
  }
  while (tot > 21 && aces > 0) { tot -= 10; aces--; }
  return tot;
}

function restoreBjUI() {
  const g = state.isDemo ? state.demoBj : state.activeBj;
  const bi = document.getElementById("betInput");
  if (!g) { if (bi) bi.disabled = false; return; }
  if (bi) { bi.value = g.bet; bi.disabled = true; }
  renderCards("bjPlayerCards", g.player_hand);
  document.getElementById("bjPlayerScore").textContent = g.player_score;
  renderCards("bjDealerCards", g.dealer_visible);
  document.getElementById("bjDealerScore").textContent = g.dealer_visible_score;
  document.getElementById("bjStartBtn").style.display = "none";
  document.getElementById("bjActionBtns").style.display = "flex";
}

function finishBjUI(data, bet) {
  renderCards("bjPlayerCards", data.player_hand);
  document.getElementById("bjPlayerScore").textContent = data.player_score;
  renderCards("bjDealerCards", data.dealer_hand);
  document.getElementById("bjDealerScore").textContent = data.dealer_score;
  document.getElementById("bjStartBtn").style.display = "block";
  document.getElementById("bjActionBtns").style.display = "none";
  const bi = document.getElementById("betInput"); if (bi) bi.disabled = false;
  state.activeBj = null; state.demoBj = null;
  applyBalance(data.balance);
  const map = { blackjack: "БЛЭКДЖЕК 2.4x", win: "Победа!", push: "Ничья", bust: "Перебор", lose: "Дилер победил" };
  showOutcome("gameResult", bet, data.win, map[data.outcome] || "", "blackjack");
}

async function bjStart() {
  if (state.busy) return;
  let prev = null;
  try {
    const bet = getBet();
    state.busy = true; prev = deductBetNow(bet); haptic("tap"); playSFX("tap");
    document.getElementById("gameResult").style.display = "none";

    if (state.isDemo) {
      const deck = demoDeck();
      const p = [deck.pop(), deck.pop()], d = [deck.pop(), deck.pop()];
      const ps = bjCalc(p), ds = bjCalc(d);
      if (ps === 21 || ds === 21) {
        let win = 0, outcome = "lose";
        if (ps === 21 && ds === 21) { win = bet; outcome = "push"; }
        else if (ps === 21) { win = capDemoWin(bet * 2.4); outcome = "blackjack"; }
        finishBjUI({ player_hand: p, player_score: ps, dealer_hand: d, dealer_score: ds, outcome, win, balance: prev - bet + win }, bet);
      } else {
        state.demoBj = { bet, deck, player_hand: p, player_score: ps, dealer_hand: d, dealer_visible: [d[0], "🂠"], dealer_visible_score: bjCalc([d[0]]) };
        restoreBjUI();
      }
      return;
    }

    const data = await apiFetch("/api/play/blackjack/start", { method: "POST", body: JSON.stringify({ bet }) });
    if (data.status === "finished") finishBjUI(data, bet);
    else { applyBalance(data.balance); state.activeBj = { ...data, bet }; restoreBjUI(); }
  } catch (e) {
    if (prev !== null) applyBalance(prev);
    showBanner("gameResult", "lose", e.message);
  } finally { state.busy = false; }
}

async function bjHit() {
  const g = state.isDemo ? state.demoBj : state.activeBj;
  if (!g || state.busy) return;
  state.busy = true; playSFX("tick");
  try {
    if (state.isDemo) {
      g.player_hand.push(g.deck.pop());
      g.player_score = bjCalc(g.player_hand);
      if (g.player_score > 21) {
        finishBjUI({ player_hand: g.player_hand, player_score: g.player_score, dealer_hand: g.dealer_hand, dealer_score: bjCalc(g.dealer_hand), outcome: "bust", win: 0, balance: state.demoBalance }, g.bet);
      } else if (g.player_score === 21) { await bjStandDemo(g); }
      else { restoreBjUI(); }
      return;
    }
    const data = await apiFetch("/api/play/blackjack/hit", { method: "POST" });
    if (data.status === "finished") finishBjUI(data, g.bet);
    else { state.activeBj = { ...state.activeBj, ...data }; restoreBjUI(); }
  } catch (e) { showBanner("gameResult", "lose", e.message); }
  finally { state.busy = false; }
}

async function bjStandDemo(g) {
  while (bjCalc(g.dealer_hand) < 17) g.dealer_hand.push(g.deck.pop());
  const ps = bjCalc(g.player_hand), ds = bjCalc(g.dealer_hand);
  const dealerNatural = (g.dealer_hand.length === 2 && ds === 21);
  let win = 0, outcome = "lose";
  if (dealerNatural && !(g.player_hand.length === 2 && ps === 21)) { win = 0; outcome = "lose"; }
  else if (ds > 21 || ps > ds) { win = capDemoWin(g.bet * 1.95); outcome = "win"; }
  else if (ps === ds) { win = g.bet; outcome = "push"; }
  finishBjUI({ player_hand: g.player_hand, player_score: ps, dealer_hand: g.dealer_hand, dealer_score: ds, outcome, win, balance: state.demoBalance + win }, g.bet);
}

async function bjStand() {
  const g = state.isDemo ? state.demoBj : state.activeBj;
  if (!g || state.busy) return;
  state.busy = true;
  try {
    if (state.isDemo) { await bjStandDemo(g); return; }
    const data = await apiFetch("/api/play/blackjack/stand", { method: "POST" });
    finishBjUI(data, g.bet);
  } catch (e) { showBanner("gameResult", "lose", e.message); }
  finally { state.busy = false; }
}

// ==================== 15. БАККАРА (ТОЧНЫЕ ПРАВИЛА 3-Й КАРТЫ) ====================
function setBac(c) {
  window._bacChoice = c;
  ["player","tie","banker"].forEach(k => document.getElementById(`bc-${k}`)?.classList.toggle("selected", k === c));
}

function bacVal(card) {
  const rk = parseCardRank(card);
  if (["10","J","Q","K"].includes(rk)) return 0;
  return rk === "A" ? 1 : (parseInt(rk, 10) || 0);
}

async function playBaccarat() {
  if (state.busy) return;
  let prev = null;
  try {
    const bet = getBet(), choice = window._bacChoice;
    state.busy = true; setBtnDisabled("playBtn", true);
    prev = deductBetNow(bet); haptic("tap"); playSFX("tap");

    let data;
    if (state.isDemo) {
      const deck = demoDeck();
      const p = [deck.pop(), deck.pop()], b = [deck.pop(), deck.pop()];
      let ps = (bacVal(p[0]) + bacVal(p[1])) % 10;
      let bs = (bacVal(b[0]) + bacVal(b[1])) % 10;
      if (ps < 8 && bs < 8) {
        let pThird = null;
        if (ps <= 5) {
          pThird = deck.pop();
          p.push(pThird);
          ps = p.reduce((a, c) => a + bacVal(c), 0) % 10;
        }
        if (pThird === null) {
          if (bs <= 5) b.push(deck.pop());
        } else {
          const tv = bacVal(pThird);
          const drawB = (
            bs <= 2
            || (bs === 3 && tv !== 8)
            || (bs === 4 && tv >= 2 && tv <= 7)
            || (bs === 5 && tv >= 4 && tv <= 7)
            || (bs === 6 && (tv === 6 || tv === 7))
          );
          if (drawB) b.push(deck.pop());
        }
        bs = b.reduce((a, c) => a + bacVal(c), 0) % 10;
      }
      const winner = ps > bs ? "player" : (bs > ps ? "banker" : "tie");
      const mults = { player: 1.95, banker: 1.90, tie: 8.0 };
      const win = choice === winner ? capDemoWin(bet * mults[winner]) : 0;
      data = { player_cards: p, banker_cards: b, player_score: ps, banker_score: bs, winner, win, balance: prev - bet + win };
    } else {
      data = await apiFetch("/api/play/baccarat", { method: "POST", body: JSON.stringify({ bet, choice }) });
    }

    renderCards("bacPCards", data.player_cards);
    renderCards("bacBCards", data.banker_cards);
    document.getElementById("bacPScore").textContent = data.player_score;
    document.getElementById("bacBScore").textContent = data.banker_score;
    applyBalance(data.balance);
    const wMap = { player: "Игрок", banker: "Банкир", tie: "Ничья" };
    pushGameHistory("baccarat", `${wMap[data.winner]} ${data.player_score}:${data.banker_score}`, data.winner === "tie" ? "green" : (data.winner === "banker" ? "red" : "win"));
    showOutcome("gameResult", bet, data.win, data.winner === "tie" ? "Ничья" : `Победил ${wMap[data.winner]}`, "baccarat");
  } catch (e) {
    if (prev !== null) applyBalance(prev);
    showBanner("gameResult", "lose", e.message);
  } finally { state.busy = false; setBtnDisabled("playBtn", false); }
}

// ==================== 16. НАПЁРСТКИ ====================
function setThBalls(n) {
  window._thBalls = n;
  document.getElementById("tb-1").classList.toggle("selected", n === 1);
  document.getElementById("tb-2").classList.toggle("selected", n === 2);
}
function setThCup(c) {
  window._thCup = c;
  for (let i = 0; i < 3; i++) {
    const el = document.getElementById(`cup-${i}`);
    el.textContent = "🥤"; el.classList.toggle("selected", i === c);
  }
}

async function playThimbles() {
  if (state.busy) return;
  let prev = null;
  try {
    const bet = getBet(), cup = window._thCup, balls = window._thBalls;
    state.busy = true; setBtnDisabled("playBtn", true);
    prev = deductBetNow(bet); haptic("tap"); playSFX("tap");

    let data;
    if (state.isDemo) {
      const pos = [0,1,2].sort(() => Math.random() - 0.5).slice(0, balls);
      const is_win = pos.includes(cup);
      const mult = balls === 1 ? 2.8 : 1.4;
      const win = is_win ? capDemoWin(bet * mult) : 0;
      data = { ball_positions: pos, is_win, win, balance: prev - bet + win };
    } else {
      data = await apiFetch("/api/play/thimbles", { method: "POST", body: JSON.stringify({ bet, cup, balls }) });
    }

    for (let i = 0; i < 3; i++) {
      document.getElementById(`cup-${i}`).textContent = data.ball_positions.includes(i) ? "🟡" : "❌";
    }
    applyBalance(data.balance);
    showOutcome("gameResult", bet, data.win, data.is_win ? "Шарик найден!" : "Пусто", "thimbles");
  } catch (e) {
    if (prev !== null) applyBalance(prev);
    showBanner("gameResult", "lose", e.message);
  } finally { state.busy = false; setBtnDisabled("playBtn", false); }
}

// ==================== 17. КНБ ====================
const RPS_ICO = { rock: "✊", scissors: "✌️", paper: "✋" };
function setRps(c) {
  window._rpsChoice = c;
  ["rock","scissors","paper"].forEach(k => document.getElementById(`rps-${k}`)?.classList.toggle("selected", k === c));
  document.getElementById("rpsYou").textContent = RPS_ICO[c];
}

async function playRps() {
  if (state.busy) return;
  let prev = null;
  try {
    const bet = getBet(), choice = window._rpsChoice;
    state.busy = true; setBtnDisabled("playBtn", true);
    prev = deductBetNow(bet); haptic("tap"); playSFX("tap");

    let data;
    if (state.isDemo) {
      const opts = ["rock","paper","scissors"];
      const bot_choice = opts[Math.floor(Math.random()*3)];
      let outcome = "lose", mult = 0;
      if (choice === bot_choice) { outcome = "draw"; mult = 1; }
      else if ((choice==="rock"&&bot_choice==="scissors")||(choice==="scissors"&&bot_choice==="paper")||(choice==="paper"&&bot_choice==="rock")) { outcome = "win"; mult = 1.85; }
      const win = capDemoWin(bet * mult);
      data = { bot_choice, outcome, win, balance: prev - bet + win };
    } else {
      data = await apiFetch("/api/play/rps", { method: "POST", body: JSON.stringify({ bet, choice }) });
    }

    document.getElementById("rpsBot").textContent = RPS_ICO[data.bot_choice];
    applyBalance(data.balance);
    showOutcome("gameResult", bet, data.win, data.outcome === "draw" ? "Ничья" : (data.outcome === "win" ? "Победа!" : "Бот победил"), "rps");
  } catch (e) {
    if (prev !== null) applyBalance(prev);
    showBanner("gameResult", "lose", e.message);
  } finally { state.busy = false; setBtnDisabled("playBtn", false); }
}

// ==================== 18. ПЕНАЛЬТИ ====================
function setPenDiff(d) {
  window._penDiff = d;
  document.getElementById("pd-normal").classList.toggle("selected", d === "normal");
  document.getElementById("pd-hard").classList.toggle("selected", d === "hard");
}
function setPenZone(z) {
  window._penZone = z;
  for (let i = 0; i < 5; i++) {
    const el = document.getElementById(`pz-${i}`);
    el.className = "goal-zone" + (i === z ? " selected" : "");
  }
}

async function playPenalty() {
  if (state.busy) return;
  let prev = null;
  try {
    const bet = getBet(), zone = window._penZone, difficulty = window._penDiff;
    state.busy = true; setBtnDisabled("playBtn", true);
    prev = deductBetNow(bet); haptic("tap"); playSFX("tap");

    let data;
    if (state.isDemo) {
      const blocks = difficulty === "normal" ? 2 : 3;
      const keeper_zones = [0,1,2,3,4].sort(() => Math.random() - 0.5).slice(0, blocks);
      const is_goal = !keeper_zones.includes(zone);
      const mult = difficulty === "normal" ? 1.55 : 2.30;
      const win = is_goal ? capDemoWin(bet * mult) : 0;
      data = { keeper_zones, is_goal, win, balance: prev - bet + win };
    } else {
      data = await apiFetch("/api/play/penalty", { method: "POST", body: JSON.stringify({ bet, zone, difficulty }) });
    }

    for (let i = 0; i < 5; i++) {
      const el = document.getElementById(`pz-${i}`);
      el.className = "goal-zone";
      if (data.keeper_zones.includes(i)) el.classList.add("goal-save");
      if (i === zone && data.is_goal) el.classList.add("goal-ok");
    }
    applyBalance(data.balance);
    showOutcome("gameResult", bet, data.win, data.is_goal ? "⚽ ГОООЛ!" : "🧤 Сейв вратаря!", "penalty");
  } catch (e) {
    if (prev !== null) applyBalance(prev);
    showBanner("gameResult", "lose", e.message);
  } finally { state.busy = false; setBtnDisabled("playBtn", false); }
}

// ==================== 19. СКРЕТЧ-КАРТА ====================
async function buyScratch() {
  if (state.busy) return;
  let prev = null;
  try {
    const bet = getBet();
    state.busy = true; setBtnDisabled("playBtn", true);
    prev = deductBetNow(bet); haptic("tap"); playSFX("tap");
    document.getElementById("gameResult").style.display = "none";
    for (let i = 0; i < 9; i++) {
      const c = document.getElementById(`sc-${i}`);
      c.className = "scratch-cell"; c.textContent = "?";
    }

    let data;
    if (state.isDemo) {
      const r = Math.floor(Math.random() * 1000);
      let win_symbol = null, mult = 0;
      if (r < 15) { win_symbol = "👑"; mult = 10; }
      else if (r < 50) { win_symbol = "💎"; mult = 5; }
      else if (r < 110) { win_symbol = "🔔"; mult = 3; }
      else if (r < 220) { win_symbol = "🍒"; mult = 2; }
      else if (r < 380) { win_symbol = "🍋"; mult = 1.2; }
      const syms = ["🍋","🍒","🔔","💎","👑","🍀"];
      let grid = [];
      if (win_symbol) {
        grid.push(win_symbol, win_symbol, win_symbol);
        const rest = syms.filter(s => s !== win_symbol).flatMap(s => [s, s]).sort(() => Math.random() - 0.5);
        grid.push(...rest.slice(0, 6));
      } else {
        grid = syms.flatMap(s => [s, s]).sort(() => Math.random() - 0.5).slice(0, 9);
      }
      grid.sort(() => Math.random() - 0.5);
      const win = capDemoWin(bet * mult);
      data = { grid, win_symbol, multiplier: mult, win, balance: prev - bet + win };
    } else {
      data = await apiFetch("/api/play/scratch", { method: "POST", body: JSON.stringify({ bet }) });
    }

    state.scratchState = { ...data, bet, opened: new Set() };
    document.getElementById("scratchAllBtn").style.display = "block";
    state.busy = false;
  } catch (e) {
    if (prev !== null) applyBalance(prev);
    state.busy = false; setBtnDisabled("playBtn", false);
    showBanner("gameResult", "lose", e.message);
  }
}

function scratchCell(i) {
  const s = state.scratchState;
  if (!s || s.opened.has(i)) return;
  s.opened.add(i);
  const c = document.getElementById(`sc-${i}`);
  c.classList.add("opened");
  c.textContent = s.grid[i];
  haptic("tap"); playSFX("tick");
  if (s.opened.size === 9) finishScratch();
}

function scratchAll() {
  const s = state.scratchState;
  if (!s) return;
  for (let i = 0; i < 9; i++) scratchCell(i);
}

function finishScratch() {
  const s = state.scratchState;
  if (!s) return;
  if (s.win_symbol) {
    for (let i = 0; i < 9; i++) {
      if (s.grid[i] === s.win_symbol) document.getElementById(`sc-${i}`)?.classList.add("matched");
    }
  }
  state.scratchState = null;
  applyBalance(s.balance);
  showOutcome("gameResult", s.bet, s.win, s.win_symbol ? `3x ${s.win_symbol} (${s.multiplier}x)` : "Нет 3 совпадений", "scratch");
  document.getElementById("scratchAllBtn").style.display = "none";
  setBtnDisabled("playBtn", false);
}

// ==================== 20. 2 КУБИКА (БОЛЬШЕ/МЕНЬШЕ 7) ====================
const DIE_FACE = ["", "⚀", "⚁", "⚂", "⚃", "⚄", "⚅"];
function setD7(c) {
  window._d7Choice = c;
  ["under","exact7","over","double"].forEach(k => document.getElementById(`d7-${k}`)?.classList.toggle("selected", k === c));
}

async function playDice7() {
  if (state.busy) return;
  let prev = null;
  try {
    const bet = getBet(), choice = window._d7Choice;
    state.busy = true; setBtnDisabled("playBtn", true);
    prev = deductBetNow(bet); haptic("tap"); playSFX("tap");

    let data;
    if (state.isDemo) {
      const d1 = Math.floor(Math.random()*6)+1, d2 = Math.floor(Math.random()*6)+1, total = d1 + d2;
      let is_win = false, mult = 0;
      if (choice === "under") { is_win = total < 7; mult = 2.2; }
      else if (choice === "over") { is_win = total > 7; mult = 2.2; }
      else if (choice === "exact7") { is_win = total === 7; mult = 5.5; }
      else { is_win = d1 === d2; mult = 5.5; }
      const win = is_win ? capDemoWin(bet * mult) : 0;
      data = { d1, d2, total, is_win, win, balance: prev - bet + win };
    } else {
      data = await apiFetch("/api/play/dice7", { method: "POST", body: JSON.stringify({ bet, choice }) });
    }

    state.pendingBalance = data.balance;
    let ticks = 0;
    const iv = safeInterval(() => {
      ticks++;
      const elA = document.getElementById("d7a"), elB = document.getElementById("d7b");
      if (elA) elA.textContent = DIE_FACE[Math.floor(Math.random()*6)+1];
      if (elB) elB.textContent = DIE_FACE[Math.floor(Math.random()*6)+1];
      if (ticks >= 10) {
        clearInterval(iv); timers.intervals.delete(iv);
        if (elA) elA.textContent = DIE_FACE[data.d1];
        if (elB) elB.textContent = DIE_FACE[data.d2];
        const sEl = document.getElementById("d7Sum");
        if (sEl) sEl.textContent = `Сумма: ${data.total} (${data.d1} + ${data.d2})`;
        state.pendingBalance = null;
        applyBalance(data.balance);
        pushGameHistory("dice7", `${data.total}`, data.is_win ? "win" : "lose");
        showOutcome("gameResult", bet, data.win, `Сумма ${data.total}`, "dice7");
        state.busy = false; setBtnDisabled("playBtn", false);
      }
    }, 55);
  } catch (e) {
    if (prev !== null) applyBalance(prev);
    state.pendingBalance = null;
    state.busy = false; setBtnDisabled("playBtn", false);
    showBanner("gameResult", "lose", e.message);
  }
}

// ==================== КАССА И АДМИНКА ====================
function buyCustomStars() {
  const raw = (document.getElementById("customStars")?.value || "").trim();
  if (!raw || !/^\d+$/.test(raw)) {
    showToast("Введите целое число Stars (1 – 10000)", "error");
    return;
  }
  buyStars(parseInt(raw, 10));
}

async function buyStars(stars) {
  try {
    if (isNaN(stars) || stars < 1 || stars > 10000) throw new Error("Укажите от 1 до 10000 Stars");
    const data = await apiFetch("/api/stars/invoice", { method: "POST", body: JSON.stringify({ stars }) });
    if (tg && tg.openInvoice) {
      tg.openInvoice(data.invoice_url, status => {
        if (status === "paid") {
          showToast("Оплата прошла успешно! Обновляем баланс...", "success");
          setTimeout(loadProfile, 1200);
        }
      });
    } else {
      window.open(data.invoice_url, "_blank");
    }
  } catch (e) { showToast(e.message, "error"); }
}

async function submitWithdraw() {
  setBtnDisabled("withdrawBtn", true);
  try {
    const amount = parseFloat(document.getElementById("withdrawAmount").value);
    const details = document.getElementById("withdrawDetails").value.trim();
    if (isNaN(amount) || amount < 1) throw new Error("Минимальная сумма вывода — $1.00");
    if (details.length < 3) throw new Error("Укажите реквизиты (от 3 символов)");
    const data = await apiFetch("/api/withdraw", { method: "POST", body: JSON.stringify({ amount, details }) });
    applyBalance(data.balance);
    showBanner("withdrawMsg", "win", `Заявка #${data.id} создана и отправлена администратору!`);
    showToast(`Заявка на вывод #${data.id} создана`, "success");
    loadProfile();
  } catch (e) {
    showBanner("withdrawMsg", "lose", e.message);
    showToast(e.message, "error");
  } finally {
    setBtnDisabled("withdrawBtn", false);
  }
}

async function adminAdjustBalance() {
  try {
    const target_user_id = parseInt(document.getElementById("adminTargetId").value);
    const amount = parseFloat(document.getElementById("adminAmount").value);
    const mode = document.getElementById("adminMode").value;
    if (isNaN(target_user_id) || target_user_id <= 0) throw new Error("Введите Telegram ID игрока");
    if (isNaN(amount) || amount < 0) throw new Error("Введите корректную сумму");
    const data = await apiFetch("/api/admin/balance", { method: "POST", body: JSON.stringify({ target_user_id, amount, mode }) });
    showBanner("adminMsg", "win", `Новый баланс ID ${data.user_id}: $${Number(data.balance).toFixed(2)}`);
    showToast(`Баланс ID ${data.user_id} обновлён`, "success");
    loadProfile();
  } catch (e) {
    showBanner("adminMsg", "lose", e.message);
    showToast(e.message, "error");
  }
}

async function handleAdminWithdraw(wd_id, action) {
  try {
    await apiFetch("/api/admin/withdraw/handle", { method: "POST", body: JSON.stringify({ wd_id, action }) });
    showToast(action === "approve" ? `Заявка #${wd_id} одобрена` : `Заявка #${wd_id} отклонена`, action === "approve" ? "success" : "warn");
    loadProfile();
  } catch (e) { showToast(e.message, "error"); }
}

updateSoundUI();
initAgeGate();
renderGamesGrid();
renderSessionHistory();
loadProfile();
