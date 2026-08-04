from typing import List, Optional, Tuple, Dict, Any
from models import PeladaState, Player, Team, SubstitutionLog
from balance_algorithm import calculate_team_stats
import database
import datetime
import uuid

def suggest_substitute(state: PeladaState, team: Team, exiting_player: Player) -> Optional[Dict[str, Any]]:
    """
    Localiza no banco de reservas o melhor substituto segundo critérios de equilíbrio.
    """
    allocated_ids = set()
    for t in state.times:
        for p in t.jogadores:
            allocated_ids.add(p.id)
            
    candidates = [
        p for p in state.presencas 
        if p.id not in allocated_ids and p.id != exiting_player.id and not p.contundido
    ]
    
    if not candidates:
        return None

    exiting_stars = exiting_player.estrelas
    curr_soma, curr_media = calculate_team_stats(team.jogadores)
    remaining_players = [p for p in team.jogadores if p.id != exiting_player.id]
    
    best_candidate = None
    best_score = float('inf')
    best_new_avg = 0.0

    for cand in candidates:
        temp_team = remaining_players + [cand]
        _, new_avg = calculate_team_stats(temp_team)
        
        star_diff = abs(cand.estrelas - exiting_stars)
        avg_impact = abs(new_avg - curr_media)
        arrival = cand.ordem_chegada
        is_mensalista_bonus = 0.0 if cand.classe == "Mensalista" else 0.1
        
        score = (star_diff * 100.0) + (avg_impact * 50.0) + (arrival * 0.01) + is_mensalista_bonus
        
        if score < best_score:
            best_score = score
            best_candidate = cand
            best_new_avg = new_avg

    if best_candidate:
        return {
            "jogador_substituto": best_candidate,
            "media_anterior": curr_media,
            "media_apos": best_new_avg,
            "origem": "Fila de espera de atletas"
        }
    return None

def execute_player_exit(
    state: PeladaState, 
    player_id: str, 
    motivo: str = "saida", 
    substitut_id: Optional[str] = None
) -> Tuple[PeladaState, str, Optional[SubstitutionLog]]:
    """
    Remove um jogador de seu time e insere o substituto escolhido (manual ou automático),
    independente da classificação técnica do substituto.
    """
    target_team = None
    exiting_player = None
    
    for t in state.times:
        for p in t.jogadores:
            if p.id == player_id:
                target_team = t
                exiting_player = p
                break
        if target_team:
            break
            
    if not target_team or not exiting_player:
        return state, "Erro: Jogador não encontrado em nenhum time.", None

    # Remove player from team
    target_team.jogadores.remove(exiting_player)
    exiting_player.status = "retirado"
    if motivo == "contusao":
        exiting_player.contundido = True
        
    state.retirados.append(exiting_player)
    state.presencas = [p for p in state.presencas if p.id != player_id]

    sub_player = None
    origem_sub = "Substituição Manual"

    if substitut_id:
        # 1. Search in current presencas (reserva or other team)
        for p in state.presencas:
            if p.id == substitut_id:
                sub_player = p
                # If sub_player is currently in another team, remove from there
                for other_team in state.times:
                    if other_team.id != target_team.id and sub_player in other_team.jogadores:
                        other_team.jogadores.remove(sub_player)
                        other_team.soma_estrelas, other_team.media_estrelas = calculate_team_stats(other_team.jogadores)
                        other_team.incompleto = (len(other_team.jogadores) < 5)
                        origem_sub = f"Transferido do {other_team.nome}"
                        break
                break

        # 2. If not found in presencas, check if it's a mensalista DB ID (e.g. "m_12")
        if not sub_player and str(substitut_id).startswith("m_"):
            try:
                m_id = int(str(substitut_id).replace("m_", ""))
                m = database.get_mensalista_by_id(m_id)
                if m:
                    now_str = datetime.datetime.now().strftime("%H:%M:%S")
                    pos = len(state.presencas) + len(state.retirados) + 1
                    sub_player = Player(
                        id=f"m_{m['id']}",
                        mensalista_id=m['id'],
                        nome=m['nome'],
                        estrelas=m['estrelas'],
                        classe="Mensalista",
                        ativo=True,
                        ordem_chegada=pos,
                        horario_chegada=now_str,
                        status="em quadra" if target_team.situacao == "em quadra" else "esperando"
                    )
                    state.presencas.append(sub_player)
                    origem_sub = "Mensalista Cadastrado (Novo)"
            except (ValueError, TypeError):
                pass

    if not sub_player and not substitut_id:
        # Fallback to auto suggestion if admin did not specify substitut_id
        sug = suggest_substitute(state, target_team, exiting_player)
        if sug:
            sub_player = sug["jogador_substituto"]
            origem_sub = "Sugestão Automática"

    log_entry = None
    now_str = datetime.datetime.now().strftime("%H:%M:%S")

    if sub_player:
        target_team.jogadores.append(sub_player)
        sub_player.status = target_team.situacao
        
        target_team.soma_estrelas, target_team.media_estrelas = calculate_team_stats(target_team.jogadores)
        target_team.incompleto = (len(target_team.jogadores) < 5)
        
        log_entry = SubstitutionLog(
            id=str(uuid.uuid4()),
            horario=now_str,
            jogador_saiu_nome=exiting_player.nome,
            jogador_entrou_nome=sub_player.nome,
            time_nome=target_team.nome,
            motivo="contusao" if motivo == "contusao" else "saida",
            origem_substituto=origem_sub
        )
        msg = f"{exiting_player.nome} saiu ({motivo}) do {target_team.nome}. Substituído manualmente por {sub_player.nome} ({sub_player.estrelas} ★)."
    else:
        target_team.soma_estrelas, target_team.media_estrelas = calculate_team_stats(target_team.jogadores)
        target_team.incompleto = (len(target_team.jogadores) < 5)
        
        log_entry = SubstitutionLog(
            id=str(uuid.uuid4()),
            horario=now_str,
            jogador_saiu_nome=exiting_player.nome,
            jogador_entrou_nome=None,
            time_nome=target_team.nome,
            motivo="contusao" if motivo == "contusao" else "saida",
            origem_substituto="Sem substituto"
        )
        msg = f"{exiting_player.nome} saiu ({motivo}) do {target_team.nome}. O time ficou sem substituto ({len(target_team.jogadores)}/5)."

    state.historico_substituicoes.append(log_entry)
    return state, msg, log_entry
