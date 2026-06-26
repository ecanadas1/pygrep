# Guía de Búsqueda en DumpLog

Esta guía explica cómo funciona el motor de búsqueda interno de la aplicación y cómo aprovechar las expresiones regulares para encontrar información específica en los logs.

## 1. Búsqueda por Palabras Clave (Regex desactivado)

Cuando la opción de **expresiones regulares** no está marcada, la aplicación procesa tu búsqueda de la siguiente manera:

1. **División por palabras**: El texto que escribes se divide en términos individuales (separados por espacios).
2. **Modo de búsqueda**: Dependiendo del valor de `search_mode` (que suele ser "AND" por defecto):
   - **Modo AND**: La línea del log debe contener **todas** las palabras que has escrito, sin importar el orden.
     - *Ejemplo*: `SIP INVITE 5060` mostrará líneas que contengan las tres palabras en cualquier posición.
   - **Modo OR**: La línea del log debe contener **al menos una** de las palabras escritas.
     - *Ejemplo*: `ERROR CRITICAL` mostrará cualquier línea que contenga "ERROR" o que contenga "CRITICAL".
3. **Insensibilidad a mayúsculas**: La búsqueda no distingue entre "error", "Error" o "ERROR".

---

## 2. Búsqueda con Expresiones Regulares (Regex marcado)

Cuando activas **Regex**, el texto se interpreta como un patrón lógico complejo. Aquí tienes algunos ejemplos útiles para el análisis de logs:

### Ejemplos Básicos

- **Líneas que comienzan con una fecha**:
  `^2026-03`

- **Líneas que terminan con la palabra "failed"**:
  `failed$`

- **Líneas que contienen ""SIP o "HTTP"
  `SIP|HTTP`

- **Busca el número exacto "5060" (evita coincidencias como "15060")**:
  `\b5060\b`

### Ejemplos Avanzados para Logs

- **Direcciones IP**:
  `\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}`
  *(Busca cualquier dirección IP estándar)*

- **Códigos de Error (Error seguido de números)**:
  `Error \d+`
  *(Coincide con "Error 404", "Error 500", etc.)*

- **Líneas que NO contienen una palabra**:
  `^((?!DEBUG).)*$`
  *(Muestra líneas que no tengan la palabra "DEBUG")*

- **Búsqueda de múltiples palabras en un orden específico**:
  `Sending.*INVITE.*to`
  *(Busca líneas donde aparezca "Sending", luego "INVITE" y luego "to", con cualquier cosa en medio)*

> [!TIP]
> Si una búsqueda regex es inválida (por ejemplo, dejas un paréntesis abierto como `(`), la aplicación ignorará el filtro para evitar errores, informándolo en los logs internos.
