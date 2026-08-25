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

// --- temas ---------------------------------------------------------------
// Cada cuenta elige el suyo (pedido explícito del usuario: admin puede
// tener un tema distinto al de otro usuario) -- se guarda en el perfil
// (auth/app/domain/users.py THEMES) y se aplica vía data-app-theme en
// <html> (ver frontend/app/static/style.css).
const THEMES = [
  { id: "freya", label: "Freya (original)" },
  { id: "claro", label: "Claro" },
  { id: "oscuro", label: "Oscuro" },
  { id: "naturaleza", label: "Naturaleza" },
  { id: "ciudad", label: "Ciudad" },
  { id: "tormenta", label: "Tormenta eléctrica" },
];

const themeSelect = document.getElementById("theme-select");
for (const t of THEMES) {
  themeSelect.appendChild(el("option", { value: t.id }, t.label));
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-app-theme", theme || "freya");
}

themeSelect.addEventListener("change", async () => {
  const theme = themeSelect.value;
  applyTheme(theme);
  try {
    await api("PATCH", "/api/session/theme", { theme });
    if (currentUser) currentUser.theme = theme;
  } catch (err) {
    if (currentUser) applyTheme(currentUser.theme);
    alert(err.message);
  }
});

async function boot() {
  try {
    currentUser = await api("GET", "/api/session/me");
    const label = currentUser.email || currentUser.first_name || currentUser.user_id;
    document.getElementById("whoami").textContent = `${label} · ${currentUser.role}`;
    document.querySelector('a[data-route="admin-users"]').classList.toggle(
      "hidden", currentUser.role !== "admin"
    );
    document.querySelector('a[data-route="admin-tenants"]').classList.toggle(
      "hidden", currentUser.role !== "admin"
    );
    // Gamification es de autoservicio para cuentas "user" (hábitos, XP,
    // recompensas) -- una cuenta admin no tiene "yo" que gamificar (pedido
    // explícito del usuario, ver gamification/app/deps.py:user_id_of).
    document.querySelector('a[data-route="progress"]').classList.toggle(
      "hidden", currentUser.role === "admin"
    );
    applyTheme(currentUser.theme);
    themeSelect.value = currentUser.theme || "freya";
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
function renderServiceGrid(content, services) {
  const grid = el("div", { class: "grid" });
  for (const svc of services) {
    grid.appendChild(
      el("div", { class: "card" },
        el("h3", {}, svc.name || svc.service),
        badge(svc.status),
        svc.description ? el("p", {}, svc.description) : null,
        svc.phase ? el("p", { class: "muted" }, `Fase ${svc.phase}`) : null,
      )
    );
  }
  content.appendChild(grid);
  if (!services.length) content.appendChild(el("p", { class: "empty" }, "Sin servicios en este proyecto."));
}

function grantedTenantsFor(service) {
  return Object.entries(currentUser.tenant_grants || {})
    .filter(([, perms]) => perms.includes(`read:${service}`))
    .map(([t]) => t);
}

function monitoringGrantedTenants() {
  return grantedTenantsFor("monitoring");
}

function renderTenantPicker(content, { title, tenants, hashBase, emptyHint }) {
  content.appendChild(el("h2", { class: "page-title" }, title));
  if (!tenants.length) {
    content.appendChild(el("p", { class: "empty" }, emptyHint));
    return;
  }
  const grid = el("div", { class: "grid" });
  for (const t of tenants) {
    grid.appendChild(el("div", { class: "card clickable", onclick: () => { location.hash = `${hashBase}/${encodeURIComponent(t)}`; } },
      el("h3", {}, `📁 ${t}`), el("p", { class: "muted" }, "Elegir este proyecto")));
  }
  content.appendChild(grid);
}

// El admin conserva la vista global de siempre, sin selector de proyecto
// (pedido explícito del usuario: "admin sólo tiene vista global de
// Freya"); una cuenta "user" siempre elige el proyecto primero -- entrar
// al Panel muestra los proyectos, no sus servicios directamente (pedido
// explícito del usuario).
route("dashboard", async (content, [project]) => {
  if (currentUser.role === "admin") {
    content.appendChild(el("h2", { class: "page-title" }, "Panel"));
    const data = await api("GET", "/api/catalog");
    renderServiceGrid(content, data.services);
    return;
  }

  const grantedTenants = monitoringGrantedTenants();
  if (!project) {
    renderTenantPicker(content, {
      title: "Panel", tenants: grantedTenants, hashBase: "#/dashboard",
      emptyHint: "No tienes acceso al monitoreo de ningún proyecto todavía. Pide a un administrador que te dé acceso.",
    });
    return;
  }

  const decodedProject = decodeURIComponent(project);
  if (!grantedTenants.includes(decodedProject)) {
    content.appendChild(el("p", { class: "error" }, "No tienes acceso al monitoreo de ese proyecto."));
    return;
  }
  content.appendChild(el("div", { class: "breadcrumb" },
    el("a", { onclick: () => { location.hash = "#/dashboard"; } }, "Panel"), ` / ${decodedProject}`));
  content.appendChild(el("h2", { class: "page-title" }, decodedProject));
  const data = await api("GET", `/api/catalog?project=${encodeURIComponent(decodedProject)}`);
  renderServiceGrid(content, data.services);
});

// --- git ------------------------------------------------------------
async function renderGitPanel(content, { tenant, repoId, hashBase }) {
  const q = `?project=${encodeURIComponent(tenant)}`;
  if (!repoId) {
    content.appendChild(el("h2", { class: "page-title" }, "Git"));
    const repos = await api("GET", `/api/git/repos${q}`);
    if (!repos.length) { content.appendChild(el("p", { class: "empty" }, "Sin repositorios.")); return; }
    const table = el("table", {},
      el("thead", {}, el("tr", {}, el("th", {}, "Repositorio"), el("th", {}, "Rama por defecto"), el("th", {}, "Visibilidad"))),
      el("tbody", {}, repos.map((r) =>
        el("tr", { class: "clickable", onclick: () => { location.hash = `${hashBase}/${r.id}`; } },
          el("td", {}, r.repo_name), el("td", {}, r.default_branch), el("td", {}, r.visibility))
      ))
    );
    content.appendChild(table);
    return;
  }

  const [repo, branches, commits] = await Promise.all([
    api("GET", `/api/git/repos/${repoId}${q}`),
    api("GET", `/api/git/repos/${repoId}/branches${q}`),
    api("GET", `/api/git/repos/${repoId}/commits${q}`),
  ]);
  content.appendChild(el("div", { class: "breadcrumb" }, el("a", { onclick: () => { location.hash = hashBase; } }, "Git"), ` / ${repo.repo_name}`));
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
}

route("git", async (content, pathParts) => {
  if (currentUser.role === "admin") {
    await renderGitPanel(content, { tenant: "freya", repoId: pathParts[0], hashBase: "#/git" });
    return;
  }
  const grantedTenants = grantedTenantsFor("git");
  const [tenant, repoId] = pathParts;
  if (!tenant) {
    renderTenantPicker(content, {
      title: "Git", tenants: grantedTenants, hashBase: "#/git",
      emptyHint: "No tienes acceso a git de ningún proyecto todavía. Pide a un administrador que te dé acceso.",
    });
    return;
  }
  const decodedTenant = decodeURIComponent(tenant);
  if (!grantedTenants.includes(decodedTenant)) {
    content.appendChild(el("p", { class: "error" }, "No tienes acceso a git de ese proyecto."));
    return;
  }
  await renderGitPanel(content, { tenant: decodedTenant, repoId, hashBase: `#/git/${tenant}` });
});

// --- storage (Mi Drive / proyectos) --------------------------------------
// Cada usuario tiene su propio espacio en el bucket reservado "users",
// siempre en el tenant "freya" (su identidad vive ahí -- pedido explícito
// del usuario: la cuenta es una sola, lo que cambia por proyecto es qué
// puede ver). Un proyecto (tenant) con storage concedido aporta además su
// bucket compartido "project". Las carpetas no son un concepto real de
// storage -- se simulan con "/" en la clave, y una carpeta vacía se
// representa con un objeto ".keep" (mismo truco que cualquier consola S3).
function driveUpload(bucket, tenant, key, file, onProgress) {
  // XMLHttpRequest, no fetch: es la única API del navegador que reporta
  // progreso de SUBIDA (xhr.upload.onprogress) -- fetch no lo expone.
  return new Promise((resolve, reject) => {
    const encodedKey = key.split("/").map(encodeURIComponent).join("/");
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", `/api/storage/${bucket}/${encodedKey}?project=${encodeURIComponent(tenant)}`);
    xhr.withCredentials = true;
    xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream");
    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    });
    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) { resolve(); return; }
      let message = `HTTP ${xhr.status}`;
      try {
        const envelope = JSON.parse(xhr.responseText);
        if (envelope && envelope.error) message = envelope.error.message;
      } catch { /* respuesta no-JSON */ }
      reject(new Error(message));
    });
    xhr.addEventListener("error", () => reject(new Error("Error de red durante la subida")));
    xhr.send(file);
  });
}

function driveDownload(bucket, tenant, key) {
  // <a download> + click programático: dispara la descarga nativa del
  // navegador (con su propia barra de progreso) sin navegar la pestaña --
  // funciona igual para uno o para varios archivos seguidos.
  const encodedKey = key.split("/").map(encodeURIComponent).join("/");
  const a = document.createElement("a");
  a.href = `/api/storage/${bucket}/${encodedKey}?project=${encodeURIComponent(tenant)}`;
  a.download = key.split("/").pop();
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function renderDirTree(nodes) {
  const ul = el("ul", { class: "dir-tree" });
  for (const n of nodes) {
    ul.appendChild(el("li", {},
      (n.type === "folder" ? "📁 " : "📄 ") + n.name,
      n.type === "folder" && n.children.length ? renderDirTree(n.children) : null,
    ));
  }
  return ul;
}

// Núcleo común del explorador de archivos: lo usa tanto Mi Drive (admin y
// personal de un "user") como el storage de un proyecto -- lo único que
// cambia es qué bucket/tenant y bajo qué ruta de hash vive cada uno.
async function renderDriveBrowser(content, { bucket, tenant, decodedParts, prefix, hashBase, driveLabel }) {
  content.appendChild(el("h2", { class: "page-title" }, driveLabel));

  const crumbs = [el("a", { onclick: () => { location.hash = hashBase; } }, driveLabel)];
  for (let i = 0; i < decodedParts.length; i++) {
    const target = decodedParts.slice(0, i + 1).map(encodeURIComponent).join("/");
    crumbs.push(" / ");
    crumbs.push(el("a", { onclick: () => { location.hash = `${hashBase}/${target}`; } }, decodedParts[i]));
  }
  content.appendChild(el("div", { class: "breadcrumb" }, crumbs));

  const folderInput = el("input", { type: "text", placeholder: "nombre de la carpeta", id: "nf-name" });
  const folderForm = el("form", { class: "inline-form" }, folderInput,
    el("button", { class: "btn btn-secondary", type: "submit" }, "Nueva carpeta"));
  const fileInput = el("input", { type: "file", id: "up-file", required: "true", multiple: "true" });
  const uploadForm = el("form", { class: "inline-form" }, fileInput,
    el("button", { class: "btn", type: "submit" }, "Subir archivos"));
  const selectAllBtn = el("button", { class: "btn btn-secondary", type: "button" }, "Seleccionar todo");
  const downloadSelectedBtn = el("button", { class: "btn btn-secondary", type: "button" }, "Descargar seleccionados");
  const deleteSelectedBtn = el("button", { class: "btn btn-danger", type: "button" }, "Eliminar seleccionados");
  const treeBtn = el("button", { class: "btn btn-secondary", type: "button" }, "Ver árbol de directorios");
  const trashBtn = el("button", { class: "btn btn-secondary", type: "button" }, "Papelera");
  content.appendChild(el("div", { class: "toolbar" }, folderForm, uploadForm, selectAllBtn, downloadSelectedBtn, deleteSelectedBtn, treeBtn, trashBtn));

  const progressLabel = el("span", { class: "muted" });
  const progressBar = el("progress", { max: "100", value: "0" });
  const progressWrap = el("div", { class: "upload-progress hidden" }, progressLabel, progressBar);
  content.appendChild(progressWrap);

  const treeWrap = el("div", { class: "hidden" });
  content.appendChild(treeWrap);

  const trashWrap = el("div", { class: "hidden" });
  content.appendChild(trashWrap);

  const toolbarError = el("p", { class: "error hidden" });
  content.appendChild(toolbarError);
  function showError(err) {
    toolbarError.textContent = err.message;
    toolbarError.classList.remove("hidden");
  }

  const table = el("table", {},
    el("thead", {}, el("tr", {}, el("th", {}, ""), el("th", {}, "Nombre"), el("th", {}, "Tamaño"), el("th", {}, "Modificado"), el("th", {}, ""))),
    el("tbody", {}),
  );
  const emptyMsg = el("p", { class: "empty hidden" }, "Carpeta vacía.");
  content.appendChild(table);
  content.appendChild(emptyMsg);

  async function listPrefix(p) {
    const res = await api("GET", `/api/storage/${bucket}?prefix=${encodeURIComponent(p)}&limit=200&project=${encodeURIComponent(tenant)}`);
    return res.objects || res.items || res;
  }

  function objectUrl(key) {
    const encodedKey = key.split("/").map(encodeURIComponent).join("/");
    return `/api/storage/${bucket}/${encodedKey}?project=${encodeURIComponent(tenant)}`;
  }

  async function deleteFolder(folderPrefix) {
    for (const o of await listPrefix(folderPrefix)) {
      await api("DELETE", objectUrl(o.key));
    }
  }

  async function load() {
    const items = await listPrefix(prefix);
    const folders = new Set();
    const files = [];
    for (const o of items) {
      const rel = o.key.slice(prefix.length);
      if (!rel) continue;
      const slash = rel.indexOf("/");
      if (slash === -1) files.push({ ...o, name: rel });
      else folders.add(rel.slice(0, slash));
    }

    const tbody = table.querySelector("tbody");
    tbody.innerHTML = "";
    emptyMsg.classList.toggle("hidden", folders.size > 0 || files.length > 0);

    for (const name of [...folders].sort()) {
      const target = [...decodedParts, name].map(encodeURIComponent).join("/");
      tbody.appendChild(el("tr", { class: "clickable", onclick: () => { location.hash = `${hashBase}/${target}`; } },
        el("td", {}, ""),
        el("td", {}, `📁 ${name}`), el("td", {}, ""), el("td", {}, ""),
        el("td", {}, el("button", {
          class: "btn btn-danger", type: "button",
          onclick: async (ev) => {
            ev.stopPropagation();
            if (!confirm(`¿Borrar la carpeta '${name}' y todo su contenido?`)) return;
            await deleteFolder(`${prefix}${name}/`);
            await load();
          },
        }, "Borrar"))));
    }
    for (const f of files.filter((f) => f.name !== ".keep").sort((a, b) => a.name.localeCompare(b.name))) {
      const fullKey = `${prefix}${f.name}`;
      const checkbox = el("input", { type: "checkbox", class: "file-select" });
      checkbox.dataset.key = fullKey;
      tbody.appendChild(el("tr", {}, el("td", {}, checkbox),
        el("td", {}, `📄 ${f.name}`), el("td", {}, String(f.size ?? "")),
        el("td", {}, f.last_modified || f.updated_at || ""),
        el("td", {},
          el("button", { class: "btn btn-secondary", type: "button", onclick: () => driveDownload(bucket, tenant, fullKey) }, "Descargar"),
          el("button", {
            class: "btn btn-danger", type: "button",
            onclick: async () => {
              if (!confirm(`¿Borrar '${f.name}'?`)) return;
              await api("DELETE", objectUrl(fullKey));
              await load();
            },
          }, "Borrar"))));
    }
  }
  await load();

  downloadSelectedBtn.addEventListener("click", () => {
    toolbarError.classList.add("hidden");
    const keys = [...table.querySelectorAll(".file-select:checked")].map((cb) => cb.dataset.key);
    if (!keys.length) { showError(new Error("Selecciona al menos un archivo para descargar")); return; }
    for (const key of keys) driveDownload(bucket, tenant, key);
  });

  selectAllBtn.addEventListener("click", () => {
    const boxes = [...table.querySelectorAll(".file-select")];
    const allChecked = boxes.length > 0 && boxes.every((cb) => cb.checked);
    for (const cb of boxes) cb.checked = !allChecked;
  });

  deleteSelectedBtn.addEventListener("click", async () => {
    toolbarError.classList.add("hidden");
    const keys = [...table.querySelectorAll(".file-select:checked")].map((cb) => cb.dataset.key);
    if (!keys.length) { showError(new Error("Selecciona al menos un archivo para eliminar")); return; }
    if (!confirm(`¿Borrar ${keys.length} archivo(s) seleccionado(s)?`)) return;
    try {
      for (const key of keys) await api("DELETE", objectUrl(key));
      await load();
    } catch (err) { showError(err); }
  });

  treeBtn.addEventListener("click", async () => {
    toolbarError.classList.add("hidden");
    trashWrap.classList.add("hidden");
    trashWrap.innerHTML = "";
    if (!treeWrap.classList.contains("hidden")) {
      treeWrap.classList.add("hidden");
      treeWrap.innerHTML = "";
      return;
    }
    try {
      const res = await api("GET", `/api/storage/${bucket}/tree?prefix=${encodeURIComponent(prefix)}&project=${encodeURIComponent(tenant)}`);
      treeWrap.innerHTML = "";
      treeWrap.appendChild(res.tree.length
        ? renderDirTree(res.tree)
        : el("p", { class: "empty" }, "Carpeta vacía."));
      treeWrap.classList.remove("hidden");
    } catch (err) { showError(err); }
  });

  async function loadTrash() {
    const res = await api("GET", `/api/storage/${bucket}/trash?project=${encodeURIComponent(tenant)}`);
    trashWrap.innerHTML = "";
    if (!res.objects.length) {
      trashWrap.appendChild(el("p", { class: "empty" }, "La papelera está vacía."));
      return;
    }
    const trashTable = el("table", {},
      el("thead", {}, el("tr", {}, el("th", {}, "Nombre"), el("th", {}, "Tamaño"), el("th", {}, "Borrado"), el("th", {}, ""))),
      el("tbody", {}, res.objects.map((o) => el("tr", {},
        el("td", {}, `📄 ${o.key}`), el("td", {}, String(o.size ?? "")), el("td", {}, o.deleted_at || ""),
        el("td", {},
          el("button", {
            class: "btn btn-secondary", type: "button",
            onclick: async () => {
              try {
                await api("POST", `/api/storage/${bucket}/trash/${o.id}/restore?project=${encodeURIComponent(tenant)}`);
                await loadTrash();
                await load();
              } catch (err) { showError(err); }
            },
          }, "Restaurar"),
          el("button", {
            class: "btn btn-danger", type: "button",
            onclick: async () => {
              if (!confirm(`¿Eliminar '${o.key}' para siempre? No se puede deshacer.`)) return;
              try {
                await api("DELETE", `/api/storage/${bucket}/trash/${o.id}?project=${encodeURIComponent(tenant)}`);
                await loadTrash();
              } catch (err) { showError(err); }
            },
          }, "Eliminar para siempre"),
        ),
      ))),
    );
    trashWrap.appendChild(trashTable);
  }

  trashBtn.addEventListener("click", async () => {
    toolbarError.classList.add("hidden");
    treeWrap.classList.add("hidden");
    treeWrap.innerHTML = "";
    if (!trashWrap.classList.contains("hidden")) {
      trashWrap.classList.add("hidden");
      trashWrap.innerHTML = "";
      return;
    }
    try {
      await loadTrash();
      trashWrap.classList.remove("hidden");
    } catch (err) { showError(err); }
  });

  folderForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    toolbarError.classList.add("hidden");
    const name = folderInput.value.trim();
    if (!name) return;
    try {
      await driveUpload(bucket, tenant, `${prefix}${name}/.keep`, new File([], ".keep"));
      folderForm.reset();
      await load();
    } catch (err) { showError(err); }
  });

  // Cola real: si se elige otro lote de archivos mientras el anterior aún
  // sube, se apilan aquí en vez de perderse -- antes cada submit disparaba
  // su propio for suelto, y un segundo submit mientras el primero seguía
  // corriendo lanzaba un segundo loop en paralelo peleando por la misma
  // barra de progreso (parecía que el archivo nuevo "reemplazaba" al
  // anterior en vez de sumarse a la cola).
  const uploadQueue = [];
  let uploadWorkerActive = false;

  async function processUploadQueue() {
    if (uploadWorkerActive) return;
    uploadWorkerActive = true;
    progressWrap.classList.remove("hidden");
    try {
      while (uploadQueue.length) {
        const { key, file } = uploadQueue[0];
        progressLabel.textContent = `Subiendo ${file.name} (quedan ${uploadQueue.length})`;
        progressBar.value = 0;
        try {
          await driveUpload(bucket, tenant, key, file, (frac) => { progressBar.value = frac * 100; });
        } catch (err) {
          showError(err);
        }
        uploadQueue.shift();
      }
      await load();
    } finally {
      progressWrap.classList.add("hidden");
      uploadWorkerActive = false;
    }
  }

  uploadForm.addEventListener("submit", (e) => {
    e.preventDefault();
    toolbarError.classList.add("hidden");
    const files = [...fileInput.files];
    if (!files.length) return;
    for (const file of files) uploadQueue.push({ key: `${prefix}${file.name}`, file });
    uploadForm.reset();
    processUploadQueue();
  });
}

function storageGrantedTenants() {
  return grantedTenantsFor("storage");
}

route("storage", async (content, pathParts) => {
  // El admin conserva exactamente el Mi Drive de siempre, sin selector de
  // proyecto (pedido explícito del usuario: "admin sólo tiene vista global
  // de Freya") -- misma ruta de hash que tenía antes de este cambio.
  if (currentUser.role === "admin") {
    const decodedParts = pathParts.map(decodeURIComponent).filter(Boolean);
    const prefix = `${currentUser.user_id}/${decodedParts.length ? decodedParts.join("/") + "/" : ""}`;
    await renderDriveBrowser(content, {
      bucket: "users", tenant: "freya", decodedParts, prefix,
      hashBase: "#/storage", driveLabel: "Mi Drive",
    });
    return;
  }

  const grantedTenants = storageGrantedTenants();
  if (!grantedTenants.length) {
    content.appendChild(el("h2", { class: "page-title" }, "Storage"));
    content.appendChild(el("p", { class: "empty" }, "No tienes acceso a storage de ningún proyecto todavía. Pide a un administrador que te dé acceso."));
    return;
  }

  const [mode, ...rest] = pathParts;

  if (!mode) {
    content.appendChild(el("h2", { class: "page-title" }, "Storage"));
    const grid = el("div", { class: "grid" });
    if (grantedTenants.includes("freya")) {
      grid.appendChild(el("div", { class: "card clickable", onclick: () => { location.hash = "#/storage/personal"; } },
        el("h3", {}, `📁 ${currentUser.first_name || currentUser.email}`),
        el("p", { class: "muted" }, "Tu espacio personal")));
    }
    for (const t of grantedTenants) {
      grid.appendChild(el("div", { class: "card clickable", onclick: () => { location.hash = `#/storage/project/${encodeURIComponent(t)}`; } },
        el("h3", {}, `📁 ${t}`), el("p", { class: "muted" }, "Storage del proyecto")));
    }
    content.appendChild(grid);
    return;
  }

  if (mode === "personal") {
    if (!grantedTenants.includes("freya")) {
      content.appendChild(el("p", { class: "error" }, "No tienes acceso a tu espacio personal."));
      return;
    }
    const decodedParts = rest.map(decodeURIComponent).filter(Boolean);
    const prefix = `${currentUser.user_id}/${decodedParts.length ? decodedParts.join("/") + "/" : ""}`;
    await renderDriveBrowser(content, {
      bucket: "users", tenant: "freya", decodedParts, prefix,
      hashBase: "#/storage/personal", driveLabel: currentUser.first_name || currentUser.email,
    });
    return;
  }

  if (mode === "project") {
    const [rawTenant, ...pathRest] = rest;
    const projectTenant = rawTenant ? decodeURIComponent(rawTenant) : "";
    if (!projectTenant || !grantedTenants.includes(projectTenant)) {
      content.appendChild(el("p", { class: "error" }, "No tienes acceso al storage de ese proyecto."));
      return;
    }
    const decodedParts = pathRest.map(decodeURIComponent).filter(Boolean);
    const prefix = decodedParts.length ? decodedParts.join("/") + "/" : "";
    await renderDriveBrowser(content, {
      bucket: "project", tenant: projectTenant, decodedParts, prefix,
      hashBase: `#/storage/project/${encodeURIComponent(projectTenant)}`, driveLabel: projectTenant,
    });
    return;
  }

  content.appendChild(el("p", { class: "error" }, "Ruta de storage desconocida."));
});

// --- cicd ------------------------------------------------------------
async function renderCicdPanel(content, { tenant, pipelineId, hashBase }) {
  const q = `?project=${encodeURIComponent(tenant)}`;
  if (!pipelineId) {
    content.appendChild(el("h2", { class: "page-title" }, "CI/CD"));
    const pipelines = await api("GET", `/api/cicd/pipelines${q}`);
    content.appendChild(el("table", {},
      el("thead", {}, el("tr", {}, el("th", {}, "Pipeline"), el("th", {}, "Servicio"), el("th", {}, "Tipo"))),
      el("tbody", {}, pipelines.map((p) =>
        el("tr", { class: "clickable", onclick: () => { location.hash = `${hashBase}/${p.id}`; } },
          el("td", {}, p.name), el("td", {}, p.service), el("td", {}, p.pipeline_type))
      ))
    ));
    return;
  }

  async function renderRuns() {
    const runs = await api("GET", `/api/cicd/pipelines/${pipelineId}/runs${q}`);
    const body = document.getElementById("runs-body");
    body.innerHTML = "";
    for (const r of runs) {
      body.appendChild(el("tr", {},
        el("td", {}, r.id.slice(-10)), badgeCell(r.status), el("td", {}, r.triggered_by),
        el("td", {}, r.started_at || ""), el("td", {}, r.finished_at || "")));
    }
  }
  function badgeCell(status) { return el("td", {}, badge(status)); }

  content.appendChild(el("div", { class: "breadcrumb" }, el("a", { onclick: () => { location.hash = hashBase; } }, "CI/CD"), ` / ${pipelineId}`));
  const toolbar = el("div", { class: "toolbar" },
    el("h2", { class: "page-title", style: "margin:0" }, "Runs"),
    el("button", { class: "btn", onclick: async (e) => {
      e.target.disabled = true;
      try { await api("POST", `/api/cicd/pipelines/${pipelineId}/trigger${q}`); await renderRuns(); }
      finally { e.target.disabled = false; }
    } }, "Disparar pipeline")
  );
  content.appendChild(toolbar);
  content.appendChild(el("table", {},
    el("thead", {}, el("tr", {}, el("th", {}, "Run"), el("th", {}, "Estado"), el("th", {}, "Origen"), el("th", {}, "Inicio"), el("th", {}, "Fin"))),
    el("tbody", { id: "runs-body" })
  ));
  await renderRuns();
}

route("cicd", async (content, pathParts) => {
  if (currentUser.role === "admin") {
    await renderCicdPanel(content, { tenant: "freya", pipelineId: pathParts[0], hashBase: "#/cicd" });
    return;
  }
  const grantedTenants = grantedTenantsFor("cicd");
  const [tenant, pipelineId] = pathParts;
  if (!tenant) {
    renderTenantPicker(content, {
      title: "CI/CD", tenants: grantedTenants, hashBase: "#/cicd",
      emptyHint: "No tienes acceso al CI/CD de ningún proyecto todavía. Pide a un administrador que te dé acceso.",
    });
    return;
  }
  const decodedTenant = decodeURIComponent(tenant);
  if (!grantedTenants.includes(decodedTenant)) {
    content.appendChild(el("p", { class: "error" }, "No tienes acceso al CI/CD de ese proyecto."));
    return;
  }
  await renderCicdPanel(content, { tenant: decodedTenant, pipelineId, hashBase: `#/cicd/${tenant}` });
});

// --- projects ------------------------------------------------------------
async function renderProjectsPanel(content, { tenant, projectId, hashBase }) {
  const q = `?project=${encodeURIComponent(tenant)}`;
  if (!projectId) {
    content.appendChild(el("h2", { class: "page-title" }, "Proyectos"));
    const projects = await api("GET", `/api/projects${q}`);
    if (!projects.length) { content.appendChild(el("p", { class: "empty" }, "Sin proyectos.")); return; }
    content.appendChild(el("div", { class: "grid" }, projects.map((p) =>
      el("div", { class: "card clickable", onclick: () => { location.hash = `${hashBase}/${p.id}`; } },
        el("h3", {}, p.project_name), el("p", { class: "muted" }, p.project_type || ""))
    )));
    return;
  }

  content.appendChild(el("div", { class: "breadcrumb" }, el("a", { onclick: () => { location.hash = hashBase; } }, "Proyectos"), ` / ${projectId}`));
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
    const kanban = await api("GET", `/api/projects/${projectId}/kanban${q}`);
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
        await api("PUT", `/api/projects/tasks/${taskId}${q}`, { status: col.status });
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
}

route("projects", async (content, pathParts) => {
  if (currentUser.role === "admin") {
    await renderProjectsPanel(content, { tenant: "freya", projectId: pathParts[0], hashBase: "#/projects" });
    return;
  }
  const grantedTenants = grantedTenantsFor("project-manager");
  const [tenant, projectId] = pathParts;
  if (!tenant) {
    renderTenantPicker(content, {
      title: "Proyectos", tenants: grantedTenants, hashBase: "#/projects",
      emptyHint: "No tienes acceso a proyectos de ningún tenant todavía. Pide a un administrador que te dé acceso.",
    });
    return;
  }
  const decodedTenant = decodeURIComponent(tenant);
  if (!grantedTenants.includes(decodedTenant)) {
    content.appendChild(el("p", { class: "error" }, "No tienes acceso a los proyectos de ese tenant."));
    return;
  }
  await renderProjectsPanel(content, { tenant: decodedTenant, projectId, hashBase: `#/projects/${tenant}` });
});

// --- admin: usuarios ------------------------------------------------------
route("admin-users", async (content) => {
  content.appendChild(el("h2", { class: "page-title" }, "Usuarios"));

  // Sólo 2 tipos de cuenta (user/admin) -- el acceso por servicio de una
  // cuenta "user" es una combinación libre de grants (checkboxes), no un
  // role aparte por servicio. storage/monitoring quedan fuera de esto
  // (tenantGrantDefs, más abajo): se conceden por proyecto, no de forma
  // global (pedido explícito del usuario).
  const [roles, grants, tenants, tenantGrantDefs] = await Promise.all([
    api("GET", "/api/admin/roles"),
    api("GET", "/api/admin/service-grants"),
    api("GET", "/api/admin/tenants"),
    api("GET", "/api/admin/tenant-grants"),
  ]);
  const grantKeys = Object.keys(grants);
  const tenantServiceKeys = Object.keys(tenantGrantDefs);

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

  async function editPermissions(u) {
    const tr = tableBody.querySelector(`tr[data-user-id="${u.id}"]`);
    if (!tr) return;
    const current = grantKeys.filter((g) => grants[g].every((p) => (u.extra_permissions || []).includes(p)));
    const idPrefix = `eu-${u.id}`;
    const checks = grantCheckboxes(idPrefix, current);

    // Accesos por proyecto (storage/monitoring, ver tenantGrantDefs) --
    // tener el tenant no da nada por sí solo, cada servicio se marca
    // aparte, por tenant (pedido explícito del usuario).
    const userTenantGrants = await api("GET", `/api/admin/users/${u.id}/tenants`);
    function tenantCheckboxId(tenantId, service) {
      return `${idPrefix}-tg-${tenantId}-${service}`;
    }
    const tenantTable = el("table", {},
      el("thead", {}, el("tr", {},
        el("th", {}, "Proyecto"), ...tenantServiceKeys.map((s) => el("th", {}, s)))),
      el("tbody", {}, tenants.map((t) => el("tr", {},
        el("td", {}, t.name || t.id),
        ...tenantServiceKeys.map((service) => el("td", {},
          el("input", {
            type: "checkbox", id: tenantCheckboxId(t.id, service),
            checked: tenantGrantDefs[service].every((p) => (userTenantGrants[t.id] || []).includes(p)) ? "true" : null,
          })
        )),
      ))),
    );

    const editError = el("p", { class: "error hidden" });
    const saveBtn = el("button", { class: "btn", type: "button" }, "Guardar");
    const cancelBtn = el("button", { class: "btn btn-secondary", type: "button" }, "Cancelar");
    saveBtn.addEventListener("click", async () => {
      editError.classList.add("hidden");
      try {
        await api("PATCH", `/api/admin/users/${u.id}/permissions`, {
          extra_permissions: selectedGrants(idPrefix),
        });
        for (const t of tenants) {
          const permissions = tenantServiceKeys
            .filter((service) => document.getElementById(tenantCheckboxId(t.id, service)).checked)
            .flatMap((service) => tenantGrantDefs[service]);
          await api("PUT", `/api/admin/users/${u.id}/tenants/${encodeURIComponent(t.id)}`, { permissions });
        }
        await renderUsers();
      } catch (err) {
        editError.textContent = err.message;
        editError.classList.remove("hidden");
      }
    });
    cancelBtn.addEventListener("click", () => { renderUsers(); });
    tr.innerHTML = "";
    tr.appendChild(el("td", { colspan: "6" },
      el("p", { class: "muted" }, `Accesos por servicio para ${u.email}:`),
      checks,
      el("p", { class: "muted" }, "Accesos por proyecto (tener el proyecto asignado no da ningún permiso por sí solo):"),
      tenantTable,
      saveBtn, " ", cancelBtn, editError,
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

// --- tenants (proyectos) ------------------------------------------------
// Crear un tenant es sólo aislamiento de datos (pedido explícito del
// usuario): registra el tenant y aprovisiona su storage (schema propio +
// bucket "project") -- no levanta ningún contenedor ni servicio nuevo.
route("admin-tenants", async (content) => {
  content.appendChild(el("h2", { class: "page-title" }, "Tenants"));
  content.appendChild(el("p", { class: "muted" },
    "Crear un tenant sólo aísla sus datos (storage). Para que alguien lo use, dale acceso desde Usuarios."));

  const idInput = el("input", { type: "text", placeholder: "id (minúsculas, ej. athenea)", id: "nt-id", required: "true", pattern: "^[a-z][a-z0-9_-]*$" });
  const nameInput = el("input", { type: "text", placeholder: "nombre", id: "nt-name", required: "true" });
  const form = el("form", { class: "inline-form" }, idInput, nameInput,
    el("button", { class: "btn", type: "submit" }, "Crear tenant"));
  const formError = el("p", { class: "error hidden" });
  content.appendChild(form);
  content.appendChild(formError);

  const tenantsError = el("p", { class: "error hidden" });
  content.appendChild(tenantsError);

  const tableBody = el("tbody", {});
  content.appendChild(el("table", {},
    el("thead", {}, el("tr", {}, el("th", {}, "Id"), el("th", {}, "Nombre"), el("th", {}, "Creado"), el("th", {}, ""))),
    tableBody,
  ));

  async function deleteTenant(t) {
    tenantsError.classList.add("hidden");
    // Aviso de antemano, con el peso que corresponde a un borrado que se
    // lleva TODO (storage, git, cicd, project-manager de ese proyecto) sin
    // vuelta atrás -- pedido explícito del usuario. Escribir el id a mano
    // es más difícil de disparar sin querer que un simple confirm().
    const typed = prompt(
      `Esto borra el tenant '${t.id}' (${t.name}) y TODO lo que tiene: storage, repositorios git, pipelines de CI/CD y proyectos. No se puede deshacer.\n\nEscribe "${t.id}" para confirmar:`
    );
    if (typed !== t.id) return;
    try {
      await api("DELETE", `/api/admin/tenants/${encodeURIComponent(t.id)}`);
      await renderTenants();
    } catch (err) {
      tenantsError.textContent = err.message;
      tenantsError.classList.remove("hidden");
    }
  }

  async function renderTenants() {
    const tenants = await api("GET", "/api/admin/tenants");
    tableBody.innerHTML = "";
    for (const t of tenants) {
      tableBody.appendChild(el("tr", {}, el("td", {}, t.id), el("td", {}, t.name), el("td", {}, t.created_at || ""),
        el("td", {}, t.id === "freya" ? "" : el("button", {
          class: "btn btn-danger", type: "button", onclick: () => deleteTenant(t),
        }, "Eliminar"))));
    }
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    formError.classList.add("hidden");
    try {
      await api("POST", "/api/admin/tenants", { id: idInput.value.trim(), name: nameInput.value.trim() });
      form.reset();
      await renderTenants();
    } catch (err) {
      formError.textContent = err.message;
      formError.classList.remove("hidden");
    }
  });

  await renderTenants();
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
