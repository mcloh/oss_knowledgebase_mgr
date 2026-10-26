const API = "https://api.osskbdb.xptoai.com.br/v1";
const state = {page:"overview", token:sessionStorage.getItem("osskbdb_token"), me:null, tenants:[], kbs:[], metrics:[]};
const app = document.querySelector("#app");
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function decode(token) { try { return JSON.parse(atob(token.split(".")[1].replace(/-/g,"+").replace(/_/g,"/"))); } catch { return null; } }
async function api(path, options={}) {
  const response = await fetch(API + path, {...options, headers:{Authorization:"Bearer " + state.token, ...options.headers}});
  if (!response.ok) throw new Error((await response.json().catch(()=>({}))).detail || "Operação não concluída");
  return response.json();
}
const isAdmin = () => state.me?.role === "admin";
const tenantName = id => state.tenants.find(t => t.id === id)?.name || id;
const activeTenant = () => document.querySelector("#tenant-filter").value;
const shownKbs = () => activeTenant() ? state.kbs.filter(k => k.tenant_id === activeTenant()) : state.kbs;
const tableRows = (rows, empty, columns) => rows || '<tr><td colspan="' + columns + '" class="metric">' + empty + "</td></tr>";

function render() {
  const kbs = shownKbs();
  const views = {
    overview: '<div class="grid"><div class="card"><div class="metric">TENANTS ATIVOS</div><div class="value">' + state.tenants.filter(t=>t.active).length + '</div></div><div class="card"><div class="metric">BASES ATIVAS</div><div class="value">' + kbs.filter(k=>k.active).length + '</div></div><div class="card"><div class="metric">EVENTOS DE CONSUMO</div><div class="value">' + state.metrics.reduce((a,m)=>a+Number(m.events||0),0) + '</div></div></div><section class="panel"><h2>Estado operacional</h2><p class="metric">Os indicadores exibem dados reais do control plane. Crie e provisione uma base para iniciar a ingestão.</p></section>',
    tenants: '<section class="panel"><div class="panel-head"><h2>Tenants</h2>' + (isAdmin()?'<button class="primary" id="tenant-page-new">+ Criar tenant</button>':"") + '</div><table class="table"><thead><tr><th>TENANT</th><th>BASES</th><th>STATUS</th>' + (isAdmin()?"<th>AÇÃO</th>":"") + '</tr></thead><tbody>' + tableRows(state.tenants.map(t=>'<tr><td><b>'+esc(t.name)+'</b><br><span class="metric">'+esc(t.slug)+'</span></td><td>'+state.kbs.filter(k=>k.tenant_id===t.id).length+'</td><td><span class="badge '+(t.active?"ok":"bad")+'">'+(t.active?"ATIVO":"INATIVO")+'</span></td>' + (isAdmin()?'<td><button class="link resend" data-id="'+t.id+'">Reenviar ativação</button></td>':"")+'</tr>').join(""), "Nenhum tenant.", isAdmin()?4:3) + '</tbody></table></section>',
    collections: '<section class="panel"><h2>Bases de conhecimento</h2><table class="table"><thead><tr><th>BASE</th><th>TENANT</th><th>STATUS</th></tr></thead><tbody>' + tableRows(kbs.map(k=>'<tr><td><b>'+esc(k.name)+'</b><br><span class="metric">'+esc(k.slug)+'</span></td><td>'+esc(tenantName(k.tenant_id))+'</td><td><span class="badge '+(k.active?"ok":"bad")+'">'+(k.active?"ATIVA":"INATIVA")+'</span></td></tr>').join(""), "Nenhuma base.", 3) + '</tbody></table></section>',
    usage: '<section class="panel"><h2>Uso e métricas</h2><table class="table"><thead><tr><th>EVENTO</th><th>QUANTIDADE</th><th>UNIDADES</th><th>LATÊNCIA MÉDIA</th></tr></thead><tbody>' + tableRows(state.metrics.map(m=>'<tr><td>'+esc(m.event_type)+'</td><td>'+m.events+'</td><td>'+(m.units||0)+'</td><td>'+(m.latency_ms?Math.round(m.latency_ms)+" ms":"—")+'</td></tr>').join(""), "Ainda não há consumo registrado.", 4) + '</tbody></table></section>',
    settings: isAdmin() ? '<section class="panel"><div class="panel-head"><div><h2>Configurações da plataforma</h2><p class="metric">SMTP é usado para ativação de tenant-admin. As senhas não são exibidas pela interface.</p></div><button id="smtp-open" class="primary">Configurar SMTP</button></div><div id="smtp-status" class="metric">Carregando…</div></section>' : '<section class="panel"><h2>Configurações</h2><p class="metric">A configuração SMTP é restrita ao administrador da plataforma.</p></section>'
  };
  app.innerHTML = views[state.page];
  const page = document.querySelector('[data-page="' + state.page + '"]');
  document.querySelector("#crumb").textContent = page.textContent.toUpperCase();
  document.querySelector("#title").textContent = page.textContent;
  document.querySelector("#tenant-page-new")?.addEventListener("click", openTenant);
  document.querySelectorAll(".resend").forEach(button=>button.addEventListener("click",()=>resend(button.dataset.id)));
  if (state.page === "settings" && isAdmin()) loadSmtp();
}
function populate() {
  const filter = document.querySelector("#tenant-filter");
  filter.innerHTML = isAdmin()?'<option value="">Todos os tenants</option>':"";
  filter.insertAdjacentHTML("beforeend", state.tenants.map(t=>'<option value="'+t.id+'">'+esc(t.name)+"</option>").join(""));
  if (!isAdmin() && state.tenants[0]) filter.value = state.tenants[0].id;
  const selector = document.querySelector('#kb-form [name="tenant_id"]');
  selector.innerHTML = state.tenants.map(t=>'<option value="'+t.id+'">'+esc(t.name)+"</option>").join("");
  selector.disabled = !isAdmin();
  document.querySelector("#new-tenant").hidden = !isAdmin();
}
async function hydrate() {
  try {
    state.me = decode(state.token);
    [state.tenants,state.kbs,state.metrics] = await Promise.all([api("/tenants"),api("/knowledge-bases"),api("/metrics/usage")]);
    document.querySelector("#profile").innerHTML = (isAdmin()?"Platform admin":esc(state.tenants[0]?.name||"Tenant")) + "<br><span>" + (isAdmin()?"Administrador":"Tenant-admin") + "</span>";
    populate(); render();
  } catch {
    sessionStorage.removeItem("osskbdb_token"); state.token=null; document.querySelector("#login").showModal();
  }
}
function openTenant() { document.querySelector("#tenant-error").textContent=""; document.querySelector("#tenant-modal").showModal(); }
function openKb() { document.querySelector("#kb-error").textContent=""; document.querySelector("#kb-modal").showModal(); }
async function resend(id) {
  if (!confirm("Reenviar o e-mail de ativação? O link anterior deixará de valer.")) return;
  try { await api("/tenants/"+id+"/activation/resend",{method:"POST"}); alert("E-mail de ativação reenviado."); } catch (error) { alert(error.message); }
}
async function loadSmtp() {
  try {
    const config=await api("/admin/smtp");
    document.querySelector("#smtp-status").textContent=config.configured ? "Configurado: "+config.host+":"+config.port+" · "+config.sender : "SMTP ainda não configurado.";
    document.querySelector("#smtp-open").onclick=()=> {
      const form=document.querySelector("#smtp-form");
      ["host","port","username","sender"].forEach(field=>{if(config[field])form.elements[field].value=config[field];});
      document.querySelector("#smtp-error").textContent=""; document.querySelector("#smtp-modal").showModal();
    };
  } catch(error) { document.querySelector("#smtp-status").textContent=error.message; }
}
document.querySelectorAll("nav button").forEach(button=>button.onclick=()=>{document.querySelector("nav .active").classList.remove("active");button.classList.add("active");state.page=button.dataset.page;render();});
document.querySelector("#tenant-filter").onchange=render;
document.querySelector("#new-tenant").onclick=openTenant;
document.querySelector("#new-kb").onclick=openKb;
document.querySelectorAll("[data-close]").forEach(button=>button.onclick=()=>document.querySelector("#"+button.dataset.close).close());
document.querySelector("#login-form").onsubmit=async event=>{
  event.preventDefault();
  try { const response=await fetch(API+"/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:email.value,password:password.value})});if(!response.ok)throw new Error();state.token=(await response.json()).access_token;sessionStorage.setItem("osskbdb_token",state.token);document.querySelector("#login").close();hydrate(); }
  catch { document.querySelector("#login-error").textContent="Não foi possível autenticar."; }
};
document.querySelector("#activate-form").onsubmit=async event=>{
  event.preventDefault();
  try { const response=await fetch(API+"/auth/activate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({token:new URLSearchParams(location.search).get("activate"),password:document.querySelector("#activation-password").value})});if(!response.ok)throw new Error((await response.json()).detail);history.replaceState({},"",location.pathname);document.querySelector("#activate").close();alert("Conta ativada. Agora faça login."); }
  catch(error) { document.querySelector("#activation-error").textContent=error.message||"Não foi possível ativar a conta."; }
};
document.querySelector("#tenant-form").onsubmit=async event=>{
  event.preventDefault();const form=new FormData(event.target);
  try { await api("/tenants",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(Object.fromEntries(form))});document.querySelector("#tenant-modal").close();event.target.reset();hydrate(); }
  catch(error) { document.querySelector("#tenant-error").textContent=error.message; }
};
document.querySelector("#kb-form").onsubmit=async event=>{
  event.preventDefault();const form=new FormData(event.target);const split=value=>{const parts=String(value).split("|").map(v=>v.trim());return {url:parts[0],model:parts[1],credentials:{},provider:"openai_compatible",dimensions:384};};
  try { await api("/knowledge-bases",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({tenant_id:form.get("tenant_id"),slug:form.get("slug"),name:form.get("name"),chunk_config:{max_tokens:450,overlap_tokens:60,min_tokens:30},database:{url:form.get("db_url"),credentials:{username:form.get("db_user"),password:form.get("db_password")},vector_dimensions:384},s3:{url:form.get("s3_url"),credentials:{access_key_id:form.get("s3_key"),secret_access_key:form.get("s3_secret")}},embedding:split(form.get("embedding")),enrichment:split(form.get("llm")),webhook_url:form.get("webhook")||null})});document.querySelector("#kb-modal").close();event.target.reset();hydrate(); }
  catch(error) { document.querySelector("#kb-error").textContent=error.message; }
};
document.querySelector("#smtp-form").onsubmit=async event=>{
  event.preventDefault();const form=Object.fromEntries(new FormData(event.target));form.port=Number(form.port);
  try { await api("/admin/smtp",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(form)});document.querySelector("#smtp-modal").close();render(); }
  catch(error) { document.querySelector("#smtp-error").textContent=error.message; }
};
if(new URLSearchParams(location.search).get("activate"))document.querySelector("#activate").showModal();else if(state.token)hydrate();else document.querySelector("#login").showModal();
