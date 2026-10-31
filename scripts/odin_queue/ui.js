"use strict";
const token = new URLSearchParams(location.hash.slice(1)).get("token") || sessionStorage.getItem("odinQueueToken") || "";
if (token) { sessionStorage.setItem("odinQueueToken", token); history.replaceState(null, "", "/"); }
let state = null, lastRevision = null, pendingKey = null;
const $ = id => document.getElementById(id);
function node(tag, text, className) { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (className) e.className = className; return e; }
async function api(path, data) {
  const response = await fetch(path, {method: data === undefined ? "GET" : "POST", headers: {Authorization: "Bearer " + token, "Content-Type": "application/json"}, body: data === undefined ? undefined : JSON.stringify(data)});
  const result = await response.json(); if (!response.ok) throw new Error(result.error || "Opération interrompue"); return result;
}
function button(text, action) {
  const e = node("button", text); e.type = "button";
  e.addEventListener("click", async () => { e.disabled = true; try { await action(); $("error").textContent = ""; await refresh(); } catch (error) { $("error").textContent = error.message; } finally { e.disabled = false; } }); return e;
}
function render(s) {
  $("mode").textContent = s.mode === "simulation" ? "Simulation · aucun agent" : "Codex · " + (s.connected ? "connecté" : "déconnecté");
  $("occupied").textContent = s.occupied; $("queued").textContent = s.queued;
  document.querySelector(".stats div span").textContent = "places occupées / " + s.capacity;
  $("finished").textContent = s.jobs.filter(j => ["completed", "failed", "interrupted", "cancelled"].includes(j.status)).length;
  $("notice").textContent = s.supervisor_error ? "Superviseur arrêté : aucun nouveau départ. Vérifier le journal local." : s.recovery_required ? "Reprise à vérifier : confirmer l’arrêt des anciennes exécutions avant de reprendre les départs." : s.paused ? "Les nouveaux départs sont suspendus. Les exécutions déjà lancées continuent." : s.engine_note;
  $("pause").textContent = s.paused ? "Reprendre les départs" : "Suspendre les départs";
  $("demo").hidden = s.mode !== "simulation";
  if (lastRevision === s.revision) return;
  lastRevision = s.revision;
  const roots = $("roots"); roots.replaceChildren(...s.roots.map(r => {const e = node("option"); e.value = r; return e;}));
  if (!$("submit").elements.cwd.value) $("submit").elements.cwd.value = s.roots[0] || "";
  const jobs = $("jobs"); jobs.replaceChildren();
  const labels = {starting:"Démarrage",running:"En cours",waiting_approval:"Validation requise",cancelling:"Arrêt demandé",unknown:"État à vérifier",completed:"Tour terminé · à revoir",failed:"Échec",interrupted:"Interrompue",cancelled:"Annulée"};
  const ordered = [...s.jobs].sort((a,b) => {const terminal = j => ["completed","failed","interrupted","cancelled"].includes(j.status); return Number(terminal(a)) - Number(terminal(b));});
  if (!ordered.length) jobs.append(node("p", "Aucune discussion. Ajoutez une mission ou lancez la démonstration."));
  for (const job of ordered) {
    const card = node("article", undefined, "job"), head = node("div", undefined, "job-head");
    card.dataset.jobId = job.id;
    head.append(node("h3", job.title), node("span", job.status === "queued" ? "File nº " + job.queue_position : labels[job.status], "badge " + job.status));
    card.append(head, node("p", job.cwd, "job-path"));
    if (job.workspace_busy) card.append(node("p", "Dossier ou discussion occupé ; les missions indépendantes peuvent passer.", "job-note"));
    if (job.note) card.append(node("p", job.note, "job-note"));
    if (job.thread_id && !job.thread_id.startsWith("demo-")) card.append(node("p", "Discussion Codex : " + job.thread_id, "job-path"));
    for (const request of job.pending) {
      const panel = node("div", undefined, "request"), p = request.params || {}, item = request.item || {};
      panel.append(node("strong", request.supported ? "Décision pour cette action uniquement" : "Demande non prise en charge par ce pilote"));
      const details = {raison:p.reason, commande:p.command || item.command, dossier:p.cwd, fichiers:item.changes, racine:p.grantRoot, réseau:p.networkApprovalContext};
      panel.append(node("pre", Object.entries(details).filter(([,v]) => v !== undefined).map(([k,v]) => k + " : " + (typeof v === "string" ? v : JSON.stringify(v,null,2))).join("\n") || "Codex attend une réponse. Interrompre ce tour pour poursuivre dans son client natif."));
      if (request.supported) {
        const decisions = p.availableDecisions || ["accept","decline"];
        for (const decision of ["accept","decline"].filter(x => decisions.includes(x))) panel.append(button(decision === "accept" ? "Autoriser cette action" : "Refuser", () => api("/api/jobs/" + job.id + "/approval", {request_id:request.id, decision})));
      }
      card.append(panel);
    }
    const actions = node("div", undefined, "job-actions");
    if (["queued", "running", "waiting_approval"].includes(job.status)) actions.append(button(job.status === "queued" ? "Retirer de la file" : "Interrompre", () => api("/api/jobs/" + job.id + "/cancel", {})));
    if (job.status === "unknown") actions.append(button("Confirmer l’arrêt vérifié", () => {if (confirm("Vérifiez que l’ancienne exécution est réellement arrêtée. Libérer sa place sans la relancer ?")) return api("/api/jobs/" + job.id + "/resolve", {stopped_confirmed:true});}));
    if (actions.children.length) card.append(actions);
    if (job.result) {const result = node("details"); result.append(node("summary", "Résultat de Codex"), node("pre", job.result, "result")); card.append(result);}
    jobs.append(card);
  }
}
async function refresh() { state = await api("/api/state"); render(state); }
$("pause").addEventListener("click", async () => { try { await api("/api/control", {paused:!state.paused}); await refresh(); } catch (error) { $("error").textContent=error.message; } });
$("demo").addEventListener("click", async () => { try { await api("/api/demo", {dedupe_key:crypto.randomUUID()}); await refresh(); } catch (error) { $("error").textContent=error.message; } });
$("submit").addEventListener("submit", async event => { event.preventDefault(); const form=event.currentTarget, submit=form.querySelector("button[type=submit]"); submit.disabled=true; pendingKey = pendingKey || crypto.randomUUID();
  try { await api("/api/jobs", {title:form.elements.title.value, cwd:form.elements.cwd.value, prompt:form.elements.prompt.value, thread_id:form.elements.thread_id.value, audit:form.elements.audit.checked, dedupe_key:pendingKey}); pendingKey=null; form.elements.prompt.value=""; form.elements.title.value=""; $("error").textContent=""; await refresh(); }
  catch (error) { $("error").textContent=error.message; } finally { submit.disabled=false; }
});
// One lightweight local refresh. This does not poll agents or consume model tokens.
(async function poll(){try{await refresh();}catch(error){$("error").textContent=error.message;}setTimeout(poll,1000);})();
