import { useEffect, useRef, useState } from "react";
import EcosystemMap from "./EcosystemMap.jsx";
import HeroEtchTrail from "./HeroEtchTrail.jsx";
import { AutoIncrementValue, SplitWords } from "./motion.jsx";
import { MOTION_OK, gsap, useGSAP } from "./gsap.js";
import { DocsPage, parseDocsHash } from "./docs.jsx";
import falkordbLogo from "./assets/falkordb.png";
import codexLogo from "./assets/codex.png";
import groqLogo from "./assets/groq.png";
import postgresLogo from "./assets/postgresql.png";
import playwrightLogo from "./assets/playwright.png";

const DASHBOARD = import.meta.env.DEV ? "http://127.0.0.1:8100" : "/dashboard";
const SETTINGS = "http://127.0.0.1:8101/settings";
const DESKTOP_NAV = "(min-width: 70em)";
const SETUP = "python -m pip install -e . && docker compose up -d --wait && retract serve";

const MENUS = [
  {
    label: "Product",
    groups: [
      {
        title: "Memory",
        span: 2,
        rows: 4,
        items: [
          ["Remember", "Store a decision with its scope and source", "#features"],
          ["Recall", "Return the current fact for the task at hand", "#features"],
          ["Supersede", "Replace a fact without deleting its history", "#features"],
          ["Impact", "Flag the plans that depended on the old fact", "#ecosystem-map"],
          ["Evidence", "Keep the excerpt that justified every change", "#spotlight"],
          ["Scopes", "Separate repositories, services, and branches", "#spotlight"],
          ["History", "Query every event that touched a fact", "#ecosystem-map"],
          ["Natural updates", "Classify plain-language corrections with Groq", "#ecosystem-map"],
        ],
      },
      {
        title: "Open source",
        span: 1,
        rows: 2,
        items: [
          ["MCP server", "Give any coding agent memory tools", "#docs/mcp"],
          ["CLI", "remember, recall, and serve from a terminal", "#docs/overview/local-setup"],
        ],
      },
    ],
  },
  {
    label: "Workflow",
    groups: [
      {
        title: "Use cases",
        span: 2,
        rows: 2,
        items: [
          ["Coding agents", "Hand a fresh session the decisions that still hold", "#cards"],
          ["Code review", "Catch plans built on a retired fact", "#cards"],
          ["Migrations", "Track what changed when the stack moved", "#cards"],
          ["Onboarding", "Answer why the project looks the way it does", "#cards"],
        ],
      },
      {
        title: "Demo",
        span: 1,
        rows: 2,
        items: [
          ["Dashboard", "Inspect facts, sources, and plans", DASHBOARD],
          ["Settings app", "The Postgres-backed demo service", SETTINGS],
        ],
      },
    ],
  },
  {
    label: "Resources",
    groups: [
      {
        title: "Learn",
        span: 1,
        rows: 3,
        items: [
          ["Docs", "Architecture, schema, and status", "#docs"],
          ["Verification", "179 tests and a live end-to-end run", "#docs/status"],
          ["Changelog", "What landed in each phase", "#docs/status"],
        ],
      },
    ],
  },
];

const LOGOS = [
  { name: "FalkorDB", src: falkordbLogo, href: "#docs/architecture", wordmark: true },
  { name: "Codex", src: codexLogo, href: "#docs/mcp" },
  { name: "Groq", src: groqLogo, href: "#docs/natural", wordmark: true },
  { name: "PostgreSQL", src: postgresLogo, href: "#docs/infrastructure" },
  { name: "Playwright", src: playwrightLogo, href: "#docs/dashboard" },
];

const FEATURES = [
  {
    title: "Remember API",
    body: "Store a decision with its scope and the source excerpt that proves it. Your agent writes once and every later session can rely on it.",
    media: "remember",
  },
  {
    title: "Recall API",
    body: "Ask for the fact that holds right now. Recall returns the current answer, its evidence, and any plan that needs a second look.",
    media: "recall",
  },
  {
    title: "Correction engine",
    body: "A confirmed change retires the old fact, keeps it in history, and flags the plans that depended on it. Questions and maybes stay pending.",
    media: "correct",
  },
];

const SPOTLIGHT = [
  "Keeps scope per repository and branch",
  "Mirrors how a team actually decides",
  "Adjusts when a decision is reversed",
  "Ignores maybes, questions, and proposals",
  "Works with any MCP client",
];

const CARDS = [
  ["Give agents a memory that lasts", "A new session starts with the decisions that still hold instead of re-reading the whole repository."],
  ["Stop re-explaining the stack", "Record that the account service runs on PostgreSQL once. Every agent recalls it with the source attached."],
  ["Catch plans built on stale facts", "When authentication moves to cookie sessions, the settings plan that assumed bearer tokens is flagged."],
  ["Keep proposals out of the record", "“Should we switch to MongoDB?” is recorded as a proposal. The accepted fact does not change."],
  ["Scope decisions where they belong", "A browser change never touches CLI authentication or the account database."],
  ["Answer “why is it like this?”", "Every fact keeps the excerpt, the event, and the fact it replaced."],
  ["Survive restarts without reseeding", "FalkorDB persists the graph. The same IDs come back after the container restarts."],
  ["Correct memory in plain language", "Groq classifies a sentence like “we moved to cookies” and applies it only when it is confirmed."],
];

const STEPS = [
  ["Start the stack", "Install the package, bring up FalkorDB and Postgres with Docker, and run the memory server."],
  ["Connect your agent", "Point Codex, Claude Code, or Cursor at the MCP server so it can remember and recall."],
  ["Make your first correction", "Change a decision in plain language and watch the old fact retire and the plan get flagged."],
];

const STATS = [
  ["Python tests", 179, "u-accent-bg--primary-pink"],
  ["JS checks", 22, "u-accent-bg--pale-gray"],
  ["Live updates classified", 16, "u-accent-bg--pale-yellow"],
  ["Mocked calls", null, "u-accent-bg--pale-blue"],
];

const FOOTER = [
  ["Memory", [["Remember", "#docs/product"], ["Recall", "#docs/architecture/retrieval"], ["Supersede", "#docs/architecture/update-pipeline"], ["Impact", "#docs/queries"], ["History", "#docs/queries/current-context-history-and-evidence"], ["Evidence", "#docs/architecture"]]],
  ["Workflow", [["Coding agents", "#docs/mcp"], ["Code review", "#docs/product"], ["Migrations", "#docs/demo"], ["Onboarding", "#docs/product"]]],
  ["Developers", [["Docs", "#docs"], ["MCP server", "#docs/mcp"], ["CLI", "#docs/overview/local-setup"], ["Verification", "#docs/status"]]],
  ["Demo", [["Dashboard", DASHBOARD], ["Settings", SETTINGS], ["Run locally", "#docs/overview/local-setup"]]],
];

const MENU_ICON_PATHS = {
  Remember: "M17 3H7c-1.1 0-2 .9-2 2v16l7-3 7 3V5c0-1.1-.9-2-2-2z",
  Recall: "M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z",
  Supersede: "M6.99 11 3 15l3.99 4v-3H14v-2H6.99v-3zM21 9l-3.99-4v3H10v2h7.01v3L21 9z",
  Impact: "M14.4 6 14 4H5v17h2v-7h5.6l.4 2h7V6z",
  Evidence: "M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z",
  Scopes: "M11.99 18.54 4.62 12.81 3 14.07l9 7 9-7-1.63-1.27-7.38 5.74zM12 16l7.36-5.73L21 9l-9-7-9 7 1.63 1.27L12 16z",
  History: "M13 3a9 9 0 0 0-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42A8.95 8.95 0 0 0 13 21a9 9 0 0 0 0-18zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8z",
  "Natural updates": "M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z",
  "MCP server": "M17 16l-4-4V8.82A3 3 0 0 0 12 3a3 3 0 0 0-1 5.82V12l-4 4H3v5h5v-3.05l4-4.2 4 4.2V21h5v-5z",
  CLI: "M20 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm0 14H4V8h16zm-10-1 1.41-1.41L8.83 13l2.58-2.59L10 9l-4 4zm6 0h-4v-2h4z",
  "Coding agents": "M20 9V7a2 2 0 0 0-2-2h-3a3 3 0 0 0-6 0H6a2 2 0 0 0-2 2v2a3 3 0 0 0 0 6v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4a3 3 0 0 0 0-6zM9 11.5A1.5 1.5 0 1 1 10.5 13 1.5 1.5 0 0 1 9 11.5zM16 17H8v-2h8zm-.5-4A1.5 1.5 0 1 1 17 11.5 1.5 1.5 0 0 1 15.5 13z",
  "Code review": "M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 14v-2.47l6.88-6.88c.2-.2.51-.2.71 0l1.77 1.77c.2.2.2.51 0 .71L8.47 14zm12 0h-7.5l2-2H18z",
  Migrations: "M16 6l2.29 2.29-4.88 4.88-4-4L2 16.59 3.41 18l6-6 4 4 6.3-6.29L22 12V6z",
  Onboarding: "M5 13.18v4L12 21l7-3.82v-4L12 17zm7-10.18L1 9l11 6 9-4.91V17h2V9z",
  Dashboard: "M3 13h8V3H3zm0 8h8v-6H3zm10 0h8V11h-8zm0-18v6h8V3z",
  "Settings app": "M19.14 12.94c.04-.31.06-.63.06-.94s-.02-.63-.06-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.49.49 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.48.48 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.49.49 0 0 0-.59.22L2.74 8.87a.49.49 0 0 0 .12.61l2.03 1.58c-.04.31-.06.63-.06.94s.02.63.06.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32a.49.49 0 0 0-.12-.61zM12 15.6A3.6 3.6 0 1 1 15.6 12 3.6 3.6 0 0 1 12 15.6z",
  Docs: "M21 5c-1.11-.35-2.33-.5-3.5-.5-1.95 0-4.05.4-5.5 1.5-1.45-1.1-3.55-1.5-5.5-1.5S2.45 4.9 1 6v14.65c0 .25.25.5.5.5.1 0 .15-.05.25-.05C3.1 20.45 5.05 20 6.5 20c1.95 0 4.05.4 5.5 1.5 1.35-.85 3.8-1.5 5.5-1.5 1.65 0 3.35.3 4.75 1.05.1.05.15.05.25.05.25 0 .5-.25.5-.5V6c-.6-.45-1.25-.75-2-1zm0 13.5c-1.1-.35-2.3-.5-3.5-.5-1.7 0-4.15.65-5.5 1.5V8c1.35-.85 3.8-1.5 5.5-1.5 1.2 0 2.4.15 3.5.5z",
  Verification: "M23 12l-2.44-2.79.34-3.69-3.61-.82-1.89-3.2L12 2.96 8.6 1.5 6.71 4.69 3.1 5.5l.34 3.7L1 12l2.44 2.79-.34 3.7 3.61.82 1.89 3.19 3.4-1.46 3.4 1.46 1.89-3.19 3.61-.82-.34-3.69zm-12.91 4.72-3.8-3.81 1.48-1.48 2.32 2.33 5.85-5.87 1.48 1.48z",
  Changelog: "M3 13h2v-2H3zm0 4h2v-2H3zm0-8h2V7H3zm4 4h14v-2H7zm0 4h14v-2H7zM7 7v2h14V7z",
};

function MenuIcon({ name }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="currentColor" d={MENU_ICON_PATHS[name] || MENU_ICON_PATHS.Docs} />
    </svg>
  );
}

function Chevron() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M9.4 18 8 16.6l4.6-4.6L8 7.4 9.4 6l6 6z" fill="currentColor" />
    </svg>
  );
}

function CopyIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M9 18q-.8 0-1.4-.6T7 16V4q0-.8.6-1.4T9 2h9q.8 0 1.4.6T20 4v12q0 .8-.6 1.4T18 18zm0-2h9V4H9zm-4 6q-.8 0-1.4-.6T3 20V6h2v14h11v2z" fill="currentColor" />
    </svg>
  );
}

function Wordmark() {
  return <span className="brand-name">Retract</span>;
}

function Nav() {
  const [open, setOpen] = useState(false);
  const [openIndex, setOpenIndex] = useState(null);

  useEffect(() => {
    document.documentElement.classList.toggle("nav-menu-open", open);
  }, [open]);

  useEffect(() => {
    const close = (event) => {
      if (event.key === "Escape") {
        setOpenIndex(null);
        setOpen(false);
      }
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, []);

  return (
    <header className="nav" role="banner">
      <a className="skip-link" href="#main">Skip to content</a>
      <div className="nav__container">
        <a className="nav__branding" href="#top">
          <Wordmark />
        </a>
        <div className="nav__menu-mobile-buttons">
          <button
            className="nav__menu-btn"
            type="button"
            aria-controls="nav__menu"
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            <span className="is-visually-hidden">Navigation</span>
            <svg className="menu-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18M3 12h18M3 18h18" stroke="currentColor" strokeWidth="2" /></svg>
            <svg className="close-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5l14 14M19 5L5 19" stroke="currentColor" strokeWidth="2" /></svg>
          </button>
        </div>
        <nav className="nav__menu" id="nav__menu" aria-label="main">
          <ul className="nav__list nav__list--primary">
            {MENUS.map((menu, index) => {
              const wide = menu.groups.length > 1;
              const columns = menu.groups.reduce((n, g) => n + g.span, 0);
              return (
                <li
                  key={menu.label}
                  className={`nav__item${wide ? " nav__item--wide" : ""}${openIndex === index ? " is-subnav-open" : ""}`}
                  onMouseEnter={() => {
                    if (window.matchMedia(DESKTOP_NAV).matches) setOpenIndex(index);
                  }}
                  onMouseLeave={() => {
                    if (window.matchMedia(DESKTOP_NAV).matches) setOpenIndex((v) => (v === index ? null : v));
                  }}
                >
                  <button
                    type="button"
                    className="nav__item__button btn btn--nav-primary"
                    aria-expanded={openIndex === index}
                    aria-controls={`menu-${index}`}
                    onClick={() => setOpenIndex((v) => (v === index ? null : index))}
                  >
                    {menu.label}
                    <svg className="nav__subnav-icon" viewBox="0 0 12 8" aria-hidden="true"><path d="M1 1l5 5 5-5" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>
                  </button>
                  <div className={`nav__subnav${wide ? " nav__subnav--has-wide-layout" : ""}`}>
                    <ul
                      id={`menu-${index}`}
                      className={`nav__subnav__list${wide ? " nav__subnav__list--group-wide" : ""}`}
                      style={{ "--nav-subnav-columns": columns }}
                    >
                      {menu.groups.map((group) => (
                        <li
                          key={group.title}
                          className="nav__subnav__group"
                          style={{ "--nav-subnav-group-span": group.span, "--nav-subnav-group-rows": group.rows }}
                        >
                          <span className="nav__subnav__eyebrow type-eyebrow-1">{group.title}</span>
                          <ul className={`nav__subnav__group-list${group.span > 1 ? " nav__subnav__group-list--columns" : ""}`}>
                            {group.items.map(([title, subtitle, href]) => (
                              <li key={title}>
                                <a
                                  className="nav__subnav__link nav__subnav__link--subtitle btn btn--nav-primary btn--menu-item"
                                  href={href}
                                  onClick={() => {
                                    setOpenIndex(null);
                                    setOpen(false);
                                  }}
                                >
                                  <span className="btn__icon" aria-hidden="true">
                                    <MenuIcon name={title} />
                                  </span>
                                  <span className="stack">
                                    <span className="btn__text">{title}</span>
                                    <span className="btn__subtitle">{subtitle}</span>
                                  </span>
                                </a>
                              </li>
                            ))}
                          </ul>
                        </li>
                      ))}
                    </ul>
                  </div>
                </li>
              );
            })}
            <li className="nav__item">
              <a className="nav__item__button btn btn--nav-primary" href="#docs" onClick={() => setOpen(false)}>Docs</a>
            </li>
          </ul>
        </nav>
        <ul className="nav__list nav__list--secondary">
          <li className="nav__item nav__item--cta nav__item--login-desktop">
            <a className="btn btn--secondary" href={DASHBOARD}>Dashboard</a>
          </li>
          <li className="nav__item nav__item--cta nav__item--login-desktop">
            <a className="btn btn--secondary" href={SETTINGS}>Settings</a>
          </li>
          <li className="nav__item nav__item--cta">
            <a className="btn btn--chevron" href="#docs/overview/local-setup">
              <span className="btn__text">Run locally</span>
              <span className="btn__icon"><Chevron /></span>
            </a>
          </li>
        </ul>
      </div>
    </header>
  );
}

function CopyButton() {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="btn btn--quaternary btn--icon-hover"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(SETUP);
          setCopied(true);
          setTimeout(() => setCopied(false), 1600);
        } catch {
          setCopied(false);
        }
      }}
    >
      <span className="btn__text">{copied ? "Copied to clipboard" : "Copy setup for your agent"}</span>
      <span className="btn__icon"><CopyIcon /></span>
    </button>
  );
}

function FeatureMedia({ kind }) {
  const ref = useRef(null);

  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add(MOTION_OK, () => {
        const items = gsap.utils.toArray(":scope > .mock > *", ref.current);
        const scrambles = gsap.utils.toArray("[data-scramble]", ref.current);
        const tl = gsap.timeline({ repeat: -1, repeatDelay: 0.4, paused: true });
        tl.from(items, { autoAlpha: 0, y: 6, duration: 0.45, ease: "power3.out", stagger: 0.45 });
        scrambles.forEach((el) => {
          tl.to(
            el,
            { duration: 0.9, ease: "none", scrambleText: { text: el.textContent, chars: "01/_·#", speed: 0.6 } },
            items.indexOf(el.closest(".mock > *")) * 0.45,
          );
        });
        tl.to(items, { autoAlpha: 0, duration: 0.35, ease: "power1.in" }, "+=3.2");
        const observer = new IntersectionObserver(([entry]) => (entry.isIntersecting ? tl.play() : tl.pause()));
        observer.observe(ref.current);
        return () => observer.disconnect();
      });
    },
    { scope: ref },
  );

  return (
    <div ref={ref} className="mockStage">
      <MockContent kind={kind} />
    </div>
  );
}

function MockContent({ kind }) {
  if (kind === "remember") {
    return (
      <div className="mock mock--remember">
        <p className="mock__head" data-scramble>remember → web-client/main</p>
        {[
          ["F5 Browser auth uses HTTP-only cookie sessions", "source: PR #212 · “we moved the browser client to cookies”"],
          ["F3 Account service stores users in PostgreSQL", "source: ADR-004 · accepted"],
          ["F2 CLI keeps bearer tokens for device login", "scope: cli/main · unchanged"],
          ["P1 Settings page reads the session from a cookie", "depends on: F5"],
        ].map(([title, line], index) => (
          <div className="mock__row" key={title} style={{ "--i": index }}>
            <span className="mock__title">{title}</span>
            <span className="mock__line">{line}</span>
          </div>
        ))}
      </div>
    );
  }
  if (kind === "recall") {
    return (
      <div className="mock mock--recall">
        <div className="mock__row mock__row--query" style={{ "--i": 0 }}>
          <span className="mock__title" data-scramble>recall(“how does the browser authenticate?”)</span>
          <span className="mock__line">scope: web-client/main</span>
        </div>
        <p className="mock__head" style={{ "--i": 1 }}>Current fact from the graph</p>
        <div className="mock__panel" style={{ "--i": 2 }}>
          <p>● F5</p>
          <p>Browser auth uses HTTP-only cookie sessions.</p>
          <p>evidence: PR #212 excerpt</p>
          <p className="mock__warn">warning: plan P1 depended on F1 and needs review</p>
        </div>
      </div>
    );
  }
  return (
    <div className="mock mock--correct">
      <div className="mock__row" style={{ "--i": 0 }}>
        <span className="mock__title">update: “we moved the browser client to cookie sessions”</span>
        <span className="mock__line">classified by Groq: confirmed · prompt v2</span>
      </div>
      <div className="mock__diff" style={{ "--i": 1 }}>
        <p className="mock__old">− F1 Browser auth uses bearer tokens</p>
        <p className="mock__new" data-scramble>+ F5 Browser auth uses HTTP-only cookie sessions</p>
      </div>
      <div className="mock__row" style={{ "--i": 2 }}>
        <span className="mock__title">P1 Settings page · needs review</span>
        <span className="mock__line">followed DEPENDS_ON from F1 · event U1 recorded</span>
      </div>
    </div>
  );
}

function FeatureStack() {
  const ref = useRef(null);
  const headerRef = useRef(null);

  useEffect(() => {
    const section = ref.current;
    const header = headerRef.current;
    if (!section || !header) return undefined;
    const observer = new ResizeObserver(() => {
      section.style.setProperty("--header-height", `${header.offsetHeight}px`);
    });
    observer.observe(header);
    return () => observer.disconnect();
  }, []);

  return (
    <section className="featureStack section" id="features" ref={ref} style={{ "--feature-count": FEATURES.length, "--feature-media-aspect-ratio": 2.2 }}>
      <div className="featureStack__container grid">
        <div className="textLockUp featureStack__textLockUp u-accent-fg--red">
          <div className="textLockUp__content" ref={headerRef}>
            <h2 className="textLockUp__title type-heading-2">
              See what <span className="u-accent">memory can do</span> for your agents.
            </h2>
            <div className="textLockUp__subhead type-subhead-2">
              <p>From the first decision to the next correction, Retract keeps agents working from facts that still hold.</p>
            </div>
          </div>
        </div>
        <ul className="featureStack__list">
          {FEATURES.map((feature, index) => (
            <li key={feature.title} style={{ "--index": index }}>
              <section className="feature feature--wide">
                <div className="grid">
                  <figure className="feature__media">
                    <div className="frame">
                      <FeatureMedia kind={feature.media} />
                    </div>
                  </figure>
                  <div className="feature__content">
                    <h3 className="textLockUp__title">{feature.title}</h3>
                    <p className="textLockUp__body">{feature.body}</p>
                    <a className="btn btn--compact" href={DASHBOARD}><span className="btn__text">Try it locally</span></a>
                  </div>
                </div>
              </section>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function Divider({ line = 1, square = 12, squareColor = "var(--color-primary-yellow)", lineAlign = "start", squareAlign = "end" }) {
  return (
    <div className="divider-wrap" aria-hidden="true">
      <div className="divider">
        <div className="divider-flex">
          {Array.from({ length: 13 }, (_, i) => (
            <div className="divider__item" key={i} />
          ))}
        </div>
        <div className="divider-grid">
          <div className="divider__line" style={{ "--divider-column": line, "--divider-block-align": lineAlign, "--divider-color": "var(--color-primary-gray)" }} />
          <div className="divider__square" style={{ "--divider-column": square, "--divider-block-align": squareAlign, "--divider-color": squareColor }} />
        </div>
      </div>
    </div>
  );
}

function Desktop() {
  return (
    <svg viewBox="0 0 914 413" role="img" aria-label="Illustration of a desktop computer reading a fact from memory">
      <rect x="250" y="40" width="420" height="270" fill="#e1e9f2" stroke="#000" strokeWidth="6" />
      <rect x="272" y="62" width="376" height="226" fill="#fff" />
      <rect x="296" y="88" width="140" height="22" fill="#ff4500" />
      <rect x="296" y="124" width="300" height="12" fill="#000" />
      <rect x="296" y="146" width="236" height="12" fill="#98afd3" />
      <rect x="296" y="182" width="120" height="58" fill="#000" />
      <rect x="430" y="182" width="120" height="58" fill="#c4edff" />
      <rect x="564" y="182" width="60" height="58" fill="#fffacd" />
      <rect x="400" y="310" width="120" height="40" fill="#c5d3e8" />
      <rect x="330" y="350" width="260" height="20" fill="#000" />
      <rect x="120" y="370" width="680" height="24" fill="#c5d3e8" />
      <rect x="700" y="250" width="70" height="120" fill="#fff" stroke="#000" strokeWidth="6" />
      <rect x="716" y="270" width="38" height="8" fill="#ff4500" />
      <rect x="716" y="290" width="38" height="8" fill="#000" />
    </svg>
  );
}

const ART = [
  ["#c4edff", "#5a78af", "#ff4500"],
  ["#fffacd", "#000", "#98afd3"],
  ["#ffdfe5", "#ff4500", "#000"],
  ["#e2e9f3", "#000", "#ff4500"],
  ["#a4f9c6", "#000", "#5a78af"],
  ["#e1eb80", "#ff4500", "#000"],
  ["#ffbaff", "#000", "#fff"],
  ["#c4edff", "#ff4500", "#000"],
];

function CardArt({ index, tall = false }) {
  const [bg, a, b] = ART[index % ART.length];
  const w = 294;
  const h = tall ? 330 : 270;
  const cells = [];
  for (let y = 0; y < 7; y += 1) {
    for (let x = 0; x < 7; x += 1) {
      const v = Math.sin((x + 1) * (index + 3) * 1.7 + (y + 2) * 2.3) * 0.5 + 0.5;
      if (v > 0.55) cells.push({ x, y, fill: v > 0.82 ? b : a });
    }
  }
  const size = 24;
  const ox = (w - size * 7) / 2;
  const oy = (h - size * 7) / 2;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <rect width={w} height={h} fill={bg} />
      {cells.map(({ x, y, fill }) => (
        <rect key={`${x}-${y}`} x={ox + x * size} y={oy + y * size} width={size - 2} height={size - 2} fill={fill} />
      ))}
    </svg>
  );
}

function StatsArt() {
  const blocks = [];
  for (let x = 0; x < 34; x += 1) {
    const height = Math.round(6 + 5 * Math.sin(x * 0.45) + 3 * Math.sin(x * 1.3 + 1));
    for (let y = 0; y < height; y += 1) {
      const shade = (x * 7 + y * 3) % 5;
      blocks.push({ x, y: 21 - y, fill: shade === 0 ? "#98afd3" : shade === 1 ? "#ffc0cb" : "#e1e9f2" });
    }
  }
  return (
    <svg viewBox="0 0 1306 800" preserveAspectRatio="xMaxYMax slice" aria-hidden="true">
      <rect width="1306" height="800" fill="#fff" />
      <g transform="translate(560 -80)">
        {blocks.map(({ x, y, fill }) => (
          <rect key={`${x}-${y}`} x={x * 22} y={y * 40} width="21" height="39" fill={fill} />
        ))}
      </g>
    </svg>
  );
}

export default function App() {
  const [hash, setHash] = useState(() => window.location.hash);
  const docs = parseDocsHash(hash);

  useEffect(() => {
    const sync = () => setHash(window.location.hash);
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  useEffect(() => {
    if (docs) return undefined;
    const id = hash.replace(/^#/, "");
    if (!id) return undefined;
    const frame = requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView());
    return () => cancelAnimationFrame(frame);
  }, [docs, hash]);

  return (
    <>
      <Nav />
      {docs ? <DocsPage slug={docs.slug} anchor={docs.anchor} /> : <main id="main" className="wrapper">
        <section className="hero" id="top">
          <div className="hero__media">
            <HeroEtchTrail />
          </div>
          <div className="hero__content">
            <div className="textLockUp textLockUp--center">
              <div className="textLockUp__content">
                <h1 className="textLockUp__title type-heading-1">
                  <span className="u-accent">Give your agents a memory they can correct.</span>
                </h1>
                <div className="textLockUp__subhead type-subhead-2">
                  <p>Retract keeps project decisions scoped, evidenced, and current for every agent session</p>
                </div>
                <div className="textLockUp__cta">
                  <div className="btn-row">
                    <a className="btn btn--chevron" href={DASHBOARD}>
                      <span className="btn__text">Open dashboard</span>
                      <span className="btn__icon"><Chevron /></span>
                    </a>
                    <CopyButton />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="logoCloud section" aria-label="Local stack">
          <p className="logoCloud__eyebrow type-eyebrow-plain">The local stack this demo actually runs on</p>
          <ul className="logoCloud__row">
            {LOGOS.map((logo) => (
              <li key={logo.name}>
                <a className="logoCloud__item" href={logo.href}>
                  <img className={logo.wordmark ? "is-wordmark" : undefined} src={logo.src} alt="" />
                  <span className={logo.wordmark ? "is-visually-hidden" : "logoCloud__name"}>{logo.name}</span>
                </a>
              </li>
            ))}
          </ul>
        </section>

        <FeatureStack />

        <Divider />

        <section className="spotlight" id="spotlight">
          <div className="spotlight__content grid">
            <div className="spotlight__text">
              <div className="spotlight__header">
                <h2 className="textLockUp__title type-heading-2" style={{ "--color-split-words-bg": "var(--color-primary-yellow)" }}>
                  <SplitWords text="Treat project memory like a database." />
                </h2>
                <div className="textLockUp__body type-body-3">
                  <p>Decisions are the project’s real interface.</p>
                  <p>Now your agents can read and correct them without guessing.</p>
                </div>
              </div>
              <div className="spotlight__list type-chip">
                <h3 className="spotlight__list-title">
                  Your <span className="u-accent">BRIDGE</span> between <span className="u-accent">AGENTS</span> and <span className="u-accent">DECISIONS</span>
                </h3>
                <ul className="spotlight__items">
                  {SPOTLIGHT.map((item) => (
                    <li className="spotlight__item" key={item}><p>{item}</p></li>
                  ))}
                </ul>
              </div>
            </div>
            <figure className="spotlight__media">
              <Desktop />
            </figure>
          </div>
          <div className="spotlight__dividers grid" aria-hidden="true">
            <div className="spotlight-divider-left">
              <div className="spotlight-divider-bottom" />
            </div>
          </div>
        </section>

        <section className="multicardV2 section" id="cards">
          <div className="multicardV2__container grid">
            <div className="textLockUp u-accent-fg--red">
              <h2 className="textLockUp__title type-heading-2">
                Anything <span className="u-accent">you decide</span>, your agent remembers.
              </h2>
              <div className="textLockUp__subhead type-subhead-2">
                <p>Skip the re-explaining. Keep what’s true in one place.</p>
              </div>
            </div>
            <div className="multicardV2__cards grid grid--4up">
              {CARDS.map(([title, body], index) => (
                <article className="cardStandard" key={title}>
                  <div className="cardStandard__media frame"><CardArt index={index} /></div>
                  <div className="cardStandard__textLockup">
                    <h3 className="cardStandard__title type-subhead-3">{title}</h3>
                    <p className="cardStandard__body type-body-3-tight">{body}</p>
                    <a className="btn btn--compact cardStandard__cta" href={DASHBOARD}><span className="btn__text">Get started</span></a>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="section ecosystemMap" id="ecosystem-map">
          <div className="ecosystemMap__container grid">
            <div className="textLockUp ecosystemMap__textLockUp">
              <h2 className="textLockUp__title type-heading-2">Every agent, every tool, one record of what’s true.</h2>
            </div>
            <EcosystemMap />
          </div>
        </section>

        <section className="multicardV2 section" id="setup">
          <div className="multicardV2__container grid">
            <div className="textLockUp u-accent-fg--red">
              <h2 className="textLockUp__title type-heading-2">
                Zero setup. <span className="u-accent">Real memory.</span>
              </h2>
              <div className="textLockUp__subhead type-subhead-2">
                <p>Start the stack, connect your agent, and make your first correction</p>
              </div>
            </div>
            <div className="multicardV2__cards grid grid--3up">
              {STEPS.map(([title, body], index) => (
                <article className="cardStandard" key={title}>
                  <div className="cardStandard__media frame frame--step"><CardArt index={index + 2} tall /></div>
                  <div className="cardStandard__textLockup">
                    <h3 className="cardStandard__title type-subhead-3">{title}</h3>
                    <p className="cardStandard__subhead type-subhead-4">{body}</p>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="section ctaBanner">
          <div className="ctaBanner__container">
            <div className="textLockUp textLockUp--center ctaBanner__textLockUp">
              <h2 className="textLockUp__title type-heading-2">
                Every decision, <span className="u-accent">current and evidenced</span>.
              </h2>
              <div className="textLockUp__body type-body-3">
                <p>No stale facts for your agents.<br />No guessing about what changed.</p>
              </div>
              <div className="textLockUp__cta">
                <div className="btn-row">
                  <a className="btn btn--chevron" href={DASHBOARD}>
                    <span className="btn__text">Open dashboard</span>
                    <span className="btn__icon"><Chevron /></span>
                  </a>
                  <a className="btn btn--secondary btn--chevron" href={SETTINGS}>
                    <span className="btn__text">See the demo</span>
                    <span className="btn__icon"><Chevron /></span>
                  </a>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="stats" data-variant="featured" id="stats">
          <div className="stats__container grid">
            <div className="stats__content grid">
              <div className="stats__featured-text">
                <div className="stats__textLockUp-wrapper">
                  <h3 className="textLockUp__title type-heading-2" style={{ "--color-split-words-bg": "var(--color-pale-pink)" }}>
                    <SplitWords text="Don’t re-explain the project. Remember it." />
                  </h3>
                </div>
              </div>
              <div className="stats__featured-stat">
                <p className="textLockUp__eyebrow u-accent-shape--magenta type-eyebrow-1"><span>automated checks on every change</span></p>
                <p className="stats-featured__value">
                  <span className="text-fit__content">
                    <AutoIncrementValue value={201} />
                    <span>+ checks passing</span>
                  </span>
                </p>
              </div>
            </div>
            <div className="stats__media"><StatsArt /></div>
          </div>
        </section>

        <Divider line={10} square={3} squareColor="var(--color-primary-magenta)" lineAlign="end" squareAlign="end" />

        <section className="stats" data-variant="grid">
          <div className="stats__container grid">
            <div className="stats__items-text">
              <h3 className="textLockUp__title type-heading-2">Verified on a real machine</h3>
            </div>
            <dl className="stats__items grid grid--4up">
              {STATS.map(([title, value, accent], index) => (
                <div className={`stats-item ${accent}`} key={title}>
                  <dt className="stats-item__title type-eyebrow-1">{title}</dt>
                  <dd className="stats-item__value">
                    {value === null ? "None" : <AutoIncrementValue value={value} index={index} hidden />}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </section>
      </main>}

      <footer className="site-footer section">
        <div className="site-footer__grid grid">
          <div className="site-footer__left">
            <a className="site-footer__branding brand-name" href="#top">Retract</a>
          </div>
          <nav className="site-footer__right footer-nav" aria-label="Footer">
            {FOOTER.map(([title, links]) => (
              <div className="footer-nav__column" key={title}>
                <h3 className="footer-nav__list-title type-eyebrow-1">{title}</h3>
                <ul className="footer-nav__list">
                  {links.map(([label, href]) => (
                    <li key={label}><a className="btn btn--nav-footer" href={href}>{label}</a></li>
                  ))}
                </ul>
              </div>
            ))}
          </nav>
          <div className="footer-meta">
            <p>Local only. No account is required for structured memory.</p>
            <p className="footer-meta__code">{SETUP}</p>
          </div>
        </div>
      </footer>
    </>
  );
}
