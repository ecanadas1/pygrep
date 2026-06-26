import flet as ft
import logging
from .Components.sidebar import Sidebar
from .Components.log_table import LogTable
from .Components.app_bar import MainAppBar
from .Librerias import i18n

logger = logging.getLogger(__name__)

class AppLayout:
    """
    Construye y gestiona la disposición visual principal de la aplicación.

    Centraliza todos los controles de la interfaz (campos de búsqueda, filtros,
    selectores de fecha/hora, paginación, etc.) y los pone a disposición del
    controlador a través de atributos públicos.

    El layout se compone de dos partes principales:
      - ``sidebar_comp`` (Sidebar): Panel lateral con filtros y controles.
      - ``table_comp`` (LogTable): Área principal con la tabla y paginación.
    """

    def __init__(self, controller):
        """
        Inicializa el AppLayout.

        Crea todos los controles de la UI, instancia los componentes
        especializados y construye la barra de aplicación inicial.

        Args:
            controller (Manager): Controlador principal al que se vinculan
                todos los callbacks de los controles.
        """
        self.controller = controller
        self.controller.layout = self
        self.page = controller.page
        
        # --- UI Controls Initialized here for central access ---
        self._init_controls()
        
        # Initialize specialized components
        self.sidebar_comp = Sidebar(controller, self)
        self.table_comp = LogTable(controller, self)
        self.context_table_comp = LogTable(controller, self, is_context=True)
        self.context_table_comp.visible = False
        
        # Contenedor para la parte derecha (tablas)
        self.main_content_area = ft.Column(
            [
                self.table_comp,
                self.context_table_comp
            ],
            expand=True,
            spacing=0
        )
        
        self.refresh_appbar()

    def _init_controls(self):
        """
        Inicializa todos los controles de la UI y los asigna como atributos.

        Crea campos de texto, barras de progreso, checkboxes, selectores de
        fecha/hora, botones y columnas de filtros, registrando los DatePickers
        y TimePickers en ``page.overlay`` para que Flet los pueda mostrar.
        """
        # State texts
        self.selected_file_text = ft.Text(i18n.t("sidebar.no_file", default="Ningún archivo seleccionado"), size=12)
        self.log_range_text = ft.Text("", size=12)
        self.status_text = ft.Text("", size=12)

        # Progress bars
        self.progress_bar = ft.ProgressBar(visible=False, width=210)
        self.search_loading = ft.ProgressRing(width=20, height=20, visible=False)

        # Search field
        self.search_field = ft.TextField(
            label=i18n.t("sidebar.search_placeholder"),
            on_submit=self.controller.on_search_submit,
            height=40,
            width=210,
            text_size=12,
            content_padding=10,
            filled=True,
            prefix_icon=ft.Icons.SEARCH,
        )

        self.regex_checkbox = ft.Checkbox(
            label=i18n.t("sidebar.regex"),
            on_change=self.controller.on_regex_change
        )

        self.search_mode_radio = ft.RadioGroup(
            content=ft.Row([
                ft.Radio(value="AND", label=i18n.t("sidebar.mode.and")),
                ft.Radio(value="OR", label=i18n.t("sidebar.mode.or")),
            ], spacing=20),
            value="AND",
            on_change=self.controller.on_search_mode_change,
        )

        self.chk_exclude_clear = ft.Checkbox(
            label=i18n.t("sidebar.exclude_clear"),
            value=True,
            on_change=self.controller.on_exclude_clear_change
        )

        self.chk_only_marked = ft.Checkbox(
            label=i18n.t("sidebar.marked_only"),
            on_change=self.controller.on_only_marked_change
        )

        # Checkbox columns
        self.level_checkboxes = ft.Column(scroll=ft.ScrollMode.AUTO)
        self.event_checkboxes = ft.Column(scroll=ft.ScrollMode.AUTO)
        self.process_checkboxes = ft.Column(scroll=ft.ScrollMode.AUTO)
        self.note_checkboxes = ft.Column(scroll=ft.ScrollMode.AUTO)

        # Filter search fields
        self.search_level_field = ft.TextField(label=f"{i18n.t('btn.search')} {i18n.t('sidebar.levels').lower()}...", height=35, text_size=11, on_change=self.controller.on_filter_search_change, data="level")
        self.search_event_field = ft.TextField(label=f"{i18n.t('btn.search')} {i18n.t('sidebar.events').lower()}...", height=35, text_size=11, on_change=self.controller.on_filter_search_change, data="event")
        self.search_process_field = ft.TextField(label=f"{i18n.t('btn.search')} {i18n.t('sidebar.processes').lower()}...", height=35, text_size=11, on_change=self.controller.on_filter_search_change, data="process")
        self.search_note_field = ft.TextField(label=f"{i18n.t('btn.search')} {i18n.t('sidebar.notes').lower()}...", height=35, text_size=11, on_change=self.controller.on_filter_search_change, data="note")

        # Date/Time Pickers
        self.date_picker_start = ft.DatePicker(on_change=self.controller.on_date_change_start)
        self.date_picker_end = ft.DatePicker(on_change=self.controller.on_date_change_end)
        self.time_picker_start = ft.TimePicker(on_change=self.controller.on_time_change_start)
        self.time_picker_end = ft.TimePicker(on_change=self.controller.on_time_change_end)
        
        self.page.overlay.extend([self.date_picker_start, self.date_picker_end, self.time_picker_start, self.time_picker_end])

        # Date/Time Labels
        self.start_date_label = ft.Text(i18n.t("sidebar.no_filter"), size=10, italic=True, color=ft.Colors.GREY_600)
        self.end_date_label = ft.Text(i18n.t("sidebar.no_filter"), size=10, italic=True, color=ft.Colors.GREY_600)

        def open_dp(dp):
            dp.open = True
            self.page.update()

        self.btn_date_start = ft.IconButton(icon=ft.Icons.DATE_RANGE, on_click=lambda _: open_dp(self.date_picker_start))
        self.btn_time_start = ft.IconButton(icon=ft.Icons.ACCESS_TIME, on_click=lambda _: open_dp(self.time_picker_start))
        self.btn_date_end = ft.IconButton(icon=ft.Icons.DATE_RANGE, on_click=lambda _: open_dp(self.date_picker_end))
        self.btn_time_end = ft.IconButton(icon=ft.Icons.ACCESS_TIME, on_click=lambda _: open_dp(self.time_picker_end))

        self.start_controls = ft.Column([
            ft.Row([ft.Text(f"{i18n.t('sidebar.start')}:", weight="bold", size=12, width=50), self.btn_date_start, self.btn_time_start]),
            self.start_date_label
        ], spacing=0)

        self.end_controls = ft.Column([
            ft.Row([ft.Text(f"{i18n.t('sidebar.end')}:", weight="bold", size=12, width=50), self.btn_date_end, self.btn_time_end]),
            self.end_date_label
        ], spacing=0)

        self.stats_column = ft.Column(spacing=5, tight=True)

        self.btn_abrir = ft.ElevatedButton(i18n.t("menu.open"), icon=ft.Icons.FOLDER_OPEN, on_click=self.controller.open_file_dialog, width=162)
        self.btn_reload = ft.IconButton(icon=ft.Icons.REFRESH, tooltip=i18n.t("menu.reload"), on_click=self.controller.reload_file, disabled=True, icon_color=ft.Colors.BLUE_400)
        self.empty_message = ft.Text(i18n.t("msg.no_matches_filters", default="No hay registros que coincidan con los filtros aplicados."), size=14, italic=True, color=ft.Colors.GREY_500, visible=False, text_align=ft.TextAlign.CENTER)

        # These will be set by LogTable or other components
        self.header_checkbox = None
        self.log_table = None
        self.context_log_table = None
        self.page_info = None
        self.btn_first = None
        self.btn_prev = None
        self.btn_next = None
        self.btn_last = None
        self.page_size_dropdown = None
        self.btn_mode_multi = None
        self.btn_mode_range = None
        self.btn_copy_selected = None
        self.btn_prev_marked = None
        self.btn_next_marked = None
        self.selection_info = None
        self.goto_line_field = ft.TextField(
            label=i18n.t("dialog.goto.title"),
            width=90,
            height=30,
            text_size=12,
            content_padding=5,
            on_submit=self.controller.goto_line,
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.InputFilter(allow=True, regex_string=r"^[0-9]*$", replacement_string=""),
        )
        self.sidebar_history_button = ft.PopupMenuButton(
            icon=ft.Icons.HISTORY,
            visible=True,
            width=40,
        )
        
        # Cache de controles de filtro para evitar recreación
        self.filter_controls = {"level": {}, "event": {}, "process": {}, "note": {}}

    def refresh_appbar(self):
        """
        Reconstruye y reemplaza la barra de aplicación (AppBar).

        Instancia un nuevo ``MainAppBar`` con el estado actual del controlador,
        lo asigna a ``page.appbar`` y llama a ``page.update()`` para reflejarlo.
        """
        self.page.appbar = MainAppBar(self.controller)
        self.page.update()

    def refresh_sidebar(self):
        """Reconstruye el Sidebar para aplicar cambios de idioma."""
        self.sidebar_comp._init_ui()
        self.sidebar_comp.update()

    def refresh_controls(self):
        """Actualiza las etiquetas y tooltips de todos los controles base al cambiar de idioma."""
        self.selected_file_text.value = f"{i18n.t('menu.file')}: {self.controller.app_state.last_file_name}" if self.controller.app_state.last_file_name else i18n.t("sidebar.no_file")
        self.search_field.label = i18n.t("sidebar.search_placeholder")
        self.regex_checkbox.label = i18n.t("sidebar.regex")
        self.search_mode_radio.content.controls[0].label = i18n.t("sidebar.mode.and")
        self.search_mode_radio.content.controls[1].label = i18n.t("sidebar.mode.or")
        self.chk_exclude_clear.label = i18n.t("sidebar.exclude_clear")
        self.chk_only_marked.label = i18n.t("sidebar.marked_only")
        
        self.search_level_field.label = f"{i18n.t('btn.search')} {i18n.t('sidebar.levels').lower()}..."
        self.search_event_field.label = f"{i18n.t('btn.search')} {i18n.t('sidebar.events').lower()}..."
        self.search_process_field.label = f"{i18n.t('btn.search')} {i18n.t('sidebar.processes').lower()}..."
        self.search_note_field.label = f"{i18n.t('btn.search')} {i18n.t('sidebar.notes').lower()}..."
        
        self.start_date_label.value = i18n.t("sidebar.no_filter") if not self.controller.app_state.start_date else self.start_date_label.value
        self.end_date_label.value = i18n.t("sidebar.no_filter") if not self.controller.app_state.end_date else self.end_date_label.value
        
        self.start_controls.controls[0].controls[0].value = f"{i18n.t('sidebar.start')}:"
        self.end_controls.controls[0].controls[0].value = f"{i18n.t('sidebar.end')}:"
        
        # Recrear botones para asegurar actualización de idioma en objetos que se reutilizan en el Sidebar
        self.btn_abrir = ft.ElevatedButton(
            i18n.t("menu.open"), 
            icon=ft.Icons.FOLDER_OPEN, 
            on_click=self.controller.open_file_dialog, 
            width=162
        )
        
        reload_disabled = getattr(self, "btn_reload", None).disabled if hasattr(self, "btn_reload") else True
        self.btn_reload = ft.IconButton(
            icon=ft.Icons.REFRESH, 
            tooltip=i18n.t("menu.reload"), 
            on_click=self.controller.reload_file, 
            disabled=reload_disabled, 
            icon_color=ft.Colors.BLUE_400
        )
        
        self.empty_message.value = i18n.t("msg.no_matches_filters")
        self.goto_line_field.label = i18n.t("dialog.goto.title")
        
        # Refrescar tablas y diálogos
        self.table_comp.refresh_ui()
        self.context_table_comp.refresh_ui()
        self.controller.dialogs.refresh_ui()
        
        self.page.update()

    def toggle_sidebar(self, e=None):
        """
        Alterna la visibilidad del panel lateral (Sidebar).

        Args:
            e: Evento Flet (opcional, ignorado).
        """
        self.sidebar_comp.visible = not self.sidebar_comp.visible
        self.sidebar_comp.update()

    def build(self):
        """
        Construye y devuelve el widget raíz de la aplicación.

        Retorna un ``ft.Row`` que contiene el sidebar y la tabla, ambos
        expandidos para ocupar toda la altura disponible.

        Returns:
            ft.Row: Contenedor raíz con el layout completo.
        """
        return ft.Row(
            [
                self.sidebar_comp,
                self.main_content_area,
            ],
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH
        )

    def update_stats(self, stats):
        """
        Actualiza el panel de estadísticas con los datos del último filtrado.

        Muestra el total de registros, los filtrados, y para cada nivel una
        barra de porcentaje de color acorde al nivel de severidad.

        Args:
            stats (dict): Diccionario con claves 'total', 'filtered' y
                'by_level' (dict nivel -> conteo).
        """
        self.stats_column.controls.clear()
        self.stats_column.controls.append(ft.Text(i18n.t("table.stats", total=stats.get('total', 0), filtered=stats.get('filtered', 0)), size=12, weight="bold"))
        self.stats_column.controls.append(ft.Divider(height=10))
        
        levels = stats.get('by_level', {})
        total_filtered = stats.get('filtered', 0)
        sorted_levels = sorted(levels.items(), key=lambda x: x[1], reverse=True)
        
        for level, count in sorted_levels:
            if count == 0: continue
            color = self._get_level_color(level)
            percentage = (count / total_filtered * 100) if total_filtered > 0 else 0
            self.stats_column.controls.append(ft.Row([ft.Container(bgcolor=color, width=10, height=10, border_radius=5), ft.Text(f"{level}: {count} ({percentage:.1f}%)", size=11, expand=True)]))
            self.stats_column.controls.append(ft.ProgressBar(value=percentage/100, color=color, bgcolor=ft.Colors.GREY_300, height=4, border_radius=2))
        self.stats_column.update()

    def _get_level_color(self, level):
        """
        Devuelve el color Flet asociado a un nivel de log.

        Args:
            level (str): Nombre del nivel (p.ej. 'ERROR', 'WARNING', 'INFO').

        Returns:
            str: Constante de color de ``ft.Colors``.
        """
        lvl = str(level).upper()
        # Niveles muy críticos (Rojo oscuro)
        if any(x in lvl for x in ["CRIT", "EMERG", "FATAL"]): return ft.Colors.RED_900
        # Niveles de error y Mayor (Rojo estándar)
        if any(x in lvl for x in ["ERROR", "FAIL", "MAJOR", "MAYOR"]): return ft.Colors.RED_500
        # Niveles de advertencia y Menor (Ámbar/Naranja)
        if any(x in lvl for x in ["WARN", "MINOR", "MENOR"]): return ft.Colors.AMBER_600
        # Niveles informativos (Azul)
        if "INFO" in lvl: return ft.Colors.BLUE_500
        # Niveles de depuración (Púrpura)
        if "DEBUG" in lvl: return ft.Colors.PURPLE_400
        # Nivel de borrado/limpieza (Gris)
        if "CLEAR" in lvl: return ft.Colors.GREY_500
        # Resto (Verde, p. ej. SUCCESS, OK, etc.)
        return ft.Colors.GREEN_500

    def crear_filtros_iniciales(self, levels, events, processes, notes):
        """
        Crea los diccionarios de controles Checkbox para cada categoría de filtro.

        Genera todos los checkboxes necesarios basándose en los valores únicos
        detectados en el log. Estos se cachean en ``self.filter_controls`` para
        poder filtrarlos visualmente después sin tener que destruirlos y recrearlos.

        Args:
            levels (list): Lista de niveles de log únicos.
            events (list): Lista de eventos únicos.
            processes (list): Lista de procesos únicos.
            notes (list): Lista de notas/reglas únicas.
        """
        self.filter_controls = {"level": {}, "event": {}, "process": {}, "note": {}}
        
        def _create_dict(items, on_change):
            # Usamos items directamente ya que ya vienen ordenados del manager
            return {str(item): ft.Checkbox(label=str(item), value=False, on_change=on_change) for item in items}

        self.filter_controls["level"] = _create_dict(levels, self.controller.on_level_change)
        self.filter_controls["event"] = _create_dict(events, self.controller.on_event_change)
        self.filter_controls["process"] = _create_dict(processes, self.controller.on_process_change)
        self.filter_controls["note"] = _create_dict(notes, self.controller.on_note_change)

        self.level_checkboxes.controls = list(self.filter_controls["level"].values())
        self.event_checkboxes.controls = list(self.filter_controls["event"].values())
        self.process_checkboxes.controls = list(self.filter_controls["process"].values())
        self.note_checkboxes.controls = list(self.filter_controls["note"].values())
        
        # Resetear visibilidad por si acaso
        for cat in self.filter_controls.values():
            for cb in cat.values():
                cb.visible = True
                
        self.page.update()

    def regenerar_checkboxes(self, target_filter=None, query=""):
        """
        Filtra visualmente los checkboxes de una categoría según una consulta.

        No destruye los controles, simplemente cambia su propiedad ``visible``
        basándose en si el texto de la consulta está contenido en la etiqueta
        del checkbox.

        Args:
            target_filter (str): Clave de la categoría ('level', 'event', etc.).
            query (str): Texto de búsqueda introducido por el usuario.
        """
        if target_filter not in self.filter_controls:
            return

        controls_dict = self.filter_controls[target_filter]
        parent_column = {
            "level": self.level_checkboxes,
            "event": self.event_checkboxes,
            "process": self.process_checkboxes,
            "note": self.note_checkboxes
        }.get(target_filter)

        if not parent_column: return

        q = query.lower()
        for label, cb in controls_dict.items():
            cb.visible = q in label.lower()
        
        parent_column.update()