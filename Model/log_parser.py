import re
import json
import os
from datetime import datetime
import pandas as pd
from typing import List, Optional
from .log_entry import LogEntry
import logging

logger = logging.getLogger(__name__)


class LogParser:
    """Clase encargada de leer y parsear archivos de log RTP."""

    # Explicación del Regex:
    # ^(\d{4}-\d{2}-\d{2})   -> Grupo 1: Fecha (YYYY-MM-DD)
    # \s+                    -> Espacios
    # (\d{2}:\d{2}:\d{2})    -> Grupo 2: Hora (HH:MM:SS)
    # \s+                    -> Espacios
    # (\S+)                  -> Grupo 3: Evento (sin espacios)
    # \s+                    -> Espacios
    # (\S+)                  -> Grupo 4: Nivel (sin espacios)
    # \s+                    -> Espacios
    # "(.*)"                 -> Grupo 5: Mensaje (contenido entre comillas)
    # \s*(.*)$               -> Grupo 6: Resto de la línea (ignorado)
    LOG_PATTERN = re.compile(r'^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})\s+(\S+)\s+(\S+)\s+"(.*)"\s*(.*)$')
    
    # Regex para extraer el PID dentro del mensaje:
    # Soporta formatos: (pid 1234), (pid:1234), (pid: 1234), (pid:1234, ...
    # Busca 'pid', separador opcional (: o espacio), dígitos, y termina en ')' o ','
    PID_PATTERN = re.compile(r'\(pid[:\s]+(\d{2,5})[),]', re.IGNORECASE)

    # Regex para sobreescribir el proceso si aparece ": Process <nombre>"
    PROCESS_OVERRIDE_PATTERN = re.compile(r': Process\s+(\S+)')

    notes_rules = []

    @classmethod
    def load_rules(cls, config_path="notes_config.json"):
        """
        Carga las reglas de anotación automática desde un fichero JSON.

        Lee el fichero indicado, pre-procesa las palabras clave de cada regla
        a minúsculas para acelerar la comparación en tiempo de parseo y las
        almacena en la variable de clase ``notes_rules``.

        Si el fichero no existe o contiene JSON inválido, registra un aviso o
        error en el log y deja ``notes_rules`` vacía.

        Args:
            config_path (str): Ruta al fichero JSON de reglas.
                Por defecto 'notes_config.json' en el directorio actual.
        """
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    rules = json.load(f)
                # Pre-procesar palabras clave a minúsculas una sola vez
                for rule in rules:
                    if "keywords" in rule:
                        rule["keywords_lower"] = [k.lower() for k in rule["keywords"]]
                cls.notes_rules = rules
                logger.info(f"Reglas de notas cargadas ({len(rules)} reglas) desde {config_path}")
            except Exception as e:
                logger.error(f"Error cargando configuración de notas: {e}")
        else:
            logger.warning(f"No se encontró el archivo de reglas de notas: {config_path}. Creando uno por defecto.")
            default_rules = [
                {
                    "keywords": ["Process", "Killed"],
                    "text": "Process Killed"
                },
                {
                    "keywords": ["full", "queue"],
                    "text": "Queue full"
                },
                {
                    "keywords": ["node", "starting"],
                    "text": "Node start"
                },
                {
                    "keywords": ["memory", "utilization"],
                    "text": "Memory Utilization"
                }
            ]
            try:
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(default_rules, f, indent=4)
                for rule in default_rules:
                    if "keywords" in rule:
                        rule["keywords_lower"] = [k.lower() for k in rule["keywords"]]
                cls.notes_rules = default_rules
                logger.info(f"Archivo de reglas de notas por defecto creado y cargado en: {config_path}")
            except Exception as e:
                logger.error(f"Error creando configuración de notas por defecto: {e}")

    def parse_file(self, file_path: str) -> List[LogEntry]:
        """
        Lee un archivo de log y lo convierte en una lista de objetos LogEntry.

        Itera línea a línea, aplicando limpieza básica y delegando el parseo
        específico de cada línea a ``_parse_line``. Registra estadísticas finales
        sobre el número de entradas válidas e inválidas.

        Args:
            file_path (str): Ruta completa al archivo de log.

        Returns:
            List[LogEntry]: Lista de objetos estructurados con los datos parseados.
        """
        entries = []
        invalid_count = 0
        logger.info(f"Iniciando parseo del archivo: {file_path}")
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as file:
                for line_number, line in enumerate(file, start=1):
                    line = line.strip()
                    if not line:
                        continue

                    entry = self._parse_line(line, line_number)
                    if entry:
                        entries.append(entry)
                    else:
                        invalid_count += 1
            logger.info(
                f"Parseo completado: {len(entries)} entradas procesadas"
                + (f", {invalid_count} líneas con formato inválido." if invalid_count else ".")
            )
        except FileNotFoundError:
            logger.error(f"El archivo '{file_path}' no fue encontrado.")
        except Exception as e:
            logger.error(f"Error inesperado al leer el archivo '{file_path}': {e}")
        
        return entries

    def _parse_line(self, line: str, line_number: int) -> Optional[LogEntry]:
        """
        Parsea una línea de texto y la convierte en un objeto LogEntry.

        Aplica el regex principal (LOG_PATTERN) para extraer los campos
        fecha/hora, evento, nivel y mensaje. Dentro del mensaje extrae
        además el proceso, el PID y las notas automáticas según las reglas
        cargadas en ``notes_rules``.

        Args:
            line (str): Línea de texto ya limpia (sin salto de línea).
            line_number (int): Número de línea en el fichero original
                (se almacena en LogEntry para trazabilidad).

        Returns:
            LogEntry: Objeto con todos los campos extraídos si la línea
                encaja con el patrón.
            None: Si la línea no coincide con el patrón o se produce un
                error durante el procesamiento.
        """
        match = self.LOG_PATTERN.match(line)
        if match:
            try:
                timestamp_str = f"{match.group(1)} {match.group(2)}"
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                
                raw_message = match.group(5)
                
                # 1. Extraer Proceso: Desde el inicio hasta el primer ':'
                # Si no hay ':', asumimos que no hay proceso especificado (cadena vacía)
                parts = raw_message.split(':', 1)
                proceso = parts[0].strip() if len(parts) > 1 else ""
                
                # 1.1 Excepción: Si aparece ": Process", la siguiente palabra es el proceso real
                proc_override_match = self.PROCESS_OVERRIDE_PATTERN.search(raw_message)
                if proc_override_match and proceso == "RTP":
                    proceso = proc_override_match.group(1)
                
                # 2. Extraer PID: Buscar patrón (pid xxxx)
                pid_match = self.PID_PATTERN.search(raw_message)
                pid = pid_match.group(1) if pid_match else None
                
                # 3. Extraer Notas (Grupo 6)
                notas = ""
                rules = self.notes_rules
                if rules:
                    detected = []
                    msg_lower = raw_message.lower()
                    for rule in rules:
                        keywords = rule.get("keywords_lower")
                        if keywords and all(k in msg_lower for k in keywords):
                            text = rule.get("text") or rule.get("note") or ""
                            if text:
                                detected.append(text)
                    if detected:
                        notas = " | ".join(detected)

                return LogEntry(line_number, timestamp, match.group(3), match.group(4), proceso, pid, raw_message, notas)
            except Exception as e:
                logger.error(f"Error procesando línea {line_number}: {e}")
                return None

    @staticmethod
    def to_dataframe(entries: List[LogEntry]) -> pd.DataFrame:
        """
        Convierte una lista de LogEntry en un DataFrame de pandas optimizado.
        
        Realiza una construcción columnar para maximizar la velocidad. Además,
        realiza optimizaciones de tipos, como convertir la fecha a datetime
        y las columnas repetitivas (nivel, evento, proceso) a tipos categóricos,
        lo que reduce significativamente el uso de memoria y acelera el filtrado.

        Args:
            entries (List[LogEntry]): Lista de entradas parseadas.

        Returns:
            pd.DataFrame: DataFrame estructurado y optimizado.
        """
        if not entries:
            return pd.DataFrame()

        df = pd.DataFrame({
            'linea':     [e.linea     for e in entries],
            'timestamp': [e.timestamp for e in entries],
            'evento':    [e.evento    for e in entries],
            'nivel':     [e.nivel     for e in entries],
            'proceso':   [e.proceso   for e in entries],
            'pid':       [e.pid       for e in entries],
            'mensaje':   [e.mensaje   for e in entries],
            'notas':     [e.notas     for e in entries],
        })
        
        # Optimizaciones de tipos
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        # Convertir columnas repetitivas a categorías para ahorrar memoria y acelerar filtrado
        for col in ['nivel', 'evento', 'proceso']:
            df[col] = df[col].astype('category')
                
        return df
    @staticmethod
    def format_dataframe_to_text(df: pd.DataFrame) -> str:
        """
        Convierte un DataFrame de logs en una cadena de texto formateada de forma vectorizada.
        
        Args:
            df (pd.DataFrame): DataFrame con las columnas 'linea', 'timestamp', 'nivel', 
                              'proceso', 'evento', 'pid', 'mensaje' y 'notas'.
        
        Returns:
            str: Cadena con todas las líneas formateadas separadas por saltos de línea.
        """
        if df.empty:
            return ""

        try:
            # Procesamiento vectorizado para máxima velocidad
            if pd.api.types.is_datetime64_any_dtype(df['timestamp']):
                formatted_ts = df['timestamp'].dt.strftime("%Y-%m-%d %H:%M:%S")
            else:
                formatted_ts = df['timestamp'].astype(str)

            pids = df['pid'].fillna("-").astype(str).str.replace(" ", "-", regex=False)
            
            # Notas: agregar coma y espacio solo si existen
            notas = df['notas'].fillna("").astype(str)
            notas_display = notas.apply(lambda x: f", {x}" if x else "")

            mensaje = df['mensaje'].fillna("").astype(str)
            evento = df['evento'].fillna("").astype(str)
            proceso = df['proceso'].fillna("").astype(str)
            nivel = df['nivel'].fillna("").astype(str)

            lines_series = (
                "#" + df['linea'].astype(str) + " " +
                "[" + formatted_ts + "] " +
                "[" + nivel + "] " +
                "[" + proceso + "] " +
                evento + ", " +
                pids + ", " +
                "\"" + mensaje + "\"" +
                notas_display
            )
            return "\n".join(lines_series)
        except Exception as e:
            logger.error(f"Error en formateo vectorizado: {e}")
            # Fallback simple si falla la vectorización
            lines = []
            for _, row in df.iterrows():
                ts_str = str(row['timestamp'])
                pid_str = str(row['pid']) if pd.notna(row['pid']) else "-"
                notas_str = f", {row['notas']}" if row['notas'] else ""
                entry_str = (
                    f"#{row['linea']} [{ts_str}] [{row['nivel']}] [{row['proceso']}] "
                    f"{row['evento']}, {pid_str}, \"{row['mensaje']}\"{notas_str}"
                )
                lines.append(entry_str)
            return "\n".join(lines)
