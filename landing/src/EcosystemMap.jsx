import { useEffect, useRef, useState } from "react";
import { gsap, useGSAP } from "./gsap.js";
import { useInView, useReducedMotion } from "./motion.jsx";

const CX = 660;
const CY = 312.5;
const RING = 204;
const BUS = { busX: 388, ringX: 436, y: 315 };
const OUT = { ringX: 884, trunkX: 983, y: 314.5 };
const PANEL = { x: 1010, y: 150, w: 286, h: 300 };

const slot = (c, r) => ({ x: 24 + 56 * c, y: -3 + 56 * r });
const SLOTS = [slot(1, 1), slot(5, 1), slot(3, 2), slot(1, 3), slot(0, 4), slot(2, 4), slot(3, 6), slot(1, 7), slot(4, 7), slot(1, 8), slot(4, 9)];
const EMPTY = [
  slot(-2, 1), slot(-2, 7), slot(-1, 0), slot(-1, 3), slot(-1, 4), slot(-1, 6), slot(-1, 10), slot(0, 3), slot(0, 5),
  slot(0, 9), slot(0, 10), slot(1, 2), slot(1, 4), slot(2, 1), slot(2, 3), slot(2, 6), slot(2, 7), slot(3, 7), slot(3, 9),
  slot(4, -1), slot(4, 0), slot(4, 3), slot(4, 10),
];

const INTEGRATIONS = [
  { key: "codex", name: "Codex", mark: "CDX" },
  { key: "mcp", name: "MCP", mark: "MCP" },
  { key: "falkor", name: "FalkorDB", mark: "FDB" },
  { key: "groq", name: "Groq", mark: "GRQ" },
  { key: "claude", name: "Claude Code", mark: "CC" },
  { key: "postgres", name: "PostgreSQL", mark: "PG" },
  { key: "playwright", name: "Playwright", mark: "PW" },
  { key: "cursor", name: "Cursor", mark: "CUR" },
  { key: "python", name: "Python", mark: "PY" },
  { key: "docker", name: "Docker", mark: "DKR" },
  { key: "vite", name: "Vite", mark: "VTE" },
];

const PRODUCTS = [
  { key: "remember", label: "Remember" },
  { key: "recall", label: "Recall" },
  { key: "supersede", label: "Supersede" },
  { key: "impact", label: "Impact" },
  { key: "evidence", label: "Evidence" },
  { key: "scopes", label: "Scopes" },
  { key: "history", label: "History" },
  { key: "server", label: "MCP server" },
];

const USE_CASES = [
  {
    key: "remember",
    shortLabel: "Remember",
    title: "Remember a scoped decision",
    icon: "M5 4h14v16l-7-4-7 4z",
    integrationKeys: ["codex", "mcp", "falkor"],
    productKeys: ["remember", "evidence", "scopes"],
    status: "Writing F5 to the graph…",
    rows: ["remember(fact, scope)", "scope: web-client/main", "source: PR #212 excerpt", "status: accepted"],
    badges: ["F5 stored", "Evidence attached"],
  },
  {
    key: "recall",
    shortLabel: "Recall",
    title: "Recall the current fact",
    icon: "M10.5 4a6.5 6.5 0 1 1 0 13 6.5 6.5 0 0 1 0-13zm5 11.5L20 20",
    integrationKeys: ["codex", "claude", "mcp", "falkor"],
    productKeys: ["recall", "scopes", "server"],
    status: "Recalling web-client auth…",
    rows: ["recall(\"browser auth\")", "F5 cookie sessions", "source: PR #212", "plan P1 flagged"],
    badges: ["Current fact", "1 warning"],
  },
  {
    key: "correct",
    shortLabel: "Correct",
    title: "Correct a stale fact",
    icon: "M4 12l5 5L20 6",
    integrationKeys: ["groq", "falkor", "postgres"],
    productKeys: ["supersede", "evidence", "history"],
    status: "Classifying the update…",
    rows: ["\"we moved to cookies\"", "classified: confirmed", "F1 bearer tokens", "F5 cookie sessions"],
    badges: ["F1 retired", "F5 accepted"],
  },
  {
    key: "impact",
    shortLabel: "Impact",
    title: "Flag the plans that depend on it",
    icon: "M12 3l9 16H3z M12 10v4 M12 17v.5",
    integrationKeys: ["falkor", "playwright", "vite"],
    productKeys: ["impact", "history", "server"],
    status: "Following DEPENDS_ON…",
    rows: ["MATCH (p)-[:DEPENDS_ON]->(f)", "P1 settings page", "P2 CLI login", "P1 needs review"],
    badges: ["P1 flagged", "P2 unaffected"],
  },
  {
    key: "audit",
    shortLabel: "Audit",
    title: "Audit what changed and why",
    icon: "M12 4a8 8 0 1 1 0 16 8 8 0 0 1 0-16zm0 4v4l3 2",
    integrationKeys: ["postgres", "docker", "python", "cursor"],
    productKeys: ["history", "evidence", "scopes"],
    status: "Reading event U1…",
    rows: ["history(\"F1\")", "U1 superseded by F5", "excerpt kept", "same IDs after restart"],
    badges: ["3 events", "Nothing reseeded"],
  },
];

const STEP_MS = 1400;

function ringAngle(index, count) {
  return -90 + (360 * index) / count;
}

function ringPoint(angle, r = RING) {
  const a = (angle * Math.PI) / 180;
  return { x: CX + r * Math.cos(a), y: CY + r * Math.sin(a) };
}

const round = (v) => Math.round(v * 100) / 100;

function linePath(points) {
  return points
    .filter((p, i) => i === 0 || p.x !== points[i - 1].x || p.y !== points[i - 1].y)
    .map(({ x, y }, i) => `${i === 0 ? "M" : "L"} ${round(x)} ${round(y)}`)
    .join(" ");
}

function tickPath(points, depth = 8, halfWidth = 12, maxInset = 20) {
  const end = points[points.length - 1];
  const prev = [...points].reverse().find((p) => p.x !== end.x || p.y !== end.y);
  if (!prev) return "";
  const len = Math.hypot(end.x - prev.x, end.y - prev.y);
  const ux = (end.x - prev.x) / len;
  const uy = (end.y - prev.y) / len;
  const inset = Math.max(0, Math.min(maxInset, (len - depth) / 2));
  const tip = { x: end.x - ux * inset, y: end.y - uy * inset };
  const back = { x: tip.x - ux * depth, y: tip.y - uy * depth };
  const n = { x: -uy * halfWidth, y: ux * halfWidth };
  return linePath([{ x: back.x + n.x, y: back.y + n.y }, tip, { x: back.x - n.x, y: back.y - n.y }]);
}

function wireFor(cell, taken) {
  const start = { x: cell.x + 56 + 6, y: cell.y + 28 };
  const points = [start];
  let y = start.y;
  const blocker = taken.filter((t) => t.y === cell.y && t.x > cell.x).sort((a, b) => a.x - b.x)[0];
  if (blocker) {
    const dir = BUS.y >= y ? 1 : -1;
    const turnX = blocker.x - 28 > cell.x + 56 ? blocker.x - 28 : start.x + 10;
    let rowTop = cell.y + 56 * dir;
    while (taken.some((t) => t.y === rowTop && t.x + 56 > turnX)) rowTop += 56 * dir;
    y = rowTop + 28;
    points.push({ x: turnX, y: start.y }, { x: turnX, y });
  }
  points.push({ x: BUS.busX, y }, { x: BUS.busX, y: BUS.y }, { x: BUS.ringX, y: BUS.y });
  return points;
}

const placed = ({ x, y, w, h }) => ({
  "--x": x,
  "--y": y,
  ...(w === undefined ? {} : { "--w": w }),
  ...(h === undefined ? {} : { "--h": h }),
});

function Icon({ path }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="square">
      <path d={path} />
    </svg>
  );
}

function HubMark({ className }) {
  return (
    <svg className={className} viewBox="0 0 48 48" aria-hidden="true">
      <rect width="48" height="48" fill="#ff4500" />
      <path d="M15 12h12a8 8 0 0 1 2.5 15.6L35 36h-6.5l-4.8-8H21v8h-6zm6 5v6h5.5a3 3 0 0 0 0-6z" fill="#fff" />
    </svg>
  );
}

function Scene({ useCase, step }) {
  const at = (n) => (step >= n ? " is-in" : "");
  const steps = useCase.rows.length;
  return (
    <>
      <svg className="ecosystemMap__wires" viewBox="0 0 1320 605" aria-hidden="true">
        <path
          className="ecosystemMap__wire"
          d={linePath([
            { x: OUT.ringX, y: OUT.y },
            { x: OUT.trunkX, y: OUT.y },
            { x: PANEL.x, y: OUT.y },
          ])}
        />
        <path className="ecosystemMap__tick" d={tickPath([{ x: OUT.trunkX, y: OUT.y }, { x: PANEL.x, y: OUT.y }])} />
      </svg>
      <div className={`ecosystemMap__agent ecosystemMap__placed ecosystemMap__reveal${at(0)}`} style={placed({ x: 1000, y: 92 })}>
        <svg className="ecosystemMap__agentCursor" viewBox="0 0 20 22" aria-hidden="true">
          <path d="M1 1l17 8-7.5 2.5L8 20z" fill="currentColor" />
        </svg>
        <span className="ecosystemMap__agentLabel">{useCase.status}</span>
      </div>
      <div className="ecosystemMap__browser ecosystemMap__placed" style={placed(PANEL)}>
        <span className="ecosystemMap__browserBar">
          <span />
          <span />
          <span />
        </span>
        <div className="ecosystemMap__code">
          {useCase.rows.map((row, index) => (
            <div key={row} className={`ecosystemMap__codeBlock ecosystemMap__reveal${at(index)}${index === steps - 1 ? " ecosystemMap__codeBlock--last" : ""}`}>
              <span className={index === 0 ? "ecosystemMap__code--agent" : index === steps - 1 ? "ecosystemMap__code--key" : "ecosystemMap__code--ident"}>
                {row}
              </span>
            </div>
          ))}
          <span className={`ecosystemMap__bar ecosystemMap__reveal${at(1)}`} style={{ width: "72%" }} />
          <span className={`ecosystemMap__bar ecosystemMap__reveal${at(2)}`} style={{ width: "54%" }} />
          <span className={`ecosystemMap__bar ecosystemMap__reveal${at(3)}`} style={{ width: "63%" }} />
        </div>
      </div>
      {useCase.badges.map((badge, index) => (
        <div
          key={badge}
          className={`ecosystemMap__badge ecosystemMap__placed ecosystemMap__reveal ecosystemMap__reveal--pop${at(steps - 2 + index)}`}
          style={placed({ x: PANEL.x + PANEL.w / 2, y: PANEL.y + PANEL.h + 18 + index * 44 })}
        >
          <span className="ecosystemMap__badgeText">{badge}</span>
          <span className="ecosystemMap__badgeCheck">
            <svg viewBox="0 0 20 20" aria-hidden="true">
              <path d="M5 10.5l3.2 3.2L15 7" fill="none" stroke="currentColor" strokeWidth="2" />
            </svg>
          </span>
        </div>
      ))}
    </>
  );
}

export default function EcosystemMap() {
  const stageRef = useRef(null);
  const mobileRef = useRef(null);
  const stageInView = useInView(stageRef);
  const mobileInView = useInView(mobileRef);
  const inView = stageInView || mobileInView;
  const reduced = useReducedMotion();
  const [active, setActive] = useState(0);
  const [hovered, setHovered] = useState(null);
  const [pointerPause, setPointerPause] = useState(false);
  const [focusPause, setFocusPause] = useState(false);
  const [autoplay, setAutoplay] = useState(true);
  const [rotation, setRotation] = useState(0);
  const [step, setStep] = useState(0);
  const [sceneKey, setSceneKey] = useState(0);
  const tabRefs = useRef([]);
  const canvasRef = useRef(null);
  const connectedRef = useRef(new Set());

  const count = USE_CASES.length;
  const useCase = USE_CASES[active];
  const lastStep = useCase.rows.length - 1;
  const shownStep = reduced ? lastStep : step;
  const done = shownStep >= lastStep;
  const paused = pointerPause || focusPause;
  const half = 180 / count;
  const from = ringPoint(-90 - half);
  const to = ringPoint(-90 + half);
  const segment = `M ${round(from.x)} ${round(from.y)} A ${RING} ${RING} 0 ${2 * half > 180 ? 1 : 0} 1 ${round(to.x)} ${round(to.y)}`;

  function go(index) {
    setActive(index);
    setStep(0);
    setSceneKey((k) => k + 1);
    setRotation((current) => current + ((((ringAngle(index, count) + 90 - current) % 360) + 540) % 360) - 180);
  }

  function select(index) {
    setAutoplay(false);
    go(index);
  }

  function onKey(event, index) {
    const next = {
      ArrowDown: (index + 1) % count,
      ArrowRight: (index + 1) % count,
      ArrowLeft: (index - 1 + count) % count,
      ArrowUp: (index - 1 + count) % count,
      Home: 0,
      End: count - 1,
    }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    select(next);
    tabRefs.current[next]?.focus();
  }

  useEffect(() => {
    if (reduced || !inView || done) return undefined;
    const timer = setTimeout(() => setStep((s) => s + 1), step === 0 ? Math.min(800, STEP_MS) : STEP_MS);
    return () => clearTimeout(timer);
  }, [done, inView, reduced, sceneKey, step]);

  useEffect(() => {
    if (reduced || !inView || !done || !autoplay || paused) return undefined;
    const timer = setTimeout(() => go((active + 1) % count), 3200);
    return () => clearTimeout(timer);
  }, [active, done, autoplay, count, inView, paused, reduced]);

  useGSAP(
    () => {
      if (reduced || !stageInView) return;
      const previous = connectedRef.current;
      connectedRef.current = new Set(useCase.integrationKeys);
      const fresh = gsap.utils.toArray("[data-wire]", canvasRef.current).filter((el) => !previous.has(el.dataset.wire));
      const tl = gsap.timeline();
      if (fresh.length) {
        tl.fromTo(fresh, { drawSVG: "0%" }, { drawSVG: "100%", duration: 0.5, ease: "power2.inOut", stagger: 0.04 });
      }
      tl.fromTo(
        ".ecosystemMap__scene .ecosystemMap__wire",
        { drawSVG: "0%" },
        { drawSVG: "100%", duration: 0.45, ease: "power2.inOut" },
        fresh.length ? "-=0.15" : 0,
      );
      tl.to(".ecosystemMap__agentLabel", { duration: 0.8, ease: "none", scrambleText: { text: useCase.status, chars: "lowerCase", speed: 0.5 } }, 0);
      tl.to(".ecosystemMap__hubTitle", { duration: 0.6, ease: "none", scrambleText: { text: useCase.title, chars: "upperCase", speed: 0.6 } }, 0);
    },
    { scope: canvasRef, dependencies: [active, sceneKey, stageInView] },
  );

  const placedLogos = INTEGRATIONS.slice(0, SLOTS.length).map((integration, index) => ({ integration, slot: SLOTS[index] }));
  const taken = placedLogos.map(({ slot: s }) => s);
  const connected = placedLogos.filter(({ integration }) => useCase.integrationKeys.includes(integration.key));
  const highlighted = new Set(useCase.productKeys);
  const half4 = Math.ceil(PRODUCTS.length / 2);
  const columns = [PRODUCTS.slice(0, half4), PRODUCTS.slice(half4)];

  return (
    <>
      <div
        className="ecosystemMap__stage"
        ref={stageRef}
        onPointerEnter={() => setPointerPause(true)}
        onPointerLeave={() => setPointerPause(false)}
        onFocus={() => setFocusPause(true)}
        onBlur={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget)) setFocusPause(false);
        }}
      >
        <div className="ecosystemMap__canvas" ref={canvasRef}>
          <svg className="ecosystemMap__wires" viewBox="0 0 1320 605" aria-hidden="true">
            {[...EMPTY, ...SLOTS].map(({ x, y }) => (
              <rect key={`${x}-${y}`} className="ecosystemMap__gridCell" x={x} y={y} width="56" height="56" />
            ))}
            {connected.map(({ integration, slot: s }) => (
              <path key={integration.key} data-wire={integration.key} className="ecosystemMap__wire" d={linePath(wireFor(s, taken))} />
            ))}
            {connected.length > 0 ? (
              <path className="ecosystemMap__tick" d={tickPath([{ x: BUS.busX, y: BUS.y }, { x: BUS.ringX, y: BUS.y }])} />
            ) : null}
            <circle className="ecosystemMap__ringTrack" cx={CX} cy={CY} r={RING} />
            {hovered !== null && hovered !== active ? (
              <path
                className="ecosystemMap__ringSegment ecosystemMap__ringSegment--preview"
                d={segment}
                transform={`rotate(${ringAngle(hovered, count) + 90} ${CX} ${CY})`}
              />
            ) : null}
            {USE_CASES.map((item, index) => (
              <path
                key={item.key}
                className="ecosystemMap__ringHit"
                d={segment}
                transform={`rotate(${ringAngle(index, count) + 90} ${CX} ${CY})`}
                onClick={() => select(index)}
                onPointerEnter={() => setHovered(index)}
                onPointerLeave={() => setHovered(null)}
              />
            ))}
            <g className="ecosystemMap__ringRotor" style={{ transform: `rotate(${rotation}deg)` }}>
              <path className="ecosystemMap__ringSegment" d={segment} />
            </g>
          </svg>

          <ul className="ecosystemMap__logos">
            {placedLogos.map(({ integration, slot: s }) => (
              <li
                key={integration.key}
                className={`ecosystemMap__cell ecosystemMap__placed${useCase.integrationKeys.includes(integration.key) ? " is-connected" : ""}`}
                style={placed({ ...s, w: 56, h: 56 })}
                title={integration.name}
              >
                <span className="ecosystemMap__logo">{integration.mark}</span>
              </li>
            ))}
          </ul>

          <svg className="ecosystemMap__wires ecosystemMap__wires--overlay" viewBox="0 0 1320 605" aria-hidden="true">
            {connected.map(({ integration, slot: s }) => (
              <g key={integration.key}>
                <rect className="ecosystemMap__cellOutline" x={s.x} y={s.y} width="56" height="56" />
                <path className="ecosystemMap__connector" d={`M ${s.x + 56 - 4.25} ${s.y + 28} l 4.25 -4.25 l 4.25 4.25 l -4.25 4.25 Z`} />
              </g>
            ))}
          </svg>

          <div className="ecosystemMap__ringIcons" role="tablist" aria-label="Use cases">
            {USE_CASES.map((item, index) => {
              const p = ringPoint(ringAngle(index, count));
              return (
                <button
                  key={item.key}
                  ref={(node) => {
                    tabRefs.current[index] = node;
                  }}
                  type="button"
                  role="tab"
                  aria-selected={index === active}
                  aria-label={item.title}
                  tabIndex={index === active ? 0 : -1}
                  className={`ecosystemMap__ringIcon ecosystemMap__placed${index === active ? " is-active" : ""}${hovered === index ? " is-hovered" : ""}`}
                  style={placed({ x: p.x - 20, y: p.y - 20, w: 40, h: 40 })}
                  onClick={() => select(index)}
                  onKeyDown={(event) => onKey(event, index)}
                  onPointerEnter={() => setHovered(index)}
                  onPointerLeave={() => setHovered(null)}
                  onFocus={() => setHovered(index)}
                  onBlur={() => setHovered(null)}
                >
                  <Icon path={item.icon} />
                  <span className="ecosystemMap__tooltip" aria-hidden="true">{item.shortLabel}</span>
                </button>
              );
            })}
          </div>

          <div className="ecosystemMap__hub ecosystemMap__placed" role="tabpanel" style={placed({ x: 493, y: 186.5, w: 334 })}>
            <HubMark className="ecosystemMap__hubLogo" />
            <p className="ecosystemMap__hubTitle" key={useCase.key}>{useCase.title}</p>
            <div className="ecosystemMap__products">
              {columns.map((column) => (
                <ul key={column[0].key} className="ecosystemMap__productColumn">
                  {column.map((product) => (
                    <li key={product.key} className={`ecosystemMap__product${highlighted.has(product.key) ? " is-highlighted" : ""}`}>
                      {product.label}
                    </li>
                  ))}
                </ul>
              ))}
            </div>
          </div>

          <div className="ecosystemMap__scene" key={`${useCase.key}-${sceneKey}`} aria-hidden="true">
            <Scene useCase={useCase} step={shownStep} />
          </div>
        </div>
      </div>

      <div className="ecosystemMap__mobile" ref={mobileRef}>
        <div className="ecosystemMap__tabs" role="tablist" aria-label="Use cases">
          {USE_CASES.map((item, index) => (
            <button
              key={item.key}
              type="button"
              role="tab"
              aria-selected={index === active}
              className={`ecosystemMap__tab${index === active ? " is-active" : ""}`}
              onClick={() => select(index)}
            >
              <span className="ecosystemMap__tabIcon"><Icon path={item.icon} /></span>
              {item.shortLabel}
            </button>
          ))}
        </div>
        <div className="ecosystemMap__flowSlide" key={`m-${useCase.key}-${sceneKey}`}>
          <div className="ecosystemMap__flowIntro">
            <p className="ecosystemMap__flowTitle">{useCase.title}</p>
            <ul className="ecosystemMap__chips">
              {PRODUCTS.filter((p) => highlighted.has(p.key)).map((p) => (
                <li key={p.key} className="ecosystemMap__chip">{p.label}</li>
              ))}
            </ul>
          </div>
          <HubMark className="ecosystemMap__flowHub" />
          <div className="ecosystemMap__code ecosystemMap__code--mobile">
            {useCase.rows.map((row, index) => (
              <div key={row} className={`ecosystemMap__codeBlock ecosystemMap__reveal${shownStep >= index ? " is-in" : ""}`}>
                {row}
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
