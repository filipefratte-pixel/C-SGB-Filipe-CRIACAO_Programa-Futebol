from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any
from datetime import datetime

# Player Classes: Mensalista or Convidado
PlayerClass = Literal["Mensalista", "Convidado"]

# Player Status in Session
# ausente, presente, escalado, em quadra, esperando, retirado
PlayerStatus = Literal["ausente", "presente", "escalado", "em quadra", "esperando", "retirado"]

class Player(BaseModel):
    id: str  # Unique string ID, e.g. "m_1" for mensalista id 1 or "g_1700000" for convidado
    mensalista_id: Optional[int] = None
    nome: str
    estrelas: int = Field(ge=1, le=5)
    classe: PlayerClass
    ativo: bool = True
    ordem_chegada: int = 0
    horario_chegada: str = ""
    status: PlayerStatus = "ausente"
    contundido: bool = False

class Team(BaseModel):
    id: str  # e.g. "team_1", "team_2"
    nome: str  # e.g. "Time 1", "Time 2"
    jogadores: List[Player] = []
    soma_estrelas: int = 0
    media_estrelas: float = 0.0
    situacao: Literal["em quadra", "esperando"] = "esperando"
    posicao_fila: int = 0
    incompleto: bool = False

class MatchResult(BaseModel):
    id: str
    numero: int
    time_a_id: str
    time_a_nome: str
    time_a_gols: int
    time_b_id: str
    time_b_nome: str
    time_b_gols: int
    vencedor_id: Optional[str] = None  # None if draw
    empate: bool = False
    horario: str = ""

class SubstitutionLog(BaseModel):
    id: str
    horario: str
    jogador_saiu_nome: str
    jogador_entrou_nome: Optional[str]
    time_nome: str
    motivo: Literal["saida", "contusao"]
    origem_substituto: str  # e.g., "Fila de espera", "Sem substituto"

class PeladaState(BaseModel):
    session_id: str
    status: Literal["PRÉ-JOGO", "EM_ANDAMENTO", "ENCERRADA"] = "PRÉ-JOGO"
    started_at: str = ""
    last_saved_at: str = ""
    
    # Session player queue / arrivals
    presencas: List[Player] = []  # List of players present today in arrival order
    retirados: List[Player] = []  # List of players removed/left
    
    # Teams state
    times: List[Team] = []
    times_em_quadra: List[str] = []  # Team IDs [TeamA_ID, TeamB_ID]
    fila_times: List[str] = []      # Waiting Team IDs in order
    
    # Match & Score history
    vencedor_anterior_id: Optional[str] = None
    ultimo_vencedor_nome: Optional[str] = None
    historico_partidas: List[MatchResult] = []
    historico_substituicoes: List[SubstitutionLog] = []
    
    # Undo state stack (last state snapshot before admin modification)
    can_undo: bool = False
    undo_state_json: Optional[str] = None

# API Request Schemas
class MensalistaCreate(BaseModel):
    nome: str
    estrelas: int = Field(ge=1, le=5)
    ativo: bool = True

class MensalistaUpdate(BaseModel):
    nome: str
    estrelas: int = Field(ge=1, le=5)
    ativo: bool = True

class ConvidadoCreate(BaseModel):
    nome: str
    estrelas: int = Field(ge=1, le=5)

class RecordMatchRequest(BaseModel):
    gols_time_a: int = Field(ge=0)
    gols_time_b: int = Field(ge=0)

class PlayerExitRequest(BaseModel):
    player_id: str
    motivo: Literal["saida", "contusao"] = "saida"
    substituto_id: Optional[str] = None  # Admin override or auto-suggested

class SwapPlayersRequest(BaseModel):
    player1_id: str
    player2_id: str

class MovePlayerRequest(BaseModel):
    player_id: str
    target_team_id: str
