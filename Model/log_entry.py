from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class LogEntry:
    """
    Representa una entrada individual estructurada de un archivo de log.

    Contiene todos los campos parseados de una línea del RTPDumpLog, incluyendo
    metadatos (línea, timestamp, nivel) y el contenido del mensaje.
    """
    linea: int
    timestamp: datetime
    evento: str
    nivel: str
    proceso: str
    pid: Optional[str]
    mensaje: str
    notas: str

    def __str__(self) -> str:
        """Formato legible para imprimir en consola y exportar."""
        formatted_timestamp = self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        
        # Handle PID: display "PID: XXXX" or "PID: -" if empty
        pid_display = f"PID: {self.pid}" if self.pid else "PID: -"
        
        # Construct the string based on the desired format
        # #N_Linea [Fecha Hora] [nivel] [proceso] Evento: XXXX, PID: XXXX, Mensaje: "        ", notas: XXXXXX
        return (f"#{self.linea} "
                f"[{formatted_timestamp}] "
                f"[{self.nivel}] "
                f"[{self.proceso}] "
                f"Evento: {self.evento}, "
                f"{pid_display}, "
                f"Mensaje: \"{self.mensaje}\", "
                f"notas: {self.notas}")
