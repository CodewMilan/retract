import { useEffect } from "react";
import { Marked } from "marked";
import readme from "../../README.md?raw";
import indexDoc from "../../docs/README.md?raw";
import direction from "../../docs/realproduct.md?raw";
import product from "../../docs/01-PRODUCT.md?raw";
import demo from "../../docs/02-DEMO-AND-EVALUATION.md?raw";
import architecture from "../../docs/03-ARCHITECTURE.md?raw";
import infrastructure from "../../docs/04-INFRASTRUCTURE-AND-COSTS.md?raw";
import plan from "../../docs/05-BUILD-PLAN.md?raw";
import status from "../../docs/06-IMPLEMENTATION-STATUS.md?raw";
import natural from "../../docs/07-NATURAL-LANGUAGE-UPDATES.md?raw";
import mcp from "../../docs/08-MCP-AND-CODING-CLIENT.md?raw";
import dashboard from "../../docs/09-DASHBOARD.md?raw";
import evaluation from "../../docs/10-EVALUATION-AND-RELEASE.md?raw";
import queries from "../../docs/11-GRAPH-QUERIES.md?raw";
import fresh from "../../docs/12-FRESH-CLIENT-RUN.md?raw";
import account from "../../examples/account-settings/README.md?raw";
import submission from "../../SUBMISSION.md?raw";
import notices from "../../THIRD_PARTY_NOTICES.md?raw";

const GITHUB = "https://github.com/CodewMilan/graph/blob/main/";

const SOURCES = [
  ["index", "Documentation", "Start", "docs/README.md", indexDoc],
  ["overview", "Overview", "Start", "README.md", readme],
  ["direction", "Product direction", "Start", "docs/realproduct.md", direction],
  ["product", "Product", "Specification", "docs/01-PRODUCT.md", product],
  ["demo", "Demo", "Specification", "docs/02-DEMO-AND-EVALUATION.md", demo],
  ["architecture", "Architecture", "Specification", "docs/03-ARCHITECTURE.md", architecture],
  ["infrastructure", "Infrastructure", "Specification", "docs/04-INFRASTRUCTURE-AND-COSTS.md", infrastructure],
  ["plan", "Build plan", "Specification", "docs/05-BUILD-PLAN.md", plan],
  ["status", "Verification", "What shipped", "docs/06-IMPLEMENTATION-STATUS.md", status],
  ["natural", "Natural language", "What shipped", "docs/07-NATURAL-LANGUAGE-UPDATES.md", natural],
  ["mcp", "MCP server and CLI", "What shipped", "docs/08-MCP-AND-CODING-CLIENT.md", mcp],
  ["dashboard", "Dashboard", "What shipped", "docs/09-DASHBOARD.md", dashboard],
  ["queries", "Graph queries", "What shipped", "docs/11-GRAPH-QUERIES.md", queries],
  ["fresh", "Fresh client run", "What shipped", "docs/12-FRESH-CLIENT-RUN.md", fresh],
  ["evaluation", "Evaluation", "What shipped", "docs/10-EVALUATION-AND-RELEASE.md", evaluation],
  ["account", "Account settings demo", "What shipped", "examples/account-settings/README.md", account],
  ["submission", "Submission draft", "Project", "SUBMISSION.md", submission],
  ["notices", "Third-party notices", "Project", "THIRD_PARTY_NOTICES.md", notices],
];

function slugify(value) {
  return value
    .replace(/<[^>]+>/g, "")
    .replace(/&[a-z]+;/g, "")
    .trim()
    .toLowerCase()
    .replace(/['’]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function resolvePath(fromFile, hrefPath) {
  const dir = fromFile.includes("/") ? fromFile.slice(0, fromFile.lastIndexOf("/")).split("/") : [];
  for (const segment of hrefPath.split("/")) {
    if (!segment || segment === ".") continue;
    if (segment === "..") dir.pop();
    else dir.push(segment);
  }
  return dir.join("/");
}

function escapeAttr(value) {
  return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

const byFile = new Map(SOURCES.map(([slug, , , file]) => [file, slug]));

function rewrite(fromFile, slug, href) {
  if (!href || /^(https?:|mailto:)/.test(href)) return href;
  const hashAt = href.indexOf("#");
  const path = hashAt >= 0 ? href.slice(0, hashAt) : href;
  const anchor = hashAt >= 0 ? href.slice(hashAt + 1) : "";
  if (!path) return `#docs/${slug}${anchor ? `/${anchor}` : ""}`;
  const rel = resolvePath(fromFile, path);
  const target = byFile.get(rel);
  if (target) return `#docs/${target}${anchor ? `/${anchor}` : ""}`;
  return `${GITHUB}${rel}${anchor ? `#${anchor}` : ""}`;
}

function render(source, file, slug) {
  const ids = new Map();
  const marked = new Marked({ gfm: true, breaks: false });
  marked.use({
    renderer: {
      html() {
        return "";
      },
      heading({ tokens, depth }) {
        const text = this.parser.parseInline(tokens);
        let id = slugify(text) || "section";
        const seen = ids.get(id) || 0;
        ids.set(id, seen + 1);
        if (seen) id = `${id}-${seen}`;
        const brand = /\bretract\b/i.test(text.replace(/<[^>]+>/g, "")) ? " brand-heading" : "";
        return `<h${depth} id="${id}" class="docs-heading${brand}">${text}</h${depth}>\n`;
      },
      link({ href, tokens, title }) {
        const text = this.parser.parseInline(tokens);
        const next = rewrite(file, slug, href || "");
        const external = /^https?:/.test(next);
        const titleAttr = title ? ` title="${escapeAttr(title)}"` : "";
        const extra = external ? ' target="_blank" rel="noopener noreferrer"' : "";
        return `<a href="${escapeAttr(next)}"${titleAttr}${extra}>${text}</a>`;
      },
    },
  });
  return marked.parse(source);
}

export const DOCS = SOURCES.map(([slug, title, group, file, source]) => ({
  slug,
  title,
  group,
  file,
  html: render(source, file, slug),
}));

const bySlug = new Map(DOCS.map((doc) => [doc.slug, doc]));

export function parseDocsHash(hash) {
  const body = hash.replace(/^#/, "");
  if (body !== "docs" && !body.startsWith("docs/")) return null;
  const rest = body === "docs" ? "" : body.slice("docs/".length);
  const [slug, ...anchor] = rest.split("/").filter(Boolean);
  return { slug: slug || "index", anchor: anchor.join("/") };
}

export function DocsPage({ slug, anchor }) {
  const doc = bySlug.get(slug);
  useEffect(() => {
    const target = anchor ? document.getElementById(anchor) : document.getElementById("docs-article");
    target?.scrollIntoView();
  }, [slug, anchor, doc]);

  const groups = [];
  for (const item of DOCS) {
    const group = groups.find((entry) => entry.title === item.group);
    if (group) group.items.push(item);
    else groups.push({ title: item.group, items: [item] });
  }

  return (
    <main id="main" className="docs">
      <div className="docs__layout">
        <nav className="docs__nav" aria-label="Documentation">
          {groups.map((group) => (
            <div key={group.title} className="docs__group">
              <h2 className="docs__group-title type-eyebrow-1">{group.title}</h2>
              <ul>
                {group.items.map((item) => (
                  <li key={item.slug}>
                    <a href={`#docs/${item.slug}`} aria-current={item.slug === slug ? "page" : undefined}>
                      {item.title}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
        <article id="docs-article" className="docs__article" tabIndex={-1}>
          {doc ? (
            <div dangerouslySetInnerHTML={{ __html: doc.html }} />
          ) : (
            <>
              <h1 className="docs-heading">This page is not in the docs</h1>
              <p>Choose a document from the list, or start with the <a href="#docs">documentation index</a>.</p>
            </>
          )}
        </article>
      </div>
    </main>
  );
}
