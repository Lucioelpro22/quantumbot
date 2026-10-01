# Estado operativo de QuantumBot

Versión: 1.0 · Fecha: 2026-10-01 · Alcance: gobernanza operativa e ingeniería.

## 1. Historia no equivale a permiso actual

Los certificados y gates `PASS` anteriores se conservan como registros históricos inmutables, ligados a sus fechas, fuentes, versiones y alcance. No autorizan ejecución, investigación ni LIVE y no se reescriben para representar el estado actual.

La exposición confirmada del holdout invalida su uso como muestra independiente en este workflow. Repetir el análisis, limitar un análisis posterior a DEVELOPMENT o cerrar administrativamente el incidente no reproduce las condiciones originales de no exposición. Esa certificación de independencia no es recuperable con el mismo holdout.

No se declara que toda prueba técnica pasada sea irreproducible: sus cálculos o tests sintéticos pueden tener reproducibilidad acotada. Lo que no puede reproducirse es una validación independiente basada en datos ya expuestos. Los metadatos históricos `UNTOUCHED` y cero accesos no prueban ausencia actual de exposición; los contadores históricos exactos de operaciones y bytes permanecen `UNKNOWN`.

## 2. Disposición vigente

| Indicador | Estado efectivo |
| --- | --- |
| HOLDOUT | EXPOSED / CONTAMINATED; inadmisible para validación independiente. |
| FASE61 / M0 | LOCKED / BLOCKED por exposición y aceptación formal pendiente. |
| RESEARCH PIPELINE | HALTED; cero estrategias validadas; STOP_PERMANENT_DEVELOPMENT. |
| LIVE TRADING | HARD-LOCKED por política; permiso declarado deshabilitado. |

La denegación por política no demuestra que un proceso activo haya sido inspeccionado. Sin evidencia fresca y verificable, sus flags de runtime son `UNKNOWN`. El guard actual cubre las entradas sucesoras, no un sandbox global ni toda invocación del harness histórico.

## 3. Prohibición de nuevos runs

Queda prohibido iniciar, reanudar, programar o incorporar a CI cualquier run de generación de alfa, optimización de parámetros, backtesting, replay evaluativo o scraping/descarga de mercado. DEMO, PAPER, SHADOW y la etiqueta “ingeniería” no son excepciones cuando la tarea realiza esas actividades.

No se reemplaza el holdout para eludir el bloqueo, no se habilita HYP-21 y no se reinicia el conteo vitalicio de 20 hipótesis. La exposición es un bloqueo adicional: incluso un eventual dataset nuevo no levantaría STOP_PERMANENT_DEVELOPMENT ni otras invariantes vigentes.

Sólo se permite preparación de ingeniería con metadata autorizada, fixtures sintéticos y transportes simulados. Cada modificación requiere el alcance aprobado correspondiente; no se ejecutan órdenes ni se alteran evidencia sellada, credenciales o bases productivas.

## 4. Checklist previo de ingeniería

Antes de elevar una propuesta formal de nueva recolección o investigación debe existir evidencia y auditoría independiente de todos estos puntos:

- [ ] P0: denegación de capacidades en entradas, clientes directos y transporte, sin habilitación por flags o argumentos.
- [ ] P0: aislamiento verificable del worker respecto de red, credenciales, datasets contaminados y almacenamiento productivo; cobertura y límites explícitos.
- [ ] P0: regresiones adversariales sintéticas, sin acceso real a mercado ni exchanges, obligatorias en CI.
- [ ] P1: imports/constructores sin efectos externos; diagnóstico separado del motor y de la lógica de mercado.
- [ ] P1: metadata/salida sanitizadas; almacenamiento operativo separado; historial preservado por hashes de fuentes autorizadas.
- [ ] P2: snapshot único para CLI/JSON; procedencia y frescura de runtime; `UNKNOWN` y conflictos nunca interpretados como permiso.
- [ ] P2: logs trazables y métricas exclusivamente de sistema; sin secretos, señales ni evaluación financiera.
- [ ] Evidencia: cambios ligados a SPEC aprobada, tests, revisión independiente y pendientes registrados; sin auto-certificación.
- [ ] CI: preservación de artefactos y rechazo de acciones prohibidas; un check de ingeniería favorable no promueve fases ni habilita LIVE.

La revisión existente acredita el guard sucesor, no el checklist completo. Las barreras globales y la instrumentación de runtime no se consideran terminadas por ese dictamen.

Completar el checklist es necesario para preparación técnica, pero no autoriza una nueva fase. Su elegibilidad debe resolverse por separado y ser compatible con las políticas superiores. Con el stop permanente vigente, no existe autorización para iniciar recolección o investigación.

## 5. Fuentes y control de cambios

Este documento no modifica invariantes ni certificados. Se aplica junto con:

- [HARNESS_POLICY](quantumbot_harness/policies/HARNESS_POLICY.md) y [V2_INVARIANTS](quantumbot_harness/policies/V2_INVARIANTS.json).
- [Incidente de exposición](quantumbot_harness/docs/FASE61_HOLDOUT_EXPOSURE_INCIDENT_001.json).
- [Revisión del guard](quantumbot_harness/docs/FASE61_HOLDOUT_EVIDENCE_GUARD_REVIEW_001.json).
- [Directiva pre-commit / CI](docs/OPERATIONAL_PRECOMMIT_CI_DIRECTIVE.md).

Integración acotada: hook local de snapshot staged instalado con baseline congelada; workflow GitHub preparado, no activado. Remoto, dependencias del runner y protección de rama siguen pendientes. Véase [configuración Git/GitHub](docs/GITHUB_ENGINEERING_SETUP.md). Este control no acredita enforcement global de runtime ni completa el checklist.
