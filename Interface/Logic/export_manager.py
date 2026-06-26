import flet as ft
import pandas as pd
import csv
import os
import asyncio
import logging
import sqlite3
from Model.log_entry import LogEntry
from Model.log_parser import LogParser
from ..Librerias import i18n

logger = logging.getLogger(__name__)

class ExportManager:
    """Gestiona la exportación de los registros filtrados a distintos formatos."""

    def __init__(self, page, app_state, layout, picker):
        """
        Inicializa el ExportManager con las dependencias necesarias.

        Args:
            page: Página Flet activa, usada para actualizar la UI.
            app_state (AppState): Estado global de la aplicación que contiene
                el DataFrame filtrado y las líneas marcadas.
            layout (AppLayout): Referencia al layout para actualizar el texto
                de estado.
            picker (ft.FilePicker): Selector de ficheros de Flet utilizado para
                que el usuario elija la ruta de destino.
        """
        self.page = page
        self.app_state = app_state
        self.layout = layout
        self.picker = picker

    async def exportar_datos(self, formato: str):
        """
        Exporta el DataFrame filtrado al formato indicado de forma no bloqueante.

        Muestra un diálogo de guardado al usuario y, si confirma una ruta,
        ejecuta la escritura del fichero en un executor (hilo separado) para
        no congelar la interfaz.

        Formatos soportados:
            - ``'txt'``: Texto plano con una línea por registro.
            - ``'csv'``: CSV con separador ';' y cabecera.
            - ``'md'``:  Tabla Markdown con cabecera.
            - ``'sqlite'``: Base de datos SQLite con tabla ``log_entries``
              incluyendo columna de marcado.

        Args:
            formato (str): Extensión/formato de salida ('txt', 'csv', 'md', 'sqlite').
        """
        if self.app_state.df.empty:
            self.layout.status_text.value = i18n.t("msg.no_data_to_export", default="No hay datos cargados para exportar.")
            self.page.update()
            return

        df_filtered = self.app_state.filtered_df
        if df_filtered.empty:
            self.layout.status_text.value = i18n.t("msg.no_matches_filters", default="No hay registros que coincidan con los filtros actuales.")
            self.page.update()
            return

        try:
            # Asegurar sincronización del picker (Inyectado desde Manager)
            if hasattr(self.page, "services") and self.picker not in self.page.services:
                self.page.services.append(self.picker)
                self.page.update()
                await asyncio.sleep(0.5)
            
            self.picker.update()
            await asyncio.sleep(0.2)
            
            file_path = await self.picker.save_file(
                dialog_title=f"{i18n.t('menu.export')} {formato.upper()}",
                file_name=f"export_filtrado.{formato}",
                allowed_extensions=[formato]
            )

            if file_path:
                self.layout.status_text.value = f"{i18n.t('msg.exporting')} ({formato.upper()})..."
                self.page.update()

                def save_to_file():
                    if formato == 'txt':
                        content = LogParser.format_dataframe_to_text(df_filtered)
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                    elif formato == 'csv':
                        column_order = ['linea', 'timestamp', 'nivel', 'proceso', 'evento', 'pid', 'mensaje', 'notas']
                        df_filtered[column_order].to_csv(file_path, sep=';', index=False, quoting=csv.QUOTE_MINIMAL, encoding='utf-8')
                    elif formato == 'md':
                        column_order = ['linea', 'timestamp', 'nivel', 'proceso', 'evento', 'pid', 'mensaje', 'notas']
                        df_export = df_filtered.copy()[column_order]
                        for col in df_export.columns:
                            df_export[col] = df_export[col].fillna("").astype(str)
                            df_export.loc[df_export[col].str.lower() == "nan", col] = ""
                            df_export[col] = df_export[col].str.replace("|", "\\|", regex=False)
                            df_export[col] = df_export[col].str.replace("\n", " ", regex=False)
                        
                        headers = df_export.columns.tolist()
                        header_row = "| " + " | ".join(headers) + " |"
                        separator_row = "| " + " | ".join([" :--- "] * len(headers)) + " |"
                        row_data = "| " + df_export[headers[0]]
                        for h in headers[1:]:
                            row_data = row_data + " | " + df_export[h]
                        row_data = row_data + " |"
                        
                        content = f"# {i18n.t('msg.exported_title', default='Registros de DumpLog Exportados')}\n\n"
                        content += header_row + "\n"
                        content += separator_row + "\n"
                        content += "\n".join(row_data) + "\n\n"
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                    elif formato == 'sqlite':
                        try:
                            # Convertir a tipos compatibles con SQLite
                            df_export = df_filtered.copy()
                            
                            # Añadir columna de marcada (boolean/int)
                            df_export['marcada'] = df_export['linea'].isin(self.app_state.marked_lines).astype(int)
                            
                            # Convertir datetime a string ISO
                            if pd.api.types.is_datetime64_any_dtype(df_export['timestamp']):
                                df_export['timestamp'] = df_export['timestamp'].astype(str)
                                
                            # Convertir categorías y objetos a string
                            for col in df_export.columns:
                                if str(df_export[col].dtype) == 'category':
                                    df_export[col] = df_export[col].astype(str)
                                elif df_export[col].dtype == 'object':
                                    df_export[col] = df_export[col].fillna("").astype(str)
                            
                            # Eliminar columna 'tags' si existe (o 'tag' si existiera)
                            if 'tags' in df_export.columns:
                                df_export = df_export.drop(columns=['tags'])
                            if 'tag' in df_export.columns:
                                df_export = df_export.drop(columns=['tag'])
                                    
                            conn = sqlite3.connect(file_path)
                            df_export.to_sql('log_entries', conn, if_exists='replace', index=False)
                            conn.commit()
                            conn.close()
                        except Exception as e:
                            logger.error(f"Error específico SQLite: {e}")
                            raise e

                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, save_to_file)

                num_registros = len(df_filtered)
                self.layout.status_text.value = i18n.t("msg.export_success", count=num_registros, file=os.path.basename(file_path), default=f"Exportados {num_registros} registros")
                logger.info(f"{num_registros} registros exportados correctamente a {file_path}")
            else:
                self.layout.status_text.value = i18n.t("msg.export_cancelled", default="Exportación cancelada.")

        except Exception as ex:
            self.layout.status_text.value = f"{i18n.t('msg.error_exporting', default='Error al exportar')}: {ex}"
            logger.error(f"Error al exportar datos: {ex}")
        finally:
            self.page.update()