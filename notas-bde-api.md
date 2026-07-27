# Banco de España — Notas de exploración de API

## API REST documentada

El Banco de España tiene un servicio web JSON documentado en:
https://www.bde.es/webbe/es/estadisticas/recursos/api-estadisticas-bde.html

### Endpoints identificados

| Endpoint | URL |
|---|---|
| Último dato | `https://www.bde.es/bierest/resources/srdatosapp/listaSeries?idioma=es&series={CODIGO}` |
| Listado de series | Mismo endpoint, sin `series` o con `code` |
| BIEST (explorador) | https://www.bde.es/webbde/es/estadis/be/inf/estadisticas/buscador/ |

### Problemas encontrados

1. **WAF / CloudFlare**: El endpoint `bierest/resources/srdatosapp/listaSeries` devuelve HTTP 400 con
   bloqueo de seguridad. La petición necesita headers específicos (User-Agent, Accept).
2. **Encoding**: El endpoint devuelve datos con problemas de codificación Latin-1/UTF-8.
3. **Accordion JS**: La página de documentación usa JavaScript que no se expande en el headless browser.
4. **Sin API key pública**: No se requiere autenticación pero hay rate limiting.

### Series de interés

Basado en los datos mostrados en la página principal de estadísticas:

| Serie | Descripción | Código probable |
|---|---|---|
| €STR | Tipo de interés a corto plazo | `ESTR` o similar |
| Euribor 1 año | Euribor a 12 meses | `EURIBOR_12M` o `E1` |
| USD/EUR | Tipo de cambio dólar/euro | `EXR_USD_EUR` |
| Deuda PDE | Deuda pública (% PIB) | `PDE_DEBT` o similar |
| Depósitos hogares | Depósitos de hogares (TVA) | `DEP_HH` |

### Próximos pasos

1. Probar el endpoint con `curl` desde el navegador (copiar cookies de sesión)
2. Probar la aplicación BIEST directamente para encontrar códigos de serie
3. Si el WAF es demasiado restrictivo, usar SDMX global (ECB SDW) como alternativa
   que cubre datos del BDE sin autenticación
