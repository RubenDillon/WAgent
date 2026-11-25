# Flight Watch Agent

Agente local para macOS orientado a **buscar, monitorear, comparar y aprender a consultar tarifas aéreas de forma reproducible**, manteniendo un histórico propio de precios y separando claramente la recolección operativa del aprendizaje/repair mediante LLM.

El proyecto comenzó como un monitor de Almundo y evolucionó hacia una arquitectura multi-provider con Playwright, SQLite, normalización de monedas, Replay reproducible y un worker inteligente basado en Ollama + Granite para aprender o reparar procedimientos de navegación.

## Objetivo actual de prueba

La configuración predeterminada utilizada para recolección y aprendizaje es:

- Origen: `EZE`
- Destino: `FCO`
- Ida: `17/07/2027`
- Regreso: `29/07/2027`
- Pasajeros: `2 adultos`
- Cabina: `Economy`
- Moneda normalizada de trabajo: `USD`
- Intervalo operativo predeterminado: `2 minutos`

## Arquitectura

```text
Flight Watch GUI
   |
   +-- Recolector operativo
   |     +-- Almundo
   |     +-- Aerolíneas Argentinas
   |     +-- futuros providers
   |            |
   |            +--> observations / SQLite
   |
   +-- Inteligencia de compra
   |     +-- mínimo
   |     +-- P10
   |     +-- P25
   |     +-- mediana / P50
   |     +-- P75
   |     +-- clasificación y score
   |
   +-- Replay
   |     +-- proceso Playwright independiente
   |     +-- perfil Chromium UUID independiente
   |
   +-- Learning Worker
         +-- un único LEARN o REPAIR a la vez
         +-- Playwright aislado
         +-- Ollama bajo demanda
         +-- Granite 4.2 8B
         +-- Flight Search Harness
         +-- Semantic Analyzer + form_mapper
         +-- validadores Python
         +-- procedimientos versionados + shadow validation
```

El recolector operativo no debe detenerse mientras el worker inteligente aprende o repara un provider.

## Providers operativos

### Almundo

Provider actualmente estable.

- Construye una búsqueda reproducible.
- Extrae ofertas verificables.
- Guarda precio en USD.
- Alimenta histórico propio.
- Soporta Replay.

### Aerolíneas Argentinas

Provider aprendido durante el desarrollo y actualmente funcional para la búsqueda completa.

Durante las iteraciones se resolvieron, entre otros, estos problemas:

- autocomplete de origen/destino;
- estado React distinto del texto visible del input;
- fechas de ida/vuelta;
- switch de fechas flexibles;
- `DayPicker` interceptando `Buscar vuelos`;
- submit SPA sin cambio inmediato de URL;
- instrumentación de network/XHR/fetch;
- detección de importes que no correspondían al total;
- diferenciación entre promociones, cuotas, asientos/equipaje y tarifa total;
- normalización ARS -> USD mediante BCRA cuando es necesaria.

Un aprendizaje importante es que, cuando el propio sitio permite elegir **Pago en USD**, el procedimiento aprendido debe preferir esa opción antes de convertir desde ARS.

## Moneda y BCRA

Flight Watch trabaja comparativamente en USD.

Cuando un provider sólo entrega ARS:

1. conserva precio y moneda originales;
2. obtiene una única cotización oficial BCRA USD/ARS por fecha publicada;
3. guarda esa cotización en `exchange_rates`;
4. normaliza la observación a USD;
5. conserva en `details` la trazabilidad completa.

Una observación histórica **no se recalcula posteriormente con otro tipo de cambio**.

## Histórico propio e inteligencia de compra

El histórico externo quedó temporalmente fuera del roadmap inmediato. La inteligencia actual se construye con observaciones verificadas por Flight Watch.

Para evitar sesgos, cada provider aporta una muestra comparable por ciclo, no todas las tarjetas de una consulta como si fueran observaciones independientes.

La UI calcula y muestra:

- precio actual;
- mínimo observado;
- P10;
- P25;
- mediana / P50;
- P75;
- máximo;
- cantidad de ciclos;
- días de historial;
- score;
- confianza.

Clasificación inicial:

```text
<= P10          EXCEPCIONAL
P10 - P25       MUY BUENO
P25 - Mediana   BUENO
Mediana - P75   NORMAL
> P75           ALTO
```

Durante las primeras observaciones el estado permanece en `APRENDIENDO`.

## Replay reproducible

Cada observación conserva el objetivo que la generó.

`Reproducir` utiliza la fila seleccionada y abre el provider correspondiente.

Los Replay se ejecutan como procesos independientes y cada uno recibe un perfil Chromium único:

```text
data/browser/replays/<uuid>/
```

Esto permite mantener simultáneamente varias búsquedas abiertas sin colisiones de Playwright ni del `user-data-dir` de Chromium.

Los logs de Replay se guardan bajo:

```text
data/diagnostics/replay/
```

## Aprendizaje y reparación

Esta es la parte actualmente en desarrollo activo.

### Principio

No queremos construir manualmente un scraper con selectores distintos para cada aerolínea.

El objetivo es que un Browser Agent local pueda aprender cómo realizar una búsqueda aérea en un sitio nuevo y reutilizar ese procedimiento posteriormente.

La separación conceptual es:

```text
LLM
  -> descubre / razona / repara

Python + Playwright
  -> observa / ejecuta / valida

SQLite
  -> guarda procedimiento, estado, logs y observaciones verificadas
```

El LLM nunca es la fuente de verdad de un precio.

### Worker separado

Aprendizaje y reparación utilizan un proceso independiente del recolector.

Sólo puede existir **un trabajo pesado activo**:

```text
LEARN activo  -> REPAIR espera
REPAIR activo -> LEARN espera
```

No existe preemption automática del trabajo activo.

El usuario puede poner el sistema en:

```text
Solo recolección
```

En ese modo:

- providers operativos continúan;
- histórico continúa creciendo;
- Replay continúa;
- LEARN/REPAIR no comienzan;
- Ollama no se carga para nuevos trabajos.

### Aprendizaje solicitado por el usuario

El usuario crea únicamente trabajos `LEARN` indicando, por ejemplo:

```text
Provider: Delta
URL: https://www.delta.com/lac/en
```

Por comodidad, Delta y esa URL están actualmente precargados en la UI de aprendizaje.

### Reparación automática

El usuario no crea tareas `REPAIR` manualmente.

El recolector cuenta fallos consecutivos. Luego de varios fallos verificables de un provider previamente operativo, Flight Watch crea una reparación pendiente automáticamente.

La reparación:

- comparte el mismo worker exclusivo de aprendizaje;
- nunca interrumpe un aprendizaje activo;
- puede permanecer en cola si el sistema está en modo Solo recolección;
- debe intentar reconstruir un procedimiento que vuelva a pasar los validadores.

## Ollama lifecycle

Ollama se utiliza sólo para LEARN/REPAIR.

Flujo:

```text
entra job
  -> comprobar /api/tags
  -> si Ollama está apagado, localizar binario
  -> iniciar `ollama serve`
  -> esperar API
  -> resolver modelo local
  -> ejecutar job
  -> mantener Ollama caliente 5 minutos
  -> si entra otro job, reutilizar
  -> si no entra nada, descargar modelo
  -> detener el servidor sólo si Flight Watch lo inició
```

Rutas contempladas para el binario:

```text
PATH
/opt/homebrew/bin/ollama
/usr/local/bin/ollama
/Applications/Ollama.app/Contents/Resources/ollama
```

Actualmente el sistema está utilizando exitosamente:

```text
granite4.2:8b
```

Se ejecuta con `think:false` para el planner de acciones cortas del navegador.

## Flight Search Harness

A partir de la serie 0.13 se incorporó un harness especializado en búsquedas aéreas.

Se instala en:

```text
agent_skills/flight-search-harness/
```

Contiene:

```text
SKILL.md
references/form-semantics.md
references/navigation-patterns.md
references/validation-rules.md
references/aerolineas-lessons.md
```

Su propósito es que Granite no tenga que descubrir desde cero qué significa reservar un vuelo.

### Máquina de estados

```text
LOCATE_FORM
SET_TRIP_TYPE
SET_ORIGIN
SET_DESTINATION
SET_DEPARTURE
SET_RETURN
SET_PASSENGERS
SET_CABIN
SET_CURRENCY
SUBMIT
VALIDATE_RESULTS
EXTRACT_TOTAL
COMPLETE
```

Python determina el estado global; Granite resuelve la variación concreta del sitio.

### Semantic Analyzer

El Browser Agent inspecciona controles HTML/accesibilidad y utiliza evidencias como:

- `id`;
- `name`;
- `type`;
- `placeholder`;
- `aria-label`;
- `aria-labelledby`;
- `autocomplete`;
- label asociado;
- texto cercano;
- `data-*`;
- `href`;
- role;
- valor actual;
- checked/disabled.

Genera hints para:

```text
origin
destination
departure_date
return_date
passengers
adults
cabin
currency
flight_search
site_search
content_navigation
```

## Herramientas de alto nivel

Además de `click`, `fill`, `press`, `wait`, `back` y `restart`, se comenzó a incorporar conocimiento de dominio como herramientas.

### fill_airport

Objetivo:

```text
fill_airport(origin, EZE)
```

El executor debe:

1. localizar un campo editable para el rol;
2. introducir el IATA;
3. esperar autocomplete;
4. localizar una sugerencia que contenga el IATA exacto;
5. seleccionarla;
6. verificar que el componente confirmó el aeropuerto;
7. hacer blur;
8. sólo entonces avanzar de estado.

Esto surgió porque escribir `EZE` visualmente no siempre compromete el estado interno de React.

## Lo probado con Delta

Delta se está utilizando deliberadamente como proveedor desconocido para probar si el agente aprende sin código específico de Delta.

URL de prueba:

```text
https://www.delta.com/lac/en
```

Los experimentos han permitido identificar varios problemas genéricos del Browser Agent.

### 1. Search general vs. Search flights

Granite inicialmente abrió el Search del encabezado y llegó a escribir allí el objetivo del viaje.

Se incorporaron:

- `site_search` semantic hint;
- guard contra `/sitesearch`;
- acciones `back` y `restart`;
- rollback antes de otra inferencia del LLM.

### 2. Modales superpuestos

Delta puede presentar simultáneamente:

- Search popup;
- date picker;
- Privacy Settings;
- otros dialogs.

El executor detecta overlays que interceptan clicks y devuelve el error al planner en vez de utilizar force-click ciegamente.

### 3. Elementos invisibles

El observador utiliza geometría, estilo y `elementFromPoint` para no exponer al LLM controles que existen en el DOM pero no son realmente accionables.

### 4. Loops

Se añadieron:

- firmas del estado del navegador;
- conteo de visitas;
- acciones sin progreso;
- rollback/restart;
- rechazo de fills vacíos;
- detector de repetición de acciones.

### 5. Contexto demasiado grande

Granite llegó a producir HTTP 400 cuando la observación acumulaba demasiados controles/modales.

Se redujo el contexto enviado y se agregó retry con representación mínima.

### 6. Thinking de Granite

Granite 4.2 devolvía `message.content` vacío porque Ollama exponía el razonamiento en `message.thinking`.

Para este planner se utiliza:

```json
"think": false
```

### 7. JSON inválido/vacío

Se agregó parser tolerante a:

- JSON puro;
- fenced JSON;
- texto + JSON;
- reparación de formato mediante segunda llamada.

### 8. Route Map / contenido promocional

Granite llegó a interpretar `Book Your Next Trip` como entrada al booking, pero navegó al mapa mundial de destinos.

Se está incorporando `content_navigation` basado, entre otros, en `href` para distinguir:

```text
route-map
find-your-destination
travel-planning-center
destinations
explore
```

El objetivo es bloquear esos caminos durante `LOCATE_FORM` antes de que el navegador abandone la página de booking.

### Estado actual del aprendizaje (0.14)

El aprendizaje se rediseñó: **Python decide y ejecuta; el LLM sólo desambigua**. El LLM nunca es fuente de verdad del precio.

Flujo (`learning_agent.run_learning`):

1. `browser_learning.observe()` ve shadow DOM, iframes, controles fuera de viewport y `<option>` de los select; `dismiss_banners()` resuelve cookies en Python.
2. `semantic_forms` anota roles (origen, destino, fechas, pasajeros, moneda, `site_search`, `content_navigation`...) y `role_state` alimenta `flight_harness.determine_state` (13 estados reales).
3. `form_mapper` mapea el formulario con heurísticas; **una** llamada LLM (acotada a candidatos dudosos y verificada por Python) sólo si hay ambigüedad.
4. `auto_action` ejecuta determinísticamente origen/destino (`fill_airport`), fechas (`fill_date`: nativo, tipeado o calendario), selects, steppers, submit y el switch nativo "Pago en USD". El planner LLM (`ollama_planner`, `num_ctx` 16384, contexto compactado por estado) sólo se usa si no hay acción determinista.
   - `fill_airport` sólo confirma si el input ya no contiene únicamente el IATA tipeado (autosuggest tipo React Autosuggest, p. ej. Aerolíneas, exige elegir la opción). Si el click no elige, reintenta por teclado (`ArrowDown`+`Enter`).
5. `navigation_guard.LoopGuard` + `off_task`/`blocked_click` impiden route-map, buscador del sitio y bucles (back/restart).
6. `validators.validate_results` decide el éxito (ruta, fechas, pasajeros, moneda, base del precio); rechaza cuotas, equipaje, asientos, pre/post partida y "desde".
7. `procedure` guarda un JSON versionado en `data/procedures/<provider>/vN.json` con locators múltiples y parámetros (`origin`, `destination`, `departure`, `return_date`).
8. `learning_worker` hace **shadow validation**: reejecuta el procedimiento sin LLM en un perfil Chromium limpio. Si no es reproducible queda `candidate_unverified` y el job `FAILED`.

Un aprendizaje exitoso produce como máximo un **procedimiento candidato**: no se promueve a producción ni escribe tarifas en el histórico.

Iteración sin el sitio real (Fase 1):

- `Recorder` graba cada paso en `data/diagnostics/learning/job_<id>/step_NN.json|html`.
- `python -m flight_watch.learning_replay data/diagnostics/learning/job_<id>` reproduce offline el estado/acción determinista con el código actual.
- `tests/fakesites.py` simula dos sitios (A: fecha escrita + selects; B: tab + calendario + stepper + ARS con switch USD) con trampas (cookies, header-search, route-map). `tests/fixtures/` contiene HTML real de Aerolíneas.

Variables de entorno: `FLIGHT_WATCH_NUM_CTX` (16384), `FLIGHT_WATCH_MODEL` (granite4.2:8b), `FLIGHT_WATCH_HEADLESS=1`, `FLIGHT_WATCH_CHANNEL=chrome` (usar Chrome instalado si Chromium es detectado).

Tests: `.venv/bin/python -m pytest -q` (`pytest.ini` define `pythonpath = src tests`).

Pendiente: probar contra Delta real, aprender el endpoint XHR de ofertas (Fase 3) y promover candidatos a providers operativos.

## Arquitectura

```text
Flight Watch GUI
   |
   +-- Recolector operativo
   |     +-- Almundo
   |     +-- Aerolíneas Argentinas
   |     +-- futuros providers
   |            |
   |            +--> observations / SQLite
   |
   +-- Inteligencia de compra
   |     +-- mínimo
   |     +-- P10
   |     +-- P25
   |     +-- mediana / P50
   |     +-- P75
   |     +-- clasificación y score
   |
   +-- Replay
   |     +-- proceso Playwright independiente
   |     +-- perfil Chromium UUID independiente
   |
   +-- Learning Worker
         +-- un único LEARN o REPAIR a la vez
         +-- Playwright aislado
         +-- Ollama bajo demanda
         +-- Granite 4.2 8B
         +-- Flight Search Harness
         +-- Semantic Analyzer + form_mapper
         +-- validadores Python
         +-- procedimientos versionados + shadow validation
```

El recolector operativo no debe detenerse mientras el worker inteligente aprende o repara un provider.

## Providers operativos

### Almundo

Provider actualmente estable.

- Construye una búsqueda reproducible.
- Extrae ofertas verificables.
- Guarda precio en USD.
- Alimenta histórico propio.
- Soporta Replay.

### Aerolíneas Argentinas

Provider aprendido durante el desarrollo y actualmente funcional para la búsqueda completa.

Durante las iteraciones se resolvieron, entre otros, estos problemas:

- autocomplete de origen/destino;
- estado React distinto del texto visible del input;
- fechas de ida/vuelta;
- switch de fechas flexibles;
- `DayPicker` interceptando `Buscar vuelos`;
- submit SPA sin cambio inmediato de URL;
- instrumentación de network/XHR/fetch;
- detección de importes que no correspondían al total;
- diferenciación entre promociones, cuotas, asientos/equipaje y tarifa total;
- normalización ARS -> USD mediante BCRA cuando es necesaria.

Un aprendizaje importante es que, cuando el propio sitio permite elegir **Pago en USD**, el procedimiento aprendido debe preferir esa opción antes de convertir desde ARS.

## Moneda y BCRA

Flight Watch trabaja comparativamente en USD.

Cuando un provider sólo entrega ARS:

1. conserva precio y moneda originales;
2. obtiene una única cotización oficial BCRA USD/ARS por fecha publicada;
3. guarda esa cotización en `exchange_rates`;
4. normaliza la observación a USD;
5. conserva en `details` la trazabilidad completa.

Una observación histórica **no se recalcula posteriormente con otro tipo de cambio**.

## Histórico propio e inteligencia de compra

El histórico externo quedó temporalmente fuera del roadmap inmediato. La inteligencia actual se construye con observaciones verificadas por Flight Watch.

Para evitar sesgos, cada provider aporta una muestra comparable por ciclo, no todas las tarjetas de una consulta como si fueran observaciones independientes.

La UI calcula y muestra:

- precio actual;
- mínimo observado;
- P10;
- P25;
- mediana / P50;
- P75;
- máximo;
- cantidad de ciclos;
- días de historial;
- score;
- confianza.

Clasificación inicial:

```text
<= P10          EXCEPCIONAL
P10 - P25       MUY BUENO
P25 - Mediana   BUENO
Mediana - P75   NORMAL
> P75           ALTO
```

Durante las primeras observaciones el estado permanece en `APRENDIENDO`.

## Replay reproducible

Cada observación conserva el objetivo que la generó.

`Reproducir` utiliza la fila seleccionada y abre el provider correspondiente.

Los Replay se ejecutan como procesos independientes y cada uno recibe un perfil Chromium único:

```text
data/browser/replays/<uuid>/
```

Esto permite mantener simultáneamente varias búsquedas abiertas sin colisiones de Playwright ni del `user-data-dir` de Chromium.

Los logs de Replay se guardan bajo:

```text
data/diagnostics/replay/
```

## Aprendizaje y reparación

Esta es la parte actualmente en desarrollo activo.

### Principio

No queremos construir manualmente un scraper con selectores distintos para cada aerolínea.

El objetivo es que un Browser Agent local pueda aprender cómo realizar una búsqueda aérea en un sitio nuevo y reutilizar ese procedimiento posteriormente.

La separación conceptual es:

```text
LLM
  -> descubre / razona / repara

Python + Playwright
  -> observa / ejecuta / valida

SQLite
  -> guarda procedimiento, estado, logs y observaciones verificadas
```

El LLM nunca es la fuente de verdad de un precio.

### Worker separado

Aprendizaje y reparación utilizan un proceso independiente del recolector.

Sólo puede existir **un trabajo pesado activo**:

```text
LEARN activo  -> REPAIR espera
REPAIR activo -> LEARN espera
```

No existe preemption automática del trabajo activo.

El usuario puede poner el sistema en:

```text
Solo recolección
```

En ese modo:

- providers operativos continúan;
- histórico continúa creciendo;
- Replay continúa;
- LEARN/REPAIR no comienzan;
- Ollama no se carga para nuevos trabajos.

### Aprendizaje solicitado por el usuario

El usuario crea únicamente trabajos `LEARN` indicando, por ejemplo:

```text
Provider: Delta
URL: https://www.delta.com/lac/en
```

Por comodidad, Delta y esa URL están actualmente precargados en la UI de aprendizaje.

### Reparación automática

El usuario no crea tareas `REPAIR` manualmente.

El recolector cuenta fallos consecutivos. Luego de varios fallos verificables de un provider previamente operativo, Flight Watch crea una reparación pendiente automáticamente.

La reparación:

- comparte el mismo worker exclusivo de aprendizaje;
- nunca interrumpe un aprendizaje activo;
- puede permanecer en cola si el sistema está en modo Solo recolección;
- debe intentar reconstruir un procedimiento que vuelva a pasar los validadores.

## Ollama lifecycle

Ollama se utiliza sólo para LEARN/REPAIR.

Flujo:

```text
entra job
  -> comprobar /api/tags
  -> si Ollama está apagado, localizar binario
  -> iniciar `ollama serve`
  -> esperar API
  -> resolver modelo local
  -> ejecutar job
  -> mantener Ollama caliente 5 minutos
  -> si entra otro job, reutilizar
  -> si no entra nada, descargar modelo
  -> detener el servidor sólo si Flight Watch lo inició
```

Rutas contempladas para el binario:

```text
PATH
/opt/homebrew/bin/ollama
/usr/local/bin/ollama
/Applications/Ollama.app/Contents/Resources/ollama
```

Actualmente el sistema está utilizando exitosamente:

```text
granite4.2:8b
```

Se ejecuta con `think:false` para el planner de acciones cortas del navegador.

## Flight Search Harness

A partir de la serie 0.13 se incorporó un harness especializado en búsquedas aéreas.

Se instala en:

```text
agent_skills/flight-search-harness/
```

Contiene:

```text
SKILL.md
references/form-semantics.md
references/navigation-patterns.md
references/validation-rules.md
references/aerolineas-lessons.md
```

Su propósito es que Granite no tenga que descubrir desde cero qué significa reservar un vuelo.

### Máquina de estados

```text
LOCATE_FORM
SET_TRIP_TYPE
SET_ORIGIN
SET_DESTINATION
SET_DEPARTURE
SET_RETURN
SET_PASSENGERS
SET_CABIN
SET_CURRENCY
SUBMIT
VALIDATE_RESULTS
EXTRACT_TOTAL
COMPLETE
```

Python determina el estado global; Granite resuelve la variación concreta del sitio.

### Semantic Analyzer

El Browser Agent inspecciona controles HTML/accesibilidad y utiliza evidencias como:

- `id`;
- `name`;
- `type`;
- `placeholder`;
- `aria-label`;
- `aria-labelledby`;
- `autocomplete`;
- label asociado;
- texto cercano;
- `data-*`;
- `href`;
- role;
- valor actual;
- checked/disabled.

Genera hints para:

```text
origin
destination
departure_date
return_date
passengers
adults
cabin
currency
flight_search
site_search
content_navigation
```

## Herramientas de alto nivel

Además de `click`, `fill`, `press`, `wait`, `back` y `restart`, se comenzó a incorporar conocimiento de dominio como herramientas.

### fill_airport

Objetivo:

```text
fill_airport(origin, EZE)
```

El executor debe:

1. localizar un campo editable para el rol;
2. introducir el IATA;
3. esperar autocomplete;
4. localizar una sugerencia que contenga el IATA exacto;
5. seleccionarla;
6. verificar que el componente confirmó el aeropuerto;
7. hacer blur;
8. sólo entonces avanzar de estado.

Esto surgió porque escribir `EZE` visualmente no siempre compromete el estado interno de React.

## Lo probado con Delta

Delta se está utilizando deliberadamente como proveedor desconocido para probar si el agente aprende sin código específico de Delta.

URL de prueba:

```text
https://www.delta.com/lac/en
```

Los experimentos han permitido identificar varios problemas genéricos del Browser Agent.

### 1. Search general vs. Search flights

Granite inicialmente abrió el Search del encabezado y llegó a escribir allí el objetivo del viaje.

Se incorporaron:

- `site_search` semantic hint;
- guard contra `/sitesearch`;
- acciones `back` y `restart`;
- rollback antes de otra inferencia del LLM.

### 2. Modales superpuestos

Delta puede presentar simultáneamente:

- Search popup;
- date picker;
- Privacy Settings;
- otros dialogs.

El executor detecta overlays que interceptan clicks y devuelve el error al planner en vez de utilizar force-click ciegamente.

### 3. Elementos invisibles

El observador utiliza geometría, estilo y `elementFromPoint` para no exponer al LLM controles que existen en el DOM pero no son realmente accionables.

### 4. Loops

Se añadieron:

- firmas del estado del navegador;
- conteo de visitas;
- acciones sin progreso;
- rollback/restart;
- rechazo de fills vacíos;
- detector de repetición de acciones.

### 5. Contexto demasiado grande

Granite llegó a producir HTTP 400 cuando la observación acumulaba demasiados controles/modales.

Se redujo el contexto enviado y se agregó retry con representación mínima.

### 6. Thinking de Granite

Granite 4.2 devolvía `message.content` vacío porque Ollama exponía el razonamiento en `message.thinking`.

Para este planner se utiliza:

```json
"think": false
```

### 7. JSON inválido/vacío

Se agregó parser tolerante a:

- JSON puro;
- fenced JSON;
- texto + JSON;
- reparación de formato mediante segunda llamada.

### 8. Route Map / contenido promocional

Granite llegó a interpretar `Book Your Next Trip` como entrada al booking, pero navegó al mapa mundial de destinos.

Se está incorporando `content_navigation` basado, entre otros, en `href` para distinguir:

```text
route-map
find-your-destination
travel-planning-center
destinations
explore
```

El objetivo es bloquear esos caminos durante `LOCATE_FORM` antes de que el navegador abandone la página de booking.

### Estado actual del aprendizaje

El aprendizaje todavía es **experimental**.

El sistema ya ha demostrado que puede:

- iniciar/detener Ollama bajo demanda;
- utilizar Granite 4.2 8B;
- abrir un sitio desconocido;
- observar controles interactivos;
- producir acciones en segundos;
- detectar overlays;
- registrar errores del executor;
- reobservar y replanificar;
- generar logs persistentes;
- trabajar con una máquina de estados y un harness de dominio.

Todavía estamos endureciendo:

- localización fiable del formulario real;
- distinción entre booking y navegación de contenido;
- autocompletes de aeropuerto;
- progreso semántico entre estados;
- promoción de un procedimiento aprendido a producción.

Actualmente un aprendizaje exitoso produce como máximo un **procedimiento candidato**. Todavía no se promueve automáticamente como provider operativo ni escribe nuevas tarifas en el histórico.

## Logs y diagnósticos

### Recolector

La UI mantiene un log en tiempo real.

### Aprendizaje

Cada trabajo persiste eventos en SQLite y además exporta:

```text
data/diagnostics/learning/job_<id>.log
```

### Learning Worker

Log técnico:

```text
data/diagnostics/learning_worker.log
```

### Providers

Los providers experimentales pueden guardar:

```text
data/diagnostics/*.png
data/diagnostics/*.html
data/diagnostics/*.json
```

Esto permite diagnosticar modificaciones del frontend sin contaminar la base con precios dudosos.

## Seguridad e integridad de datos

Flight Watch actualmente sigue estas reglas:

- no compra boletos automáticamente;
- no ingresa tarjetas;
- no completa documentos personales;
- no intenta resolver/bypassear CAPTCHA;
- no acepta precios sin moneda/contexto;
- no considera promociones o adicionales como total;
- no permite que el LLM inserte directamente un precio en SQLite;
- Python valida antes de guardar observaciones;
- Replay entrega el navegador al usuario para continuar manualmente.

## Instalación básica

```bash
chmod +x instalar.sh run.sh
./instalar.sh
./run.sh
```

Los scripts son relocatables y calculan la raíz a partir de su propia ubicación.

## Roadmap inmediato

1. Estabilizar `Flight Search Harness` con Delta.
2. Lograr que un aprendizaje complete EZE -> FCO de punta a punta.
3. Shadow validation del procedimiento candidato en varias sesiones limpias.
4. Guardar/promover procedimientos versionados.
5. Probar un segundo proveedor realmente desconocido sin código específico.
6. Usar el mismo mecanismo para reparación automática de un provider roto.
7. Incorporar LATAM/Despegar mediante aprendizaje, no implementándolos manualmente.
8. Después: alertas macOS/Pushover/iPhone/Apple Watch.
9. Separar finalmente el recolector operativo como daemon/launchd para que continúe aunque la GUI esté cerrada.
