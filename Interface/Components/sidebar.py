import flet as ft
from ..Librerias import i18n

class Sidebar(ft.Container):
    """
    Panel lateral deslizable con todos los controles de filtrado.

    Organiza en una columna desplazable:
      - Sección de archivo (abrir / recargar, barra de progreso, rango de fechas).
      - Sección de búsqueda libre (campo, modo AND/OR, regex).
      - Filtros de nivel 'clear' y de líneas marcadas.
      - Paneles desplegables (ExpansionTile) para Fecha/Hora, Niveles,
        Procesos, Eventos, Notas y Estadísticas.
      - Barra de estado en la parte inferior.
    """

    def __init__(self, controller, layout):
        """
        Inicializa el Sidebar.

        Args:
            controller (Manager): Controlador principal con los callbacks de acción.
            layout (AppLayout): Referencia al layout para acceder a los controles
                ya instanciados (campos de búsqueda, checkboxes, etc.).
        """
        super().__init__()
        self.controller = controller
        self.layout = layout
        
        self.width = 250
        self.padding = 20
        self.border_radius = 10
        self._init_ui()

    def _init_ui(self):
        """Inicializa o reconstruye el contenido de la UI."""
        self.content = self._build()

    def _build(self):
        """
        Construye y devuelve el contenido completo del Sidebar.

        Returns:
            ft.Column: Columna con todas las secciones del panel lateral.
        """
        return ft.Column(
            [
                ft.Column(
                    [
                        ft.Text(i18n.t("sidebar.filters"), size=20, weight=ft.FontWeight.BOLD),
                        ft.Divider(),
                        
                        ft.Text(i18n.t("menu.file"), weight=ft.FontWeight.BOLD),
                        ft.Row([
                            self.layout.btn_abrir,
                            self.layout.btn_reload,
                        ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        self.layout.progress_bar,
                        self.layout.selected_file_text,
                        self.layout.log_range_text,
                        ft.Divider(),

                        # Filtro de fecha/hora encima de la sección de filtros
                        self._build_expansion_tile(i18n.t("sidebar.date_time"), ft.Column([self.layout.start_controls, self.layout.end_controls])),

                        ft.Row([
                            ft.Text(f"{i18n.t('sidebar.filters')}:", weight=ft.FontWeight.BOLD),
                            self.layout.search_loading,
                        ], spacing=10),
                        ft.ElevatedButton(i18n.t("sidebar.clear_all"), on_click=self.controller.clear_filters, width=210),
                        
                        self.layout.chk_exclude_clear,
                        self.layout.chk_only_marked,

                        ft.ExpansionTile(
                            title=ft.Row([
                                ft.Icon(ft.Icons.SEARCH, size=18, color=ft.Colors.BLUE_400),
                                ft.Text(i18n.t("sidebar.free_filter"), weight=ft.FontWeight.BOLD),
                            ], spacing=10),
                            controls=[
                                ft.Column([
                                    self.layout.search_field,
                                    self.layout.search_mode_radio,
                                    ft.Row([
                                        self.layout.regex_checkbox,
                                        self.layout.sidebar_history_button
                                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                                ], spacing=8)
                            ],
                            controls_padding=10
                        ),

                        # Filtros desplegables
                        self._build_expansion_tile(i18n.t("sidebar.levels"), ft.Column([self.layout.search_level_field, ft.Container(self.layout.level_checkboxes, height=200)])),
                        self._build_expansion_tile(i18n.t("sidebar.processes"), ft.Column([self.layout.search_process_field, ft.Container(self.layout.process_checkboxes, height=200)])),
                        self._build_expansion_tile(i18n.t("sidebar.events"), ft.Column([self.layout.search_event_field, ft.Container(self.layout.event_checkboxes, height=200)])),
                        self._build_expansion_tile(i18n.t("sidebar.notes"), ft.Column([self.layout.search_note_field, ft.Container(self.layout.note_checkboxes, height=200)])),
                        self._build_expansion_tile(i18n.t("table.stats_title", default="Estadísticas"), self.layout.stats_column),
                    ],
                    spacing=5,
                    scroll=ft.ScrollMode.AUTO,
                    expand=True
                ),
                ft.Row([self.layout.status_text]),
            ],
            spacing=0
        )

    def _build_expansion_tile(self, title, controls_col):
        """
        Crea un panel desplegable (ExpansionTile) con título y contenido.

        Args:
            title (str): Texto del encabezado del panel.
            controls_col (ft.Column): Columna de controles que se muestran
                al expandir el panel.

        Returns:
            ft.ExpansionTile: Panel desplegable configurado.
        """
        return ft.ExpansionTile(
            title=ft.Text(title, weight=ft.FontWeight.BOLD),
            controls=[controls_col],
            controls_padding=10
        )
