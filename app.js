// Global Application State
let appState = {
  mensalistas: [],
  session: null,
  excelSummary: null,
  convidadoStars: 3,
  exitPlayerId: null,
  draggedPlayerId: null,
  draggedTeamId: null,
  selectedPlayerForSwap: null
};

// Safe API Fetch Helper
async function apiFetch(url, options = {}) {
  const response = await fetch(url, options);
  const contentType = response.headers.get("content-type");
  const isJson = contentType && contentType.includes("application/json");
  const data = isJson
    ? await response.json()
    : { error: await response.text() };

  if (!response.ok) {
    console.error(`Erro técnico na API (${url}):`, data);
    const errorMsg = data.detail || data.error || `Erro do servidor: ${response.status}`;
    throw new Error(errorMsg);
  }
  return data;
}

// --- INITIALIZATION ---
document.addEventListener("DOMContentLoaded", () => {
  initStarSelectors();
  loadMensalistas();
  loadSession(true); // true = show recovery toast if session recovered
});

function showToast(message, isSuccess = true) {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.style.borderLeft = isSuccess ? "4px solid #10b981" : "4px solid #ef4444";
  toast.innerHTML = `<span>${isSuccess ? '✅' : '⚠️'}</span> <span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 4000);
}

// --- STAR SELECTORS ---
function initStarSelectors() {
  const container = document.getElementById("convidado-stars-selector");
  if (!container) return;
  const stars = container.querySelectorAll(".star-option");
  stars.forEach((star) => {
    star.addEventListener("click", () => {
      const val = parseInt(star.getAttribute("data-value"));
      appState.convidadoStars = val;
      stars.forEach((s) => {
        const sVal = parseInt(s.getAttribute("data-value"));
        if (sVal <= val) s.classList.add("active");
        else s.classList.remove("active");
      });
    });
  });
}

function renderStarsHtml(count) {
  let stars = "";
  for (let i = 1; i <= 5; i++) {
    stars += i <= count ? "★" : "☆";
  }
  return `<span class="stars-display">${stars}</span>`;
}

// --- MENSALISTAS MANAGEMENT ---
async function loadMensalistas(query = "") {
  try {
    appState.mensalistas = await apiFetch(`/api/mensalistas?q=${encodeURIComponent(query)}`);
    renderMensalistasList();
    updateStatsBar();
  } catch (err) {
    showToast(err.message, false);
  }
}

function filterMensalistas() {
  const q = document.getElementById("search-mensalistas").value;
  loadMensalistas(q);
}

function renderMensalistasList() {
  const container = document.getElementById("mensalistas-list");
  if (!container) return;
  container.innerHTML = "";

  const presencasIds = new Set(
    (appState.session?.presencas || []).map((p) => p.mensalista_id)
  );

  appState.mensalistas.forEach((m) => {
    const isPresent = presencasIds.has(m.id);
    const item = document.createElement("div");
    item.className = `player-item ${isPresent ? "present" : ""}`;
    item.innerHTML = `
      <div class="player-info">
        <span class="player-name">${m.nome} ${renderStarsHtml(m.estrelas)}</span>
        <div class="player-meta">
          <span class="badge ${m.ativo ? "badge-mensalista" : "badge-convidado"}">${m.ativo ? "Ativo" : "Inativo"}</span>
          ${isPresent ? '<span style="color:var(--accent-green); font-weight:700;">✓ Presente</span>' : ''}
        </div>
      </div>
      <div style="display:flex; gap:0.4rem;">
        ${!isPresent && m.ativo ? `
          <button class="btn btn-green btn-sm" onclick="registerArrival(${m.id})">Chegada</button>
        ` : ''}
        <button class="btn btn-secondary btn-sm" onclick="openEditMensalistaModal(${m.id})">✏️</button>
        <button class="btn btn-danger btn-sm" onclick="deleteMensalista(${m.id})">🗑️</button>
      </div>
    `;
    container.appendChild(item);
  });
}

// --- SESSION MANAGEMENT & RECOVERY ---
async function loadSession(initial = false) {
  try {
    appState.session = await apiFetch("/api/session");
    
    if (initial && appState.session?.status === "EM_ANDAMENTO") {
      showToast("Sessão da pelada recuperada com sucesso!");
    }
    
    renderAppView();
    updateStatsBar();
  } catch (err) {
    showToast(err.message, false);
  }
}

function renderAppView() {
  const preView = document.getElementById("view-pre-match");
  const matchView = document.getElementById("view-match-control");
  
  if (appState.session?.status === "EM_ANDAMENTO") {
    preView.style.display = "none";
    matchView.style.display = "flex";
    renderMatchControl();
  } else {
    preView.style.display = "grid";
    matchView.style.display = "none";
    renderFilaList();
    renderMensalistasList();
  }
}

function updateStatsBar() {
  const presencas = appState.session?.presencas || [];
  const mensalistasCount = presencas.filter((p) => p.classe === "Mensalista").length;
  const convidadosCount = presencas.filter((p) => p.classe === "Convidado").length;
  
  document.getElementById("stat-presentes").innerText = presencas.length;
  document.getElementById("stat-mensalistas").innerText = mensalistasCount;
  document.getElementById("stat-convidados").innerText = convidadosCount;
  
  const teams = appState.session?.times || [];
  const fullTeams = teams.filter((t) => t.jogadores.length === 5).length;
  document.getElementById("stat-times-completos").innerText = fullTeams;
  
  const lastTeam = teams[teams.length - 1];
  const lastCount = lastTeam ? `${lastTeam.jogadores.length}/5` : "0/5";
  document.getElementById("stat-ultimo-time").innerText = lastCount;
}

// --- ARRIVALS & FILA DO DIA ---
async function registerArrival(mensalistaId) {
  try {
    appState.session = await apiFetch("/api/session/register-arrival", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mensalista_id: mensalistaId })
    });
    showToast("Chegada registrada!");
    renderAppView();
    updateStatsBar();
  } catch (err) {
    showToast(err.message, false);
  }
}

async function handleUndoArrival(playerId) {
  try {
    appState.session = await apiFetch("/api/session/undo-arrival", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_id: playerId })
    });
    renderAppView();
    updateStatsBar();
  } catch (err) {
    showToast(err.message, false);
  }
}

async function handleAddConvidado(e) {
  e.preventDefault();
  const nome = document.getElementById("input-convidado-nome").value;
  try {
    appState.session = await apiFetch("/api/session/add-convidado", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nome: nome, estrelas: appState.convidadoStars })
    });
    document.getElementById("input-convidado-nome").value = "";
    showToast("Convidado adicionado!");
    renderAppView();
    updateStatsBar();
  } catch (err) {
    showToast(err.message, false);
  }
}

function renderFilaList() {
  const container = document.getElementById("fila-list");
  if (!container) return;
  container.innerHTML = "";
  
  const presencas = appState.session?.presencas || [];
  document.getElementById("badge-total-fila").innerText = `${presencas.length} atletas`;

  if (presencas.length === 0) {
    container.innerHTML = `<p style="text-align:center; color:var(--text-muted); padding:1rem;">Nenhum atleta na fila do dia.</p>`;
    return;
  }

  presencas.forEach((p, idx) => {
    const item = document.createElement("div");
    item.className = "player-item";
    item.innerHTML = `
      <div class="player-info">
        <span class="player-name">#${idx + 1} ${p.nome} ${renderStarsHtml(p.estrelas)}</span>
        <div class="player-meta">
          <span class="badge ${p.classe === 'Mensalista' ? 'badge-mensalista' : 'badge-convidado'}">${p.classe}</span>
          <span>⏱️ ${p.horario_chegada}</span>
        </div>
      </div>
      <button class="btn btn-secondary btn-sm" onclick="handleUndoArrival('${p.id}')">Desfazer</button>
    `;
    container.appendChild(item);
  });
}

// --- FORM TEAMS (MONTAR TIMES) ---
async function handleFormTeams() {
  try {
    const response = await fetch("/api/session/form-teams", {
      method: "POST",
      headers: { "Content-Type": "application/json" }
    });

    const contentType = response.headers.get("content-type");
    const isJson = contentType && contentType.includes("application/json");
    const data = isJson ? await response.json() : { error: await response.text() };

    if (!response.ok) {
      console.error("Erro ao montar os times:", data);
      let userMsg = "Não foi possível montar os times. Verifique os jogadores cadastrados ou tente novamente.";
      if (data && data.detail && !data.detail.includes("Internal Server Error")) {
        userMsg = data.detail;
      }
      throw new Error(userMsg);
    }

    appState.session = data;
    showToast("Times equilibrados e montados com sucesso!");
    renderAppView();
    updateStatsBar();
  } catch (err) {
    showToast(err.message, false);
  }
}

// --- MATCH CONTROL & DRAG AND DROP ---
function renderMatchControl() {
  const teams = appState.session?.times || [];
  const courtTeamIds = appState.session?.times_em_quadra || [];
  const teamsDict = {};
  teams.forEach(t => teamsDict[t.id] = t);

  const teamA = teamsDict[courtTeamIds[0]];
  const teamB = teamsDict[courtTeamIds[1]];

  if (teamA) {
    document.getElementById("score-team-a-name").innerText = teamA.nome;
    document.getElementById("score-team-a-stats").innerText = `Soma: ${teamA.soma_estrelas} ★ | Média: ${teamA.media_estrelas.toFixed(2)}`;
  }
  if (teamB) {
    document.getElementById("score-team-b-name").innerText = teamB.nome;
    document.getElementById("score-team-b-stats").innerText = `Soma: ${teamB.soma_estrelas} ★ | Média: ${teamB.media_estrelas.toFixed(2)}`;
  }

  const grid = document.getElementById("teams-grid");
  grid.innerHTML = "";

  teams.forEach((t) => {
    const isOnCourt = courtTeamIds.includes(t.id);
    const card = document.createElement("div");
    card.className = `team-card ${isOnCourt ? "on-court" : ""}`;
    card.dataset.teamId = t.id;
    
    // Team Card Drop Target (Moving a player into this team)
    card.addEventListener("dragover", (e) => {
      e.preventDefault();
      card.classList.add("drag-over");
    });
    card.addEventListener("dragleave", () => {
      card.classList.remove("drag-over");
    });
    card.addEventListener("drop", (e) => {
      e.preventDefault();
      card.classList.remove("drag-over");
      handleDropOnTeam(t.id);
    });

    let badgeHtml = isOnCourt ? `<span class="badge badge-court">EM QUADRA</span>` : `<span class="badge badge-waiting">Fila #${t.posicao_fila}</span>`;
    if (t.incompleto) badgeHtml += ` <span class="badge badge-incomplete">Incompleto (${t.jogadores.length}/5)</span>`;

    card.innerHTML = `
      <div class="team-card-header">
        <h3 style="font-size:1.1rem; font-weight:700;">${t.nome}</h3>
        ${badgeHtml}
      </div>
      <div class="team-stats-row">
        <span>Soma: ${t.soma_estrelas} ★</span>
        <span>Média: ${t.media_estrelas.toFixed(2)}</span>
      </div>
      <div class="player-list" style="max-height:none;">
        ${t.jogadores.map(p => {
          const isSelected = appState.selectedPlayerForSwap === p.id;
          return `
            <div class="player-item draggable ${isSelected ? 'selected-for-swap' : ''}" 
                 draggable="true" 
                 data-player-id="${p.id}" 
                 data-team-id="${t.id}">
              <div class="player-info" onclick="handleTapPlayerForSwap('${p.id}', '${t.id}')">
                <span class="player-name"><span class="drag-handle">⣿</span> ${p.nome} ${renderStarsHtml(p.estrelas)}</span>
                <div class="player-meta">
                  <span class="badge ${p.classe === 'Mensalista' ? 'badge-mensalista' : 'badge-convidado'}">${p.classe}</span>
                  <span style="font-size:0.75rem; color:var(--accent-orange);">↕ Arraste ou clique para trocar</span>
                </div>
              </div>
              <button class="btn btn-secondary btn-sm" style="color:var(--danger-red);" onclick="openPlayerExitModal('${p.id}')">Sair</button>
            </div>
          `;
        }).join('')}
      </div>
    `;

    grid.appendChild(card);
  });

  // Attach Drag Event Listeners to all player items
  document.querySelectorAll(".player-item.draggable").forEach(item => {
    item.addEventListener("dragstart", (e) => {
      appState.draggedPlayerId = item.dataset.playerId;
      appState.draggedTeamId = item.dataset.teamId;
      item.classList.add("dragging");
      e.dataTransfer.setData("text/plain", JSON.stringify({
        playerId: item.dataset.playerId,
        teamId: item.dataset.teamId
      }));
    });

    item.addEventListener("dragend", () => {
      item.classList.remove("dragging");
      document.querySelectorAll(".drag-over").forEach(el => el.classList.remove("drag-over"));
    });

    item.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.stopPropagation();
      item.classList.add("drag-over");
    });

    item.addEventListener("dragleave", (e) => {
      e.stopPropagation();
      item.classList.remove("drag-over");
    });

    item.addEventListener("drop", (e) => {
      e.preventDefault();
      e.stopPropagation();
      item.classList.remove("drag-over");
      const targetPlayerId = item.dataset.playerId;
      const targetTeamId = item.dataset.teamId;
      handleDropOnPlayer(targetPlayerId, targetTeamId);
    });
  });

  // History lists
  const historyList = document.getElementById("match-history-list");
  historyList.innerHTML = (appState.session?.historico_partidas || []).map(m => `
    <div style="padding:0.4rem 0; border-bottom:1px solid #e2e8f0;">
      <strong>Partida #${m.numero}:</strong> ${m.time_a_nome} ${m.time_a_gols} x ${m.time_b_gols} ${m.time_b_nome}
    </div>
  `).join('') || '<p style="color:var(--text-muted);">Nenhuma partida realizada ainda.</p>';

  const subList = document.getElementById("sub-history-list");
  subList.innerHTML = (appState.session?.historico_substituicoes || []).map(s => `
    <div style="padding:0.4rem 0; border-bottom:1px solid #e2e8f0;">
      ⏱️ ${s.horario} - <strong>${s.jogador_saiu_nome}</strong> saiu (${s.motivo}). ${s.jogador_entrou_nome ? `Entrou: ${s.jogador_entrou_nome}` : 'Sem substituto.'}
    </div>
  `).join('') || '<p style="color:var(--text-muted);">Nenhuma substituição realizada.</p>';
}

// --- HANDLERS PARA DRAG & DROP E TOQUE ---
async function handleDropOnPlayer(targetPlayerId, targetTeamId) {
  const sourcePlayerId = appState.draggedPlayerId;
  const sourceTeamId = appState.draggedTeamId;

  if (!sourcePlayerId || sourcePlayerId === targetPlayerId) return;

  if (sourceTeamId && sourceTeamId !== targetTeamId) {
    // Swap 2 players between teams
    try {
      appState.session = await apiFetch("/api/session/swap-players", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player1_id: sourcePlayerId, player2_id: targetPlayerId })
      });
      showToast("🔄 Troca de jogadores realizada por arrasto com sucesso!");
      renderAppView();
      updateStatsBar();
    } catch (err) {
      showToast(err.message, false);
    }
  } else if (!sourceTeamId) {
    // Substitute targetPlayerId with reserve sourcePlayerId
    try {
      const result = await apiFetch("/api/session/player-exit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player_id: targetPlayerId, substituto_id: sourcePlayerId })
      });
      appState.session = result.state;
      showToast("🔄 Substituição realizada por arrasto com sucesso!");
      renderAppView();
      updateStatsBar();
    } catch (err) {
      showToast(err.message, false);
    }
  }
}

async function handleDropOnTeam(targetTeamId) {
  const sourcePlayerId = appState.draggedPlayerId;
  const sourceTeamId = appState.draggedTeamId;

  if (!sourcePlayerId || sourceTeamId === targetTeamId) return;

  try {
    appState.session = await apiFetch("/api/session/move-player", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_id: sourcePlayerId, target_team_id: targetTeamId })
    });
    showToast("➡️ Atleta movido para a equipe por arrasto!");
    renderAppView();
    updateStatsBar();
  } catch (err) {
    showToast(err.message, false);
  }
}

// Tap-to-Swap option for mobile touchscreen users
async function handleTapPlayerForSwap(playerId, teamId) {
  if (!appState.selectedPlayerForSwap) {
    appState.selectedPlayerForSwap = playerId;
    showToast("🎯 Atleta selecionado. Clique no atleta de destino para trocar!");
    renderMatchControl();
  } else if (appState.selectedPlayerForSwap === playerId) {
    appState.selectedPlayerForSwap = null;
    showToast("Seleção cancelada.");
    renderMatchControl();
  } else {
    const p1Id = appState.selectedPlayerForSwap;
    const p2Id = playerId;
    appState.selectedPlayerForSwap = null;

    try {
      appState.session = await apiFetch("/api/session/swap-players", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player1_id: p1Id, player2_id: p2Id })
      });
      showToast("🔄 Troca manual efetuada com sucesso!");
      renderAppView();
      updateStatsBar();
    } catch (err) {
      showToast(err.message, false);
    }
  }
}

async function handleRecordMatch() {
  const goalsA = parseInt(document.getElementById("score-team-a-goals").value) || 0;
  const goalsB = parseInt(document.getElementById("score-team-b-goals").value) || 0;
  
  try {
    const result = await apiFetch("/api/session/record-match", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ gols_time_a: goalsA, gols_time_b: goalsB })
    });
    appState.session = result.state;
    showToast(result.message);
    document.getElementById("score-team-a-goals").value = 0;
    document.getElementById("score-team-b-goals").value = 0;
    renderAppView();
    updateStatsBar();
  } catch (err) {
    showToast(err.message, false);
  }
}

// --- EXIT & SUBSTITUTION MODAL ---
function openPlayerExitModal(playerId) {
  appState.exitPlayerId = playerId;
  let playerObj = null;
  let teamObj = null;
  
  for (const t of (appState.session?.times || [])) {
    for (const p of t.jogadores) {
      if (p.id === playerId) {
        playerObj = p;
        teamObj = t;
        break;
      }
    }
  }

  if (!playerObj || !teamObj) return;

  document.getElementById("exit-modal-player-info").innerText = `${playerObj.nome} (${playerObj.classe} - ${playerObj.estrelas} ★) do ${teamObj.nome}`;
  
  const allocatedIds = new Set();
  (appState.session?.times || []).forEach(t => t.jogadores.forEach(p => allocatedIds.add(p.id)));

  const reserves = (appState.session?.presencas || []).filter(
    p => !allocatedIds.has(p.id) && p.id !== playerId && !p.contundido
  );

  const playersInOtherTeams = [];
  (appState.session?.times || []).forEach(t => {
    if (t.id !== teamObj.id) {
      t.jogadores.forEach(p => {
        playersInOtherTeams.push({ player: p, teamName: t.nome });
      });
    }
  });

  const presencasMensalistaIds = new Set((appState.session?.presencas || []).map(p => p.mensalista_id));
  const unpresentMensalistas = appState.mensalistas.filter(m => m.ativo && !presencasMensalistaIds.has(m.id));

  const subSelect = document.getElementById("exit-substitut-select");
  subSelect.innerHTML = "";

  if (reserves.length > 0) {
    const autoSub = reserves[0];
    const autoOpt = document.createElement("option");
    autoOpt.value = autoSub.id;
    autoOpt.innerText = `💡 (Sugestão Automática) ${autoSub.nome} (${autoSub.estrelas} ★)`;
    subSelect.appendChild(autoOpt);
  }

  if (reserves.length > 0) {
    const groupReserves = document.createElement("optgroup");
    groupReserves.label = "📋 Atletas Livres na Reserva";
    reserves.forEach(c => {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.innerText = `👤 ${c.nome} (${c.classe} - ${c.estrelas} ★)`;
      groupReserves.appendChild(opt);
    });
    subSelect.appendChild(groupReserves);
  }

  if (playersInOtherTeams.length > 0) {
    const groupOthers = document.createElement("optgroup");
    groupOthers.label = "🔁 Transferir de Outro Time";
    playersInOtherTeams.forEach(item => {
      const opt = document.createElement("option");
      opt.value = item.player.id;
      opt.innerText = `🔄 ${item.player.nome} (do ${item.teamName} - ${item.player.estrelas} ★)`;
      groupOthers.appendChild(opt);
    });
    subSelect.appendChild(groupOthers);
  }

  if (unpresentMensalistas.length > 0) {
    const groupDB = document.createElement("optgroup");
    groupDB.label = "⭐ Mensalistas Cadastrados (Entrando Agora)";
    unpresentMensalistas.forEach(m => {
      const opt = document.createElement("option");
      opt.value = `m_${m.id}`;
      opt.innerText = `⭐ ${m.nome} (Mensalista - ${m.estrelas} ★)`;
      groupDB.appendChild(opt);
    });
    subSelect.appendChild(groupDB);
  }

  const noSubOpt = document.createElement("option");
  noSubOpt.value = "";
  noSubOpt.innerText = "❌ Deixar sem substituto (Manter time incompleto)";
  subSelect.appendChild(noSubOpt);

  const sugBox = document.getElementById("exit-sub-suggestion-box");
  sugBox.innerHTML = `
    <strong>💡 Substituição Manual Totalmente Livre:</strong><br>
    <span style="font-size:0.8rem; color:var(--text-dark);">
      Arraste o atleta diretamente pelo card ou selecione qualquer nome na lista acima.
    </span>
  `;

  document.getElementById("modal-player-exit").style.display = "flex";
}

async function handleConfirmPlayerExit() {
  const motivo = document.getElementById("exit-motivo-select").value;
  const chosenSubId = document.getElementById("exit-substitut-select").value || null;

  try {
    const result = await apiFetch("/api/session/player-exit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        player_id: appState.exitPlayerId,
        motivo: motivo,
        substituto_id: chosenSubId
      })
    });
    appState.session = result.state;
    showToast(result.message);
    closeModal("modal-player-exit");
    renderAppView();
    updateStatsBar();
  } catch (err) {
    showToast(err.message, false);
  }
}

// --- MANUAL PLAYER SWAP BETWEEN TEAMS ---
function openSwapModal() {
  const select1 = document.getElementById("swap-player-1-select");
  const select2 = document.getElementById("swap-player-2-select");
  select1.innerHTML = "";
  select2.innerHTML = "";

  const allTeamPlayers = [];
  (appState.session?.times || []).forEach(t => {
    t.jogadores.forEach(p => {
      allTeamPlayers.push({ player: p, teamName: t.nome });
    });
  });

  if (allTeamPlayers.length < 2) {
    showToast("São necessários pelo menos 2 jogadores escalados para realizar uma troca.", false);
    return;
  }

  allTeamPlayers.forEach(item => {
    const opt1 = document.createElement("option");
    opt1.value = item.player.id;
    opt1.innerText = `${item.player.nome} (${item.teamName} - ${item.player.estrelas} ★)`;
    select1.appendChild(opt1);

    const opt2 = document.createElement("option");
    opt2.value = item.player.id;
    opt2.innerText = `${item.player.nome} (${item.teamName} - ${item.player.estrelas} ★)`;
    select2.appendChild(opt2);
  });

  if (select2.options.length > 1) {
    select2.selectedIndex = 1;
  }

  document.getElementById("modal-swap-players").style.display = "flex";
}

async function handleConfirmSwapPlayers() {
  const p1Id = document.getElementById("swap-player-1-select").value;
  const p2Id = document.getElementById("swap-player-2-select").value;

  if (p1Id === p2Id) {
    showToast("Selecione dois jogadores diferentes para realizar a troca.", false);
    return;
  }

  try {
    appState.session = await apiFetch("/api/session/swap-players", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player1_id: p1Id, player2_id: p2Id })
    });
    showToast("Troca manual de jogadores realizada com sucesso!");
    closeModal("modal-swap-players");
    renderAppView();
    updateStatsBar();
  } catch (err) {
    showToast(err.message, false);
  }
}

// --- LATE ARRIVAL MODAL ---
function openLateArrivalModal() {
  const select = document.getElementById("late-mensalista-select");
  select.innerHTML = "";
  
  const presencasIds = new Set((appState.session?.presencas || []).map(p => p.mensalista_id));
  const availableMensalistas = appState.mensalistas.filter(m => m.ativo && !presencasIds.has(m.id));
  
  availableMensalistas.forEach(m => {
    const opt = document.createElement("option");
    opt.value = m.id;
    opt.innerText = `${m.nome} (${m.estrelas} ★)`;
    select.appendChild(opt);
  });
  
  document.getElementById("modal-late-arrival").style.display = "flex";
}

function toggleLateArrivalType() {
  const type = document.getElementById("late-type-select").value;
  document.getElementById("late-mensalista-box").style.display = type === "mensalista" ? "flex" : "none";
  document.getElementById("late-convidado-box").style.display = type === "convidado" ? "flex" : "none";
}

async function handleConfirmLateArrival() {
  const type = document.getElementById("late-type-select").value;
  let payload = {};
  
  if (type === "mensalista") {
    payload.mensalista_id = parseInt(document.getElementById("late-mensalista-select").value);
  } else {
    payload.convidado_nome = document.getElementById("late-convidado-nome").value;
    payload.estrelas = parseInt(document.getElementById("late-convidado-stars").value);
  }

  try {
    appState.session = await apiFetch("/api/session/late-arrival", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    showToast("Jogador adicionado ao último time!");
    closeModal("modal-late-arrival");
    renderAppView();
    updateStatsBar();
  } catch (err) {
    showToast(err.message, false);
  }
}

// --- UNDO ACTION ---
async function handleUndoLastAction() {
  try {
    appState.session = await apiFetch("/api/session/undo-last-action", { method: "POST" });
    showToast("Ação anterior desfeita com sucesso!");
    renderAppView();
    updateStatsBar();
  } catch (err) {
    showToast(err.message, false);
  }
}

// --- EXCEL IMPORT / EXPORT ---
function openExcelModal() {
  document.getElementById("modal-excel").style.display = "flex";
  document.getElementById("excel-summary-container").style.display = "none";
  document.getElementById("btn-confirm-import").style.display = "none";
}

async function handleValidateExcel() {
  const fileInput = document.getElementById("excel-file-input");
  if (!fileInput.files || fileInput.files.length === 0) {
    showToast("Selecione um arquivo Excel (.xlsx ou .xls).", false);
    return;
  }

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);

  try {
    const res = await fetch("/api/excel/validate", {
      method: "POST",
      body: formData
    });
    const contentType = res.headers.get("content-type");
    const isJson = contentType && contentType.includes("application/json");
    const data = isJson ? await res.json() : { error: await res.text() };

    if (!res.ok) {
      throw new Error(data.detail || data.error || "Erro ao validar planilha.");
    }
    appState.excelSummary = data;
    
    document.getElementById("sum-novos").innerText = appState.excelSummary.novos.length;
    document.getElementById("sum-atualizados").innerText = appState.excelSummary.atualizados.length;
    document.getElementById("sum-duplicados").innerText = appState.excelSummary.duplicados.length;
    document.getElementById("sum-invalidos").innerText = appState.excelSummary.invalidos.length;
    document.getElementById("sum-total").innerText = appState.excelSummary.total_importado;
    
    const details = document.getElementById("excel-invalid-details");
    details.innerHTML = appState.excelSummary.invalidos.map(inv => `Linha ${inv.linha}: ${inv.motivo}`).join('<br>');

    document.getElementById("excel-summary-container").style.display = "block";
    document.getElementById("btn-confirm-import").style.display = "inline-flex";
  } catch (err) {
    showToast(err.message, false);
  }
}

async function handleConfirmExcelImport() {
  if (!appState.excelSummary) return;
  try {
    const data = await apiFetch("/api/excel/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(appState.excelSummary)
    });
    showToast(data.message);
    closeModal("modal-excel");
    loadMensalistas();
  } catch (err) {
    showToast(err.message, false);
  }
}

function downloadExcelTemplate() {
  window.location.href = "/api/excel/template";
}

function exportExcel() {
  window.location.href = "/api/excel/export";
}

// --- END PELADA ---
function confirmEndPelada() {
  document.getElementById("modal-end-pelada").style.display = "flex";
}

async function handleExecuteEndPelada() {
  try {
    const data = await apiFetch("/api/session/end-pelada", { method: "POST" });
    appState.session = data.state;
    closeModal("modal-end-pelada");
    showToast("Pelada encerrada! O cadastro permanente dos mensalistas foi mantido.");
    renderAppView();
    updateStatsBar();
  } catch (err) {
    showToast(err.message, false);
  }
}

// --- CRUD MENSALISTA MODAL ---
function openAddMensalistaModal() {
  document.getElementById("modal-mensalista-title").innerText = "Adicionar Mensalista";
  document.getElementById("edit-mensalista-id").value = "";
  document.getElementById("edit-mensalista-nome").value = "";
  document.getElementById("edit-mensalista-estrelas").value = 3;
  document.getElementById("edit-mensalista-ativo").checked = true;
  document.getElementById("modal-mensalista-crud").style.display = "flex";
}

function openEditMensalistaModal(id) {
  const m = appState.mensalistas.find(x => x.id === id);
  if (!m) return;
  document.getElementById("modal-mensalista-title").innerText = "Editar Mensalista";
  document.getElementById("edit-mensalista-id").value = m.id;
  document.getElementById("edit-mensalista-nome").value = m.nome;
  document.getElementById("edit-mensalista-estrelas").value = m.estrelas;
  document.getElementById("edit-mensalista-ativo").checked = m.ativo;
  document.getElementById("modal-mensalista-crud").style.display = "flex";
}

async function handleSaveMensalista(e) {
  e.preventDefault();
  const id = document.getElementById("edit-mensalista-id").value;
  const nome = document.getElementById("edit-mensalista-nome").value;
  const estrelas = parseInt(document.getElementById("edit-mensalista-estrelas").value);
  const ativo = document.getElementById("edit-mensalista-ativo").checked;

  const url = id ? `/api/mensalistas/${id}` : "/api/mensalistas";
  const method = id ? "PUT" : "POST";

  try {
    await apiFetch(url, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nome, estrelas, ativo })
    });
    closeModal("modal-mensalista-crud");
    showToast("Mensalista salvo com sucesso!");
    loadMensalistas();
  } catch (err) {
    showToast(err.message, false);
  }
}

async function deleteMensalista(id) {
  if (!confirm("Deseja realmente excluir este mensalista?")) return;
  try {
    await apiFetch(`/api/mensalistas/${id}`, { method: "DELETE" });
    showToast("Mensalista excluído!");
    loadMensalistas();
  } catch (err) {
    showToast(err.message, false);
  }
}

function closeModal(id) {
  document.getElementById(id).style.display = "none";
}
