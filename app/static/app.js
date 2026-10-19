/* Kleine Helfer ohne Abhängigkeiten. Die Seite funktioniert auch ohne JavaScript. */
document.documentElement.classList.replace("no-js", "js");

document.addEventListener("DOMContentLoaded", () => {
  // Hamburger-Menü
  document.querySelectorAll(".menu-toggle").forEach((btn) => {
    const nav = document.getElementById(btn.getAttribute("aria-controls"));
    if (!nav) return;
    const close = () => { btn.setAttribute("aria-expanded", "false"); nav.classList.remove("is-open"); };
    btn.addEventListener("click", () => {
      const open = btn.getAttribute("aria-expanded") !== "true";
      btn.setAttribute("aria-expanded", String(open));
      nav.classList.toggle("is-open", open);
    });
    nav.querySelectorAll("a").forEach((a) => a.addEventListener("click", close));
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
  });

  // Quittungsfelder nur bei Bedarf zeigen
  document.querySelectorAll("[data-toggles]").forEach((box) => {
    const target = document.getElementById(box.dataset.toggles);
    const sync = () => { target.hidden = !box.checked; };
    box.addEventListener("change", sync);
    sync();
  });

  // Bildfeld ausblenden, wenn anonym
  const anon = document.getElementById("f-anonym");
  const imgField = document.querySelector("[data-hide-when-anonymous]");
  if (anon && imgField) {
    const sync = () => { imgField.hidden = anon.checked; };
    anon.addEventListener("change", sync);
    sync();
  }

  // Teilen
  document.querySelectorAll("[data-share]").forEach((btn) => {
    btn.hidden = false;
    btn.addEventListener("click", async () => {
      const data = { title: btn.dataset.title, url: btn.dataset.url };
      if (navigator.share) {
        try { await navigator.share(data); } catch (e) { /* abgebrochen */ }
      } else if (navigator.clipboard) {
        await navigator.clipboard.writeText(data.url);
        btn.textContent = btn.dataset.copied || "Link kopiert";
      }
    });
  });

  // Rückfrage vor dem Löschen
  document.querySelectorAll("form[data-confirm]").forEach((f) => {
    f.addEventListener("submit", (e) => { if (!confirm(f.dataset.confirm)) e.preventDefault(); });
  });

  // Filter sofort anwenden
  document.querySelectorAll("[data-autosubmit]").forEach((el) => el.addEventListener("change", () => el.form.submit()));

  // Sprach-Tabs im Admin (Deutsch/Englisch nebeneinander statt untereinander)
  document.querySelectorAll(".lang-tabs").forEach((box) => {
    const buttons = box.querySelectorAll("[data-lang-tab]");
    const panels = box.querySelectorAll("[data-lang-panel]");
    if (!buttons.length) return;
    const show = (lang) => {
      buttons.forEach((b) => b.classList.toggle("is-active", b.dataset.langTab === lang));
      panels.forEach((p) => { p.hidden = p.dataset.langPanel !== lang; });
    };
    buttons.forEach((b) => b.addEventListener("click", () => show(b.dataset.langTab)));
    show(buttons[0].dataset.langTab);
  });

  // Mailvorlagen als Tabs; der gewählte Tab bleibt nach dem Speichern erhalten
  const tplButtons = document.querySelectorAll("[data-tpl-tab]");
  if (tplButtons.length) {
    const tplPanels = document.querySelectorAll("[data-tpl-panel]");
    const showTpl = (key) => {
      tplButtons.forEach((b) => {
        const on = b.dataset.tplTab === key;
        b.classList.toggle("is-active", on);
        b.setAttribute("aria-selected", String(on));
        b.tabIndex = on ? 0 : -1;
      });
      tplPanels.forEach((p) => { p.hidden = p.dataset.tplPanel !== key; });
      try { sessionStorage.setItem("tplTab", key); } catch (e) { /* egal */ }
    };
    let saved = null;
    try { saved = sessionStorage.getItem("tplTab"); } catch (e) { /* egal */ }
    const keys = [...tplButtons].map((b) => b.dataset.tplTab);
    showTpl(keys.includes(saved) ? saved : keys[0]);
    tplButtons.forEach((b, i) => {
      b.addEventListener("click", () => showTpl(b.dataset.tplTab));
      b.addEventListener("keydown", (e) => {
        const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
        if (!step) return;
        const next = tplButtons[(i + step + tplButtons.length) % tplButtons.length];
        showTpl(next.dataset.tplTab);
        next.focus();
      });
    });
  }

  // Passwort ein-/ausblenden
  document.querySelectorAll("[data-toggle-password]").forEach((btn) => {
    const input = document.getElementById(btn.dataset.togglePassword);
    if (!input) return;
    btn.hidden = false;
    btn.addEventListener("click", () => {
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.setAttribute("aria-pressed", String(show));
      btn.setAttribute("aria-label", show ? "Passwort verbergen" : "Passwort anzeigen");
      input.focus();
    });
  });

  // Mailserver speichern/testen ohne Neuladen (ohne JS: normales Formular)
  document.querySelectorAll("form[data-ajax-smtp]").forEach((form) => {
    const out = form.querySelector("[data-smtp-result]");
    const buttons = form.querySelectorAll("button[type=submit]");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = e.submitter;
      const url = (btn && btn.getAttribute("formaction")) || form.action;
      const label = btn ? btn.textContent : "";
      buttons.forEach((b) => { b.disabled = true; });
      if (btn && btn.dataset.busy) btn.textContent = btn.dataset.busy;
      out.replaceChildren();
      try {
        const res = await fetch(url, {
          method: "POST", body: new FormData(form),
          headers: { "X-Requested-With": "fetch", Accept: "application/json" },
        });
        if (!res.ok) throw new Error(`Serverfehler ${res.status}`);
        const data = await res.json();
        const alert = document.createElement("div");
        alert.className = `alert alert--${data.ok ? "ok" : "warn"}`;
        alert.setAttribute("role", "status");
        alert.textContent = data.message;
        out.append(alert);
        if (data.log && data.log.length) {
          const ul = document.createElement("ul");
          ul.className = "log";
          data.log.forEach((line) => { const li = document.createElement("li"); li.textContent = line; ul.append(li); });
          out.append(ul);
        }
        if (data.ok) {
          const pw = form.querySelector("[name=smtp_password]");
          if (pw && data.password_saved) {
            pw.value = "";
            pw.placeholder = pw.dataset.savedPlaceholder;
            const toggle = form.querySelector(`[data-toggle-password="${pw.id}"]`);
            if (toggle && pw.type === "text") toggle.click();
          }
          // beim Test gefundene Variante übernehmen
          form.querySelector("[name=smtp_port]").value = data.smtp_port;
          form.querySelector("[name=smtp_security]").value = data.smtp_security;
        }
      } catch (err) {
        const alert = document.createElement("div");
        alert.className = "alert alert--warn";
        alert.textContent = `Anfrage fehlgeschlagen: ${err.message}. Bitte Seite neu laden.`;
        out.append(alert);
      } finally {
        buttons.forEach((b) => { b.disabled = false; });
        if (btn) btn.textContent = label;
      }
    });
  });

  // Countdown vor dem Lauf und Laufuhr (Restzeit). Ziel und Serverzeit kommen aus dem HTML,
  // damit eine falsch gehende Uhr am Gerät nichts verfälscht.
  const pad = (n) => String(n).padStart(2, "0");
  const fmtRest = (rest, tageWort) => {
    const tage = Math.floor(rest / 86400);
    const h = Math.floor((rest % 86400) / 3600);
    const m = Math.floor((rest % 3600) / 60);
    const s = rest % 60;
    const text = h || tage ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
    return tage ? `${tage} ${tageWort} ${text}` : text;
  };
  let clockOffset = null;
  const tickClocks = () => {
    document.querySelectorAll("[data-clock-ziel]").forEach((el) => {
      if (clockOffset === null) clockOffset = Number(el.dataset.clockJetzt) - Date.now();
      const rest = Math.max(0, Math.ceil((Number(el.dataset.clockZiel) - (Date.now() + clockOffset)) / 1000));
      const text = fmtRest(rest, el.dataset.clockTage || "Tage");
      if (el.textContent !== text) el.textContent = text;
      el.classList.toggle("clock--null", rest === 0);
    });
  };
  if (document.querySelector("[data-clock-ziel]")) {
    tickClocks();
    window.__clockTimer = setInterval(tickClocks, 250);
  }

  // Admin „Lauf“: zum Fälligkeitszeitpunkt der Mail „Vorläufiges Ergebnis“ neu laden (löst den Versand aus)
  const reloadAt = document.querySelector("[data-reload-at]");
  if (reloadAt) {
    const warte = Number(reloadAt.dataset.reloadAt) - Date.now() + 2000;
    setTimeout(() => window.location.reload(), Math.max(2000, warte));
  }

  // Live-Aktualisierung (Live-Zählung und Countdown). Wechselt die Phase, Seite neu laden.
  const live = document.querySelector("[data-live]");
  if (live) {
    setInterval(async () => {
      try {
        const res = await fetch(live.dataset.live, { cache: "no-store" });
        if (!res.ok) return;
        const doc = new DOMParser().parseFromString(await res.text(), "text/html");
        const neu = doc.querySelector("[data-mode]");
        if (neu && live.dataset.mode && neu.dataset.mode !== live.dataset.mode) {
          window.location.reload();
          return;
        }
        doc.querySelectorAll("[data-part]").forEach((part) => {
          const here = document.querySelector(`[data-part="${part.dataset.part}"]`);
          if (here) here.innerHTML = part.innerHTML;
        });
        if (document.querySelector("[data-clock-ziel]")) {
          clockOffset = null;
          tickClocks();
          if (!window.__clockTimer) window.__clockTimer = setInterval(tickClocks, 250);
        }
      } catch (e) { /* nächster Versuch in 15 Sekunden */ }
    }, 15000);
  }
});
