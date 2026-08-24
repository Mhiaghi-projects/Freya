"use strict";

// --- API helper -------------------------------------------------------
async function api(method, path, body) {
  const opts = { method, credentials: "same-origin", headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (res.status === 204) return null;
  let envelope = null;
  try { envelope = await res.json(); } catch { /* respuesta no-JSON (descargas) */ }
  if (!res.ok || (envelope && envelope.success === false)) {
    const message = envelope && envelope.error ? envelope.error.message : `HTTP ${res.status}`;
    const err = new Error(message);
    err.status = res.status;
    throw err;
  }
  return envelope ? envelope.data : null;
}

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined) continue;
    node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

function badge(status) {
  const cls = "badge badge-" + (status || "unknown").toLowerCase();
  return el("span", { class: cls }, status || "unknown");
}

// --- screens ------------------------------------------------------------
const screens = {
  login: document.getElementById("login-screen"),
  changePassword: document.getElementById("change-password-screen"),
  app: document.getElementById("app-shell"),
};

function showScreen(name) {
  for (const s of Object.values(screens)) s.classList.add("hidden");
  screens[name].classList.remove("hidden");
}

// --- auth flow ------------------------------------------------------------
document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = document.getElementById("login-email").value;
  const password = document.getElementById("login-password").value;
  const errorEl = document.getElementById("login-error");
  errorEl.classList.add("hidden");
  try {
    const data = await api("POST", "/api/session/sign-in", { email, password });
    if (data.must_change_password) {
      showScreen("changePassword");
    } else {
      await boot();
    }
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
  }
});

document.getElementById("change-password-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const current_password = document.getElementById("cp-current").value;
  const new_password = document.getElementById("cp-new").value;
  const errorEl = document.getElementById("cp-error");
  errorEl.classList.add("hidden");
  try {
    await api("POST", "/api/session/change-password", { current_password, new_password });
    await boot();
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
  }
});

document.getElementById("logout-btn").addEventListener("click", async () => {
  try { await api("POST", "/api/session/sign-out"); } catch { /* la cookie se limpia igual */ }
  showScreen("login");
});

let currentUser = null;

async function boot() {
  try {
    currentUser = await api("GET", "/api/session/me");
    const label = currentUser.email || currentUser.first_name || currentUser.user_id;
    document.getElementById("whoami").textContent = `${label} · ${currentUser.role}`;
    document.querySelector('a[data-route="admin-users"]').classList.toggle(
      "hidden", currentUser.role !== "admin"
    );
    showScreen("app");
    router();
  } catch {
    showScreen("login");
  }
}

// --- router ------------------------------------------------------------
const routes = {};
function route(name, render) { routes[name] = render; }

async function router() {
  const hash = location.hash.replace(/^#\//, "") || "dashboard";
  const [name, ...rest] = hash.split("/");
  for (const a of document.querySelectorAll(".sidebar a")) {
    a.classList.toggle("active", a.dataset.route === name);
  }
  const content = document.getElementById("content");
  const render = routes[name] || routes.dashboard;
  content.innerHTML = "";
  try {
    await render(content, rest);
  } catch (err) {
    content.appendChild(el("p", { class: "error" }, err.message));
  }
}
window.addEventListener("hashchange", router);

// --- dashboard / catalog -------------------------------------------------
route("dashboard", async (content) => {
  content.appendChild(el("h2", { class: "page-title" }, "Panel"));
  const data = await api("GET", "/api/catalog");
  const grid = el("div", { class: "grid" });
  for (const svc of data.services) {
    grid.appendChild(
      el("div", { class: "card" },
        el("h3", {}, svc.name),
        badge(svc.status),
        el("p", {}, svc.description),
        el("p", { class: "muted" }, `Fase ${svc.phase}`),
      )
    );
  }
  content.appendChild(grid);
});

// --- git ------------------------------------------------------------
route("git", async (content, [repoId]) => {
  if (!repoId) {
    content.appendChild(el("h2", { class: "page-title" }, "Git"));
    const repos = await api("GET", "/api/git/repos");
    if (!repos.length) { content.appendChild(el("p", { class: "empty" }, "Sin repositorios.")); return; }
    const table = el("table", {},
      el("thead", {}, el("tr", {}, el("th", {}, "Repositorio"), el("th", {}, "Rama por defecto"), el("th", {}, "Visibilidad"))),
      el("tbody", {}, repos.map((r) =>
        el("tr", { class: "clickable", onclick: () => { location.hash = `#/git/${r.id}`; } },
          el("td", {}, r.repo_name), el("td", {}, r.default_branch), el("td", {}, r.visibility))
      ))
    );
    content.appendChild(table);
    return;
  }

  const [repo, branches, commits] = await Promise.all([
    api("GET", `/api/git/repos/${repoId}`),
    api("GET", `/api/git/repos/${repoId}/branches`),
    api("GET", `/api/git/repos/${repoId}/commits`),
  ]);
  content.appendChild(el("div", { class: "breadcrumb" }, el("a", { onclick: () => { location.hash = "#/git"; } }, "Git"), ` / ${repo.repo_name}`));
  content.appendChild(el("h2", { class: "page-title" }, repo.repo_name));

  content.appendChild(el("h3", {}, "Ramas"));
  content.appendChild(el("div", { class: "grid" }, branches.map((b) =>
    el("div", { class: "card" }, el("h3", {}, b.name), b.protected ? badge("protected") : "")
  )));

  content.appendChild(el("h3", {}, "Commits recientes"));
  const items = commits.commits || [];
  if (!items.length) {
    content.appendChild(el("p", { class: "empty" }, "Sin commits."));
  } else {
    content.appendChild(el("table", {},
      el("thead", {}, el("tr", {}, el("th", {}, "SHA"), el("th", {}, "Mensaje"), el("th", {}, "Autor"), el("th", {}, "Fecha"))),
      el("tbody", {}, items.map((c) =>
        el("tr", {}, el("td", {}, c.short_hash || c.hash.slice(0, 8)), el("td", {}, c.message),
          el("td", {}, c.author ? c.author.name : ""),
          el("td", {}, c.timestamp ? new Date(c.timestamp * 1000).toLocaleString() : ""))
      ))
    ));
  }
});

// --- storage ------------------------------------------------------------
route("storage", async (content, [bucket]) => {
  if (!bucket) {
    content.appendChild(el("h2", { class: "page-title" }, "Storage"));

    const bucketForm = el("form", { class: "inline-form" },
      el("input", { type: "text", placeholder: "nombre del bucket", id: "nb-name", required: "true", pattern: "[a-z0-9-]+" }),
      el("button", { class: "btn", type: "submit" }, "Crear bucket"),
    );
    const bucketError = el("p", { class: "error hidden" });
    content.appendChild(bucketForm);
    content.appendChild(bucketError);
    bucketForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      bucketError.classList.add("hidden");
      try {
        const name = document.getElementById("nb-name").value;
        await api("PUT", `/api/storage/buckets/${encodeURIComponent(name)}`, {});
        location.hash = `#/storage/${name}`;
      } catch (err) {
        bucketError.textContent = err.message;
        bucketError.classList.remove("hidden");
      }
    });

    const buckets = await api("GET", "/api/storage/buckets");
    if (!buckets.length) { content.appendChild(el("p", { class: "empty" }, "Sin buckets todavía.")); return; }
    content.appendChild(el("div", { class: "grid" }, buckets.map((b) =>
      el("div", { class: "card clickable", onclick: () => { location.hash = `#/storage/${b.bucket}`; } },
        el("h3", {}, b.bucket), el("p", { class: "muted" }, b.versioning ? "con versionado" : "sin versionado"))
    )));
    return;
  }

  content.appendChild(el("div", { class: "breadcrumb" }, el("a", { onclick: () => { location.hash = "#/storage"; } }, "Storage"), ` / ${bucket}`));
  content.appendChild(el("h2", { class: "page-title" }, bucket));

  // Subida real, en streaming (fetch con un File como body) -- api() no
  // sirve aquí porque siempre manda JSON.stringify, nunca bytes crudos.
  const fileInput = el("input", { type: "file", id: "up-file", required: "true" });
  const keyInput = el("input", { type: "text", placeholder: "ruta (opcional, ej: fotos/2026/img.jpg)", id: "up-key" });
  const uploadForm = el("form", { class: "inline-form" }, fileInput, keyInput,
    el("button", { class: "btn", type: "submit" }, "Subir"));
  const uploadError = el("p", { class: "error hidden" });
  content.appendChild(uploadForm);
  content.appendChild(uploadError);

  const table = el("table", {},
    el("thead", {}, el("tr", {}, el("th", {}, "Clave"), el("th", {}, "Tamaño"), el("th", {}, "Modificado"), el("th", {}, ""))),
    el("tbody", {}),
  );
  const emptyMsg = el("p", { class: "empty hidden" }, "Bucket vacío.");
  content.appendChild(table);
  content.appendChild(emptyMsg);

  async function renderObjects() {
    const objects = await api("GET", `/api/storage/${bucket}`);
    const items = objects.items || objects.objects || objects;
    const tbody = table.querySelector("tbody");
    tbody.innerHTML = "";
    emptyMsg.classList.toggle("hidden", Array.isArray(items) && items.length > 0);
    if (!Array.isArray(items)) return;
    for (const o of items) {
      const encodedKey = o.key.split("/").map(encodeURIComponent).join("/");
      tbody.appendChild(el("tr", {}, el("td", {}, o.key), el("td", {}, String(o.size ?? "")),
        el("td", {}, o.last_modified || o.updated_at || ""),
        el("td", {},
          el("a", { href: `/api/storage/${encodeURIComponent(bucket)}/${encodedKey}`, target: "_blank", class: "btn btn-secondary" }, "Descargar"),
          el("button", {
            class: "btn btn-danger", type: "button",
            onclick: async () => {
              if (!confirm(`¿Borrar '${o.key}'?`)) return;
              await api("DELETE", `/api/storage/${encodeURIComponent(bucket)}/${encodedKey}`);
              await renderObjects();
            },
          }, "Borrar"))));
    }
  }
  await renderObjects();

  uploadForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    uploadError.classList.add("hidden");
    const file = fileInput.files[0];
    const key = keyInput.value.trim() || file.name;
    const encodedKey = key.split("/").map(encodeURIComponent).join("/");
    try {
      const res = await fetch(`/api/storage/${encodeURIComponent(bucket)}/${encodedKey}`, {
        method: "PUT",
        credentials: "same-origin",
        headers: { "Content-Type": file.type || "application/octet-stream" },
        body: file,
      });
      if (!res.ok) {
        const envelope = await res.json().catch(() => null);
        throw new Error(envelope && envelope.error ? envelope.error.message : `HTTP ${res.status}`);
      }
      uploadForm.reset();
      await renderObjects();
    } catch (err) {
      uploadError.textContent = err.message;
      uploadError.classList.remove("hidden");
    }
  });
});

// --- cicd ------------------------------------------------------------
route("cicd", async (content, [pipelineId]) => {
  if (!pipelineId) {
    content.appendChild(el("h2", { class: "page-title" }, "CI/CD"));
    const pipelines = await api("GET", "/api/cicd/pipelines");
    content.appendChild(el("table", {},
      el("thead", {}, el("tr", {}, el("th", {}, "Pipeline"), el("th", {}, "Servicio"), el("th", {}, "Tipo"))),
      el("tbody", {}, pipelines.map((p) =>
        el("tr", { class: "clickable", onclick: () => { location.hash = `#/cicd/${p.id}`; } },
          el("td", {}, p.name), el("td", {}, p.service), el("td", {}, p.pipeline_type))
      ))
    ));
    return;
  }

  async function renderRuns() {
    const runs = await api("GET", `/api/cicd/pipelines/${pipelineId}/runs`);
    const body = document.getElementById("runs-body");
    body.innerHTML = "";
    for (const r of runs) {
      body.appendChild(el("tr", {},
        el("td", {}, r.id.slice(-10)), badgeCell(r.status), el("td", {}, r.triggered_by),
        el("td", {}, r.started_at || ""), el("td", {}, r.finished_at || "")));
    }
  }
  function badgeCell(status) { return el("td", {}, badge(status)); }

  content.appendChild(el("div", { class: "breadcrumb" }, el("a", { onclick: () => { location.hash = "#/cicd"; } }, "CI/CD"), ` / ${pipelineId}`));
  const toolbar = el("div", { class: "toolbar" },
    el("h2", { class: "page-title", style: "margin:0" }, "Runs"),
    el("button", { class: "btn", onclick: async (e) => {
      e.target.disabled = true;
      try { await api("POST", `/api/cicd/pipelines/${pipelineId}/trigger`); await renderRuns(); }
      finally { e.target.disabled = false; }
    } }, "Disparar pipeline")
  );
  content.appendChild(toolbar);
  content.appendChild(el("table", {},
    el("thead", {}, el("tr", {}, el("th", {}, "Run"), el("th", {}, "Estado"), el("th", {}, "Origen"), el("th", {}, "Inicio"), el("th", {}, "Fin"))),
    el("tbody", { id: "runs-body" })
  ));
  await renderRuns();
});

// --- projects ------------------------------------------------------------
route("projects", async (content, [projectId]) => {
  if (!projectId) {
    content.appendChild(el("h2", { class: "page-title" }, "Proyectos"));
    const projects = await api("GET", "/api/projects");
    if (!projects.length) { content.appendChild(el("p", { class: "empty" }, "Sin proyectos.")); return; }
    content.appendChild(el("div", { class: "grid" }, projects.map((p) =>
      el("div", { class: "card clickable", onclick: () => { location.hash = `#/projects/${p.id}`; } },
        el("h3", {}, p.project_name), el("p", { class: "muted" }, p.project_type || ""))
    )));
    return;
  }

  content.appendChild(el("div", { class: "breadcrumb" }, el("a", { onclick: () => { location.hash = "#/projects"; } }, "Proyectos"), ` / ${projectId}`));
  content.appendChild(el("h2", { class: "page-title" }, "Kanban"));
  const board = el("div", { class: "kanban" });
  content.appendChild(board);

  // Arrastrar y soltar en el navegador exige preventDefault() en TANTO
  // dragenter COMO dragover para que el drop se acepte de forma fiable --
  // con sólo dragover, algunos navegadores lo aceptan "a veces sí, a veces
  // no" (justo el fallo intermitente reportado en vivo). El target del
  // drop es la columna entera, no sólo la lista de tarjetas: así soltar
  // cerca del borde o sobre el hueco bajo la última tarjeta también cuenta
  // -- un target angosto es la otra causa típica de "a veces no engancha".
  let draggedTaskId = null;

  async function renderBoard() {
    const kanban = await api("GET", `/api/projects/${projectId}/kanban`);
    board.innerHTML = "";
    for (const col of kanban.columns || []) {
      const taskList = el("div", { class: "kanban-tasks" },
        (col.tasks || []).map((t) => taskCard(t))
      );
      const column = el("div", { class: "kanban-column" },
        el("h3", {}, `${col.label} (${col.task_count})`),
        taskList,
      );
      column.addEventListener("dragenter", (e) => {
        e.preventDefault();
        column.classList.add("drag-over");
      });
      column.addEventListener("dragover", (e) => {
        e.preventDefault();
      });
      column.addEventListener("dragleave", (e) => {
        if (!column.contains(e.relatedTarget)) column.classList.remove("drag-over");
      });
      column.addEventListener("drop", async (e) => {
        e.preventDefault();
        column.classList.remove("drag-over");
        const taskId = draggedTaskId || e.dataTransfer.getData("text/plain");
        if (!taskId) return;
        await api("PUT", `/api/projects/tasks/${taskId}`, { status: col.status });
        await renderBoard();
      });
      board.appendChild(column);
    }
  }

  function taskCard(t) {
    const card = el("div", { class: "task-card", draggable: "true" },
      el("p", { class: "task-title" }, t.title),
      el("p", { class: "muted" }, [t.priority, t.assigned_to].filter(Boolean).join(" · ")),
    );
    card.addEventListener("dragstart", (e) => {
      draggedTaskId = t.task_id;
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", t.task_id);
      card.classList.add("dragging");
    });
    card.addEventListener("dragend", () => {
      draggedTaskId = null;
      card.classList.remove("dragging");
    });
    return card;
  }

  await renderBoard();
});

// --- admin: usuarios ------------------------------------------------------
route("admin-users", async (content) => {
  content.appendChild(el("h2", { class: "page-title" }, "Usuarios"));

  // Sólo 2 tipos de cuenta (user/admin) -- el acceso por servicio de una
  // cuenta "user" es una combinación libre de grants (checkboxes), no un
  // role aparte por servicio.
  const [roles, grants] = await Promise.all([
    api("GET", "/api/admin/roles"),
    api("GET", "/api/admin/service-grants"),
  ]);
  const grantKeys = Object.keys(grants);

  function grantCheckboxes(idPrefix, checked) {
    return el("div", { class: "grant-checks" }, grantKeys.map((g) =>
      el("label", { class: "grant-check" },
        el("input", {
          type: "checkbox", value: g, id: `${idPrefix}-${g}`,
          checked: checked.includes(g) ? "true" : null,
        }),
        ` ${g}`,
      )
    ));
  }
  function selectedGrants(idPrefix) {
    return grantKeys
      .filter((g) => document.getElementById(`${idPrefix}-${g}`).checked)
      .flatMap((g) => grants[g]);
  }

  const nuGrants = grantCheckboxes("nu-grant", []);
  const roleSelect = el("select", { id: "nu-role" },
    Object.keys(roles).map((r) => el("option", { value: r }, r))
  );
  roleSelect.addEventListener("change", () => {
    nuGrants.classList.toggle("hidden", roleSelect.value !== "user");
  });

  const form = el("form", { class: "inline-form" },
    el("input", { type: "text", placeholder: "usuario o correo", id: "nu-email", required: "true" }),
    el("input", { type: "text", placeholder: "nombre", id: "nu-first-name", required: "true" }),
    el("input", { type: "password", placeholder: "contraseña (mín. 8)", id: "nu-password", required: "true" }),
    roleSelect,
    el("button", { class: "btn", type: "submit" }, "Crear"),
  );
  const formError = el("p", { class: "error hidden" });
  content.appendChild(form);
  content.appendChild(el("p", { class: "muted" }, "Acceso por servicio (sólo aplica a role=user):"));
  content.appendChild(nuGrants);
  content.appendChild(formError);

  const tableBody = el("tbody", {});
  content.appendChild(el("table", {},
    el("thead", {}, el("tr", {},
      el("th", {}, "Usuario"), el("th", {}, "Nombre"), el("th", {}, "Rol"),
      el("th", {}, "Accesos"), el("th", {}, "Creado"), el("th", {}, ""))),
    tableBody,
  ));

  async function renderUsers() {
    const users = await api("GET", "/api/admin/users");
    tableBody.innerHTML = "";
    for (const u of users) {
      tableBody.appendChild(el("tr", { "data-user-id": u.id },
        el("td", {}, u.email), el("td", {}, [u.first_name, u.last_name].filter(Boolean).join(" ")),
        badgeCellRole(u.role),
        el("td", {}, grantsSummary(u)),
        el("td", {}, u.created_at || ""), actionsCell(u)));
    }
  }
  function grantsSummary(u) {
    if (u.role === "admin") return "todos";
    const active = grantKeys.filter((g) => grants[g].every((p) => (u.extra_permissions || []).includes(p)));
    return active.length ? active.join(", ") : "—";
  }
  function badgeCellRole(role) {
    return el("td", {}, el("span", { class: "badge " + (role === "admin" ? "badge-healthy" : "badge-unknown") }, role));
  }
  function actionsCell(u) {
    const actions = [
      el("button", { class: "btn btn-secondary", onclick: () => resetPassword(u) }, "Restablecer contraseña"),
      " ",
      el("button", { class: "btn btn-secondary", onclick: () => removeUser(u) }, "Eliminar"),
    ];
    if (u.role === "user") {
      actions.unshift(
        el("button", { class: "btn btn-secondary", onclick: () => editPermissions(u) }, "Editar accesos"),
        " ",
      );
    }
    return el("td", {}, actions);
  }

  function editPermissions(u) {
    const tr = tableBody.querySelector(`tr[data-user-id="${u.id}"]`);
    if (!tr) return;
    const current = grantKeys.filter((g) => grants[g].every((p) => (u.extra_permissions || []).includes(p)));
    const idPrefix = `eu-${u.id}`;
    const checks = grantCheckboxes(idPrefix, current);
    const editError = el("p", { class: "error hidden" });
    const saveBtn = el("button", { class: "btn", type: "button" }, "Guardar");
    const cancelBtn = el("button", { class: "btn btn-secondary", type: "button" }, "Cancelar");
    saveBtn.addEventListener("click", async () => {
      editError.classList.add("hidden");
      try {
        await api("PATCH", `/api/admin/users/${u.id}/permissions`, {
          extra_permissions: selectedGrants(idPrefix),
        });
        await renderUsers();
      } catch (err) {
        editError.textContent = err.message;
        editError.classList.remove("hidden");
      }
    });
    cancelBtn.addEventListener("click", () => { renderUsers(); });
    tr.innerHTML = "";
    tr.appendChild(el("td", { colspan: "6" },
      el("p", { class: "muted" }, `Accesos para ${u.email}:`),
      checks, saveBtn, " ", cancelBtn, editError,
    ));
  }

  async function resetPassword(u) {
    const newPassword = prompt(`Nueva contraseña para ${u.email} (mín. 8 caracteres):`);
    if (!newPassword) return;
    try {
      await api("POST", `/api/admin/users/${u.id}/reset-password`, { new_password: newPassword });
      alert(`Contraseña de ${u.email} restablecida. Deberá cambiarla en su próximo login.`);
    } catch (err) {
      alert(err.message);
    }
  }

  async function removeUser(u) {
    if (!confirm(`¿Eliminar a ${u.email}? Esta acción no se puede deshacer.`)) return;
    try {
      await api("DELETE", `/api/admin/users/${u.id}`);
      await renderUsers();
    } catch (err) {
      alert(err.message);
    }
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    formError.classList.add("hidden");
    try {
      await api("POST", "/api/admin/users", {
        email: document.getElementById("nu-email").value,
        first_name: document.getElementById("nu-first-name").value,
        password: document.getElementById("nu-password").value,
        role: document.getElementById("nu-role").value,
        extra_permissions: selectedGrants("nu-grant"),
      });
      form.reset();
      nuGrants.classList.remove("hidden");
      await renderUsers();
    } catch (err) {
      formError.textContent = err.message;
      formError.classList.remove("hidden");
    }
  });

  await renderUsers();
});

// --- mi progreso (gamification) --------------------------------------
route("progress", async (content) => {
  content.appendChild(el("h2", { class: "page-title" }, "Mi Progreso"));

  const [me, achievements, habits, rewards, goals, leaders] = await Promise.all([
    api("GET", "/api/gamification/me"),
    api("GET", "/api/gamification/achievements"),
    api("GET", "/api/gamification/habits"),
    api("GET", "/api/gamification/rewards"),
    api("GET", "/api/gamification/goals"),
    api("GET", "/api/gamification/leaderboard"),
  ]);

  content.appendChild(el("div", { class: "stat-tiles" },
    el("div", { class: "stat-tile" }, el("div", { class: "value" }, `${me.level}`), el("div", { class: "label" }, "Nivel")),
    el("div", { class: "stat-tile" }, el("div", { class: "value" }, `${me.total_xp}`), el("div", { class: "label" }, "XP total")),
    el("div", { class: "stat-tile" }, el("div", { class: "value" }, `${me.coins}`), el("div", { class: "label" }, "Monedas")),
    el("div", { class: "stat-tile" }, el("div", { class: "value" }, `${me.current_streak}🔥`), el("div", { class: "label" }, "Racha actual")),
    el("div", { class: "stat-tile" }, el("div", { class: "value" }, `${me.longest_streak}`), el("div", { class: "label" }, "Mejor racha")),
  ));

  const pct = me.xp_for_next_level ? Math.round((me.xp_into_level / me.xp_for_next_level) * 100) : 0;
  content.appendChild(el("p", { class: "muted" }, `${me.xp_into_level} / ${me.xp_for_next_level} XP para el nivel ${me.level + 1}`));
  content.appendChild(el("div", { class: "xp-bar-track" }, el("div", { class: "xp-bar-fill", style: `width:${pct}%` })));

  // --- logros ---
  content.appendChild(el("h3", { class: "section-title" }, "Logros"));
  content.appendChild(el("div", { class: "grid" }, achievements.map((a) =>
    el("div", { class: "card achievement-card" + (a.unlocked ? " unlocked" : "") },
      el("span", { class: "icon" }, a.icon), " ",
      el("h3", { style: "display:inline" }, a.name),
      el("p", { class: "muted" }, a.description),
    )
  )));

  // --- habitos ---
  content.appendChild(el("h3", { class: "section-title" }, "Hábitos"));
  const habitForm = el("form", { class: "inline-form" },
    el("input", { type: "text", placeholder: "nombre del hábito", id: "nh-name", required: "true" }),
    el("select", { id: "nh-freq" },
      el("option", { value: "daily" }, "diario"),
      el("option", { value: "weekly" }, "semanal"),
    ),
    el("button", { class: "btn", type: "submit" }, "Añadir"),
  );
  content.appendChild(habitForm);
  const habitList = el("div", { class: "grid" }, habits.map((h) => habitCard(h)));
  content.appendChild(habitList);

  function habitCard(h) {
    return el("div", { class: "card" },
      el("h3", {}, h.name), el("p", { class: "muted" }, `${h.frequency} · racha ${h.streak}`),
      el("button", {
        class: "btn btn-secondary", disabled: h.logged_today ? "true" : null,
        onclick: async (e) => {
          await api("POST", `/api/gamification/habits/${h.id}/log`);
          location.reload();
        },
      }, h.logged_today ? "Hecho hoy" : "Marcar hecho hoy"),
    );
  }
  habitForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    await api("POST", "/api/gamification/habits", {
      name: document.getElementById("nh-name").value,
      frequency: document.getElementById("nh-freq").value,
    });
    location.reload();
  });

  // --- recompensas ---
  content.appendChild(el("h3", { class: "section-title" }, "Recompensas"));
  const rewardForm = el("form", { class: "inline-form" },
    el("input", { type: "text", placeholder: "nombre de la recompensa", id: "nr-name", required: "true" }),
    el("input", { type: "number", placeholder: "coste en monedas", id: "nr-cost", min: "1", required: "true" }),
    el("button", { class: "btn", type: "submit" }, "Añadir"),
  );
  content.appendChild(rewardForm);
  const rewardError = el("p", { class: "error hidden" });
  content.appendChild(rewardError);
  content.appendChild(el("div", { class: "grid" }, rewards.map((r) =>
    el("div", { class: "card" },
      el("h3", {}, r.name), el("p", { class: "muted" }, `${r.coin_cost} monedas`),
      el("button", { class: "btn btn-secondary", onclick: async () => {
        rewardError.classList.add("hidden");
        try {
          await api("POST", `/api/gamification/rewards/${r.id}/redeem`);
          location.reload();
        } catch (err) {
          rewardError.textContent = err.message;
          rewardError.classList.remove("hidden");
        }
      } }, "Canjear"),
    )
  )));
  rewardForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    await api("POST", "/api/gamification/rewards", {
      name: document.getElementById("nr-name").value,
      coin_cost: Number(document.getElementById("nr-cost").value),
    });
    location.reload();
  });

  // --- metas ---
  content.appendChild(el("h3", { class: "section-title" }, "Metas"));
  const goalForm = el("form", { class: "inline-form" },
    el("select", { id: "ng-period" },
      el("option", { value: "daily" }, "diaria"),
      el("option", { value: "weekly" }, "semanal"),
      el("option", { value: "monthly" }, "mensual"),
      el("option", { value: "annual" }, "anual"),
    ),
    el("select", { id: "ng-type" },
      el("option", { value: "tasks_completed" }, "tasks completadas"),
      el("option", { value: "xp_earned" }, "XP ganado"),
    ),
    el("input", { type: "number", placeholder: "objetivo", id: "ng-value", min: "1", required: "true" }),
    el("button", { class: "btn", type: "submit" }, "Añadir"),
  );
  content.appendChild(goalForm);
  content.appendChild(el("div", { class: "grid" }, goals.map((g) => {
    const goalPct = Math.min(100, Math.round((g.progress / g.target_value) * 100));
    return el("div", { class: "card" },
      el("h3", {}, `${g.period} · ${g.target_type}`),
      el("p", { class: "muted" }, `${g.progress} / ${g.target_value}${g.completed ? " ✅" : ""}`),
      el("div", { class: "progress-track" }, el("div", { class: "progress-fill", style: `width:${goalPct}%` })),
    );
  })));
  goalForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    await api("POST", "/api/gamification/goals", {
      period: document.getElementById("ng-period").value,
      target_type: document.getElementById("ng-type").value,
      target_value: Number(document.getElementById("ng-value").value),
    });
    location.reload();
  });

  // --- leaderboard ---
  content.appendChild(el("h3", { class: "section-title" }, "Leaderboard"));
  content.appendChild(el("table", {},
    el("thead", {}, el("tr", {}, el("th", {}, "#"), el("th", {}, "Usuario"), el("th", {}, "Nivel"), el("th", {}, "XP"))),
    el("tbody", {}, leaders.map((l) =>
      el("tr", {}, el("td", {}, `${l.rank}`), el("td", {}, l.user_id), el("td", {}, `${l.level}`), el("td", {}, `${l.total_xp}`))
    ))
  ));
});

boot();
