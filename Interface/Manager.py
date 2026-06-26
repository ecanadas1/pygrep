import flet as ft
import asyncio
import os
import logging
import threading
from typing import Optional
from .state import AppState
from .app_layout import AppLayout
from .Logic.filter_manager import FilterManager
from .Logic.export_manager import ExportManager
from .Logic.dialogs import Dialogs
from .Logic.selection_manager import SelectionManager
from .Logic.table_renderer import TableRenderer
from .Logic.file_manager import FileManager
from .Logic.system_manager import SystemManager
from .Logic.ui_action_manager import UIActionManager
from .Librerias.config_manager import ConfigManager
from .Librerias.app_settings import AppSettings, Version
from .Librerias import i18n
from Model.log_parser import LogParser

logger = logging.getLogger(__name__)

class Manager:
    """
    Controlador principal de la aplicación (patrón MVC).

    Coordina la interacción entre el modelo (LogParser / AppState), la vista
    (AppLayout y sus componentes) y los módulos de lógica especializados
    (FileManager, FilterManager, ExportManager, SelectionManager,
    TableRenderer, SystemManager y Dialogs).

    Se instancia una única vez en la función ``main`` y recibe la página Flet
    como primer argumento.
    """

    def __init__(self, page: ft.Page, config_manager: ConfigManager, configuracion: AppSettings, metadata: Version):
        """
        Inicializa el Manager y pone en marcha toda la aplicación.

        Secuencia de inicialización:
          1. Configura propiedades básicas de la ventana (título, tamaño mínimo, locale).
          2. Crea el AppState y copia el ajuste de resaltado de sintaxis.
          3. Inicializa variables de control de debounce y filtrado.
          4. Instancia todos los managers y el layout.
          5. Registra el FilePicker en la página (services u overlay).
          6. Aplica geometría y tema guardados.
          7. Construye y muestra la UI, carga las reglas de notas.

        Args:
            page (ft.Page): Página Flet activa.
            config_manager (ConfigManager): Gestiona la lectura/escritura del .ini.
            configuracion (AppSettings): Configuración ya cargada desde el .ini.
            metadata (Version): Datos de versión/autor/ayuda de la aplicación.
        """
        self.page = page
        self.config_manager = config_manager
        self.configuracion = configuracion
        self.metadata = metadata
        
        # Cargar idioma inicial
        i18n.load(self.configuracion.app.idioma)
        
        self.page.title = metadata.title
        icon_path = self._get_resource_path("assets/icon.ico")
        if os.path.exists(icon_path):
            self.page.window.icon = icon_path
            self.page.icon = "icon.ico" 
            try:
                self.page.window_icon = icon_path
            except:
                pass
        else:
            print(f"Icon NOT found at: {icon_path}")
        self.page.window.min_width, self.page.window.min_height = 900, 750
        self.page.locale_configuration = ft.LocaleConfiguration(
            current_locale=ft.Locale(self.configuracion.app.idioma, "US" if self.configuracion.app.idioma == 'en' else "ES"),
            supported_locales=[ft.Locale("es", "ES"), ft.Locale("en", "US")],
        )

        self.app_state = AppState()
        # Inicializar configuración de resaltado desde settings
        self.app_state.syntax_highlighting = self.configuracion.app.resaltado_sintaxis
        # Inicializar tamaño de página desde settings
        self.app_state.page_size = self.configuracion.app.page_size_default
        # Inicializar rango de contexto desde settings
        self.app_state.context_range = self.configuracion.app.context_range

        self._debounce_task = None
        self._filter_controls_debounce_task = None
        self._current_filter_field = None 
        self._is_filtering = False
        self._needs_refilter = False
        self._ui_lock = threading.RLock() 

        # Managers & Renderer
        self.dialogs = Dialogs(self)
        self.layout = AppLayout(self)
        # Se pasa 'self' como controller al TableRenderer
        self.table_renderer = TableRenderer(self.page, self.app_state, self.layout, self.on_row_click, self)
        self.selection_mgr = SelectionManager(self.page, self.app_state, self.layout, self)
        
        self.picker = ft.FilePicker()
        if hasattr(self.page, "services") and self.picker not in self.page.services:
            self.page.services.append(self.picker)
        elif self.picker not in self.page.overlay:
            self.page.overlay.append(self.picker)
        
        self.file_mgr = FileManager(page, self.app_state, self.layout, configuracion, config_manager, self.picker, self)
        self.system_mgr = SystemManager(page, configuracion, config_manager, self.layout)
        self.export_mgr = ExportManager(page, self.app_state, self.layout, self.picker)
        self.filter_mgr = FilterManager(self.app_state)
        self.ui_actions = UIActionManager(self)

        self.system_mgr.apply_geometry()
        self.system_mgr.apply_theme()
        
        self.page.add(self.layout.build())
        # Asegurar compatibilidad con varias versiones de Flet para el cierre
        self.page.window_prevent_close = True
        self.page.window.prevent_close = True
        self.page.on_window_event = self.on_window_event
        self.page.update()
        LogParser.load_rules()
        # Carga inicial del historial en la interfaz
        self.refresh_history_ui()
    def _get_resource_path(self, relative_path: str) -> str:
        """Devuelve la ruta absoluta de un recurso, compatible con compilación."""
        import sys
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(sys._MEIPASS, relative_path)
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_path, relative_path)

    # --- System Delegation ---
    def cambiar_tema(self, mode):
        """Cambia el tema de la aplicación (claro/oscuro)."""
        self.system_mgr.cambiar_tema(mode)

    def cambiar_log_level(self, level):
        """Cambia el nivel de logging global."""
        self.system_mgr.cambiar_log_level(level)

    async def close_app_handler(self, e):
        """Maneja el cierre controlado de la aplicación, guardando el estado necesario."""
        # Persistir marcas antes de cerrar la app
        self.file_mgr.save_marks()
        await self.system_mgr.close_app_handler(e)
    
    async def on_window_event(self, e):
        """Maneja los eventos de la ventana, como el cierre por el botón de la barra de título (X)."""
        if e.data == "close":
            await self.close_app_handler(None)
    def cambiar_page_size_default(self, size: int):
        """
        Cambia el tamaño de página por defecto en la configuración y lo guarda.
        Luego actualiza el tamaño de página actual de la aplicación y el control Dropdown.
        """
        self.configuracion.app.page_size_default = size
        self.config_manager.guardar(self.configuracion)
        
        # Sincronizar el tamaño de página activo
        self.app_state.page_size = size
        self.app_state.current_page = 1
        
        # Actualizar el Dropdown en la UI si el layout ya existe
        if self.layout and self.layout.page_size_dropdown:
            self.layout.page_size_dropdown.value = str(size)
            self.layout.page_size_dropdown.update()

        self.refresh_table()
        self.layout.refresh_appbar()

    def cambiar_context_range(self, range_val: int):
        """Cambia el rango de líneas de la vista de contexto y lo guarda."""
        self.configuracion.app.context_range = range_val
        self.config_manager.guardar(self.configuracion)
        self.app_state.context_range = range_val
        # Actualizar el texto en la UI si el control existe
        if hasattr(self.layout, 'context_title') and self.layout.context_title:
            self.layout.context_title.value = f"Vista de Contexto (±{range_val} líneas)"
            self.layout.context_title.update()

        # Si la vista de contexto está abierta, refrescarla para aplicar el nuevo rango
        if self.app_state.context_mode and self.app_state.context_line is not None:
            self.show_context_view(self.app_state.context_line)
        self.layout.refresh_appbar()

    def cambiar_idioma(self, lang: str):
        """Cambia el idioma de la aplicación y refresca la UI."""
        i18n.load(lang)
        self.configuracion.app.idioma = lang
        self.config_manager.guardar(self.configuracion)
        
        # Reconstruir componentes estáticos
        self.page.locale_configuration.current_locale = ft.Locale(lang, "US" if lang == 'en' else "ES")
        self.layout.refresh_appbar()
        self.layout.refresh_controls()
        self.layout.refresh_sidebar()
        self._update_date_labels_ui()
        self.page.update()

    # --- File Delegation ---
    async def open_file_dialog(self, e):
        """Abre el diálogo de selección de fichero."""
        await self.file_mgr.open_file_dialog(e)

    async def reload_file(self, e):
        """Recarga el fichero actual desde el disco."""
        await self.file_mgr.reload_file(e)
    
    async def _cargar_fichero_async(self, file_path: str, file_name: str):
        """
        Delega la carga asíncrona del fichero al FileManager y resetea la UI.

        Args:
            file_path (str): Ruta completa al fichero de log.
            file_name (str): Nombre del fichero (para mostrarlo en la barra de estado).
        """
        # Guardar marcas del fichero que estamos cerrando antes de cargar el nuevo
        self.file_mgr.save_marks()
        if await self.file_mgr.cargar_fichero_async(file_path, file_name):
            self._reset_ui_after_load()

    def _reset_ui_after_load(self):
        """
        Restablece la interfaz tras cargar un nuevo fichero.

        Limpia los controles de filtro (incluyendo fechas), refresca la barra de aplicación,
        recrea los checkboxes con los valores únicos del nuevo DataFrame
        y aplica los filtros (que quedarán vacíos al haberse reseteado).
        """
        self._reset_filters_ui()
        self._reset_date_filters_ui()   # Al cargar fichero nuevo SÍ se borran las fechas
        self.layout.refresh_appbar()
        self.layout.crear_filtros_iniciales(
            self.app_state.unique_levels,
            self.app_state.unique_events,
            self.app_state.unique_processes,
            self.app_state.unique_notes
        )
        self.apply_filters()

    # --- Export Delegation ---
    async def _exportar_datos(self, e, formato: str):
        await self.export_mgr.exportar_datos(formato)

    # --- Table Delegation ---
    def refresh_table(self): 
        """Refresca los datos y visuales de la tabla principal y la información de selección."""
        self.table_renderer.refresh_table()
        if self.app_state.context_mode:
            self.refresh_context_table(auto_scroll=False)
        self.update_selection_info()

    def refresh_context_table(self, auto_scroll=True):
        """Actualiza la tabla de contexto si está visible."""
        self.table_renderer.refresh_context_table(auto_scroll=auto_scroll)

    def show_context_view(self, line_num):
        """
        Activa la vista de contexto para una línea específica.
        Calcula 10 líneas antes y 10 después del DataFrame original.
        """
        df = self.app_state.df
        if df.empty: return

        try:
            # Encontrar el índice de la línea en el DF original
            idx = df[df['linea'].astype(int) == int(line_num)].index[0]
            
            # Obtener rango (± context_range)
            ctx_range = self.app_state.context_range
            start_idx = max(0, idx - ctx_range)
            end_idx = min(len(df), idx + ctx_range + 1)
            
            self.app_state.context_df = df.iloc[start_idx:end_idx]
            self.app_state.context_line = int(line_num)
            self.app_state.context_mode = True
            
            # Ajustar visibilidad en el layout
            self.layout.context_table_comp.visible = True
            self.layout.main_content_area.update()
            
            # Renderizar datos en la tabla de contexto
            self.refresh_context_table()
            
        except Exception as e:
            logger.error(f"Error al mostrar contexto: {e}")

    def close_context_view(self, e=None):
        """Cierra la vista de contexto y vuelve a pantalla completa."""
        self.app_state.context_mode = False
        self.app_state.context_line = None
        self.app_state.context_df = self.app_state.df.iloc[0:0] # Vaciar
        
        self.layout.context_table_comp.visible = False
        self.layout.main_content_area.update()

    def update_selection_info(self):
        """Actualiza el contador visual de posición en la selección (p.ej. '1 de 10')."""
        if not self.layout.selection_info: return
        
        selected = self.app_state.selected_lines
        if not selected:
            self.layout.selection_info.value = ""
        else:
            total = len(selected)
            curr_line = self.app_state.last_selected_line
            
            # Intentamos determinar la posición relativa en el conjunto filtrado
            try:
                df = self.app_state.filtered_df
                # Solo consideramos las que están en el DF filtrado actual
                all_selected = df[df['linea'].astype(int).isin(selected)]['linea'].tolist()
                total_in_view = len(all_selected)
                
                if curr_line in all_selected:
                    idx = all_selected.index(curr_line) + 1
                    self.layout.selection_info.value = i18n.t("table.selection_info", idx=idx, total=total_in_view)
                else:
                    self.layout.selection_info.value = i18n.t("table.selection_info_total", total=total_in_view)
            except Exception:
                self.layout.selection_info.value = i18n.t("table.selection_info_total", total=total)
        
        try:
            self.layout.selection_info.update()
        except Exception:
            pass

    def refresh_selection_visuals(self): 
        """Actualiza los colores de las filas y la información de selección."""
        self.table_renderer.update_row_colors()
        self.update_selection_info()

    def toggle_mark_all_on_page(self, e, is_context=False):
        """Marca o desmarca todas las líneas visibles en la página actual."""
        self.table_renderer.toggle_mark_all_on_page(e, is_context)

    def update_filter_controls(self, target_filter: Optional[str] = None):
        """
        Actualiza la visibilidad de los checkboxes de un filtro concreto.

        Llama a ``layout.regenerar_checkboxes`` pasando la consulta de búsqueda
        interna del filtro indicado, de modo que solo se muestren las opciones
        que coincidan con lo que el usuario escribió en el campo de búsqueda
        interno del panel.

        Args:
            target_filter (Optional[str]): Clave del filtro a actualizar
                ('level', 'event', 'process', 'note'). Si es None o vacío,
                no hace nada.
        """
        if not target_filter: return
        query = {
            "level": self.app_state.search_level,
            "event": self.app_state.search_event,
            "process": self.app_state.search_process,
            "note": self.app_state.search_note
        }.get(target_filter, "")
        self.layout.regenerar_checkboxes(target_filter, query)

    # --- Selection Delegation ---
    def toggle_mode_multi(self, e):
        """Activa/desactiva el modo de selección múltiple."""
        self.selection_mgr.toggle_mode_multi(e)

    def toggle_mode_range(self, e):
        """Activa/desactiva el modo de selección por rango."""
        self.selection_mgr.toggle_mode_range(e)

    def on_row_click(self, e, line_num):
        """Maneja el clic en una fila de la tabla."""
        self.selection_mgr.on_row_click(e, line_num)

    async def copy_selected_lines(self, e=None):
        """Copia al portapapeles el contenido de las líneas seleccionadas."""
        await self.selection_mgr.copy_selected_lines(e)

    def select_all_on_page(self, e=None):
        """Selecciona todas las líneas de la página actual."""
        self.selection_mgr.select_all_on_page(e)

    def open_search_selection_dialog(self, e=None):
        """Abre el diálogo para seleccionar líneas mediante búsqueda."""
        self.dialogs.open_search_selection(e)

    async def select_by_search(self, query: str):
        """Selecciona líneas que coincidan con la consulta de búsqueda."""
        await self.selection_mgr.select_by_search(query)

    def mark_selected(self, e=None):
        """Marca permanentemente las líneas actualmente seleccionadas."""
        self.selection_mgr.mark_selected_lines(True)

    def unmark_selected(self, e=None):
        """Quita la marca permanente de las líneas actualmente seleccionadas."""
        self.selection_mgr.mark_selected_lines(False)

    # --- Filtering Logic ---
    def apply_filters(self):
        """
        Lanza el proceso de filtrado de forma segura ante llamadas concurrentes.

        Si ya hay un filtrado en curso, activa el flag ``_needs_refilter`` para
        que al terminar se vuelva a filtrar automáticamente. En caso contrario,
        muestra el indicador de carga, resetea la página y selección, y delega
        el trabajo pesado a ``_apply_filters_thread_safe`` en un hilo secundario.
        """
        if self._is_filtering:
            self._needs_refilter = True
            return

        self._is_filtering = True
        self._needs_refilter = False
        
        if not self.layout.search_loading.visible:
            self.layout.search_loading.visible = True
            self.layout.search_loading.update()

        self.app_state.current_page = 1
        self.app_state.selected_lines.clear()
        self.app_state.last_selected_line = None
        self.selection_mgr.set_mode(multi=False, rango=False)

        self.page.run_thread(self._apply_filters_thread_safe)

    def _apply_filters_thread_safe(self):
        """
        Ejecuta el filtrado real en un hilo secundario (thread-safe).

        Aplica los filtros mediante el FilterManager, actualiza el feedback
        visual de regex si procede, recalcula las estadísticas y refresca la
        tabla. Al finalizar (sin error o con error) oculta el indicador de
        carga y, si se solicitó un nuevo refilter durante la ejecución, lo
        lanza de nuevo.
        """
        try:
            self.filter_mgr.apply_filters(self.layout.chk_exclude_clear.value)
            try:
                if self.app_state.use_regex:
                    self.layout.search_field.error_text = "Expresión regular inválida" if self.app_state.regex_error else None
                    self.layout.search_field.border_color = ft.Colors.RED_400 if self.app_state.regex_error else None
                    self.layout.search_field.update()
            except Exception:
                pass

            stats = self.filter_mgr.calculate_statistics()
            self.layout.update_stats(stats)
            self.layout.search_loading.visible = False
            self.refresh_table()
        except Exception as e:
            logger.error(f"Error filtrando: {e}")
            self.layout.search_loading.visible = False
            self.page.update()
        finally:
            self._is_filtering = False
            if self._needs_refilter: self.page.run_thread(self.apply_filters)

    def _reset_filters_ui(self):
        """
        Restablece todos los controles de la UI de filtros a sus valores por defecto,
        EXCEPTO los selectores de fecha/hora (que se preservan al usar 'Limpiar Filtros').

        Para borrar también las fechas (p.ej. al cargar un fichero nuevo) llama
        adicionalmente a ``_reset_date_filters_ui``.
        """
        self.app_state.reset_filters()
        l = self.layout
        l.search_field.value = ""
        l.search_field.error_text = None
        l.search_field.border_color = None
        l.search_mode_radio.value = "AND"
        l.regex_checkbox.value = False
        l.chk_only_marked.value = False
        l.chk_exclude_clear.value = True
        
        if hasattr(l, 'filter_controls'):
            for category in l.filter_controls.values():
                for cb in category.values():
                    cb.value = False
                    cb.visible = True
            
            if l.level_checkboxes.page: l.level_checkboxes.update()
            if l.event_checkboxes.page: l.event_checkboxes.update()
            if l.process_checkboxes.page: l.process_checkboxes.update()
            if l.note_checkboxes.page: l.note_checkboxes.update()
            
            l.search_level_field.value = ""
            l.search_event_field.value = ""
            l.search_process_field.value = ""
            l.search_note_field.value = ""
            if l.search_level_field.page: l.search_level_field.update()
            if l.search_event_field.page: l.search_event_field.update()
            if l.search_process_field.page: l.search_process_field.update()
            if l.search_note_field.page: l.search_note_field.update()

        # Las etiquetas de fecha reflejan el estado actual (sin borrar las fechas)
        self._update_date_labels_ui()

    def _reset_date_filters_ui(self):
        """
        Borra los selectores de fecha/hora y actualiza el estado y las etiquetas.
        Se llama únicamente al cargar un fichero nuevo, no al limpiar filtros.
        """
        l = self.layout
        self.app_state.start_date = None
        self.app_state.end_date = None
        self.app_state.start_time = None
        self.app_state.end_time = None
        l.date_picker_start.value = None
        l.date_picker_end.value = None
        l.time_picker_start.value = None
        l.time_picker_end.value = None
        self._update_date_labels_ui()

    def _trigger_debounced_filter(self, reason: str):
        """Lanza el filtrado con un pequeño retardo para agrupar cambios rápidos."""
        self.ui_actions.trigger_debounced_filter(reason)
    def _update_date_labels_ui(self):
        """
        Actualiza las etiquetas de fecha/hora de inicio y fin con los
        valores actuales del AppState y refresca la página.
        """
        def fmt(d): 
            if not d: return i18n.t("sidebar.no_filter")
            # Si tiene zona horaria, pasar a local para mostrar el día correcto
            if hasattr(d, "tzinfo") and d.tzinfo is not None:
                d = d.astimezone(None)
            return d.strftime('%Y-%m-%d')
            
        def fmt_t(t): return t.strftime('%H:%M') if t else ""
        self.layout.start_date_label.value = f"{fmt(self.app_state.start_date)} {fmt_t(self.app_state.start_time)}"
        self.layout.end_date_label.value = f"{fmt(self.app_state.end_date)} {fmt_t(self.app_state.end_time)}"
        self.page.update()

    def on_search_submit(self, e):
        """Maneja el evento de envío (Enter) en el campo de búsqueda."""
        self.ui_actions.on_search_submit(e)

    def _on_sidebar_history_click(self, e):
        """Maneja el clic en un elemento del historial de la barra lateral."""
        self.ui_actions._on_sidebar_history_click(e)

    # --- UI Action Delegation ---
    def change_page(self, e, delta=0, first=False, last=False):
        """Cambia la página actual de la tabla."""
        self.ui_actions.change_page(e, delta, first, last)

    def on_page_size_change(self, e):
        """Maneja el cambio de tamaño de página."""
        self.ui_actions.on_page_size_change(e)

    def on_level_change(self, e):
        """Maneja el cambio en los filtros de nivel de log."""
        self.ui_actions.on_level_change(e)

    def on_event_change(self, e):
        """Maneja el cambio en los filtros de evento."""
        self.ui_actions.on_event_change(e)

    def on_process_change(self, e):
        """Maneja el cambio en los filtros de proceso."""
        self.ui_actions.on_process_change(e)

    def on_note_change(self, e):
        """Maneja el cambio en los filtros de nota."""
        self.ui_actions.on_note_change(e)

    def on_exclude_clear_change(self, e):
        """Maneja el cambio en el checkbox de exclusión de mensajes vacíos."""
        self.ui_actions.on_exclude_clear_change(e)

    def on_only_marked_change(self, e):
        """Maneja el cambio en el checkbox de mostrar solo marcadas."""
        self.ui_actions.on_only_marked_change(e)

    def on_search_mode_change(self, e):
        """Maneja el cambio entre modo AND/OR en la búsqueda."""
        self.ui_actions.on_search_mode_change(e)

    def on_filter_search_change(self, e):
        """Maneja el cambio en los campos de búsqueda interna de los filtros laterales."""
        self.ui_actions.on_filter_search_change(e)

    def on_date_change_start(self, e):
        """Maneja el cambio en la fecha de inicio."""
        self.ui_actions.on_date_change_start(e)

    def on_date_change_end(self, e):
        """Maneja el cambio en la fecha de fin."""
        self.ui_actions.on_date_change_end(e)

    def on_time_change_start(self, e):
        """Maneja el cambio en la hora de inicio."""
        self.ui_actions.on_time_change_start(e)

    def on_time_change_end(self, e):
        """Maneja el cambio en la hora de fin."""
        self.ui_actions.on_time_change_end(e)

    def on_search_change(self, e):
        """Maneja el cambio de texto en el campo de búsqueda principal."""
        self.ui_actions.on_search_change(e)

    def on_regex_change(self, e):
        """Maneja el cambio en el checkbox de uso de expresiones regulares."""
        self.ui_actions.on_regex_change(e)

    def on_clear_filters(self, e):
        """Maneja el clic en el botón de limpiar filtros."""
        self.ui_actions.on_clear_filters(e)

    async def _debounce_update_filter_controls(self):
        """
        Corutina de debounce: espera 0.3 s y actualiza los controles del
        filtro activo sin lanzar un filtrado completo.

        Se cancela silenciosamente si se recibe un nuevo evento de búsqueda
        antes de que transcurra el tiempo.
        """
        try:
            await asyncio.sleep(0.3)
            self.update_filter_controls(target_filter=self._current_filter_field)
            self._current_filter_field = None
        except asyncio.CancelledError: pass


    def toggle_mark(self, e, line_num):
        """
        Alterna el estado de marcado de una línea individual.

        Si la línea estaba marcada la elimina; si no, la añade. Cuando el
        filtro 'solo marcadas' está activo, relanza el filtrado con debounce
        para que la fila desaparezca o aparezca al instante.

        Args:
            e: Evento Flet del Checkbox de la fila.
            line_num (int): Número de línea en el fichero original.
        """
        line_num = int(line_num) if line_num is not None else None
        if line_num is None: return

        if line_num in self.app_state.marked_lines: 
            self.app_state.marked_lines.discard(line_num)
            logger.info(f"Línea {line_num} desmarcada")
        else: 
            self.app_state.marked_lines.add(line_num)
            logger.info(f"Línea {line_num} marcada")

        if self.app_state.show_only_marked: 
            self._trigger_debounced_filter("toggle_mark")
        else:
            self.refresh_table()
        
        # Forzar actualización de página para asegurar sincronización visual
        self.page.update()

    def toggle_syntax_highlighting(self, e):
        """
        Alterna el resaltado de sintaxis en la columna de mensajes.

        Invierte el valor en AppState y en la configuración persistente,
        guarda los cambios en el .ini, refresca la tabla y la barra de la
        aplicación para que el ícono de estado se actualice.

        Args:
            e: Evento Flet (no se usa el valor; solo sirve como trigger).
        """
        new_val = not self.app_state.syntax_highlighting
        self.app_state.syntax_highlighting = new_val
        self.configuracion.app.resaltado_sintaxis = new_val
        self.config_manager.guardar(self.configuracion)
        self.refresh_table()
        self.layout.refresh_appbar()

    def clear_filters(self):
        """
        Limpia todos los filtros y restaura la vista completa del log.
        """
        self._reset_filters_ui()
        self.apply_filters()
    async def goto_line(self, e):
        """Abre el diálogo para saltar a una línea específica."""
        await self.selection_mgr.goto_line(e)

    async def goto_next_marked(self, e):
        """Salta a la siguiente línea marcada."""
        await self.selection_mgr.navigate_marked(1)

    async def goto_prev_marked(self, e):
        """Salta a la línea marcada anterior."""
        await self.selection_mgr.navigate_marked(-1)

    async def _jump_to_line(self, line_num: int):
        """Realiza el salto efectivo a una línea, cambiando de página si es necesario."""
        await self.selection_mgr.jump_to_line(line_num)

    def refresh_history_ui(self):
        """Actualiza los botones de historial (sidebar y diálogo) con los últimos datos."""
        history = self.configuracion.app.historial_busqueda

        # 1. Actualizar botón de la barra lateral
        if history:
            items_sidebar = []
            for h in history:
                item = ft.PopupMenuItem(content=ft.Text(h), data=h)
                item.on_click = self._on_sidebar_history_click
                items_sidebar.append(item)
            self.layout.sidebar_history_button.items = items_sidebar
        else:
            # Opción por defecto si no hay nada
            self.layout.sidebar_history_button.items = [
                ft.PopupMenuItem(content=ft.Text("Sin historial..."))
            ]
        
        # 2. Actualizar también el del diálogo
        if hasattr(self, 'dialogs'):
            self.dialogs.refresh_history_ui()
            
        try:
            self.layout.sidebar_history_button.update()
        except Exception:
            pass
