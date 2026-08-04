from typing import List, Dict, Tuple, Optional, Any
from models import PeladaState, Team, MatchResult, Player
from balance_algorithm import calculate_team_stats
import datetime
import uuid
import itertools

def execute_rotation(state: PeladaState, gols_a: int, gols_b: int) -> Tuple[PeladaState, str]:
    """
    Executa as regras de rodízio da pelada após a digitação de um placar.
    Garante que NENHUM time incompleto permaneça jogando em quadra se houver atletas disponíveis.
    """
    if len(state.times_em_quadra) < 2:
        return state, "Erro: Não há 2 times em quadra."

    # Identify current teams on court
    team_a_id = state.times_em_quadra[0]
    team_b_id = state.times_em_quadra[1]
    
    teams_dict = {t.id: t for t in state.times}
    team_a = teams_dict.get(team_a_id)
    team_b = teams_dict.get(team_b_id)
    
    if not team_a or not team_b:
        return state, "Erro: Times em quadra não encontrados."

    # Create match record
    match_number = len(state.historico_partidas) + 1
    now_str = datetime.datetime.now().strftime("%H:%M:%S")
    
    vencedor_id = None
    empate = (gols_a == gols_b)
    
    if gols_a > gols_b:
        vencedor_id = team_a.id
    elif gols_b > gols_a:
        vencedor_id = team_b.id
        
    match_rec = MatchResult(
        id=str(uuid.uuid4()),
        numero=match_number,
        time_a_id=team_a.id,
        time_a_nome=team_a.nome,
        time_a_gols=gols_a,
        time_b_id=team_b.id,
        time_b_nome=team_b.nome,
        time_b_gols=gols_b,
        vencedor_id=vencedor_id,
        empate=empate,
        horario=now_str
    )
    
    state.historico_partidas.append(match_rec)
    
    num_waiting = len(state.fila_times)
    msg = f"Partida #{match_number} registrada: {team_a.nome} {gols_a} x {gols_b} {team_b.nome}. "
    donor_team_id = None

    # CASE 1: WINNER EXISTS
    if not empate:
        winner_id = team_a.id if gols_a > gols_b else team_b.id
        loser_id = team_b.id if gols_a > gols_b else team_a.id
        donor_team_id = loser_id
        
        state.vencedor_anterior_id = winner_id
        state.ultimo_vencedor_nome = teams_dict[winner_id].nome
        
        if num_waiting > 0:
            next_team_id = state.fila_times.pop(0)
            state.times_em_quadra = [winner_id, next_team_id]
            state.fila_times.append(loser_id)
            msg += f"Vencedor ({teams_dict[winner_id].nome}) continua em quadra. {teams_dict[loser_id].nome} vai para a fila. {teams_dict[next_team_id].nome} entra em quadra."
        else:
            msg += f"Sem times esperando. Ambos os times permanecem em quadra."

    # CASE 2: TIE WITH 1 TEAM WAITING
    elif num_waiting == 1:
        next_team_id = state.fila_times.pop(0)
        prev_winner_id = state.vencedor_anterior_id
        
        if prev_winner_id in (team_a.id, team_b.id):
            leaving_id = prev_winner_id
            staying_id = team_b.id if prev_winner_id == team_a.id else team_a.id
            reason_str = f"Vencedor anterior ({teams_dict[leaving_id].nome}) sai pelo desempate."
        else:
            leaving_id = team_a.id
            staying_id = team_b.id
            reason_str = f"{team_a.nome} sai conforme regra de empate."
            
        donor_team_id = leaving_id
        state.times_em_quadra = [staying_id, next_team_id]
        state.fila_times.append(leaving_id)
        msg += f"Empate com 1 time esperando. {reason_str} {teams_dict[next_team_id].nome} entra em quadra."

    # CASE 3: TIE WITH 2+ TEAMS WAITING
    elif num_waiting >= 2:
        next_1_id = state.fila_times.pop(0)
        next_2_id = state.fila_times.pop(0)
        donor_team_id = team_a.id
        
        state.fila_times.append(team_a.id)
        state.fila_times.append(team_b.id)
        state.times_em_quadra = [next_1_id, next_2_id]
        msg += f"Empate com 2+ esperando. {team_a.nome} e {team_b.nome} vão para a fila. Entram {teams_dict[next_1_id].nome} e {teams_dict[next_2_id].nome}."

    # CASE 4: TIE WITH 0 TEAMS WAITING
    else:
        state.vencedor_anterior_id = None
        msg += f"Empate sem times esperando. Ambos os times permanecem em quadra."

    # GUARANTEE: Complete any incomplete team on court using donor/waiting players
    inc_msgs = ensure_court_teams_complete(state, donor_team_id)
    if inc_msgs:
        msg += " " + " ".join(inc_msgs)

    # Update queue positions
    for pos, t_id in enumerate(state.fila_times, start=1):
        if t_id in teams_dict:
            teams_dict[t_id].posicao_fila = pos
        
    return state, msg

def ensure_court_teams_complete(state: PeladaState, donor_team_id: Optional[str] = None) -> List[str]:
    """
    Garante que todos os times em quadra possuam 5 jogadores (se houver atletas disponíveis).
    Transfere atletas do time doador ou da fila mantendo o equilíbrio técnico.
    """
    messages = []
    teams_dict = {t.id: t for t in state.times}
    court_teams = [teams_dict[tid] for tid in state.times_em_quadra if tid in teams_dict]

    for team in court_teams:
        if len(team.jogadores) < 5:
            needed = 5 - len(team.jogadores)
            
            # Find opponent team on court for balance calculation
            opponent = [t for t in court_teams if t.id != team.id]
            opponent_avg = opponent[0].media_estrelas if opponent else team.media_estrelas
            
            candidates = []
            # 1. Donor team (team that just lost or exited)
            if donor_team_id and donor_team_id in teams_dict:
                d_team = teams_dict[donor_team_id]
                if d_team.id not in state.times_em_quadra:
                    candidates.extend(d_team.jogadores)

            # 2. Other waiting teams in queue
            if len(candidates) < needed:
                for tid in reversed(state.fila_times):
                    if tid != donor_team_id:
                        w_team = teams_dict[tid]
                        for p in w_team.jogadores:
                            if p not in candidates:
                                candidates.append(p)

            if not candidates:
                continue

            actual_take = min(needed, len(candidates))
            best_combo = None
            best_diff = float('inf')

            for combo in itertools.combinations(candidates, actual_take):
                temp_players = team.jogadores + list(combo)
                _, temp_avg = calculate_team_stats(temp_players)
                diff = abs(temp_avg - opponent_avg)
                if diff < best_diff:
                    best_diff = diff
                    best_combo = combo

            if best_combo:
                transferred_names = []
                for p in best_combo:
                    # Remove from previous team
                    for t in state.times:
                        if p in t.jogadores:
                            t.jogadores.remove(p)
                            t.soma_estrelas, t.media_estrelas = calculate_team_stats(t.jogadores)
                            t.incompleto = (len(t.jogadores) < 5)
                            break
                    
                    team.jogadores.append(p)
                    p.status = "em quadra"
                    transferred_names.append(p.nome)

                team.soma_estrelas, team.media_estrelas = calculate_team_stats(team.jogadores)
                team.incompleto = (len(team.jogadores) < 5)
                messages.append(f"O {team.nome} foi completado para 5 jogadores com {len(best_combo)} atleta(s): {', '.join(transferred_names)}.")

    # Always enforce situation and player status
    for t in state.times:
        if t.id in state.times_em_quadra:
            t.situacao = "em quadra"
            for p in t.jogadores:
                p.status = "em quadra"
        else:
            t.situacao = "esperando"
            for p in t.jogadores:
                p.status = "esperando"

    return messages
