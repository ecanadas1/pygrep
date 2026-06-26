from dataclasses import dataclass, field
from datetime import datetime, time
from typing import List, Set, Optional, Dict, Any
import pandas as pd
from Model.log_entry import LogEntry

@dataclass
class AppState:
    """
    Gestiona el estado global de la aplicación de forma centralizada y tipada.

    Almacena los datos del log (DataFrames), los filtros activos, el estado
    de la paginación, las líneas marcadas y seleccionadas, y la configuración
    visual temporal.
    """
    entries: List[LogEntry] = field(default_factory=list)
    df: pd.DataFrame = field(default_factory=pd.DataFrame)
    filtered_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    search_source: pd.Series = field(default_factory=lambda: pd.Series(dtype='str'))
    
    # Listas de valores únicos precalculadas para optimización
    unique_levels: List[str] = field(default_factory=list)
    unique_events: List[str] = field(default_factory=list)
    unique_processes: List[str] = field(default_factory=list)
    unique_notes: List[str] = field(default_factory=list)
    
    # Filtros temporales
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    
    # Filtros de selección
    selected_levels: Set[str] = field(default_factory=set)
    selected_events: Set[str] = field(default_factory=set)
    selected_processes: Set[str] = field(default_factory=set)
    selected_notes: Set[str] = field(default_factory=set)
    
    # Búsqueda y Paginación (Filtro)
    search_query: str = ""
    search_mode: str = "AND"
    use_regex: bool = False  
    
    # Búsqueda de Selección (Ctrl+F)
    selection_search_mode: str = "AND"
    selection_use_regex: bool = False
    
    # Búsquedas internas de filtros
    search_level: str = ""
    search_event: str = ""
    search_process: str = ""
    search_note: str = ""

    current_page: int = 1
    page_size: int = 50
    total_pages: int = 1
    stats: Dict[str, Any] = field(default_factory=dict)
    regex_error: bool = False

    # Configuración de visualización
    syntax_highlighting: bool = True

    # Fichero cargado
    last_file_path: Optional[str] = None
    last_file_name: Optional[str] = None

    # Marcación de líneas (checkboxes)
    marked_lines: Set[int] = field(default_factory=set)
    show_only_marked: bool = False

    # Selección visual de filas (resaltado con click/shift/ctrl)
    selected_lines: Set[int] = field(default_factory=set)
    last_selected_line: Optional[int] = None

    # Context View (Split Screen)
    context_mode: bool = False
    context_line: Optional[int] = None
    context_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    context_range: int = 10

    def reset_filters(self):
        """Reinicia los filtros de selección y búsqueda (excepto fechas)."""
        self.current_page = 1
        self.search_query = ""
        self.search_level = ""
        self.search_event = ""
        self.search_process = ""
        self.search_note = ""
        self.selected_levels = set()
        self.selected_events = set()
        self.selected_processes = set()
        self.selected_notes = set()
        self.use_regex = False
        self.show_only_marked = False
        # Limpiar selección visual
        self.selected_lines.clear()
        self.last_selected_line = None
        # Al resetear, el DF filtrado vuelve a ser el original
        self.filtered_df = self.df
