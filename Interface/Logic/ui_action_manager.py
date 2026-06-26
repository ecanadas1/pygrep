import asyncio
import logging
import flet as ft
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..Manager import Manager

logger = logging.getLogger(__name__)

class UIActionManager:
    """
    Gestiona los eventos y acciones de la interfaz de usuario.
    
    Esta clase descarga al Manager principal de la lógica de manejo de eventos 
    de los controles (filtros, paginación, búsquedas, etc.).
    """

    def __init__(self, manager: 'Manager'):
        self.mgr = manager
        self.app_state = manager.app_state
        self.layout = manager.layout

    # --- Pagination ---
    def change_page(self, e, delta=0, first=False, last=False):
        """Cambia la página actual de la tabla."""
        if first: self.app_state.current_page = 1
        elif last: self.app_state.current_page = self.app_state.total_pages
        else: self.app_state.current_page = max(1, min(self.app_state.total_pages, self.app_state.current_page + delta))
        self.mgr.refresh_table()

    def on_page_size_change(self, e):
        """Maneja el cambio de tamaño de página."""
        raw = e.data if e.data else (e.control.value if hasattr(e.control, 'value') else None)
        if not raw: return
        self.app_state.page_size = int(raw)
        self.app_state.current_page = 1
        self.mgr.refresh_table()

    # --- Sidebar Filters ---
    def _update_set(self, s, e):
        """Actualiza un conjunto de selección y lanza filtrado debounced."""
        if e.control.value: s.add(e.control.label)
        else: s.discard(e.control.label)
        self.mgr._trigger_debounced_filter("set")

    def on_level_change(self, e):
        """Maneja el cambio en el checkbox de nivel de log."""
        self._update_set(self.app_state.selected_levels, e)

    def on_event_change(self, e):
        """Maneja el cambio en el checkbox de evento."""
        self._update_set(self.app_state.selected_events, e)

    def on_process_change(self, e):
        """Maneja el cambio en el checkbox de proceso."""
        self._update_set(self.app_state.selected_processes, e)

    def on_note_change(self, e):
        """Maneja el cambio en el checkbox de nota."""
        self._update_set(self.app_state.selected_notes, e)
    
    def on_exclude_clear_change(self, e):
        """Maneja el cambio en el filtro de exclusión de niveles 'clear'."""
        self.mgr._trigger_debounced_filter("exclude")
    
    def on_only_marked_change(self, e):
        """Maneja el cambio en el filtro de mostrar solo líneas marcadas."""
        self.app_state.show_only_marked = e.control.value
        self.mgr._trigger_debounced_filter("marked")

    def on_search_mode_change(self, e):
        """Cambia entre modo AND y OR."""
        self.app_state.search_mode = e.control.value
        self.mgr._trigger_debounced_filter("mode")

    def on_filter_search_change(self, e):
        """Maneja la búsqueda interna en los paneles de filtros (checkboxes)."""
        val, field = e.control.value, e.control.data
        if field == "level": self.app_state.search_level = val
        elif field == "event": self.app_state.search_event = val
        elif field == "process": self.app_state.search_process = val
        elif field == "note": self.app_state.search_note = val
        self.mgr._current_filter_field = field
        
        if self.mgr._filter_controls_debounce_task and not self.mgr._filter_controls_debounce_task.done():
            self.mgr._filter_controls_debounce_task.cancel()
        self.mgr._filter_controls_debounce_task = asyncio.create_task(self.mgr._debounce_update_filter_controls())

    # --- Date/Time Filters ---
    def on_date_change_start(self, e):
        """Maneja el cambio en el selector de fecha de inicio."""
        if e.control.value:
            self.app_state.start_date = e.control.value
            self.mgr._update_date_labels_ui()
            self.mgr._trigger_debounced_filter("date_start")

    def on_date_change_end(self, e):
        """Maneja el cambio en el selector de fecha de fin."""
        if e.control.value:
            self.app_state.end_date = e.control.value
            self.mgr._update_date_labels_ui()
            self.mgr._trigger_debounced_filter("date_end")

    def on_time_change_start(self, e):
        """Maneja el cambio en el selector de hora de inicio."""
        if e.control.value:
            self.app_state.start_time = e.control.value
            self.mgr._update_date_labels_ui()
            self.mgr._trigger_debounced_filter("time_start")

    def on_time_change_end(self, e):
        """Maneja el cambio en el selector de hora de fin."""
        if e.control.value:
            self.app_state.end_time = e.control.value
            self.mgr._update_date_labels_ui()
            self.mgr._trigger_debounced_filter("time_end")

    # --- Search Bar ---
    def on_search_change(self, e):
        """Maneja el cambio en la barra de búsqueda principal."""
        self.app_state.search_query = e.control.value
        self.mgr._trigger_debounced_filter("search")

    def on_regex_change(self, e):
        """Activa/Desactiva el uso de Regex en la búsqueda."""
        self.app_state.use_regex = e.control.value
        self.mgr._trigger_debounced_filter("regex")

    def on_clear_filters(self, e):
        """Resetea todos los filtros de la aplicación."""
        self.mgr.clear_filters()

    def on_search_submit(self, e):
        """Maneja el envío de la búsqueda (Enter)."""
        query = self.layout.search_field.value.strip()
        self.app_state.search_query = query
        # Guardar en historial persistente a través del selection manager
        self.mgr.selection_mgr._add_to_history(query)
        self.mgr.refresh_history_ui()
        self.mgr.apply_filters()

    def _on_sidebar_history_click(self, e):
        """Al pulsar un item del historial en la barra lateral."""
        query = e.control.data
        self.layout.search_field.value = query
        self.app_state.search_query = query
        self.mgr.apply_filters()
        self.layout.search_field.update()

    # --- Debounce Logic ---
    def trigger_debounced_filter(self, reason: str):
        """Activa el filtrado con debounce."""
        if not self.layout.search_loading.visible:
            self.layout.search_loading.visible = True
            self.layout.search_loading.update()
        if self.mgr._debounce_task and not self.mgr._debounce_task.done():
            self.mgr._debounce_task.cancel()
        self.mgr._debounce_task = asyncio.create_task(self._debounce_refresh())

    async def _debounce_refresh(self):
        """Corutina de espera para el debounce de filtrado."""
        try:
            await asyncio.sleep(0.4)
            self.mgr.apply_filters()
        except asyncio.CancelledError: pass
