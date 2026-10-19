import { useEffect, useRef, useState } from "react";

const SIGN_IN = import.meta.env.DEV ? "http://127.0.0.1:8100/dashboard" : "/dashboard";

function loadClerk(issuer, key) {
  if (window.Clerk) return Promise.resolve(window.Clerk);
  return new Promise((resolve, reject) => {
    const element = document.createElement("script");
    element.src = `${issuer}/npm/@clerk/clerk-js@6/dist/clerk.browser.js`;
    element.async = true;
    element.crossOrigin = "anonymous";
    element.dataset.clerkPublishableKey = key;
    element.onload = () => resolve(window.Clerk);
    element.onerror = () => reject(new Error("Account service unavailable"));
    document.head.append(element);
  });
}

function snapshot(user) {
  return {
    firstName: user.firstName || "",
    lastName: user.lastName || "",
    email: user.primaryEmailAddress?.emailAddress || "",
    imageUrl: user.imageUrl || "",
  };
}

function displayName(user) {
  return [user.firstName, user.lastName].filter(Boolean).join(" ") || user.email || "Account";
}

function clerkError(failure) {
  return failure?.errors?.[0]?.longMessage || failure?.errors?.[0]?.message || "Could not save your account.";
}

export function AccountLink() {
  const [phase, setPhase] = useState("loading");
  const [user, setUser] = useState(null);
  const [clerk, setClerk] = useState(null);
  const [open, setOpen] = useState(false);
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [photoBroken, setPhotoBroken] = useState(false);
  const buttonRef = useRef(null);
  const firstRef = useRef(null);
  const panelRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch("/api/config", { cache: "no-store" });
        if (!response.ok) throw new Error("config");
        const config = await response.json();
        if (!config.publishable_key || !config.issuer) {
          if (!cancelled) setPhase("out");
          return;
        }
        const client = await loadClerk(config.issuer, config.publishable_key);
        await client.load();
        if (cancelled) return;
        setClerk(client);
        if (client.user && (location.search.includes("__clerk") || location.hash.includes("sso-callback"))) {
          window.location.assign(SIGN_IN);
          return;
        }
        if (client.user) {
          setUser(snapshot(client.user));
          setPhase("in");
        } else setPhase("out");
      } catch {
        if (!cancelled) setPhase("out");
      }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    firstRef.current?.focus();
    const onKey = (event) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      buttonRef.current?.focus();
    };
    const onPointer = (event) => {
      if (!panelRef.current?.contains(event.target) && !buttonRef.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open]);

  if (phase !== "in" || !user) {
    if (phase === "loading") return <span className="account-slot" aria-hidden="true" />;
    return <a className="btn btn--secondary" href={SIGN_IN}>Sign in</a>;
  }

  const name = displayName(user);
  const initial = (name[0] || "A").toUpperCase();
  const showPhoto = user.imageUrl && !photoBroken;

  function openPanel() {
    setFirst(user.firstName);
    setLast(user.lastName);
    setError("");
    setSaved(false);
    setOpen(true);
  }

  async function save(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      await clerk.user.update({ firstName: first.trim(), lastName: last.trim() });
      setUser(snapshot(clerk.user));
      setSaved(true);
    } catch (failure) {
      setError(clerkError(failure));
    } finally {
      setSaving(false);
    }
  }

  async function changePhoto(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setError("");
    setSaved(false);
    if (file.size > 10 * 1024 * 1024) {
      setError("Use a photo smaller than 10 MB.");
      return;
    }
    try {
      await clerk.user.setProfileImage({ file });
      setPhotoBroken(false);
      setUser(snapshot(clerk.user));
      setSaved(true);
    } catch (failure) {
      setError(clerkError(failure));
    }
  }

  async function signOut() {
    try {
      await clerk.signOut();
      setOpen(false);
      setUser(null);
      setPhase("out");
    } catch (failure) {
      setError(clerkError(failure));
    }
  }

  return (
    <div className="account-menu">
      <button
        ref={buttonRef}
        type="button"
        className="account-avatar-btn"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={`Account, ${name}`}
        onClick={() => (open ? setOpen(false) : openPanel())}
      >
        {showPhoto ? <img src={user.imageUrl} alt="" onError={() => setPhotoBroken(true)} /> : <span>{initial}</span>}
      </button>
      {open ? (
        <div ref={panelRef} className="account-panel" role="dialog" aria-label="Your account">
          <form onSubmit={save}>
            <label className="account-photo">
              <span className="account-avatar-btn account-avatar-btn--large" aria-hidden="true">
                {showPhoto ? <img src={user.imageUrl} alt="" /> : <span>{initial}</span>}
              </span>
              <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" onChange={changePhoto} />
              <span>Change photo</span>
            </label>
            <label htmlFor="nav-account-first">First name</label>
            <input id="nav-account-first" ref={firstRef} value={first} onChange={(event) => setFirst(event.target.value)} maxLength={80} autoComplete="given-name" />
            <label htmlFor="nav-account-last">Last name</label>
            <input id="nav-account-last" value={last} onChange={(event) => setLast(event.target.value)} maxLength={80} autoComplete="family-name" />
            <p className="account-email">{user.email}</p>
            {error ? <p className="account-error" role="alert">{error}</p> : null}
            {saved ? <p className="account-saved" role="status">Saved.</p> : null}
            <button className="btn account-save" type="submit" disabled={saving}>{saving ? "Saving…" : "Save"}</button>
            <div className="account-links">
              <a href={SIGN_IN}>Workspace</a>
              <button type="button" onClick={signOut}>Sign out</button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}
