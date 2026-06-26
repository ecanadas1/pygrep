import flet as ft
from ..Librerias import i18n

class LogTable(ft.Column):
    """
    Componente principal de visualización de la tabla de logs.

    Construye la cabecera simulada (con el checkbox de marcado masivo),
    la lista virtual de filas (``ft.ListView`` con ``item_extent`` fijo para
    rendimiento óptimo), la fila de paginación y los botones de modo de
    selección y copia.

    Los controles creados aquí se asignan al layout (``AppLayout``) para
    que el resto de la aplicación pueda acceder a ellos sin acoplamiento.
    """

    def __init__(self, controller, layout, is_context=False):
        """
        Inicializa el LogTable.

        Args:
            controller (Manager): Controlador principal con los callbacks de
                paginación, selección y marcado.
            layout (AppLayout): Referencia al layout donde se registran
                los controles creados (``log_table``, ``page_info``, etc.).
            is_context (bool): Si es True, se configura como tabla de contexto
                (sin paginación y con referencia separada).
        """
        super().__init__()
        self.controller = controller
        self.layout = layout
        self.is_context = is_context
        self.expand = True
        
        # Referencia para la lista de filas (antes era log_table.rows, ahora será log_list.controls)
        self.log_list = None 
        
        self._init_controls()
        self.controls = self._build()

    def _init_controls(self):
        """
        Crea e inicializa todos los controles del componente.

        Construye la cabecera (checkbox + etiquetas de columna), la lista
        virtual de filas, los botones de paginación, el selector de tamaño
        de página y los botones de modo de selección y copia. Registra
        todos los controles relevantes en el objeto ``layout``.
        """
        # Configuración de anchos de columna optimizados
        self.col_widths = {
            "chk": 35, 
            "line": 55,   # Aumentado para 6 dígitos cómodos
            "ts": 135,    # Aumentado para fecha completa sin cortes
            "level": 75,  # Aumentado para "CRITICAL"
            "event": 85,  # Ajustado
            "proc": 90,   # Ajustado
            "pid": 50,    # Aumentado para 5 dígitos
            "msg": None,  # Expandible
            "note": 90    # Ajustado
        }

        # Checkbox de cabecera
        self.header_checkbox = ft.Checkbox(
            scale=0.8,
            on_change=lambda e: self.controller.toggle_mark_all_on_page(e, is_context=self.is_context),
            tooltip=i18n.t("btn.mark")
        )

        # Cabecera simulada
        self.header_row = ft.Container(
            bgcolor="surfaceVariant",
            padding=ft.Padding(5, 2, 5, 2),
            content=ft.Row(
                spacing=5,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(content=self.header_checkbox, width=self.col_widths["chk"], alignment=ft.alignment.Alignment(-1, 0)),
                    ft.Container(content=ft.Text(i18n.t("table.col.line"), weight="bold", size=12), width=self.col_widths["line"], alignment=ft.alignment.Alignment(-1, 0)),
                    ft.Container(content=ft.Text(i18n.t("table.col.time"), weight="bold", size=12), width=self.col_widths["ts"], alignment=ft.alignment.Alignment(-1, 0)),
                    ft.Container(content=ft.Text(i18n.t("table.col.level"), weight="bold", size=12), width=self.col_widths["level"], alignment=ft.alignment.Alignment(-1, 0)),
                    ft.Container(content=ft.Text(i18n.t("table.col.event"), weight="bold", size=12), width=self.col_widths["event"], alignment=ft.alignment.Alignment(-1, 0)),
                    ft.Container(content=ft.Text(i18n.t("table.col.process"), weight="bold", size=12), width=self.col_widths["proc"], alignment=ft.alignment.Alignment(-1, 0)),
                    ft.Container(content=ft.Text(i18n.t("table.col.pid"), weight="bold", size=12), width=self.col_widths["pid"], alignment=ft.alignment.Alignment(-1, 0)),
                    ft.Container(content=ft.Text(i18n.t("table.col.message"), weight="bold", size=12), expand=True, alignment=ft.alignment.Alignment(-1, 0)), # Expandible
                    ft.Container(content=ft.Text(i18n.t("table.col.notes"), weight="bold", size=12), width=self.col_widths["note"], alignment=ft.alignment.Alignment(-1, 0)),
                ]
            )
        )

        # Lista de logs (Sustituye al DataTable)
        self.log_list = ft.ListView(
            expand=True,
            spacing=0, 
            item_extent=25, 
        )
        
        if self.is_context:
            self.layout.context_log_table = self.log_list
        else:
            self.layout.log_table = self.log_list 
            self.layout.header_checkbox = self.header_checkbox

        # Paginación
        self.page_info = ft.Text(i18n.t("table.pagination", current=1, total=1), size=12)
        self.btn_first = ft.IconButton(
            ft.Icons.FIRST_PAGE, on_click=lambda e: self.controller.change_page(e, first=True),
            disabled=True, tooltip=i18n.t("pagination.first", default="Primera página"), icon_size=20)
        self.btn_prev = ft.IconButton(
            ft.Icons.CHEVRON_LEFT, on_click=lambda e: self.controller.change_page(e, delta=-1),
            disabled=True, tooltip=i18n.t("pagination.prev", default="Página anterior"), icon_size=20)
        self.btn_next = ft.IconButton(
            ft.Icons.CHEVRON_RIGHT, on_click=lambda e: self.controller.change_page(e, delta=1),
            disabled=True, tooltip=i18n.t("pagination.next", default="Página siguiente"), icon_size=20)
        self.btn_last = ft.IconButton(
            ft.Icons.LAST_PAGE, on_click=lambda e: self.controller.change_page(e, last=True),
            disabled=True, tooltip=i18n.t("pagination.last", default="Última página"), icon_size=20)

        # Botones de salto entre marcas
        self.btn_prev_marked = ft.IconButton(
            ft.Icons.KEYBOARD_ARROW_UP, on_click=self.controller.goto_prev_marked,
            tooltip=i18n.t("btn.prev_marked", default="Anterior línea seleccionada"), icon_size=24)
        self.btn_next_marked = ft.IconButton(
            ft.Icons.KEYBOARD_ARROW_DOWN, on_click=self.controller.goto_next_marked,
            tooltip=i18n.t("btn.next_marked", default="Siguiente línea seleccionada"), icon_size=24)

        # Selector de tamaño de página (Cargar valor por defecto desde el estado)
        self.page_size_dropdown = ft.Dropdown(
            value=str(self.controller.app_state.page_size),
            options=[
                ft.dropdown.Option(key="50",  text="50"),
                ft.dropdown.Option(key="100", text="100"),
                ft.dropdown.Option(key="200", text="200"),
                ft.dropdown.Option(key="500", text="500"),
            ],
            width=80,
            text_size=12,
            content_padding=5,
        )
        self.page_size_dropdown.on_select = self.controller.on_page_size_change

        self.selection_info = ft.Text("", size=12, italic=True)

        # Registro en el layout (solo si NO es contexto)
        if not self.is_context:
            self.layout.page_info = self.page_info
            self.layout.btn_first = self.btn_first
            self.layout.btn_prev = self.btn_prev
            self.layout.btn_next = self.btn_next
            self.layout.btn_last = self.btn_last
            self.layout.btn_prev_marked = self.btn_prev_marked
            self.layout.btn_next_marked = self.btn_next_marked
            self.layout.page_size_dropdown = self.page_size_dropdown
            self.layout.selection_info = self.selection_info

        if not self.is_context:
            self.pagination_row = ft.Row(
                [
                    self.btn_first, self.btn_prev, self.page_info, self.btn_next, self.btn_last,
                    ft.VerticalDivider(width=10),
                    ft.Text(f"{i18n.t('menu.page_size').split(' ')[0]}:", size=12),
                    self.page_size_dropdown,
                    ft.VerticalDivider(width=10),
                    self.layout.goto_line_field,
                    ft.VerticalDivider(width=10),
                    self.btn_prev_marked, self.btn_next_marked,
                    self.selection_info,
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                height=40
            )
        else:
            # Barra de herramientas para la tabla de contexto
            self.layout.context_title = ft.Text(i18n.t("table.context_title", range=self.controller.app_state.context_range), size=12, weight="bold", italic=True)
            self.pagination_row = ft.Row(
                [
                    self.layout.context_title,
                    ft.VerticalDivider(width=10),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        tooltip=i18n.t("btn.close", default="Cerrar"),
                        on_click=self.controller.close_context_view,
                        icon_size=20,
                        icon_color=ft.Colors.RED_400
                    )
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                height=40
            )

        # Botones de modo de selección
        self.btn_mode_multi = ft.IconButton(
            icon=ft.Icons.ADD_BOX_OUTLINED,
            tooltip=i18n.t("btn.multi_tooltip", default="Modo Multi-selección (Ctrl+clic)"), 
            on_click=self.controller.toggle_mode_multi,
            icon_size=20,
            icon_color=ft.Colors.WHITE,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=5))
        )
        self.btn_mode_range = ft.IconButton(
            icon=ft.Icons.UNFOLD_MORE, 
            tooltip=i18n.t("btn.range_tooltip", default="Modo Rango (Shift+clic)"), 
            on_click=self.controller.toggle_mode_range,
            icon_size=20,
            icon_color=ft.Colors.WHITE,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=5))
        )
        self.btn_select_all = ft.IconButton(
            icon=ft.Icons.SELECT_ALL,
            tooltip=i18n.t("btn.all_tooltip", default="Seleccionar todo en la página (Ctrl+A)"),
            on_click=self.controller.select_all_on_page,
            icon_size=20,
            icon_color=ft.Colors.WHITE,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=5))
        )
        self.btn_search_selection = ft.IconButton(
            icon=ft.Icons.SEARCH_SHARP,
            tooltip=i18n.t("btn.search_tooltip", default="Seleccionar por texto (Ctrl+F)"),
            on_click=self.controller.open_search_selection_dialog,
            icon_size=20,
            icon_color=ft.Colors.WHITE,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=5))
        )
        self.btn_mark_selected = ft.IconButton(
            icon=ft.Icons.CHECK_BOX,
            icon_color=ft.Colors.GREEN_400,
            tooltip=i18n.t("btn.mark_selected", default="Marcar líneas seleccionadas"),
            on_click=self.controller.mark_selected,
            icon_size=20,
            style = ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=5))
        )
        self.btn_unmark_selected = ft.IconButton(
            icon=ft.Icons.CHECK_BOX_OUTLINE_BLANK,
            icon_color=ft.Colors.RED_400,
            tooltip=i18n.t("btn.unmark_selected", default="Desmarcar líneas seleccionadas"),
            on_click=self.controller.unmark_selected,
            icon_size=20,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=5))
        )
        self.btn_copy_selected = ft.IconButton(
            icon=ft.Icons.COPY, 
            tooltip=i18n.t("btn.copy_tooltip", default="Copiar filas resaltadas (Ctrl+C)"),
            on_click=lambda e: self.controller.page.run_task(self.controller.copy_selected_lines),
            icon_size=20,
            icon_color=ft.Colors.WHITE,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=5))
        )

        if not self.is_context:
            self.layout.btn_mode_multi = self.btn_mode_multi
            self.layout.btn_mode_range = self.btn_mode_range
            self.layout.btn_select_all = self.btn_select_all
            self.layout.btn_search_selection = self.btn_search_selection
            self.layout.btn_mark_selected = self.btn_mark_selected
            self.layout.btn_unmark_selected = self.btn_unmark_selected
            self.layout.btn_copy_selected = self.btn_copy_selected

    def _build(self):
        """
        Construye y devuelve la lista de controles hijos del ``ft.Column``.

        Returns:
            list: Lista con la cabecera, divisores, lista de logs, mensaje
                de lista vacía y fila de paginación.
        """
        return [
            self.header_row,
            ft.Divider(height=1, thickness=1),
            self.log_list,
            ft.Divider(height=1, thickness=1),
            self.layout.empty_message if not self.is_context else ft.Container(),
            self.pagination_row
        ]
    def refresh_ui(self):
        """Actualiza las traducciones de los controles internos de la tabla."""
        self.header_checkbox.tooltip = i18n.t("btn.mark")
        
        # Actualizar textos de cabecera (suponiendo orden fijo)
        header_controls = self.header_row.content.controls
        header_controls[1].content.value = i18n.t("table.col.line")
        header_controls[2].content.value = i18n.t("table.col.time")
        header_controls[3].content.value = i18n.t("table.col.level")
        header_controls[4].content.value = i18n.t("table.col.event")
        header_controls[5].content.value = i18n.t("table.col.process")
        header_controls[6].content.value = i18n.t("table.col.pid")
        header_controls[7].content.value = i18n.t("table.col.message")
        header_controls[8].content.value = i18n.t("table.col.notes")

        if not self.is_context:
            self.page_info.value = i18n.t("table.pagination", current=self.controller.app_state.current_page, total=self.controller.app_state.total_pages)
            self.btn_first.tooltip = i18n.t("pagination.first")
            self.btn_prev.tooltip = i18n.t("pagination.prev")
            self.btn_next.tooltip = i18n.t("pagination.next")
            self.btn_last.tooltip = i18n.t("pagination.last")
            self.btn_prev_marked.tooltip = i18n.t("btn.prev_marked")
            self.btn_next_marked.tooltip = i18n.t("btn.next_marked")
            self.pagination_row.controls[6].value = f"{i18n.t('menu.page_size').split(' ')[0]}:"
        else:
            self.layout.context_title.value = i18n.t("table.context_title", range=self.controller.app_state.context_range)
            self.pagination_row.controls[2].tooltip = i18n.t("btn.close")

        self.btn_mode_multi.tooltip = i18n.t("btn.multi_tooltip")
        self.btn_mode_range.tooltip = i18n.t("btn.range_tooltip")
        self.btn_select_all.tooltip = i18n.t("btn.all_tooltip")
        self.btn_search_selection.tooltip = i18n.t("btn.search_tooltip")
        self.btn_mark_selected.tooltip = i18n.t("btn.mark_selected")
        self.btn_unmark_selected.tooltip = i18n.t("btn.unmark_selected")
        self.btn_copy_selected.tooltip = i18n.t("btn.copy_tooltip")
        
        self.update()
