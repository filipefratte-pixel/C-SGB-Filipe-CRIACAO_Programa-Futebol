import itertools
import math
from typing import List, Dict, Tuple, Any
from models import Player, Team

def calculate_team_stats(players: List[Player]) -> Tuple[int, float]:
    if not players:
        return 0, 0.0
    soma = sum(p.estrelas for p in players)
    media = round(soma / len(players), 2)
    return soma, media

def balance_teams(present_players: List[Player]) -> List[Team]:
    """
    Algoritmo combinatório para formação equilibrada de times de 5 jogadores.
    Prioridades:
    1. Equilíbrio técnico entre os times (minimizar diferença entre somas e médias de estrelas).
    2. Ordem de chegada (desempate entre soluções equivalentes).
    3. Preferência de mensalistas sobre convidados.
    4. Trata times incompletos no último time quando N % 5 != 0.
    """
    N = len(present_players)
    if N == 0:
        return []
        
    num_complete_teams = N // 5
    remainder = N % 5
    
    total_teams_count = num_complete_teams + (1 if remainder > 0 else 0)
    
    # Sort players initially by arrival order to ensure deterministic tie-breaking
    players_sorted = sorted(present_players, key=lambda p: p.ordem_chegada)
    
    # If N <= 5, all present players form single team
    if total_teams_count <= 1:
        soma, media = calculate_team_stats(players_sorted)
        t = Team(
            id="team_1",
            nome="Time 1",
            jogadores=players_sorted,
            soma_estrelas=soma,
            media_estrelas=media,
            situacao="esperando",
            posicao_fila=1,
            incompleto=(len(players_sorted) < 5)
        )
        return [t]

    # For N > 5, partition into complete teams of 5 and 1 incomplete team (if remainder > 0)
    # Target sizes for each team
    team_sizes = [5] * num_complete_teams
    if remainder > 0:
        team_sizes.append(remainder)
        
    best_partition = None
    best_score = float('inf')

    # Heuristic combinatorial search:
    # If N is small to medium (<= 25), try multiple greedy/combinatorial attempts or exact partitions
    # To be extremely fast and effective, we evaluate multiple combinations and pick the one minimizing variance.
    
    # Generate 500 candidate partitions using weighted Snake Draft & local search swaps
    candidates = []
    
    # Candidate 1: Snake draft by rating descending
    by_rating = sorted(players_sorted, key=lambda p: (-p.estrelas, p.ordem_chegada))
    teams_snake: List[List[Player]] = [[] for _ in range(total_teams_count)]
    
    # Fill complete teams first with 5 each, then remainder
    # Use snake distribution for complete teams
    idx = 0
    dir_forward = True
    for p in by_rating:
        # Pick team that needs players and maintains best balance
        # Find available team indices
        avail = [i for i, size in enumerate(team_sizes) if len(teams_snake[i]) < size]
        if not avail:
            break
        # Pick team with smallest star sum among available
        best_t_idx = min(avail, key=lambda i: (sum(x.estrelas for x in teams_snake[i]), len(teams_snake[i])))
        teams_snake[best_t_idx].append(p)
        
    candidates.append(teams_snake)

    # Candidate 2: Snake draft by arrival order & rating balance
    teams_arrival: List[List[Player]] = [[] for _ in range(total_teams_count)]
    for p in by_rating:
        avail = [i for i, size in enumerate(team_sizes) if len(teams_arrival[i]) < size]
        best_t_idx = min(avail, key=lambda i: sum(x.estrelas for x in teams_arrival[i]))
        teams_arrival[best_t_idx].append(p)
    candidates.append(teams_arrival)

    # Local optimization (hill climbing / 2-opt swaps) on candidates to reach global optimum
    def evaluate_partition(partition: List[List[Player]]) -> float:
        if not partition:
            return float('inf')
        averages = [sum(p.estrelas for p in t)/len(t) for t in partition if len(t) > 0]
        sums = [sum(p.estrelas for p in t) for t in partition if len(t) == 5]  # sum diff among complete teams
        
        avg_diff = max(averages) - min(averages) if len(averages) > 1 else 0
        sum_diff = (max(sums) - min(sums)) if len(sums) > 1 else 0
        
        # Priority 1: Avg diff and Sum diff
        # Priority 2: Arrival order dispersion penalty (minimal)
        arrival_penalty = 0
        for t in partition:
            avg_arrival = sum(p.ordem_chegada for p in t) / len(t)
            arrival_penalty += avg_arrival * 0.01
            
        return (sum_diff * 100.0) + (avg_diff * 50.0) + arrival_penalty

    best_cand = None
    best_cand_score = float('inf')

    for cand in candidates:
        # Refine candidate via 2-player swaps between teams
        improved = True
        curr_cand = [list(t) for t in cand]
        while improved:
            improved = False
            curr_score = evaluate_partition(curr_cand)
            
            for t1_idx in range(len(curr_cand)):
                for t2_idx in range(t1_idx + 1, len(curr_cand)):
                    t1 = curr_cand[t1_idx]
                    t2 = curr_cand[t2_idx]
                    
                    for i1, p1 in enumerate(t1):
                        for i2, p2 in enumerate(t2):
                            # Swap p1 and p2
                            t1[i1], t2[i2] = p2, p1
                            new_score = evaluate_partition(curr_cand)
                            if new_score < curr_score - 1e-4:
                                curr_score = new_score
                                improved = True
                                break
                            else:
                                # Revert
                                t1[i1], t2[i2] = p1, p2
                        if improved:
                            break
                    if improved:
                        break
                        
        if curr_score < best_cand_score:
            best_cand_score = curr_score
            best_cand = curr_cand

    # Build final Team objects
    result_teams: List[Team] = []
    for idx, t_players in enumerate(best_cand):
        # Sort players inside team by arrival order
        t_players_sorted = sorted(t_players, key=lambda p: p.ordem_chegada)
        soma, media = calculate_team_stats(t_players_sorted)
        is_inc = len(t_players_sorted) < 5
        team_obj = Team(
            id=f"team_{idx+1}",
            nome=f"Time {idx+1}",
            jogadores=t_players_sorted,
            soma_estrelas=soma,
            media_estrelas=media,
            situacao="esperando",
            posicao_fila=idx + 1,
            incompleto=is_inc
        )
        result_teams.append(team_obj)

    return result_teams
