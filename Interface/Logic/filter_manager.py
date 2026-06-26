import pandas as pd
import logging
import threading
from typing import Dict, Any
import re
import datetime

logger = logging.getLogger(__name__)
_state_lock = threading.Lock()

class FilterManager:
    """
    Aplica los filtros definidos por el usuario al DataFrame completo.

    Se encarga de construir una máscara booleana acumulativa combinando
    todos los criterios activos: rango temporal, nivel 'clear', checkboxes
    de nivel/evento/proceso/nota, líneas marcadas y búsqueda libre
    (modo AND/OR o expresión regular).
    """

    def __init__(self, app_state):
        """
        Inicializa el FilterManager.

        Args:
            app_state (AppState): Estado global que contiene el DataFrame completo
                y todos los parámetros de filtrado activos.
        """
        self.app_state = app_state

    def apply_filters(self, exclude_clear: bool):
        """
        Calcula el DataFrame filtrado y lo guarda en el estado global.

        Evalúa secuencialmente los criterios de fecha, niveles, eventos, procesos,
        notas, marcas y búsqueda libre (palabras o regex). El resultado se almacena
        en ``self.app_state.filtered_df``.

        Args:
            exclude_clear (bool): Si es True, se descartan automáticamente los
                registros con nivel 'clear'.
        """
        logger.info("Aplicando filtros...")
        df = self.app_state.df
        if df.empty:
            self.app_state.filtered_df = df
            return

        mask = pd.Series(True, index=df.index)

        # Filtro de fecha/hora
        start_dt = self.app_state.start_date
        if start_dt:
            # IMPORTANTE: Algunos frameworks (como Flet en ciertas versiones/entornos) 
            # devuelven la fecha como un datetime en UTC que puede representar las 23:00 del día anterior.
            # Convertimos a la zona horaria local antes de extraer los componentes.
            if hasattr(start_dt, "tzinfo") and start_dt.tzinfo is not None:
                start_dt = start_dt.astimezone(None)
            
            y, m, d = start_dt.year, start_dt.month, start_dt.day
            if self.app_state.start_time:
                t = self.app_state.start_time
                start_ts = pd.Timestamp(year=y, month=m, day=d, hour=t.hour, minute=t.minute, second=t.second)
            else:
                start_ts = pd.Timestamp(year=y, month=m, day=d)
            
            mask &= (df['timestamp'] >= start_ts)

        end_dt = self.app_state.end_date
        if end_dt:
            if hasattr(end_dt, "tzinfo") and end_dt.tzinfo is not None:
                end_dt = end_dt.astimezone(None)
                
            y, m, d = end_dt.year, end_dt.month, end_dt.day
            if self.app_state.end_time:
                t = self.app_state.end_time
                end_ts = pd.Timestamp(year=y, month=m, day=d, hour=t.hour, minute=t.minute, second=t.second)
            else:
                end_ts = pd.Timestamp(year=y, month=m, day=d, hour=23, minute=59, second=59, microsecond=999999)
            
            mask &= (df['timestamp'] <= end_ts)

        # Filtro de nivel 'clear' (desde el checkbox)
        if exclude_clear:
            mask &= (df['nivel'] != 'clear')

        # Filtros de selección (Niveles, Eventos, Procesos, Notas)
        if self.app_state.selected_levels:
            mask &= (df['nivel'].isin(self.app_state.selected_levels))
        if self.app_state.selected_events:
            mask &= (df['evento'].isin(self.app_state.selected_events))
        if self.app_state.selected_processes:
            mask &= (df['proceso'].isin(self.app_state.selected_processes))
        if self.app_state.selected_notes:
            mask &= (df['notas'].isin(self.app_state.selected_notes))

        # Filtro de líneas marcadas
        if self.app_state.show_only_marked:
            # Asegurar que comparamos enteros con enteros
            marked = [int(x) for x in self.app_state.marked_lines]
            mask &= (df['linea'].astype(int).isin(marked))

        # Filtro de búsqueda libre (optimizado con pandas)
        # IMPORTANTE: search_source es pre-calculado siempre sobre el df COMPLETO (no sobre filtered_df)
        # La máscara 'mask' se aplica sobre df.index, lo que es consistente.
        # Si search_source apuntara al filtered_df cambiaría su índice y la operación & fallaría.
        search_query = self.app_state.search_query
        if search_query:
            search_source = self.app_state.search_source
            if search_source.empty:
                search_source = df['mensaje'].str.lower()
            
            if self.app_state.use_regex:
                try:
                    # Si es regex, usamos str.contains con regex=True
                    # case=False para ignorar mayúsculas/minúsculas por defecto
                    mask &= search_source.str.contains(search_query, case=False, regex=True, na=False)
                    self.app_state.regex_error = False
                except re.error:
                    # Regex inválida: señalizar el error para feedback visual en la UI
                    logger.warning(f"Regex inválida: {search_query}")
                    self.app_state.regex_error = True
            else:
                # Lógica normal de palabras clave
                search_query = search_query.lower()
                terms = search_query.split()
                search_mask = pd.Series(self.app_state.search_mode == "AND", index=df.index)

                for term in terms:
                    term_mask = search_source.str.contains(term, case=False, regex=False, na=False)
                    if self.app_state.search_mode == "AND":
                        search_mask &= term_mask
                    else:
                        search_mask |= term_mask
                mask &= search_mask
        logger.info("Filtros aplicados")

        # Calcular el resultado fuera del lock para minimizar el tiempo bloqueado,
        # y solo asignar al AppState de forma atómica para evitar lecturas parciales
        # desde el hilo de UI mientras se construye el DataFrame filtrado.
        new_filtered = df[mask]
        with _state_lock:
            self.app_state.filtered_df = new_filtered

    def calculate_statistics(self) -> Dict[str, Any]:
        """
        Calcula las estadísticas de los logs basándose en el estado actual.

        Cuenta el total de registros originales, cuántos quedan tras el filtrado
        y el desglose por niveles de severidad en el conjunto filtrado.

        Returns:
            Dict[str, Any]: Diccionario con 'total', 'filtered' y 'by_level'.
        """
        df_all = self.app_state.df
        df_filtered = self.app_state.filtered_df
        
        if df_all.empty:
            return {'total': 0, 'filtered': 0, 'by_level': {}}
            
        by_level = df_filtered['nivel'].value_counts().to_dict()
        
        stats = {
            'total': len(df_all),
            'filtered': len(df_filtered),
            'by_level': by_level
        }
        self.app_state.stats = stats
        return stats
