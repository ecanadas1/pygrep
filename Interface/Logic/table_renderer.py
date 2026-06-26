import flet as ft
import pandas as pd
import logging
import re
import time
import asyncio
from Model.log_entry import LogEntry
from ..Librerias import i18n

logger = logging.getLogger(__name__)

class TableRenderer:
    """
    Renderiza y actualiza la tabla de registros de log de forma eficiente.

    Usa un **pool de filas** (reciclaje de contenedores existentes) para evitar
    reconstruir el árbol de controles completo en cada cambio de página o
    filtrado, lo que reduce significativamente el número de objetos creados.

    El resaltado de sintaxis en la columna Mensaje se aplica usando patrones
    regex precompilados que detectan IPs, puertos, códigos hexadecimales,
    palabras clave de error/éxito, etc.
    """

    # Patrones regex compilados para el resaltado de sintaxis del campo Mensaje.
    # Cada tupla es (patrón_compilado, color_flet).
    _MSG_PATTERNS = [
        (re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'), ft.Colors.BLUE_400),          # Direcciones IP
        (re.compile(r'(?<=:)\d{4,5}\b'), ft.Colors.AMBER_600),                      # Puerto tras ':'
        (re.compile(r'\bport\s+(\d{4,5})\b', re.IGNORECASE), ft.Colors.AMBER_600), # Palabra 'port NNN'
        (re.compile(r'\b(ERROR|FAIL|FAILED|restart|CRITICAL|FAILURE|shutdown|reboot|DOWN)\b', re.IGNORECASE), ft.Colors.RED_500),
        (re.compile(r'\b(SUCCESSFULLY|SUCCESS|OK|DONE|COMPLETED|UP)\b', re.IGNORECASE), ft.Colors.GREEN_500),
        (re.compile(r'\b0x[0-9a-fA-F]+\b'), ft.Colors.PURPLE_400),                 # Valores hexadecimales
    ]

    # Límite de caracteres visibles en la columna Mensaje (el resto se trunca con '...')
    MAX_DISPLAY_LEN = 500

    def __init__(self, page, app_state, layout, on_row_click, controller):
        """
        Inicializa el TableRenderer.

        Args:
            page: Página Flet activa.
            app_state (AppState): Estado global de la aplicación.
            layout (AppLayout): Referencia al layout con la lista ``log_table``.
            on_row_click: Callback que se invoca al hacer clic en una fila.
            toggle_mark: Callback que se invoca al marcar/desmarcar el checkbox de una fila.
            controller (Manager): Controlador principal; necesario para acceder
                al lock ``_ui_lock`` y a otros métodos.
        """
        self.page = page
        self.app_state = app_state
        self.layout = layout
        self.on_row_click = on_row_click
        self.controller = controller
        
        # Definición de anchos ajustados (debe coincidir con log_table.py)
        self.col_widths = {
            "chk": 35, 
            "line": 55,
            "ts": 135, 
            "level": 75,
            "event": 85,
            "proc": 90,
            "pid": 50,
            "note": 90
        }

    # Wrappers para evitar lambdas en el bucle
    def _handle_row_click(self, e):
        """
        Wrapper interno para el evento on_tap de las filas.
        """
        if e.control.data is not None:
            self.on_row_click(e, e.control.data)

    def _handle_row_double_click(self, e):
        """
        Wrapper interno para el evento on_double_tap de las filas.
        Lanza la vista de contexto para la línea pulsada.
        """
        if e.control.data is not None:
            self.controller.show_context_view(e.control.data)

    def _handle_checkbox_change(self, e):
        """Wrapper interno para el evento on_change de los checkboxes de marcado."""
        if e.control.data is not None:
            self.controller.toggle_mark(e, e.control.data)

    def update_row_colors(self):
        """
        Actualiza solo el color de fondo de las filas visibles según la selección.

        Recorre los controles de la tabla y cambia el ``bgcolor`` de los contenedores
        internos si su estado de selección ha cambiado, evitando reconstruir las filas.
        """
        selected_lines = self.app_state.selected_lines
        selected_color = ft.Colors.with_opacity(0.25, ft.Colors.BLUE)
        
        rows = self.layout.log_table.controls
        if not rows:
            return

        for row_gesture in rows:
            if not row_gesture.visible:
                continue
                
            line_num = row_gesture.data
            is_selected = line_num in selected_lines
            new_color = selected_color if is_selected else None
            
            # El color está en el Container interior del GestureDetector
            container = row_gesture.content
            if container.bgcolor != new_color:
                container.bgcolor = new_color
        
        self.page.update()
        self.update_status_bar()

    def refresh_table(self):
        """
        Reconstruye (o recicla) las filas de la tabla con los datos de la página actual.

        Adquiere el lock de UI para evitar actualizaciones concurrentes. Calcula
        la ventana de datos (``page_df``) a partir del DataFrame filtrado, luego:
          - Reutiliza contenedores existentes (pool) actualizando solo sus valores.
          - Crea nuevos contenedores únicamente para las filas extra necesarias.
          - Elimina los contenedores sobrantes del final de la lista.

        Llama a ``update_pagination_ui`` y ``update_status_bar`` al terminar.
        """
        with self.controller._ui_lock:
            df = self.app_state.filtered_df
            total_items = len(df)
            
            self.app_state.total_pages = max(1, (total_items + self.app_state.page_size - 1) // self.app_state.page_size)
            if self.app_state.current_page > self.app_state.total_pages:
                self.app_state.current_page = self.app_state.total_pages
            if self.app_state.current_page < 1:
                self.app_state.current_page = 1

            if df.empty:
                self.layout.log_table.controls.clear()
                self.layout.empty_message.visible = True
                self.update_pagination_ui()
                self.update_status_bar()
                self.page.update()
                return
            
            self.layout.empty_message.visible = False

            start_idx = (self.app_state.current_page - 1) * self.app_state.page_size
            end_idx = start_idx + self.app_state.page_size
            page_df = df.iloc[start_idx:end_idx]
            
            current_rows_count = len(page_df)

            page_line_nums = set(page_df['linea'].astype(int))
            all_marked = page_line_nums.issubset(self.app_state.marked_lines) if page_line_nums else False
            self.layout.header_checkbox.value = all_marked
            try:
                self.layout.header_checkbox.update()
            except:
                pass

            marked_lines = self.app_state.marked_lines
            selected_lines = self.app_state.selected_lines
            selected_color = ft.Colors.with_opacity(0.25, ft.Colors.BLUE)

            existing_rows = self.layout.log_table.controls
            rows_needed = current_rows_count
            rows_available = len(existing_rows)
            
            # --- FUNCIÓN HELPER PARA CREAR UNA FILA ---
            def create_row(line_num, row_data):
                is_marked = line_num in marked_lines
                
                raw_msg = str(row_data.mensaje)
                if len(raw_msg) > self.MAX_DISPLAY_LEN:
                    display_msg = raw_msg[:self.MAX_DISPLAY_LEN] + "..."
                    tooltip_msg = raw_msg[:1000]
                else:
                    display_msg = raw_msg
                    tooltip_msg = None

                level_color = self.layout._get_level_color(row_data.nivel) if self.app_state.syntax_highlighting else None
                level_weight = ft.FontWeight.BOLD if self.app_state.syntax_highlighting else None
                msg_val, msg_spans = self._calculate_message_content(display_msg)

                # Construir celdas usando Containers
                cells = [
                    ft.Container(content=ft.Checkbox(value=is_marked, on_change=self._handle_checkbox_change, data=line_num, scale=0.8), width=self.col_widths["chk"], alignment=ft.alignment.Alignment(-1, 0)),
                    ft.Container(content=ft.Text(str(line_num), size=11, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, max_lines=1, text_align=ft.TextAlign.LEFT), width=self.col_widths["line"], alignment=ft.alignment.Alignment(-1, 0)),
                    ft.Container(content=ft.Text(str(row_data.timestamp), size=11, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, max_lines=1, text_align=ft.TextAlign.LEFT), width=self.col_widths["ts"], alignment=ft.alignment.Alignment(-1, 0)),
                    ft.Container(content=ft.Text(str(row_data.nivel), size=11, color=level_color, weight=level_weight, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, max_lines=1, text_align=ft.TextAlign.LEFT), width=self.col_widths["level"], alignment=ft.alignment.Alignment(-1, 0)),
                    ft.Container(content=ft.Text(str(row_data.evento), size=11, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, max_lines=1, text_align=ft.TextAlign.LEFT, tooltip=str(row_data.evento)), width=self.col_widths["event"], alignment=ft.alignment.Alignment(-1, 0)),
                    ft.Container(content=ft.Text(str(row_data.proceso), size=11, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, max_lines=1, text_align=ft.TextAlign.LEFT, tooltip=str(row_data.proceso)), width=self.col_widths["proc"], alignment=ft.alignment.Alignment(-1, 0)),
                    ft.Container(content=ft.Text(str(row_data.pid) if pd.notna(row_data.pid) else "-", size=11, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, max_lines=1, text_align=ft.TextAlign.LEFT), width=self.col_widths["pid"], alignment=ft.alignment.Alignment(-1, 0)),
                    # Mensaje expandible
                    ft.Container(
                        content=ft.Text(value=msg_val, spans=msg_spans, size=11, selectable=True, tooltip=tooltip_msg, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, max_lines=1, text_align=ft.TextAlign.LEFT),
                        expand=True,
                        padding=ft.Padding.only(right=10),
                        alignment=ft.alignment.Alignment(-1, 0)
                    ),
                    ft.Container(content=ft.Text(str(row_data.notas), size=11, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, max_lines=1, text_align=ft.TextAlign.LEFT, tooltip=str(row_data.notas) if row_data.notas else None), width=self.col_widths["note"], alignment=ft.alignment.Alignment(-1, 0)),
                ]
                
                row_content = ft.Row(controls=cells, spacing=5, vertical_alignment=ft.CrossAxisAlignment.CENTER)
                
                # Borde sutil que se adapta al tema
                container = ft.Container(
                    content=row_content,
                    bgcolor=selected_color if line_num in selected_lines else None,
                    padding=ft.Padding.symmetric(horizontal=5, vertical=0),
                    border=ft.Border.only(bottom=ft.BorderSide(0.5, "outlineVariant")),
                    height=25 
                )

                return ft.GestureDetector(
                    content=container,
                    on_tap=self._handle_row_click,
                    on_double_tap=self._handle_row_double_click,
                    data=line_num
                )

            # --- ESTRATEGIA DE POOL ---
            for i, row in enumerate(page_df.itertuples(index=False)):
                line_num = int(row.linea)
                
                if i < rows_available:
                    # RECICLAR
                    gesture_row = existing_rows[i]
                    gesture_row.data = line_num
                    
                    container_row = gesture_row.content
                    container_row.bgcolor = selected_color if line_num in selected_lines else None
                    
                    inner_row = container_row.content
                    cells = inner_row.controls
                    
                    # 0: Checkbox
                    is_marked = int(line_num) in marked_lines
                    if cells[0].content.value != is_marked:
                        cells[0].content.value = is_marked
                        # Forzar update del checkbox individual por si acaso
                        try:
                            cells[0].content.update()
                        except:
                            pass
                    cells[0].content.data = int(line_num) 
    
                    # 1-6: Textos
                    cells[1].content.value = str(line_num)
                    cells[2].content.value = str(row.timestamp)
                    
                    # 3: Nivel (con color)
                    cells[3].content.value = str(row.nivel)
                    cells[3].content.color = self.layout._get_level_color(row.nivel) if self.app_state.syntax_highlighting else None
                    cells[3].content.weight = ft.FontWeight.BOLD if self.app_state.syntax_highlighting else None

                    cells[4].content.value = str(row.evento)
                    cells[4].content.tooltip = str(row.evento)
                    cells[5].content.value = str(row.proceso)
                    cells[5].content.tooltip = str(row.proceso)
                    cells[6].content.value = str(row.pid) if pd.notna(row.pid) else "-"
                    
                    # 7: Mensaje
                    raw_msg = str(row.mensaje)
                    if len(raw_msg) > self.MAX_DISPLAY_LEN:
                        display_msg = raw_msg[:self.MAX_DISPLAY_LEN] + "..."
                        tooltip_msg = raw_msg[:1000]
                    else:
                        display_msg = raw_msg
                        tooltip_msg = None
    
                    msg_val, msg_spans = self._calculate_message_content(display_msg)
                    
                    msg_control = cells[7].content
                    
                    if msg_control.value != msg_val:
                        msg_control.value = msg_val
                    
                    msg_control.spans = msg_spans 
                    msg_control.tooltip = tooltip_msg
                    
                    # 8: Notas
                    cells[8].content.value = str(row.notas)
                    cells[8].content.tooltip = str(row.notas) if row.notas else None
                
                else:
                    # CREAR
                    self.layout.log_table.controls.append(create_row(line_num, row))

            # Podar excedentes
            if rows_available > rows_needed:
                del self.layout.log_table.controls[rows_needed:]

            self.update_pagination_ui()
            self.update_status_bar()
            self.layout.log_table.update()
            self.page.update()

    def refresh_context_table(self, auto_scroll=True):
        """
        Renderiza las filas de la tabla de contexto (± context_range líneas).

        Calcula las filas alrededor de la línea central y aplica un resaltado especial
        a esta última.

        Args:
            auto_scroll (bool): Si es True, hace scroll automático hasta la línea central.
        """
        with self.controller._ui_lock:
            df = self.app_state.context_df
            if df.empty or not self.layout.context_log_table:
                return

            marked_lines = self.app_state.marked_lines
            selected_lines = self.app_state.selected_lines
            selected_color = ft.Colors.with_opacity(0.25, ft.Colors.BLUE)
            highlight_color = ft.Colors.with_opacity(0.3, ft.Colors.AMBER) # Color para la línea central

            target_line = self.app_state.context_line
            
            # Actualizar checkbox de cabecera de la tabla de contexto
            context_line_nums = set(df['linea'].astype(int))
            all_marked = context_line_nums.issubset(marked_lines) if context_line_nums else False
            if self.layout.context_table_comp:
                self.layout.context_table_comp.header_checkbox.value = all_marked
                self.layout.context_table_comp.header_checkbox.update()
            
            # --- FUNCIÓN HELPER PARA CREAR UNA FILA (SIMPLIFICADA) ---
            def create_context_row(line_num, row_data):
                is_marked = line_num in marked_lines
                
                raw_msg = str(row_data.mensaje)
                if len(raw_msg) > self.MAX_DISPLAY_LEN:
                    display_msg = raw_msg[:self.MAX_DISPLAY_LEN] + "..."
                    tooltip_msg = raw_msg[:1000]
                else:
                    display_msg = raw_msg
                    tooltip_msg = None

                level_color = self.layout._get_level_color(row_data.nivel) if self.app_state.syntax_highlighting else None
                msg_val, msg_spans = self._calculate_message_content(display_msg)

                # Si es la línea sobre la que se dio doble clic, resaltarla
                bgcolor = highlight_color if line_num == target_line else (selected_color if line_num in selected_lines else None)

                cells = [
                    ft.Container(
                        content=ft.Checkbox(
                            value=is_marked, 
                            on_change=lambda e, ln=line_num: self.controller.toggle_mark(e, ln), 
                            data=line_num, 
                            scale=0.8
                        ), 
                        width=self.col_widths["chk"], 
                        alignment=ft.alignment.Alignment(-1, 0)
                    ),
                    ft.Container(content=ft.Text(str(line_num), size=11, weight=ft.FontWeight.BOLD if line_num == target_line else None), width=self.col_widths["line"], alignment=ft.alignment.Alignment(-1, 0)),
                    ft.Container(content=ft.Text(str(row_data.timestamp), size=11), width=self.col_widths["ts"], alignment=ft.alignment.Alignment(-1, 0)),
                    ft.Container(content=ft.Text(str(row_data.nivel), size=11, color=level_color), width=self.col_widths["level"], alignment=ft.alignment.Alignment(-1, 0)),
                    ft.Container(content=ft.Text(str(row_data.evento), size=11, tooltip=str(row_data.evento), no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, max_lines=1), width=self.col_widths["event"], alignment=ft.alignment.Alignment(-1, 0)),
                    ft.Container(content=ft.Text(str(row_data.proceso), size=11, tooltip=str(row_data.proceso), no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, max_lines=1), width=self.col_widths["proc"], alignment=ft.alignment.Alignment(-1, 0)),
                    ft.Container(content=ft.Text(str(row_data.pid) if pd.notna(row_data.pid) else "-", size=11), width=self.col_widths["pid"], alignment=ft.alignment.Alignment(-1, 0)),
                    ft.Container(
                        content=ft.Text(value=msg_val, spans=msg_spans, size=11, selectable=True, tooltip=tooltip_msg, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, max_lines=1),
                        expand=True,
                        padding=ft.Padding.only(right=10),
                        alignment=ft.alignment.Alignment(-1, 0)
                    ),
                    ft.Container(content=ft.Text(str(row_data.notas), size=11, tooltip=str(row_data.notas) if row_data.notas else None, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, max_lines=1), width=self.col_widths["note"], alignment=ft.alignment.Alignment(-1, 0)),
                ]
                
                row_content = ft.Row(controls=cells, spacing=5, vertical_alignment=ft.CrossAxisAlignment.CENTER)
                
                return ft.Container(
                    content=row_content,
                    bgcolor=bgcolor,
                    on_click=self._handle_row_click,
                    data=line_num,
                    key=str(line_num),
                    padding=ft.Padding.symmetric(horizontal=5, vertical=0),
                    border=ft.Border.only(bottom=ft.BorderSide(0.5, "outlineVariant")),
                    height=25 
                )

            # Reconstrucción simple para el contexto (solo son 21 líneas máx)
            self.layout.context_log_table.controls = [create_context_row(int(row.linea), row) for row in df.itertuples(index=False)]
            try:
                self.layout.context_log_table.update()
            except:
                pass
            
            # Hacer scroll a la línea central (aprox) si se solicita
            if auto_scroll:
                try:
                    # Calculamos el índice relativo en el DataFrame de contexto
                    # para saber cuántas filas bajar.
                    target_idx = 0
                    lineas_contexto = df['linea'].astype(int).tolist()
                    if target_line in lineas_contexto:
                        target_idx = lineas_contexto.index(target_line)
                    
                    # Scroll al offset (índice * altura_fila)
                    # Definimos una pequeña función asíncrona para manejar el scroll si es necesario
                    async def perform_scroll():
                        res = self.layout.context_log_table.scroll_to(offset=target_idx * 25, duration=0)
                        if asyncio.iscoroutine(res):
                            await res

                    # Lanzamos la tarea y nos olvidamos del resultado para evitar avisos
                    self.page.run_task(perform_scroll)
                except Exception:
                    pass
            
            self.page.update()

    def update_pagination_ui(self):
        """
        Actualiza el texto de información de página y el estado (habilitado/deshabilitado)
        de los botones de navegación de la paginación.
        """
        cp = self.app_state.current_page
        tp = self.app_state.total_pages
        self.layout.page_info.value = i18n.t("table.pagination", current=cp, total=tp)
        self.layout.btn_first.disabled = cp == 1
        self.layout.btn_prev.disabled = cp == 1
        self.layout.btn_next.disabled = cp == tp
        self.layout.btn_last.disabled = cp == tp

    def update_status_bar(self):
        """
        Actualiza el texto de la barra de estado con el número de registros
        filtrados, la consulta de búsqueda activa (si existe) y el número de
        líneas seleccionadas (si hay alguna).
        """
        msg = i18n.t("table.records", filtered=len(self.app_state.filtered_df), total=len(self.app_state.df))
        if self.app_state.search_query: msg += f" | {i18n.t('btn.search')}: '{self.app_state.search_query}'"
        self.layout.status_text.value = msg
        self.layout.status_text.update()

    def _calculate_message_content(self, text):
        """
        Calcula el contenido visual del campo Mensaje con resaltado de sintaxis.

        Si el resaltado está desactivado o el texto es corto y sin dígitos,
        devuelve el texto plano sin spans. En caso contrario, busca coincidencias
        de todos los patrones compilados (IPs, puertos, errores, etc.), ordena
        las coincidencias, elimina solapamientos y construye una lista de
        ``ft.TextSpan`` con el color correspondiente a cada patrón.

        Args:
            text (str): Texto del mensaje a analizar (ya truncado si supera MAX_DISPLAY_LEN).

        Returns:
            tuple: ``(value, spans)`` donde:
                - ``value`` es el texto plano (str o None si se usan spans).
                - ``spans`` es la lista de TextSpan (None si no hay resaltado).
        """
        if not text: 
            return "", None
        
        # Chequeo de la opción global de resaltado
        if not self.app_state.syntax_highlighting:
            return text, None
        
        if len(text) < 150 and not any(c in text for c in "0123456789"):
             return text, None

        search_text = text[:self.MAX_DISPLAY_LEN]
        matches = []
        has_matches = False
        for compiled, color in self._MSG_PATTERNS:
            for m in compiled.finditer(search_text):
                has_matches = True
                start, end = m.span(1) if m.lastindex else m.span()
                matches.append((start, end, color))
        
        if not has_matches:
            return text, None

        matches.sort(key=lambda x: x[0])
        
        filtered_matches = []
        current_pos = 0
        for start, end, color in matches:
            if start >= current_pos:
                filtered_matches.append((start, end, color))
                current_pos = end

        spans = []
        last_idx = 0
        for start, end, color in filtered_matches:
            if start > last_idx:
                spans.append(ft.TextSpan(text[last_idx:start]))
            spans.append(ft.TextSpan(text[start:end], style=ft.TextStyle(color=color, weight=ft.FontWeight.BOLD)))
            last_idx = end
        
        if last_idx < len(text):
            spans.append(ft.TextSpan(text[last_idx:]))
            
        return None, spans

    def toggle_mark_all_on_page(self, e, is_context=False):
        """
        Marca o desmarca todas las líneas de la página actual o del contexto.

        El estado del checkbox de cabecera (``is_checked``) determina si se
        añaden o eliminan las líneas de la página del conjunto ``marked_lines``.
        Al terminar refresca la tabla completa para actualizar los checkboxes
        de cada fila.

        Args:
            e: Evento Flet del Checkbox de cabecera con ``e.control.value``.
            is_context (bool): Si es True, opera sobre las líneas del contexto.
        """
        is_checked = e.control.value
        
        if is_context:
            page_df = self.app_state.context_df
        else:
            df = self.app_state.filtered_df
            if df.empty: return
            start_idx = (self.app_state.current_page - 1) * self.app_state.page_size
            end_idx = start_idx + self.app_state.page_size
            page_df = df.iloc[start_idx:end_idx]
            
        if page_df.empty: return
        
        lines_to_modify = set(page_df['linea'].astype(int))
        
        if is_checked:
            self.app_state.marked_lines.update(lines_to_modify)
        else:
            self.app_state.marked_lines.difference_update(lines_to_modify)
        
        self.controller.refresh_table()
