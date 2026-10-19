const PATTERN = [
  "#7eb6ea", "#8ec0ee", "#9cc8f0", "#6eabe4",
  "#fff6ee", "#f4d94a", "#ff4500", "#f7d0dc",
  "#1c2430", "#141210", "#262a16", "#1d1a14",
];
const REDUCED = "(prefers-reduced-motion: reduce)";
let loadingGsap;

function loadGsap() {
  if (window.gsap) return Promise.resolve(window.gsap);
  if (loadingGsap) return loadingGsap;
  loadingGsap = new Promise((resolve, reject) => {
    const element = document.createElement("script");
    element.src = "/assets/gsap.min.js";
    element.async = true;
    element.onload = () => resolve(window.gsap);
    element.onerror = () => reject(new Error("Loader motion unavailable"));
    document.head.append(element);
  });
  return loadingGsap;
}

export function paintWait(host, {gsap: gsapLib, label = "", compact = false, brand = false, quiet = false} = {}) {
  if (!host) return () => {};
  host.replaceChildren();
  const root = document.createElement("div");
  root.className = compact ? "wait wait--compact" : "wait";
  if (label) root.setAttribute("aria-label", label);
  if (brand) {
    const mark = document.createElement("span");
    mark.className = "brand-name";
    mark.textContent = "Retract";
    root.append(mark);
  }
  const grid = document.createElement("div");
  grid.className = "wait-grid";
  grid.setAttribute("aria-hidden", "true");
  const cells = PATTERN.map(color => {
    const cell = document.createElement("span");
    cell.style.background = color;
    grid.append(cell);
    return cell;
  });
  root.append(grid);
  if (label && !quiet) {
    const text = document.createElement("p");
    text.className = "wait-label";
    text.textContent = label;
    root.append(text);
  }
  host.append(root);
  let tween;
  const motion = gsapLib || null;
  const animate = gsap => {
    if (!gsap || window.matchMedia(REDUCED).matches || !root.isConnected) return;
    const sky = cells.slice(0, 4);
    const sun = cells.slice(4, 8);
    const ground = cells.slice(8);
    gsap.set(ground, {autoAlpha: 1, scale: 1});
    tween = gsap.timeline({
      repeat: -1,
      yoyo: true,
      repeatDelay: 0.18,
      onRepeat() { if (!root.isConnected) this.kill(); },
    });
    tween.fromTo(sky, {autoAlpha: 0.5}, {autoAlpha: 1, duration: 0.8, ease: "sine.inOut", stagger: 0.08}, 0);
    tween.fromTo(sun, {autoAlpha: 0.45, scale: 0.78}, {autoAlpha: 1, scale: 1, duration: 0.55, ease: "power2.inOut", stagger: 0.07}, 0.12);
  };
  if (motion) animate(motion);
  else loadGsap().then(animate).catch(() => {});
  return () => tween?.kill();
}

export function holdControl(button, label) {
  const previous = button.textContent;
  const hold = document.createElement("span");
  hold.className = "wait-hold";
  const mark = document.createElement("span");
  const text = document.createElement("span");
  text.textContent = label;
  hold.append(mark, text);
  button.replaceChildren(hold);
  const stop = paintWait(mark, {compact: true, quiet: true, label});
  return () => {
    stop();
    button.textContent = previous;
  };
}
