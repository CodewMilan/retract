const DASHBOARD = "http://127.0.0.1:8100";
const SETTINGS = "http://127.0.0.1:8101/settings";

const NAV = [
  ["Product", "#product"],
  ["Workflow", "#workflow"],
  ["Graph", "#graph"],
  ["Demo", "#demo"],
  ["Docs", "#docs"],
];

const STACK = ["FalkorDB", "Codex", "MCP", "Groq", "PostgreSQL", "Playwright"];

const POINTS = [
  ["Confirmed only.", "A question, a maybe, or an untrusted note is recorded and left pending. It never becomes the accepted fact."],
  ["Scope stays put.", "The browser client can change without touching CLI authentication or the account database."],
  ["Evidence stays attached.", "The source excerpt, the retired fact, and the event that replaced it remain queryable."],
  ["The graph finds the plan.", "Impact follows a stored DEPENDS_ON edge. There is no hardcoded list of affected plans."],
];

const CARDS = [
  {
    quote: "Browser authentication moved from bearer tokens to HTTP-only cookie sessions. The settings plan that depended on the old fact needs review.",
    label: "web-client/main",
    meta: "F1 retired · F5 accepted · P1 flagged",
  },
  {
    quote: "“Should we switch the account database to MongoDB?” stays a proposal. PostgreSQL remains the accepted fact.",
    label: "account-service/main",
    meta: "F3 unchanged",
  },
  {
    quote: "A later session calls recall and receives the current fact, its source, and the plan warning. Nothing is reseeded.",
    label: "Fresh session",
    meta: "Same IDs after restart",
  },
];

const FOOTER = [
  ["Memory", [["Remember", "#workflow"], ["Recall", "#demo"], ["History", "#graph"], ["Updates", "#workflow"]]],
  ["Graph", [["Facts", "#graph"], ["Sources", "#graph"], ["Plans", "#demo"], ["Events", "#graph"]]],
  ["Demo", [["Dashboard", DASHBOARD], ["Settings", SETTINGS], ["Seed", "#docs"], ["Restart", "#docs"]]],
  ["Project", [["Docs", "#docs"], ["Product", "#product"], ["Workflow", "#workflow"], ["Status", "#docs"]]],
];

function peaks(cols) {
  return Array.from({ length: cols }, (_, x) => {
    const t = x / (cols - 1);
    const ridge =
      18 * Math.sin(t * Math.PI) +
      6 * Math.sin(t * 11.3 + 0.6) +
      3.2 * Math.sin(t * 23 + 1.4);
    return Math.max(4, Math.round(22 - ridge));
  });
}

function Mountain() {
  const cols = 96;
  const rows = 36;
  const top = peaks(cols);
  const cells = [];
  for (let x = 0; x < cols; x += 1) {
    for (let y = top[x]; y < rows; y += 1) {
      const depth = y - top[x];
      const shade = (x * 17 + y * 13) % 7;
      let fill = "#1b140e";
      if (depth < 2 && shade > 3) fill = "#f3d48a";
      else if (depth < 5) fill = shade % 2 ? "#e07a22" : "#c45a18";
      else if (depth < 10) fill = shade > 4 ? "#8a3e12" : "#5c2c10";
      else if (shade === 0) fill = "#3a2414";
      cells.push(<rect key={`${x}-${y}`} x={x} y={y} width="1" height="1" fill={fill} />);
    }
  }
  const clouds = [
    [8, 6, 10, 3],
    [14, 8, 6, 2],
    [70, 5, 12, 3],
    [82, 9, 7, 2],
  ];
  return (
    <svg className="mountain" viewBox={`0 0 ${cols} ${rows}`} preserveAspectRatio="none" role="img" aria-label="Pixel ridge under the hero">
      {clouds.map(([x, y, w, h]) => (
        <rect key={`${x}-${y}`} x={x} y={y} width={w} height={h} fill="#f7fbff" opacity="0.85" />
      ))}
      {cells}
    </svg>
  );
}

function Monitor() {
  return (
    <svg className="monitor" viewBox="0 0 420 280" role="img" aria-label="A session reading the current fact">
      <rect x="70" y="18" width="250" height="180" fill="#d7efe4" stroke="#1a1a1a" strokeWidth="4" />
      <rect x="86" y="34" width="218" height="148" fill="#f4f7fb" />
      <rect x="100" y="52" width="92" height="14" fill="#ff4b00" />
      <rect x="100" y="76" width="150" height="8" fill="#1a1a1a" />
      <rect x="100" y="92" width="120" height="8" fill="#8d8d8d" />
      <rect x="100" y="118" width="70" height="28" fill="#111" />
      <rect x="178" y="118" width="70" height="28" fill="#ececec" />
      <rect x="150" y="198" width="90" height="12" fill="#cfcfcf" />
      <rect x="118" y="210" width="154" height="10" fill="#9ad7c4" />
      <rect x="40" y="228" width="300" height="16" fill="#b7e3d2" />
    </svg>
  );
}

export default function App() {
  return (
    <>
      <a className="skip" href="#product">Skip to content</a>
      <header className="nav">
        <a className="brand" href="#product">
          <span className="mark" aria-hidden="true">R</span>
          RETRACT
        </a>
        <nav className="nav-links" aria-label="Primary">
          {NAV.map(([label, href]) => (
            <a key={label} href={href}>{label}</a>
          ))}
        </nav>
        <div className="nav-actions">
          <a href={DASHBOARD}>Dashboard</a>
          <a href={SETTINGS}>Settings</a>
          <a className="pill pill-dark" href="#docs">Run locally <span aria-hidden="true">›</span></a>
        </div>
      </header>

      <main>
        <section className="hero-wrap" id="product">
          <div className="hero">
            <div className="hero-copy">
              <h1>
                <span>Give your agents a memory</span>
                <span>they can correct.</span>
              </h1>
              <p>RETRACT keeps a project decision scoped and evidenced. A confirmed change replaces the old fact and flags the plans that depend on it.</p>
              <div className="hero-actions">
                <a className="pill pill-dark" href={DASHBOARD}>Open dashboard <span aria-hidden="true">›</span></a>
                <a className="pill pill-soft" href="#demo">See the demo</a>
              </div>
            </div>
            <Mountain />
          </div>
        </section>

        <section className="logos" aria-label="Local stack">
          <p>The local stack this demo actually runs on</p>
          <ul>
            {STACK.map((name) => <li key={name}>{name}</li>)}
          </ul>
        </section>

        <section className="sheet" id="workflow">
          <span className="chip chip-blue chip-bar" aria-hidden="true" />
          <span className="chip chip-blue chip-sq chip-tr" aria-hidden="true" />
          <span className="chip chip-lime chip-sq chip-bl" aria-hidden="true" />
          <span className="chip chip-orange chip-bar chip-br" aria-hidden="true" />
          <div className="split">
            <div>
              <h2>A real correction.</h2>
              <p className="lede">The old fact stays in history. Recall returns the new one. The plan that depended on the old fact is flagged.</p>
              {POINTS.map(([title, body]) => (
                <p key={title}><strong>{title}</strong> {body}</p>
              ))}
            </div>
            <Monitor />
          </div>
        </section>

        <section className="quote" id="graph">
          <figure>
            <blockquote>
              <span className="hl">A confirmed change supersedes the old fact, keeps its evidence, and flags the plan that depended on it.</span>
            </blockquote>
            <figcaption>account-settings · event U1</figcaption>
          </figure>
        </section>

        <section className="sheet sheet-cards" id="demo">
          <span className="chip chip-magenta chip-bar" aria-hidden="true" />
          <span className="chip chip-pink chip-sq chip-tr" aria-hidden="true" />
          <span className="chip chip-orange chip-sq chip-ml" aria-hidden="true" />
          <span className="chip chip-orange chip-bar chip-br" aria-hidden="true" />
          <ul className="cards">
            {CARDS.map((card) => (
              <li key={card.label}>
                <p>{card.quote}</p>
                <div>
                  <strong>{card.label}</strong>
                  <span>{card.meta}</span>
                </div>
              </li>
            ))}
          </ul>
        </section>
      </main>

      <footer className="footer" id="docs">
        <div className="footer-brand">
          <span className="footer-mark" aria-hidden="true">R</span>
          <span>RETRACT</span>
        </div>
        <div className="footer-cols">
          {FOOTER.map(([title, links]) => (
            <div key={title}>
              <h2>{title}</h2>
              <ul>
                {links.map(([label, href]) => (
                  <li key={label}><a href={href}>{label}</a></li>
                ))}
              </ul>
            </div>
          ))}
          <div className="footer-legal">
            <p>Local only. No account is required for structured memory.</p>
            <p>python -m pip install -e . · docker compose up -d --wait · retract serve</p>
          </div>
        </div>
      </footer>
    </>
  );
}
