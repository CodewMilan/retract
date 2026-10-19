const CELL = 4;
const REDUCED = "(prefers-reduced-motion: reduce)";
const SKY = ["#7eb6ea", "#8ec0ee", "#6eabe4", "#9cc8f0", "#78b4e8"];
const ROCK = {
  black: ["#141210", "#1d1a14", "#262a16"],
  red: ["#ff4500", "#ff5a1a"],
  orange: ["#ff7a12", "#ff8f2a"],
  lime: ["#d6e63a", "#e3ee5a", "#c4da2a"],
  yellow: ["#f4d94a", "#f8e98a"],
};
const CLOUD = ["#fff6ee", "#f7d0dc", "#f8ddc4", "#e7f08c"];

function hash(x, y) {
  const s = Math.sin(x * 127.1 + y * 311.7) * 43758.5453;
  return s - Math.floor(s);
}
function cellNoise(x, y) {
  const s = 43758.5453 * Math.sin(127.1 * x + 311.7 * y);
  return (s - Math.floor(s)) * 2 - 1;
}
function smooth(t) { return t * t * (3 - 2 * t); }
function valueNoise(x, y, period) {
  const ix = Math.floor(x);
  const iy = Math.floor(y);
  const fx = smooth(x - ix);
  const fy = smooth(y - iy);
  const wrap = v => (period ? ((v % period) + period) % period : v);
  const a = hash(wrap(ix), iy);
  const b = hash(wrap(ix + 1), iy);
  const c = hash(wrap(ix), iy + 1);
  const d = hash(wrap(ix + 1), iy + 1);
  return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy;
}
function fbm(x, y, period = 0) {
  let sum = 0;
  let amp = 0.5;
  let freq = 1;
  for (let o = 0; o < 4; o += 1) {
    sum += amp * valueNoise(x * freq, y * freq, period ? period * freq : 0);
    freq *= 2;
    amp *= 0.5;
  }
  return sum / 0.9375;
}
function gauss(x, c, w) {
  const d = (x - c) / w;
  return Math.exp(-d * d);
}
function pick(list, r) { return list[Math.min(list.length - 1, Math.floor(r * list.length))]; }
function ridge(cols, rows) {
  return Array.from({length: cols}, (_, x) => {
    const t = x / Math.max(1, cols - 1);
    const shape = 0.46
      - 0.16 * gauss(t, 0.22, 0.12)
      - 0.12 * gauss(t, 0.48, 0.1)
      - 0.1 * gauss(t, 0.68, 0.06)
      - 0.2 * gauss(t, 0.9, 0.12)
      + 0.03 * (fbm(t * 14, 3.1) - 0.5);
    return Math.max(4, Math.round(shape * rows));
  });
}
function rockColor(x, y, depth) {
  const r = hash(x * 1.3, y * 0.7);
  if (depth < 1) return r > 0.5 ? pick(ROCK.black, r) : pick(ROCK.lime, r);
  const streak = Math.sin((x * 0.9 - y * 1.4) * 0.16 + fbm(x * 0.05, y * 0.05) * 5);
  const v = fbm(x * 0.045 + y * 0.02, y * 0.07) * 0.75 + streak * 0.18 + (r - 0.5) * 0.22;
  if (v > 0.6) return pick(ROCK.lime, r);
  if (v > 0.52) return r > 0.6 ? pick(ROCK.yellow, r) : pick(ROCK.orange, r);
  if (v > 0.44) return pick(ROCK.red, r);
  if (v > 0.38) return r > 0.5 ? pick(ROCK.orange, r) : pick(ROCK.black, r);
  return r > 0.94 ? pick(ROCK.red, r) : pick(ROCK.black, r);
}
function cloudAt(x, y, rows) {
  const t = y / rows;
  if (t > 0.48) return null;
  const n = fbm(x * 0.035, y * 0.09 + 11.3);
  const edge = 0.52 - (0.48 - t) * 0.2;
  if (n < edge) return null;
  const r = hash(x * 2.1, y * 3.7);
  if (n < edge + 0.04) return r > 0.5 ? CLOUD[3] : CLOUD[2];
  return pick(CLOUD.slice(0, 3), r);
}
function paintBase(ctx, cols, rows, top) {
  const img = ctx.createImageData(cols, rows);
  const put = (i, hex) => {
    img.data[i] = parseInt(hex.slice(1, 3), 16);
    img.data[i + 1] = parseInt(hex.slice(3, 5), 16);
    img.data[i + 2] = parseInt(hex.slice(5, 7), 16);
    img.data[i + 3] = 255;
  };
  for (let y = 0; y < rows; y += 1) {
    for (let x = 0; x < cols; x += 1) {
      const i = (y * cols + x) * 4;
      const cloud = cloudAt(x, y, rows);
      if (cloud) put(i, cloud);
      else if (y >= top[x]) put(i, rockColor(x, y, y - top[x]));
      else {
        const r = hash(x, y);
        const n = fbm(x * 0.03, y * 0.05);
        put(i, SKY[Math.floor((n * 0.7 + r * 0.3) * SKY.length) % SKY.length]);
      }
    }
  }
  ctx.putImageData(img, 0, 0);
}
function paintReveal(ctx, width, rows, period) {
  const img = ctx.createImageData(width, rows);
  const scale = 1 / 24;
  for (let y = 0; y < rows; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const i = (y * width + x) * 4;
      const r = hash(x * 0.7, y * 1.9);
      const c = fbm(x * scale, y * (1 / 14) + 3.7, period * scale) + (r - 0.5) * 0.06;
      const deep = fbm(x * scale * 0.6 + 40, y * (1 / 30), period * scale * 0.6) - y / rows * 0.35;
      let rgb;
      if (c > 0.66) rgb = r > 0.85 ? [243, 230, 196] : [238, 242, 250];
      else if (c > 0.58) rgb = [201, 216, 240];
      else if (c > 0.52) rgb = r > 0.5 ? [159, 189, 232] : [120, 168, 230];
      else if (deep > 0.42) rgb = r > 0.3 ? [22, 44, 190] : [30, 64, 205];
      else rgb = r > 0.4 ? [33, 128, 232] : [24, 104, 222];
      img.data[i] = rgb[0];
      img.data[i + 1] = rgb[1];
      img.data[i + 2] = rgb[2];
      img.data[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
}
function dotPattern(ctx) {
  const tile = document.createElement("canvas");
  tile.width = CELL;
  tile.height = CELL;
  const t = tile.getContext("2d");
  t.fillStyle = "rgba(255,255,255,0.28)";
  t.fillRect(CELL - 1, 0, 1, CELL);
  t.fillRect(0, CELL - 1, CELL, 1);
  return ctx.createPattern(tile, "repeat");
}
function loadGsap() {
  if (window.gsap) return Promise.resolve(window.gsap);
  return new Promise((resolve, reject) => {
    const element = document.createElement("script");
    element.src = "/assets/gsap.min.js";
    element.onload = () => resolve(window.gsap);
    element.onerror = () => reject(new Error("Motion library failed to load"));
    document.head.append(element);
  });
}

export function mountPortrait(root) {
  const art = root?.querySelector(".auth-art");
  if (!art || art.dataset.ready) return;
  art.dataset.ready = "1";
  const baseCanvas = document.createElement("canvas");
  const canvas = document.createElement("canvas");
  baseCanvas.className = "auth-poster";
  canvas.className = "auth-reveal";
  art.append(baseCanvas, canvas);
  const base = baseCanvas.getContext("2d", {willReadFrequently: true});
  const ctx = canvas.getContext("2d", {willReadFrequently: true});
  const mask = document.createElement("canvas");
  const maskCtx = mask.getContext("2d");
  const small = document.createElement("canvas");
  const smallCtx = small.getContext("2d");
  const source = document.createElement("canvas");
  const sourceCtx = source.getContext("2d");
  let cols = 0;
  let rows = 0;
  let width = 0;
  let height = 0;
  let grid = [];
  let held = new Set();
  const pending = new Set();
  let revealed = 0;
  let boost = 0;
  let lastX = null;
  let lastY = null;
  let lastT = null;
  let stopTimer = 0;
  let revealWidth = 0;
  let started = 0;
  let pattern = null;
  let pointerAt = 0;
  let ticker = null;

  function build() {
    const rect = art.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) return;
    cols = Math.ceil(rect.width / CELL);
    rows = Math.ceil(rect.height / CELL);
    width = cols * CELL;
    height = rows * CELL;
    for (const c of [baseCanvas, canvas, mask]) {
      c.width = width;
      c.height = height;
    }
    small.width = cols;
    small.height = rows;
    base.imageSmoothingEnabled = false;
    smallCtx.imageSmoothingEnabled = false;
    maskCtx.imageSmoothingEnabled = false;
    ctx.imageSmoothingEnabled = false;
    pattern = dotPattern(ctx);
    const top = ridge(cols, rows);
    paintBase(smallCtx, cols, rows, top);
    base.drawImage(small, 0, 0, width, height);
    base.fillStyle = dotPattern(base);
    base.fillRect(0, 0, width, height);
    revealWidth = Math.ceil((cols * 2) / 24) * 24;
    source.width = revealWidth;
    source.height = rows;
    paintReveal(sourceCtx, revealWidth, rows, revealWidth);
    held = new Set();
    pending.clear();
    revealed = 0;
    maskCtx.clearRect(0, 0, width, height);
    ctx.clearRect(0, 0, width, height);
    grid = [];
    for (let y = 0; y < rows; y += 1) {
      const row = [];
      for (let x = 0; x < cols; x += 1) {
        row.push({expiresAt: 0, isInteractive: y < top[x], isRevealed: false, noiseOffset: 22 * cellNoise(0.5 * x, 0.5 * y)});
      }
      grid.push(row);
    }
  }
  function draw() {
    if (revealed === 0) {
      ctx.clearRect(0, 0, width, height);
      return;
    }
    if (!started) started = performance.now();
    const shift = (((performance.now() - started) / 1000) * 6) % revealWidth;
    const offset = Math.floor(shift);
    ctx.clearRect(0, 0, width, height);
    const first = Math.min(cols, revealWidth - offset);
    ctx.drawImage(source, offset, 0, first, rows, 0, 0, first * CELL, height);
    if (first < cols) ctx.drawImage(source, 0, 0, cols - first, rows, first * CELL, 0, (cols - first) * CELL, height);
    ctx.fillStyle = pattern;
    ctx.fillRect(0, 0, width, height);
    ctx.globalCompositeOperation = "destination-in";
    ctx.drawImage(mask, 0, 0);
    ctx.globalCompositeOperation = "source-over";
  }
  function setCell(y, x, on) {
    const cell = grid[y]?.[x];
    if (!cell || cell.isRevealed === on) return;
    cell.isRevealed = on;
    revealed += on ? 1 : -1;
    maskCtx.clearRect(x * CELL, y * CELL, CELL, CELL);
    if (on) {
      maskCtx.fillStyle = "#ffffff";
      maskCtx.fillRect(x * CELL, y * CELL, CELL, CELL);
    }
    if (revealed === 0) started = 0;
  }
  function expire(y, x) {
    const cell = grid[y]?.[x];
    if (!cell) return;
    cell.expiresAt = performance.now() + 80 + 340 * Math.random();
    pending.add(y * cols + x);
  }
  function tickExpiry() {
    const now = performance.now();
    for (const key of pending) {
      if (held.has(key)) { pending.delete(key); continue; }
      const y = Math.floor(key / cols);
      const x = key % cols;
      const cell = grid[y]?.[x];
      if (cell && !(cell.expiresAt > now)) {
        pending.delete(key);
        setCell(y, x, false);
      }
    }
  }
  function apply(next) {
    for (const key of next) {
      if (held.has(key)) continue;
      const y = Math.floor(key / cols);
      const x = key % cols;
      const cell = grid[y]?.[x];
      if (!cell) continue;
      cell.expiresAt = 0;
      pending.delete(key);
      setCell(y, x, true);
    }
    for (const key of held) if (!next.has(key)) expire(Math.floor(key / cols), key % cols);
    held = next;
  }
  function cellsWithin(px, py, radius) {
    const out = new Set();
    if (radius < 1) return out;
    const reach = radius + 22;
    const x0 = Math.max(0, Math.floor((px - reach) / CELL));
    const x1 = Math.min(cols - 1, Math.ceil((px + reach) / CELL));
    const y0 = Math.max(0, Math.floor((py - reach) / CELL));
    const y1 = Math.min(rows - 1, Math.ceil((py + reach) / CELL));
    for (let y = y0; y <= y1; y += 1) {
      const row = grid[y];
      const cy = CELL * y + 2 - py;
      for (let x = x0; x <= x1; x += 1) {
        const cell = row?.[x];
        if (!cell?.isInteractive) continue;
        const r = radius + cell.noiseOffset;
        if (r <= 0) continue;
        const cx = CELL * x + 2 - px;
        if (cx * cx + cy * cy < r * r) out.add(y * cols + x);
      }
    }
    return out;
  }
  function onMove(event) {
    if (event.pointerType === "touch" || grid.length === 0) return;
    pointerAt = performance.now();
    const rect = canvas.getBoundingClientRect();
    const lx = Math.min(Math.max(event.clientX - rect.left, 0), rect.width);
    const ly = Math.min(Math.max(event.clientY - rect.top, 0), rect.height);
    const px = Math.min(lx * (width / rect.width), width - 1);
    const py = Math.min(ly * (height / rect.height), height - 1);
    const now = performance.now();
    const cell = grid[Math.floor(py / CELL)]?.[Math.floor(px / CELL)];
    let speed = 0;
    if (lastX !== null && lastT !== null) speed = Math.hypot(event.clientX - lastX, event.clientY - lastY) / Math.max(1, now - lastT);
    lastX = event.clientX;
    lastY = event.clientY;
    lastT = now;
    if (!cell?.isInteractive) return;
    clearTimeout(stopTimer);
    boost = Math.min(1, Math.max(boost, 0.2) + 0.42 * Math.min(1, speed / 2.5));
    apply(cellsWithin(px, py, 85 * boost));
    stopTimer = setTimeout(() => { boost = 0; for (const key of held) expire(Math.floor(key / cols), key % cols); held = new Set(); }, 40);
  }
  function onLeave() {
    clearTimeout(stopTimer);
    boost = 0;
    lastX = null;
    lastY = null;
    lastT = null;
    for (const key of held) expire(Math.floor(key / cols), key % cols);
    held = new Set();
  }

  build();
  const observer = new ResizeObserver(() => build());
  observer.observe(art);
  const reduced = window.matchMedia(REDUCED).matches;
  if (reduced) return;
  root.addEventListener("pointermove", onMove);
  root.addEventListener("pointerleave", onLeave);
  loadGsap().then(gsap => {
    if (art.dataset.stopped) return;
    gsap.from(".auth-float", {y: 18, autoAlpha: 0, duration: 0.7, ease: "power2.out"});
    ticker = () => {
      tickExpiry();
      if (performance.now() - pointerAt > 900 && width > 0) {
        const t = performance.now() / 1000;
        apply(cellsWithin(width * (0.5 + 0.32 * Math.sin(t * 0.65)), height * (0.22 + 0.06 * Math.cos(t * 1.1)), 48));
      }
      draw();
    };
    gsap.ticker.add(ticker);
  }).catch(() => {});
}
