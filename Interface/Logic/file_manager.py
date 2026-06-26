import flet as ft
import asyncio
import os
import logging
from pathlib import Path
from Model.log_parser import LogParser
from ..Librerias import i18n

logger = logging.getLogger(__name__)

class FileManager:
    """Gestiona la apertura, carga y recarga de ficheros de log."""

    def __init__(self, page: ft.Page, app_state, layout, configuracion, config_manager, picker, controller):
        """
        Inicializa el FileManager con todas las dependencias necesarias.

        Args:
            page (ft.Page): Página Flet activa.
            app_state (AppState): Estado global de la aplicación.
            layout (AppLayout): Referencia al layout para actualizar indicadores.
            configuracion (AppSettings): Configuración con el directorio inicial.
            config_manager (ConfigManager): Para guardar el directorio usado.
            picker (ft.FilePicker): Selector de ficheros de Flet.
            controller (Manager): Controlador principal para llamar a _reset_ui_after_load.
        """
        self.page = page
        self.app_state = app_state
        self.layout = layout
        self.configuracion = configuracion
        self.config_manager = config_manager
        self.picker = picker
        self.controller = controller

    async def open_file_dialog(self, e=None):
        """
        Muestra el diálogo de selección de fichero y carga el archivo elegido.

        Abre el FilePicker filtrado a extensiones txt/log, partiendo del
        directorio guardado en la configuración. Si el usuario selecciona un
        fichero válido, delega la carga a ``cargar_fichero_async`` y, en caso
        de éxito, resetea la UI.

        Args:
            e: Evento Flet (opcional, ignorado).
        """
        initial_directory = str(self.configuracion.app.dir_ini)
        result = await self.picker.pick_files(
            allowed_extensions=["txt", "log"],
            dialog_title=i18n.t("menu.open"),
            initial_directory=initial_directory
        )
        if result:
            if await self.cargar_fichero_async(result[0].path, result[0].name):
                self.controller._reset_ui_after_load()

    async def reload_file(self, e=None):
        """
        Recarga el último fichero de log abierto.

        No hace nada si no hay ningún fichero previo cargado
        (``app_state.last_file_path`` es None).

        Args:
            e: Evento Flet (opcional, ignorado).
        """
        if self.app_state.last_file_path:
            if await self.cargar_fichero_async(self.app_state.last_file_path, self.app_state.last_file_name):
                self.controller._reset_ui_after_load()

    async def cargar_fichero_async(self, file_path: str, file_name: str):
        """
        Carga y parsea un fichero de log de forma asíncrona.

        Muestra la barra de progreso durante la operación. Parsea el fichero
        en un executor para no bloquear el hilo principal, convierte las
        entradas a DataFrame y precalcula los valores únicos de cada columna
        categórica. Guarda el directorio del fichero en la configuración.

        Args:
            file_path (str): Ruta completa al fichero a cargar.
            file_name (str): Nombre del fichero (para mostrarlo en la UI).

        Returns:
            bool: True si la carga fue exitosa, False si se produjo un error.
        """
        try:
            self.layout.progress_bar.visible = True
            self.page.update()
            
            loop = asyncio.get_running_loop()
            # Usamos el parser (ya optimizado a diccionarios)
            entries = await loop.run_in_executor(None, lambda: LogParser().parse_file(file_path))
            df = await loop.run_in_executor(None, lambda: LogParser.to_dataframe(entries))
            
            self.app_state.entries = [] # Liberar memoria tras conversión
            self.app_state.df = df
            self.app_state.filtered_df = df
            self.app_state.last_file_path = file_path
            self.app_state.last_file_name = file_name
            
            # Intentar cargar marcas guardas previamente antes de limpiar
            self.app_state.marked_lines.clear()
            self.load_marks(file_path)
            
            if not df.empty:
                # Precalcular valores únicos para los filtros
                self.app_state.unique_levels = await loop.run_in_executor(None, lambda: sorted(df['nivel'].unique().tolist()))
                self.app_state.unique_events = await loop.run_in_executor(None, lambda: sorted(df['evento'].unique().tolist()))
                self.app_state.unique_processes = await loop.run_in_executor(None, lambda: sorted([p for p in df['proceso'].unique().tolist() if p]))
                self.app_state.unique_notes = await loop.run_in_executor(None, lambda: sorted([n for n in df['notas'].unique().tolist() if n]))

                msg_lower = await loop.run_in_executor(None, lambda: df['mensaje'].str.lower())
                self.app_state.search_source = msg_lower
                ts = df['timestamp']
                self.layout.log_range_text.value = f"{i18n.t('sidebar.start')}: {ts.iloc[0]}\n{i18n.t('sidebar.end')}:    {ts.iloc[-1]}"
            
            self.configuracion.app.dir_ini = Path(os.path.dirname(file_path))
            self.config_manager.guardar(self.configuracion)
            
            # El Manager se encarga de llamar a apply_filters y update_filter_controls
            self.layout.selected_file_text.value = f"{i18n.t('menu.file')}: {file_name}"
            self.layout.btn_reload.disabled = False
            
            return True # Éxito
        except Exception as ex:
            self.layout.status_text.value = f"{i18n.t('msg.error', default='Error')}: {ex}"
            logger.error(f"Error cargando fichero: {ex}", exc_info=True)
            return False
        finally:
            self.layout.progress_bar.visible = False
            self.page.update()

    def save_marks(self):
        """
        Guarda las líneas marcadas en un archivo de texto con extensión .marks.
        El archivo se crea en el mismo directorio que el log original.
        Si no hay marcas, intenta eliminar el archivo .marks si existe para limpiar.
        """
        if not self.app_state.last_file_path:
            return

        marks_path = f"{self.app_state.last_file_path}.marks"
        
        if not self.app_state.marked_lines:
            if os.path.exists(marks_path):
                try:
                    os.remove(marks_path)
                    logger.info(f"Archivo de marcas eliminado por estar vacío: {marks_path}")
                except Exception as e:
                    logger.error(f"Error eliminando archivo de marcas vacío: {e}")
            return

        try:
            with open(marks_path, "w", encoding="utf-8") as f:
                # Escribimos los números de línea ordenados, uno por línea
                f.write("\n".join(map(str, sorted(self.app_state.marked_lines))))
            logger.info(f"Marcas persistidas en: {marks_path} ({len(self.app_state.marked_lines)} líneas)")
        except Exception as e:
            logger.error(f"No se pudieron guardar las marcas: {e}")

    def load_marks(self, file_path: str):
        """
        Carga las marcas asociadas a un fichero de log desde su archivo .marks.
        
        Args:
            file_path (str): Ruta al fichero de log original.
        """
        marks_path = f"{file_path}.marks"
        if not os.path.exists(marks_path):
            return

        try:
            with open(marks_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                marks = {int(line.strip()) for line in lines if line.strip().isdigit()}
                self.app_state.marked_lines = marks
                logger.info(f"Marcas cargadas desde {marks_path}: {len(marks)} líneas")
        except Exception as e:
            logger.error(f"Error cargando marcas desde {marks_path}: {e}")
