import flet as ft
import logging
from ..Librerias import i18n

logger = logging.getLogger(__name__)

class Dialogs:
    """
    Gestiona los diálogos modales de la aplicación: 'Acerca de', 'Ayuda' y 'Selección por búsqueda'.

    Inicializa los ``ft.AlertDialog`` en el constructor y los registra en
    ``page.overlay.append`` para que Flet pueda mostrarlos cuando se soliciten.
    """

    def __init__(self, controller):
        """
        Inicializa los diálogos y los registra en la página.

        Args:
            controller (Manager): Controlador principal con acceso a los
                metadatos (título, versión, autor, texto de ayuda) y a la página.
        """
        self.controller = controller
        self._init_dialogs()
        self.controller.page.overlay.extend([self.about_dialog, self.help_dialog, self.search_selection_dialog])

    def _init_dialogs(self):
        """
        Crea los widgets ``ft.AlertDialog`` para 'Acerca de', 'Ayuda' y 'Búsqueda de Selección'.
        """
        self.about_dialog = ft.AlertDialog(
            title=ft.Text(i18n.t("menu.about")),
            content=ft.Column([
                ft.Text(self.controller.metadata.title, weight=ft.FontWeight.BOLD, size=20),
                ft.Text(f"{i18n.t('app.version')}: {self.controller.metadata.version}"),
                ft.Text(f"{i18n.t('app.date')}: {self.controller.metadata.date}"),
                ft.Text(f"{i18n.t('app.author')}: {self.controller.metadata.author}"),
                ft.Divider(),
                ft.Text(i18n.t("app.description", default="Herramienta para visualizar y filtrar logs RTP.")),
            ], tight=True, width=400),
            actions=[ft.TextButton(i18n.t("btn.close", default="Cerrar"), on_click=lambda e: self.close_dialog(self.about_dialog))],
        )
        
        self.help_markdown = ft.Markdown(
            "",
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
        )

        self.help_dialog = ft.AlertDialog(
            title=ft.Text(i18n.t("menu.help")),
            content=ft.Container(
                content=ft.ListView(
                    [self.help_markdown]
                ),
                width=800,
                height=500,
            ),
            actions=[ft.TextButton(i18n.t("btn.close", default="Cerrar"), on_click=lambda e: self.close_dialog(self.help_dialog))],
        )

        # Diálogo para buscar y seleccionar con motor AND/OR/REGEX
        # Campo de texto para búsqueda
        self.search_input = ft.TextField(
            hint_text=i18n.t("dialog.search_selection.placeholder"),
            autofocus=True,
            on_submit=self._on_search_selection_submit,
            prefix_icon=ft.Icons.SEARCH,
            border_radius=10,
            height=45,
            content_padding=10,
            text_size=14,
            expand=True
        )

        # Botón de historial (Popup Menu)
        self.history_button = ft.PopupMenuButton(
            icon=ft.Icons.HISTORY,
            items=[],
            visible=False,
        )

        self.selection_search_mode_radio = ft.RadioGroup(
            content=ft.Row([
                ft.Radio(value="AND", label=i18n.t("sidebar.mode.and"), label_style=ft.TextStyle(size=10)),
                ft.Radio(value="OR", label=i18n.t("sidebar.mode.or"), label_style=ft.TextStyle(size=10)),
            ], spacing=5, alignment=ft.MainAxisAlignment.CENTER),
            value=self.controller.app_state.selection_search_mode,
        )
        self.selection_search_mode_radio.on_change = self._on_selection_search_mode_change

        self.selection_use_regex_check = ft.Checkbox(
            label=i18n.t("sidebar.regex"),
            label_style=ft.TextStyle(size=10),
            value=self.controller.app_state.selection_use_regex,
        )
        self.selection_use_regex_check.on_change = self._on_selection_use_regex_change
        
        self.search_selection_dialog = ft.AlertDialog(
            content=ft.Column([
                ft.Row([self.search_input, self.history_button], spacing=5),
                ft.Row([
                    self.selection_search_mode_radio,
                    ft.Container(width=5),
                    self.selection_use_regex_check
                ], alignment=ft.MainAxisAlignment.CENTER, height=30)
            ], tight=True, spacing=5, width=320, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            shape=ft.RoundedRectangleBorder(radius=10),
            actions=[],
            actions_padding=0,
            inset_padding=ft.Padding(40, 10, 40, 10),
        )

    def refresh_ui(self):
        """Actualiza los textos de los diálogos al cambiar de idioma."""
        self.about_dialog.title.value = i18n.t("menu.about")
        # El contenido del diálogo 'Acerca de' necesita ser reconstruido o sus controles actualizados
        about_col = self.about_dialog.content
        about_col.controls[1].value = f"{i18n.t('app.version')}: {self.controller.metadata.version}"
        about_col.controls[2].value = f"{i18n.t('app.date')}: {self.controller.metadata.date}"
        about_col.controls[3].value = f"{i18n.t('app.author')}: {self.controller.metadata.author}"
        about_col.controls[5].value = i18n.t("app.description")
        
        self.help_dialog.title.value = i18n.t("menu.help")
        self.help_dialog.actions[0].text = i18n.t("btn.close")
        self.about_dialog.actions[0].text = i18n.t("btn.close")
        
        self.search_input.hint_text = i18n.t("dialog.search_selection.placeholder")
        self.selection_search_mode_radio.content.controls[0].label = i18n.t("sidebar.mode.and")
        self.selection_search_mode_radio.content.controls[1].label = i18n.t("sidebar.mode.or")
        self.selection_use_regex_check.label = i18n.t("sidebar.regex")
        
        self.about_dialog.update()
        self.help_dialog.update()
        self.search_selection_dialog.update()

    def close_dialog(self, dialog):
        """
        Cierra el diálogo indicado poniendo su propiedad ``open`` a False.

        Args:
            dialog (ft.AlertDialog): Diálogo a cerrar.
        """
        dialog.open = False
        self.controller.page.update()

    def open_about(self, e):
        """Abre el diálogo 'Acerca de'."""
        logger.info("Abriendo diálogo 'Acerca de'")
        self.about_dialog.open = True
        self.controller.page.update()

    def open_help(self, e):
        """Abre el diálogo 'Ayuda'."""
        logger.info("Abriendo diálogo 'Ayuda'")
        # Cargar texto de ayuda según idioma
        from ..help import get_help_text
        self.help_markdown.value = get_help_text(i18n.current())
        self.help_dialog.open = True
        self.controller.page.update()

    def open_search_selection(self, e=None):
        """Abre el diálogo de búsqueda para selección y sincroniza valores."""
        self.search_input.value = ""
        # Actualizar visualmente el historial
        self.refresh_history_ui()
            
        # Sincronizar UI con el AppState cada vez que se abre
        self.selection_search_mode_radio.value = self.controller.app_state.selection_search_mode
        self.selection_use_regex_check.value = self.controller.app_state.selection_use_regex
        
        self.selection_search_mode_radio.visible = not self.controller.app_state.selection_use_regex
        
        self.search_selection_dialog.open = True
        self.controller.page.update()

    def refresh_history_ui(self):
        """Actualiza los items del botón de historial del diálogo."""
        history = self.controller.configuracion.app.historial_busqueda
        if history:
            items = []
            for h in history:
                item = ft.PopupMenuItem(content=ft.Text(h), data=h)
                item.on_click = self._on_history_item_click
                items.append(item)
            self.history_button.items = items
            self.history_button.visible = True
        else:
            self.history_button.visible = False
        
        if self.history_button.page:
            self.history_button.update()

    def _on_history_item_click(self, e):
        """Al seleccionar del historial, lo ponemos en el input y lanzamos búsqueda."""
        self.search_input.value = e.control.data
        self.controller.page.run_task(self._on_search_selection_submit, None)

    def _on_selection_search_mode_change(self, e):
        """Maneja el cambio de modo (AND/OR) en el diálogo de selección."""
        self.controller.app_state.selection_search_mode = e.control.value
        self.controller.page.update()

    def _on_selection_use_regex_change(self, e):
        """Maneja el cambio de uso de expresiones regulares en el diálogo de selección."""
        self.controller.app_state.selection_use_regex = e.control.value
        self.selection_search_mode_radio.visible = not e.control.value
        self.controller.page.update()

    async def _on_search_selection_submit(self, e):
        """Maneja la acción de buscar y seleccionar desde el diálogo."""
        query = self.search_input.value.strip()
        self.close_dialog(self.search_selection_dialog)
        if query:
            await self.controller.select_by_search(query)

    async def show_loading(self, message="Procesando..."):
        """Muestra feedback visual en la barra de estado (no bloqueante)"""
        pass
