"""
Contiene el texto de ayuda en formato Markdown que se muestra en el diálogo de ayuda de la aplicación.
"""

ES_HELP_TEXT = """
# **Descripción:**

Carga un archivo resultante de un RTPDumpLog de la OSV para analizarlo.
Permitir realizar múltiples filtros para localizar errores y exportar los datos filtrados.  

---

# **Instrucciones de uso:**

- Abre un archivo de log (.txt)
- Puedes ocultar los niveles 'clear'
- Usa el panel lateral para filtrar por: 
  - Fecha y hora (Filtrar por fecha y hora de inicio y fin).
  - Búsqueda por palabras clave: 
    - Múltiples palabras con separadores AND u OR.
    - Búsquedas con Expresiones Regulares (Regex).  
  - Por elementos del log:
    - Nivel. 
    - Evento. 
    - Proceso. 
  - Notas (crea notas automáticas en función de palabras clave preestablecidas en fichero **"notes_config.json"**)
  - Puedes marcar manualmente líneas para posteriormente filtrar por ellas.
- Todos los filtros son acumulativos.
- Una vez filtrados todos los datos necesarios, puedes exportarlos.
---

# **Portapapeles:**

- Puedes seleccionar líneas para posteriormente copiarlas al portapapeles de la siguiente manera:
    - Pulsando sobre una línea del Log.
    - Pulsando sobre el botón **+ Multi** e ir pulsando sobre las líneas deseadas o **Ctrl + Clic**.
    - Pulsando sobre el botón **Rango** e introducir el rango de líneas deseadas o **Shift + Clic**.
    - Pulsando sobre el botón **Todo** o **Ctrl+A** para seleccionar todas las líneas visibles en pantalla.
    - Pulsando sobre el botón **Buscar** o **Ctrl+F** para seleccionar líneas por búsqueda de texto en todo el documento.
- Copiar al portapapeles todas las líneas seleccionadas: Pulsando sobre el botón **Copiar** o **Ctrl+C**.
---

# **Marcar Líneas:**

- Puedes marcar cada una de las líneas de log para filtrar posteriormente por ellas. Para marcarlas:
    - Pulsando en la casilla a la izquierda de cada línea del log.
    - Pulsando el botón de marcar todas las líneas seleccionadas.
    - Pulsando la casilla para marcar todas las líneas de la página actual.
    - Puedes marcar las líneas desde la ventana contextual.
 
---

# **Vista contextual:**

- Haciendo doble clic sobre cualquier línea del Log se abrirá una ventana con las N líneas anteriores y posteriores sin ningún filtro aplicado.
- Puedes modificar el número de líneas a mostrar en la vista contextual en el menú de configuración.
- Puedes marcar líneas dentro de la vista contextual para posteriormente filtrarlas.

---

# **Exportación:**

- El log visible, resultado del filtrado, se puede exportar a archivos con diferentes formatos:
    - CSV
    - TXT
    - Markdown
    - Base de datos SQLITE

---

# **Notas:**

- Puedes crear notas automáticas en función de palabras clave preestablecidas en fichero **"notes_config.json"**

  - El fichero **"notes_config.json"** se encuentra en el directorio de la aplicación. Si no existe, se creará uno por defecto.
  - El fichero **"notes_config.json"** se puede editar con cualquier editor de texto.
  - El fichero **"notes_config.json"** tiene la siguiente estructura:

  ```json
  [
      {
          "keywords": ["keyword1", "keyword2"],
          "text": "text to add"
      }
  ]
  ```

  Donde:
  - **keywords**: Es una lista de palabras clave que se buscarán en el log.
  - **text**: Es el texto que se añadirá al log cuando se encuentren las palabras clave.
  
---

# **Guía de búsqueda y filtrado libre**

Esta guía explica cómo funciona el motor de búsqueda interno de la aplicación y cómo aprovechar las expresiones regulares para encontrar información específica en los logs.

## 1. Búsqueda por Palabras Clave (Regex desactivado)

Cuando la opción de **expresiones regulares** no está marcada, la aplicación procesa tu búsqueda de la siguiente manera:

1. **División por palabras**: El texto que escribes se divide en términos individuales (separados por espacios).
2. **Modo de búsqueda**: Dependiendo del valor del modo de búsqueda (que suele ser "AND" por defecto):
   - **Modo AND**: La línea del log debe contener **todas** las palabras que has escrito, sin importar el orden.
     - *Ejemplo*: `SIP INVITE 5060` mostrará líneas que contengan las tres palabras en cualquier posición.
   - **Modo OR**: La línea del log debe contener **al menos una** de las palabras escritas.
     - *Ejemplo*: `ERROR CRITICAL` mostrará cualquier línea que contenga "ERROR" o que contenga "CRITICAL".
3. **Insensibilidad a mayúsculas**: La búsqueda no distingue entre "error", "Error" o "ERROR".

## 2. Búsqueda con Expresiones Regulares (Regex marcado)

Cuando activas **Regex**, el texto se interpreta como un patrón lógico complejo. 
Algunos ejemplos útiles para el análisis de logs:

### Ejemplos Básicos

- **Líneas que comienzan con una fecha**:  
  `^2026-03`

- **Líneas que terminan con la palabra "failed"**:  
  `failed$`

- **Líneas que contienen "SIP" o "HTTP"**:  
  `SIP|HTTP`

- **Busca el número exacto "5060"**:  
  `\\b5060\\b`  
  *(evita coincidencias como "15060")*

### Ejemplos Avanzados para Logs

- **Direcciones IP**:  
  `\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}`  
  *(Busca cualquier dirección IP estándar)*

- **Códigos de Error (Error seguido de números)**:  
  `Error \\d+`  
  *(Coincide con "Error 404", "Error 500", etc.)*

- **Líneas que NO contienen una palabra**:  
  `^((?!DEBUG).)*$`  
  *(Muestra líneas que no tengan la palabra "DEBUG")*

- **Búsqueda de múltiples palabras en un orden específico**:  
  `Sending.*INVITE.*to`  
  *(Busca líneas donde aparezca "Sending", luego "INVITE" y luego "to", con cualquier cosa en medio)*
"""

EN_HELP_TEXT = """
# **Description:**

Loads an OSV RTPDumpLog output file for analysis.
Allows multiple filters to locate errors and export filtered data.

---

# **Usage Instructions:**

- Open a log file (.txt)
- You can hide 'clear' levels
- Use the sidebar to filter by:
  - Date and time (Filter by start and end date/time).
  - Keyword search:
    - Multiple words with AND or OR separators.
    - Regular Expression (Regex) searches.
  - By log elements:
    - Level.
    - Event.
    - Process.
  - Notes (creates automatic notes based on preset keywords in **"notes_config.json"**)
  - You can manually mark lines to filter by them later.
- All filters are cumulative.
- Once all necessary data is filtered, you can export it.
---

# **Clipboard:**

- You can select lines to copy them to the clipboard as follows:
    - Clicking on a log line.
    - Clicking the **+ Multi** button and selecting desired lines or **Ctrl + Click**.
    - Clicking the **Range** button and entering the desired line range or **Shift + Click**.
    - Clicking the **All** button or **Ctrl+A** to select all lines visible on screen.
    - Clicking the **Search** button or **Ctrl+F** to select lines by text search in the entire document.
- Copy all selected lines to the clipboard: Clicking the **Copy** button or **Ctrl+C**.
---

# **Marking Lines:**

- You can mark each log line to filter by them later. To mark them:
    - Clicking the checkbox to the left of each log line.
    - Clicking the button to mark all selected lines.
    - Clicking the checkbox to mark all lines on the current page.
    - You can mark lines from the context window.

---

# **Context View:**

- Double-clicking on any log line will open a window with the N preceding and following lines without any filter applied.
- You can change the number of lines to show in the context view in the settings menu.
- You can mark lines within the context view to filter them later.

---

# **Export:**

- The visible log, result of filtering, can be exported to files with different formats:
    - CSV
    - TXT
    - Markdown
    - SQLITE database

---

# **Notes:**

- You can create automatic notes based on preset keywords in **"notes_config.json"**

  - The **"notes_config.json"** file is located in the application directory. If it doesn't exist, a default one will be created.
  - The **"notes_config.json"** file can be edited with any text editor.
  - The **"notes_config.json"** file has the following structure:

  ```json
  [
      {
          "keywords": ["keyword1", "keyword2"],
          "text": "text to add"
      }
  ]
  ```

  Where:
  - **keywords**: Is a list of keywords that will be searched for in the log.
  - **text**: Is the text that will be added to the log when keywords are found.

---

# **Search and Free Filtering Guide**

This guide explains how the application's internal search engine works and how to take advantage of regular expressions to find specific information in logs.

## 1. Keyword Search (Regex off)

When the **regular expressions** option is not checked, the application processes your search as follows:

1. **Word splitting**: The text you type is split into individual terms (separated by spaces).
2. **Search mode**: Depending on the search mode value (usually "AND" by default):
   - **Mode AND**: The log line must contain **all** the words you have written, regardless of order.
     - *Example*: `SIP INVITE 5060` will show lines containing all three words in any position.
   - **Mode OR**: The log line must contain **at least one** of the written words.
     - *Example*: `ERROR CRITICAL` will show any line containing "ERROR" or containing "CRITICAL".
3. **Case insensitivity**: The search does not distinguish between "error", "Error", or "ERROR".

## 2. Regular Expression Search (Regex on)

When you activate **Regex**, the text is interpreted as a complex logical pattern.
Some useful examples for log analysis:

### Basic Examples

- **Lines starting with a date**:
  `^2026-03`

- **Lines ending with the word "failed"**:
  `failed$`

- **Lines containing "SIP" or "HTTP"**:
  `SIP|HTTP`

- **Search for exact number "5060"**:
  `\\b5060\\b`
  *(avoids matches like "15060")*

### Advanced Examples for Logs

- **IP Addresses**:
  `\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}`
  *(Searches for any standard IP address)*

- **Error Codes (Error followed by numbers)**:
  `Error \\d+`
  *(Matches "Error 404", "Error 500", etc.)*

- **Lines NOT containing a word**:
  `^((?!DEBUG).)*$`
  *(Shows lines that do not have the word "DEBUG")*

- **Search for multiple words in a specific order**:
  `Sending.*INVITE.*to`
  *(Searches for lines where "Sending" appears, then "INVITE", and then "to", with anything in between)*
"""

def get_help_text(lang: str) -> str:
    """Devuelve el texto de ayuda en el idioma solicitado."""
    if lang == "en":
        return EN_HELP_TEXT
    return ES_HELP_TEXT
