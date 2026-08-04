import os
import uuid
import datetime
import json
import traceback
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, UploadFile, File, Response, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

import database
from models import (
    PeladaState, Player, Team, MatchResult, SubstitutionLog,
    MensalistaCreate, MensalistaUpdate, ConvidadoCreate, RecordMatchRequest,
    PlayerExitRequest, SwapPlayersRequest, MovePlayerRequest
)
from balance_algorithm import balance_teams, calculate_team_stats
from rotation_logic import execute_rotation
from substitution_logic import execute_player_exit, suggest_substitute
from excel_handler import (
    parse_and_validate_excel, confirm_excel_import,
    generate_excel_template, export_mensalistas_excel
)

app = FastAPI(title="Gestão da Pelada API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Database at startup
database.init_db()

# --- GLOBAL EXCEPTION HANDLERS (ALWAYS RETURN VALID JSON) ---
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "detail": exc.detail,
            "error": str(exc.detail)
        }
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "detail": "Dados de requisição inválidos.",
            "error": str(exc)
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print("❌ ERRO TÉCNICO NO SERVIDOR:", traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "detail": "Erro interno ao processar a requisição no servidor.",
            "error": str(exc)
        }
    )

def get_current_or_create_session() -> PeladaState:
    session_data = database.get_active_session()
    if session_data:
        try:
            state_dict = session_data['state']
            if isinstance(state_dict.get('presencas'), list):
                sanitized = []
                seen_ids = set()
                for p in state_dict['presencas']:
                    if isinstance(p, dict) and p.get('nome') and str(p.get('nome')).strip():
                        try:
                            stars = int(p.get('estrelas', 3))
                            if not (1 <= stars <= 5):
                                continue # Discard invalid stars
                            p['estrelas'] = stars
                        except (ValueError, TypeError):
                            continue
                        
                        pid = str(p.get('id', ''))
                        if pid and pid in seen_ids:
                            continue
                        if pid:
                            seen_ids.add(pid)
                        sanitized.append(p)
                state_dict['presencas'] = sanitized
            return PeladaState(**state_dict)
        except Exception as err:
            print("Aviso: Falha ao carregar sessão, gerando nova limpa:", err)

    # Create new session if none is active or if load failed
    new_id = f"session_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    new_state = PeladaState(session_id=new_id, status="PRÉ-JOGO", started_at=datetime.datetime.now().strftime("%d/%m/%Y %H:%M"))
    database.save_session(new_id, new_state.model_dump())
    return new_state

def save_and_push_undo(state: PeladaState) -> PeladaState:
    # Save previous state snapshot to undo stack safely without exponential nesting
    curr_data = database.get_active_session()
    if curr_data and curr_data.get('state_json'):
        try:
            prev_dict = json.loads(curr_data['state_json'])
            # Clear nested undo string in previous snapshot to prevent bloat
            prev_dict['undo_state_json'] = None
            prev_dict['can_undo'] = False
            state.undo_state_json = json.dumps(prev_dict, ensure_ascii=False)
            state.can_undo = True
        except Exception as err:
            print("Aviso snapshot undo:", err)
            state.undo_state_json = None
            state.can_undo = False
    state.last_saved_at = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    database.save_session(state.session_id, state.model_dump())
    return state

# ----------------- MENSALISTAS ENDPOINTS -----------------
@app.get("/api/mensalistas")
def list_mensalistas(q: Optional[str] = None):
    return database.get_all_mensalistas(q)

@app.post("/api/mensalistas")
def create_mensalista(m: MensalistaCreate):
    try:
        existing = database.get_mensalista_by_name(m.nome)
        if existing:
            raise HTTPException(status_code=400, detail="Já existe um mensalista com este nome.")
        return database.add_mensalista(m.nome, m.estrelas, m.ativo)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/api/mensalistas/{mensalista_id}")
def update_mensalista(mensalista_id: int, m: MensalistaUpdate):
    try:
        updated = database.update_mensalista(mensalista_id, m.nome, m.estrelas, m.ativo)
        if not updated:
            raise HTTPException(status_code=404, detail="Mensalista não encontrado.")
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/mensalistas/{mensalista_id}")
def delete_mensalista(mensalista_id: int):
    success = database.delete_mensalista(mensalista_id)
    if not success:
        raise HTTPException(status_code=404, detail="Mensalista não encontrado.")
    return {"message": "Mensalista excluído com sucesso."}

# ----------------- EXCEL ENDPOINTS -----------------
@app.post("/api/excel/validate")
async def validate_excel(file: UploadFile = File(...)):
    if not (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        raise HTTPException(status_code=400, detail="Apenas arquivos .xlsx ou .xls são permitidos.")
    content = await file.read()
    try:
        summary = parse_and_validate_excel(content)
        return summary
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/excel/import")
def import_excel(summary: Dict[str, Any]):
    added, updated = confirm_excel_import(summary)
    return {"message": f"Importação concluída! {added} novos adicionados, {updated} atualizados."}

@app.get("/api/excel/template")
def download_excel_template():
    content = generate_excel_template()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Modelo_Mensalistas.xlsx"}
    )

@app.get("/api/excel/export")
def export_excel():
    content = export_mensalistas_excel()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=Mensalistas_{datetime.datetime.now().strftime('%Y%m%d')}.xlsx"}
    )

# ----------------- PELADA SESSION ENDPOINTS -----------------
@app.get("/api/session")
def get_session():
    state = get_current_or_create_session()
    return state

@app.post("/api/session/register-arrival")
def register_arrival(payload: Dict[str, int]):
    mensalista_id = payload.get("mensalista_id")
    if not mensalista_id:
        raise HTTPException(status_code=400, detail="ID do mensalista é obrigatório.")
        
    m = database.get_mensalista_by_id(mensalista_id)
    if not m:
        raise HTTPException(status_code=404, detail="Mensalista não encontrado.")
    if not m['ativo']:
        raise HTTPException(status_code=400, detail="Mensalista está inativo.")
        
    state = get_current_or_create_session()
    
    # Check duplicate entry
    if any(p.mensalista_id == mensalista_id for p in state.presencas):
        raise HTTPException(status_code=400, detail="Jogador já está registrado na pelada do dia.")
        
    now_str = datetime.datetime.now().strftime("%H:%M:%S")
    pos = len(state.presencas) + len(state.retirados) + 1
    
    p = Player(
        id=f"m_{m['id']}",
        mensalista_id=m['id'],
        nome=m['nome'],
        estrelas=m['estrelas'],
        classe="Mensalista",
        ativo=True,
        ordem_chegada=pos,
        horario_chegada=now_str,
        status="presente"
    )
    
    state.presencas.append(p)
    save_and_push_undo(state)
    return state

@app.post("/api/session/undo-arrival")
def undo_arrival(payload: Dict[str, str]):
    player_id = payload.get("player_id")
    state = get_current_or_create_session()
    
    if state.status == "EM_ANDAMENTO":
        raise HTTPException(status_code=400, detail="A pelada já começou. Use a opção de saída do atleta.")
        
    state.presencas = [p for p in state.presencas if p.id != player_id]
    save_and_push_undo(state)
    return state

@app.post("/api/session/add-convidado")
def add_convidado(c: ConvidadoCreate):
    state = get_current_or_create_session()
    now_str = datetime.datetime.now().strftime("%H:%M:%S")
    pos = len(state.presencas) + len(state.retirados) + 1
    
    conv_id = f"g_{uuid.uuid4().hex[:8]}"
    p = Player(
        id=conv_id,
        nome=c.nome.strip(),
        estrelas=c.estrelas,
        classe="Convidado",
        ativo=True,
        ordem_chegada=pos,
        horario_chegada=now_str,
        status="presente"
    )
    
    state.presencas.append(p)
    
    # If session is already in progress, handle late arrival logic
    if state.status == "EM_ANDAMENTO":
        if not state.times:
            state.times = balance_teams(state.presencas)
        else:
            last_team = state.times[-1]
            if len(last_team.jogadores) < 5:
                last_team.jogadores.append(p)
                p.status = last_team.situacao
                last_team.soma_estrelas, last_team.media_estrelas = calculate_team_stats(last_team.jogadores)
                last_team.incompleto = (len(last_team.jogadores) < 5)
            else:
                new_t = Team(
                    id=f"team_{len(state.times)+1}",
                    nome=f"Time {len(state.times)+1}",
                    jogadores=[p],
                    situacao="esperando",
                    posicao_fila=len(state.fila_times)+1,
                    incompleto=True
                )
                p.status = "esperando"
                new_t.soma_estrelas, new_t.media_estrelas = calculate_team_stats(new_t.jogadores)
                state.times.append(new_t)
                state.fila_times.append(new_t.id)

    save_and_push_undo(state)
    return state

@app.post("/api/session/reorder-queue")
def reorder_queue(payload: Dict[str, List[str]]):
    ordered_ids = payload.get("ordered_ids", [])
    state = get_current_or_create_session()
    
    id_map = {p.id: p for p in state.presencas}
    new_presencas = []
    
    for idx, pid in enumerate(ordered_ids, start=1):
        if pid in id_map:
            p = id_map[pid]
            p.ordem_chegada = idx
            new_presencas.append(p)
            
    state.presencas = new_presencas
    save_and_push_undo(state)
    return state

@app.post("/api/session/form-teams")
def form_teams():
    state = get_current_or_create_session()
    
    # 1. Validate presencas array is non-null
    if not isinstance(state.presencas, list):
        state.presencas = []

    # 2. Strict validation of present players
    valid_players = []
    seen_ids = set()

    for p in state.presencas:
        if not p or not getattr(p, 'nome', None) or not str(p.nome).strip():
            continue
        try:
            stars = int(p.estrelas)
            if not (1 <= stars <= 5):
                continue
        except (ValueError, TypeError):
            continue

        if p.classe not in ("Mensalista", "Convidado"):
            continue

        if p.id in seen_ids:
            continue
        seen_ids.add(p.id)

        valid_players.append(p)

    state.presencas = valid_players

    # 3. Check minimum players required (at least 5)
    if len(valid_players) < 5:
        raise HTTPException(
            status_code=400,
            detail="São necessários pelo menos 5 jogadores para montar um time."
        )

    teams = balance_teams(valid_players)
    state.times = teams
    state.status = "EM_ANDAMENTO"

    if len(teams) >= 2:
        teams[0].situacao = "em quadra"
        teams[1].situacao = "em quadra"
        for p in teams[0].jogadores + teams[1].jogadores:
            p.status = "em quadra"

        state.times_em_quadra = [teams[0].id, teams[1].id]
        state.fila_times = []
        for pos, t in enumerate(teams[2:], start=1):
            t.situacao = "esperando"
            t.posicao_fila = pos
            for p in t.jogadores:
                p.status = "esperando"
            state.fila_times.append(t.id)
    elif len(teams) == 1:
        teams[0].situacao = "em quadra"
        for p in teams[0].jogadores:
            p.status = "em quadra"
        state.times_em_quadra = [teams[0].id]
        state.fila_times = []

    save_and_push_undo(state)
    return state

@app.post("/api/session/record-match")
def record_match(req: RecordMatchRequest):
    state = get_current_or_create_session()
    if state.status != "EM_ANDAMENTO":
        raise HTTPException(status_code=400, detail="A pelada não está em andamento.")
        
    new_state, msg = execute_rotation(state, req.gols_time_a, req.gols_time_b)
    save_and_push_undo(new_state)
    return {"state": new_state, "message": msg}

@app.post("/api/session/player-exit")
def player_exit(req: PlayerExitRequest):
    state = get_current_or_create_session()
    new_state, msg, log = execute_player_exit(state, req.player_id, req.motivo, req.substituto_id)
    save_and_push_undo(new_state)
    return {"state": new_state, "message": msg}

@app.post("/api/session/late-arrival")
def late_arrival(payload: Dict[str, Any]):
    mensalista_id = payload.get("mensalista_id")
    convidado_nome = payload.get("convidado_nome")
    estrelas = payload.get("estrelas", 3)
    
    state = get_current_or_create_session()
    now_str = datetime.datetime.now().strftime("%H:%M:%S")
    pos = len(state.presencas) + len(state.retirados) + 1
    
    if mensalista_id:
        m = database.get_mensalista_by_id(mensalista_id)
        if not m:
            raise HTTPException(status_code=404, detail="Mensalista não encontrado.")
        if any(p.mensalista_id == mensalista_id for p in state.presencas):
            raise HTTPException(status_code=400, detail="Jogador já presente.")
        p = Player(
            id=f"m_{m['id']}", mensalista_id=m['id'], nome=m['nome'],
            estrelas=m['estrelas'], classe="Mensalista", ordem_chegada=pos,
            horario_chegada=now_str, status="esperando"
        )
    elif convidado_nome:
        p = Player(
            id=f"g_{uuid.uuid4().hex[:8]}", nome=convidado_nome.strip(),
            estrelas=estrelas, classe="Convidado", ordem_chegada=pos,
            horario_chegada=now_str, status="esperando"
        )
    else:
        raise HTTPException(status_code=400, detail="Dados de atleta não informados.")
        
    state.presencas.append(p)
    
    # Put into last team
    if not state.times:
        state.times = balance_teams(state.presencas)
    else:
        last_team = state.times[-1]
        if len(last_team.jogadores) < 5:
            last_team.jogadores.append(p)
            p.status = last_team.situacao
            last_team.soma_estrelas, last_team.media_estrelas = calculate_team_stats(last_team.jogadores)
            last_team.incompleto = (len(last_team.jogadores) < 5)
            
            # Rebalance check if last team reached 5 players
            if len(last_team.jogadores) == 5:
                waiting_teams = [t for t in state.times if t.situacao == "esperando"]
                if len(waiting_teams) > 1:
                    waiting_players = [p for t in waiting_teams for p in t.jogadores]
                    rebalanced_waiting = balance_teams(waiting_players)
                    non_waiting = [t for t in state.times if t.situacao != "esperando"]
                    state.times = non_waiting + rebalanced_waiting
        else:
            new_t = Team(
                id=f"team_{len(state.times)+1}",
                nome=f"Time {len(state.times)+1}",
                jogadores=[p],
                situacao="esperando",
                posicao_fila=len(state.fila_times)+1,
                incompleto=True
            )
            p.status = "esperando"
            new_t.soma_estrelas, new_t.media_estrelas = calculate_team_stats(new_t.jogadores)
            state.times.append(new_t)
            state.fila_times.append(new_t.id)

    save_and_push_undo(state)
    return state

@app.post("/api/session/swap-players")
def swap_players(req: SwapPlayersRequest):
    state = get_current_or_create_session()
    p1, t1 = None, None
    p2, t2 = None, None
    
    for t in state.times:
        for p in t.jogadores:
            if p.id == req.player1_id:
                p1, t1 = p, t
            if p.id == req.player2_id:
                p2, t2 = p, t

    if not p1 or not p2 or not t1 or not t2:
        raise HTTPException(status_code=400, detail="Um ou ambos os jogadores não foram encontrados em times.")

    t1.jogadores.remove(p1)
    t2.jogadores.remove(p2)
    
    t1.jogadores.append(p2)
    t2.jogadores.append(p1)
    
    p1.status = t2.situacao
    p2.status = t1.situacao
    
    t1.soma_estrelas, t1.media_estrelas = calculate_team_stats(t1.jogadores)
    t2.soma_estrelas, t2.media_estrelas = calculate_team_stats(t2.jogadores)

    save_and_push_undo(state)
    return state

@app.post("/api/session/move-player")
def move_player(req: MovePlayerRequest):
    state = get_current_or_create_session()
    target_team = next((t for t in state.times if t.id == req.target_team_id), None)
    if not target_team:
        raise HTTPException(status_code=404, detail="Time de destino não encontrado.")
        
    p1, source_team = None, None
    for t in state.times:
        for p in t.jogadores:
            if p.id == req.player_id:
                p1, source_team = p, t
                break
                
    if not p1 or not source_team:
        raise HTTPException(status_code=400, detail="Jogador não encontrado em nenhum time.")
        
    source_team.jogadores.remove(p1)
    target_team.jogadores.append(p1)
    p1.status = target_team.situacao
    
    source_team.soma_estrelas, source_team.media_estrelas = calculate_team_stats(source_team.jogadores)
    target_team.soma_estrelas, target_team.media_estrelas = calculate_team_stats(target_team.jogadores)
    
    source_team.incompleto = (len(source_team.jogadores) < 5)
    target_team.incompleto = (len(target_team.jogadores) < 5)

    save_and_push_undo(state)
    return state

@app.post("/api/session/undo-last-action")
def undo_last_action():
    state = get_current_or_create_session()
    if not state.can_undo or not state.undo_state_json:
        raise HTTPException(status_code=400, detail="Nenhuma alteração anterior para desfazer.")
        
    previous_state_dict = json.loads(state.undo_state_json)
    restored_state = PeladaState(**previous_state_dict)
    restored_state.can_undo = False
    restored_state.undo_state_json = None
    
    database.save_session(restored_state.session_id, restored_state.model_dump())
    return restored_state

@app.post("/api/session/end-pelada")
def end_pelada():
    state = get_current_or_create_session()
    database.end_session(state.session_id)
    
    new_id = f"session_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    new_state = PeladaState(session_id=new_id, status="PRÉ-JOGO", started_at=datetime.datetime.now().strftime("%d/%m/%Y %H:%M"))
    database.save_session(new_id, new_state.model_dump())
    return {"message": "Pelada encerrada com sucesso! O cadastro dos mensalistas foi mantido.", "state": new_state}

# Serve static directory for SPA
static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.get("/")
def read_root():
    return FileResponse(os.path.join(static_path, "index.html"))
