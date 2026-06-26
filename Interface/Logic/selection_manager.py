import flet as ft
import pandas as pd
import logging
import time
import re
import ctypes
import numpy as np
from Model.log_parser import LogParser
from ..Librerias import i18n

# Constantes de Windows para códigos de teclas virtuales
VK_SHIFT = 0x10
VK_CONTROL = 0x11

logger = logging.getLogger(__name__)

class SelectionManager:
    """
    Gestiona la selección visual de filas y la copia al portapapeles.

    Soporta tres modos de selección:
      - **Normal**: un solo clic selecciona únicamente esa fila.
      - **Multi**: cada clic añade o elimina la fila del conjunto seleccionado.
      - **Rango**: selecciona todas las filas entre el último ancla y la fila clicada.

    También registra el evento de teclado global para Ctrl+C (copiar) y
    Ctrl+A (seleccionar todo en la página actual).
    """

    def __init__(self, page, app_state, layout, manager):
        """
        Inicializa el SelectionManager.

        Args:
            page: Página Flet activa; se usa para registrar el listener de teclado.
            app_state (AppState): Estado global de la aplicación.
            layout (AppLayout): Referencia al layout para actualizar colores de botón.
            manager (Manager): Controlador principal para llamar a refresh_selection_visuals.
        """
        self.page = page
        self.app_state = app_state
        self.layout = layout
        self.manager = manager
        
        self.mode_multi = False
        self.mode_range = False
        self._last_click_key = (-1, 0.0, False)
        
        # Estado de teclas modificadoras
        self.ctrl_pressed = False
        self.shift_pressed = False
        
        # Registrar evento de teclado
        self.page.on_keyboard_event = self._on_keyboard_event

    def _on_keyboard_event(self, e: ft.KeyboardEvent):
        """
        Handler global de teclado registrado en ``page.on_keyboard_event``.
        Actualiza el estado de Ctrl/Shift y ejecuta acciones rápidas.
        """
        # Actualizar estado de modificadores (Flet KeyboardEvent tiene estas propiedades)
        self.ctrl_pressed = e.ctrl
        self.shift_pressed = e.shift

        if e.key == "C" and e.ctrl and not e.shift and not e.alt:
            self.page.run_task(self.copy_selected_lines)
        elif e.key == "A" and e.ctrl and not e.shift and not e.alt:
            self.select_all_on_page()
        elif e.key == "F" and e.ctrl and not e.shift and not e.alt:
            self.manager.open_search_selection_dialog()

    def set_mode(self, multi: bool, rango: bool):
        """
        Establece el modo de selección activo y actualiza los colores de los botones.

        Args:
            multi (bool): Si True, activa el modo multi-selección.
            rango (bool): Si True, activa el modo de selección por rango.
        """
        self.mode_multi = multi
        self.mode_range = rango
        
        # Actualización de colores para IconButton (usando icon_color)
        # Forzamos Blanco cuando no está activo para que se vea en el AppBar negro con tema claro
        self.layout.btn_mode_multi.icon_color = ft.Colors.BLUE_400 if multi else ft.Colors.WHITE
        self.layout.btn_mode_range.icon_color = ft.Colors.BLUE_400 if rango else ft.Colors.WHITE
        
        # Fondo sutil para destacar el botón activo
        self.layout.btn_mode_multi.bgcolor = ft.Colors.with_opacity(0.2, ft.Colors.BLUE) if multi else None
        self.layout.btn_mode_range.bgcolor = ft.Colors.with_opacity(0.2, ft.Colors.BLUE) if rango else None

        self.layout.btn_mode_multi.update()
        self.layout.btn_mode_range.update()

    def toggle_mode_multi(self, e=None):
        """
        Alterna el modo multi-selección (desactivando el modo rango).

        Args:
            e: Evento Flet (opcional, ignorado).
        """
        new_val = not self.mode_multi
        self.set_mode(multi=new_val, rango=False)

    def toggle_mode_range(self, e=None):
        """
        Alterna el modo de selección por rango (desactivando el modo multi).

        Args:
            e: Evento Flet (opcional, ignorado).
        """
        new_val = not self.mode_range
        self.set_mode(multi=False, rango=new_val)

    def on_row_click(self, e, line_num: int):
        """
        Maneja el clic en una fila de la tabla.

        Implementa un mecanismo anti-rebote de 50 ms para evitar eventos
        duplicados. Según el modo activo:
          - **Multi**: añade/elimina la fila del conjunto seleccionado.
          - **Rango**: selecciona todas las filas desde el ancla hasta la actual.
          - **Normal**: selecciona únicamente la fila clicada.

        Al terminar actualiza únicamente los colores de selección (sin
        reconstruir toda la tabla).

        Args:
            e: Evento Flet con ``e.control.selected`` si existe.
            line_num (int): Número de línea en el fichero original.
        """
        now = time.monotonic()
        is_selected_event = e.control.selected if hasattr(e.control, 'selected') else True
        
        last_line, last_ts, last_was_selected = self._last_click_key
        
        if line_num == last_line and (now - last_ts) < 0.05:
            if last_was_selected and not is_selected_event:
                return

        self._last_click_key = (line_num, now, is_selected_event)
        df = self.app_state.filtered_df

        # Método "Herramientas de Windows": Consultar directamente el estado del teclado al SO
        # GetAsyncKeyState (0x8000) detecta si la tecla está pulsada en el instante actual
        is_ctrl = (ctypes.windll.user32.GetAsyncKeyState(VK_CONTROL) & 0x8000) != 0
        is_shift = (ctypes.windll.user32.GetAsyncKeyState(VK_SHIFT) & 0x8000) != 0

        # Determinar el modo efectivo
        is_multi = is_ctrl or self.mode_multi
        is_range = is_shift or self.mode_range

        if is_multi:
            if line_num in self.app_state.selected_lines:
                self.app_state.selected_lines.discard(line_num)
            else:
                self.app_state.selected_lines.add(line_num)
            self.app_state.last_selected_line = line_num

        elif is_range:
            anchor = self.app_state.last_selected_line
            if anchor is not None:
                lineas_arr = df['linea'].values.astype(int)
                anchor_pos = np.where(lineas_arr == anchor)[0]
                current_pos = np.where(lineas_arr == line_num)[0]
                if anchor_pos.size > 0 and current_pos.size > 0:
                    lo = min(anchor_pos[0], current_pos[0])
                    hi = max(anchor_pos[0], current_pos[0])
                    self.app_state.selected_lines = set(lineas_arr[lo:hi + 1].tolist())
                else:
                    self.app_state.selected_lines = {line_num}
                    self.app_state.last_selected_line = line_num
            else:
                self.app_state.selected_lines = {line_num}
                self.app_state.last_selected_line = line_num
        else:
            self.app_state.selected_lines = {line_num}
            self.app_state.last_selected_line = line_num

        # Usar la actualización visual optimizada en lugar de refresh_table completo
        self.manager.refresh_selection_visuals()

    async def copy_selected_lines(self, e=None):
        """
        Copia las líneas seleccionadas al portapapeles.

        Construye una representación de texto de cada línea usando operaciones
        vectorizadas de pandas (más rápido que iterar fila a fila). Si la
        vectorización falla, usa un bucle de fallback. Intenta copiar con
        ``pyperclip``; si no está disponible, usa la API de Flet.

        Args:
            e: Evento Flet (opcional, ignorado).
        """
        if not self.app_state.selected_lines:
            return

        df = self.app_state.filtered_df
        selected_rows = df[df['linea'].astype(int).isin(self.app_state.selected_lines)]
        n = len(selected_rows)

        if n > 10000:
            self._show_snack(i18n.t("msg.selecting"))

        text_to_copy = LogParser.format_dataframe_to_text(selected_rows)

        try:
            import pyperclip
            pyperclip.copy(text_to_copy)
        except Exception:
            await ft.Clipboard().set(text_to_copy)
            
        self._show_snack(i18n.t("msg.copied", n=n, s='s' if n != 1 else ''))

    def select_all_on_page(self, e=None):
        """
        Selecciona todos los registros visibles en la página actual.

        Actualiza el conjunto de líneas seleccionadas y establece el ancla en la
        última línea para facilitar selecciones de rango posteriores.

        Args:
            e: Evento Flet (opcional, ignorado).
        """
        df = self.app_state.filtered_df
        if df.empty:
            return

        start_idx = (self.app_state.current_page - 1) * self.app_state.page_size
        end_idx = start_idx + self.app_state.page_size
        page_df = df.iloc[start_idx:end_idx]
        
        page_lines = set(page_df['linea'].astype(int))
        self.app_state.selected_lines.update(page_lines)
        
        # Opcional: poner el anchor en la última línea para Shift+Click posterior
        if not page_df.empty:
            self.app_state.last_selected_line = int(page_df.iloc[-1]['linea'])

        self.manager.refresh_selection_visuals()

    async def select_by_search(self, query: str):
        """
        Busca texto en todas las columnas y selecciona las líneas coincidentes.

        Utiliza el motor de búsqueda (AND/OR/REGEX) configurado para el diálogo de
        selección. Limpia la selección previa y salta automáticamente a la primera
        línea encontrada.

        Args:
            query (str): Texto a buscar en las columnas de los registros.
        """
        df = self.app_state.filtered_df
        if df.empty or not query:
            return

        # Añadir al historial persistente
        self._add_to_history(query)

        # Columnas donde buscar
        search_cols = ['nivel', 'evento', 'proceso', 'mensaje', 'notas', 'pid']
        
        # Concatenar columnas relevantes en una sola serie para buscar más rápido
        search_source = df[search_cols].fillna("").astype(str).agg(' '.join, axis=1)

        if self.app_state.selection_use_regex:
            try:
                mask = search_source.str.contains(query, case=False, regex=True, na=False)
            except Exception:
                self._show_snack(i18n.t("msg.regex_invalid"))
                return
        else:
            query_lower = query.lower()
            terms = query_lower.split()
            search_mask = pd.Series(self.app_state.selection_search_mode == "AND", index=df.index)

            for term in terms:
                term_mask = search_source.str.contains(term, case=False, regex=False, na=False)
                if self.app_state.selection_search_mode == "AND":
                    search_mask &= term_mask
                else:
                    search_mask |= term_mask
            mask = search_mask

        matched_lines = set(df[mask]['linea'].astype(int))
        self.app_state.selected_lines.clear()

        if matched_lines:
            self.app_state.selected_lines.update(matched_lines)
            self._show_snack(i18n.t("msg.selected", n=len(matched_lines)))
            
            # Saltar a la primera línea encontrada (primera en el orden del DF filtrado)
            first_line = int(df[mask].iloc[0]['linea'])
            await self.manager._jump_to_line(first_line)
        else:
            self._show_snack(i18n.t("msg.no_matches", query=query))
            
        self.manager.refresh_selection_visuals()

    def mark_selected_lines(self, mark: bool):
        """
        Marca o desmarca masivamente las líneas que están actualmente seleccionadas.

        Si el filtro 'solo marcadas' está activo, lanza un refiltrado completo para
        actualizar la vista.

        Args:
            mark (bool): True para marcar, False para desmarcar.
        """
        
        if mark:
            self.app_state.marked_lines.update(self.app_state.selected_lines)
        else:
            self.app_state.marked_lines.difference_update(self.app_state.selected_lines)
        
        n = len(self.app_state.selected_lines)
        msg_key = "msg.marked" if mark else "msg.unmarked"
        self._show_snack(i18n.t(msg_key, n=n, s='s' if n != 1 else ''))
        
        # Si el filtro 'solo marcadas' está activo, forzamos un refiltrado completo
        if self.app_state.show_only_marked:
            self.manager.apply_filters()
        else:
            self.manager.refresh_table()

    def _add_to_history(self, query: str):
        """Añade una búsqueda al historial de la configuración y lo guarda."""
        if not query: return
        
        history = self.manager.configuracion.app.historial_busqueda
        
        # Eliminar si ya existe para moverlo al principio
        if query in history:
            history.remove(query)
            
        # Insertar al principio
        history.insert(0, query)
        
        # Limitar a 20 entradas
        self.manager.configuracion.app.historial_busqueda = history[:20]
        
        # Guardar físicamente en el .ini
        self.manager.config_manager.guardar(self.manager.configuracion)

    def _show_snack(self, message: str):
        """Muestra un SnackBar compatible con distintas versiones de Flet."""
        snack = ft.SnackBar(content=ft.Text(message), open=True)
        # Limpiar snacks anteriores del overlay para no acumularlos
        self.page.overlay[:] = [c for c in self.page.overlay if not isinstance(c, ft.SnackBar)]
        self.page.overlay.append(snack)
        self.page.snack_bar = snack
        self.page.update()

    async def goto_line(self, e):
        """
        Salta a un número de línea específico introducido en el campo de texto.

        Args:
            e: Evento Flet del campo de texto.
        """
        val = self.layout.goto_line_field.value.strip()
        if not val: return
        
        try:
            line_num = int(val)
            df = self.app_state.filtered_df
            if line_num in df['linea'].astype(int).values:
                await self.jump_to_line(line_num)
            else:
                self._show_snack(i18n.t("msg.line_not_found", n=line_num))
        except (ValueError, TypeError):
            pass
        finally:
            self.layout.goto_line_field.value = ""
            self.layout.goto_line_field.update()

    async def jump_to_line(self, line_num: int):
        """
        Realiza el salto efectivo a una línea, cambiando de página si es necesario.

        Calcula la página correspondiente, la activa y hace scroll hasta la fila.

        Args:
            line_num (int): Número de línea de destino.
        """
        df = self.app_state.filtered_df
        lineas = df['linea'].astype(int).tolist()
        try:
            pos = lineas.index(line_num)
            new_page = (pos // self.app_state.page_size) + 1
            self.app_state.current_page = new_page
            self.app_state.last_selected_line = line_num
            self.manager.refresh_table()
            
            import asyncio
            await asyncio.sleep(0.1)
            pos_in_page = pos % self.app_state.page_size
            if self.layout.log_table:
                res = self.layout.log_table.scroll_to(offset=pos_in_page * 25, duration=300)
                if asyncio.iscoroutine(res):
                    await res
        except (ValueError, Exception):
            pass

    async def navigate_marked(self, direction: int):
        """
        Navega entre las líneas seleccionadas en el sentido indicado.

        Args:
            direction (int): 1 para avanzar a la siguiente, -1 para retroceder.
        """
        df = self.app_state.filtered_df
        target_set = self.app_state.selected_lines
        if df.empty or not target_set: return
        
        lineas_df = df['linea'].astype(int).tolist()
        current_line = self.app_state.last_selected_line
        if current_line is None:
            idx = (self.app_state.current_page - 1) * self.app_state.page_size
            current_line = lineas_df[idx] if idx < len(lineas_df) else lineas_df[0]

        try:
            curr_pos = lineas_df.index(current_line)
        except ValueError:
            curr_pos = 0

        target_line = None
        if direction == 1:
            for line in lineas_df[curr_pos + 1:]:
                if line in target_set:
                    target_line = line
                    break
            if target_line is None:
                for line in lineas_df:
                    if line in target_set:
                        target_line = line
                        break
        else:
            for line in reversed(lineas_df[:curr_pos]):
                if line in target_set:
                    target_line = line
                    break
            if target_line is None:
                for line in reversed(lineas_df):
                    if line in target_set:
                        target_line = line
                        break
        
        if target_line is not None:
            await self.jump_to_line(target_line)
