# Directiva de pre-commit / CI: ingeniería sin habilitación operativa

Versión: 1.1 · Fecha: 2026-10-01 · Estado: control local acotado instalado; workflow preparado, integración remota pendiente.

## Objetivo y alcance

Aplicar [OPERATIONAL_STATE.md](../OPERATIONAL_STATE.md). Un check favorable sólo significa conformidad de ingeniería del snapshot revisado: nunca PASS de FASE61/M0, permiso de investigación, despliegue de runners ni autorización LIVE.

El pre-commit es una ayuda local eludible; CI debe ser obligatorio mediante protección de la rama. Esa protección debe configurarse y verificarse separadamente: no está acreditada por este documento.

## Reglas de admisión

1. Validar el snapshot staged en pre-commit y el commit exacto en un checkout aislado de CI; no usar archivos unstaged para justificar el commit.
2. Rechazar tareas de alfa, optimización, backtesting/replay evaluativo o scraping/descarga, incluidas tareas mixtas o renombradas. Inspeccionar también scripts de lanzamiento, hooks, YAML y timers. Búsquedas de texto son auxiliares: no sustituyen revisión de alcance ni aislamiento.
3. Exigir SPEC aprobada y allowlist de cambios para código protegido. Rechazar debilitamiento de bloqueos, exposición de secretos y alteraciones de evidencia sellada. Actualizaciones legítimas append-only requieren su proceso formal específico, no excepciones tácitas.
4. Comparar metadata/código histórico permitido contra una baseline confiable de la rama protegida o evidencia previamente auditada. No confiar únicamente en hashes o aprobaciones que el mismo cambio sustituya. Nunca abrir/hash RAW, holdout, credenciales o bases productivas para este check.
5. Usar dependencias preinstaladas y verificadas, sin auto-install, red, secretos ni montajes de mercado. Si faltan recursos, fallar; no descargarlos para completar el check.
6. Ejecutar sólo suites allowlisted de ingeniería. No usar `--include-historical`, una suite global, pipelines de investigación ni comandos del harness histórico como autoridad actual.

## Checks mínimos y semántica

| Check | Condición necesaria |
| --- | --- |
| Alcance | Cambios exclusivamente de ingeniería, autorizados; ninguna acción prohibida introducida. |
| Preservación | Fuentes protegidas y baseline coinciden; linaje histórico y excepciones formales conservados. |
| Regresión | Suite sintética allowlisted termina con exit 0; ninguna prueba actual se omite sin justificación revisada. |
| Incidente | Snapshot preservado verificado; exposición confirmada; operaciones/bytes exactos UNKNOWN. |
| Barrera vigente | Verificadores sucesores devuelven BLOCKED por HOLDOUT_EXPOSURE_CONFIRMED. |
| Autoridad | Sin gate nuevo, sin promoción, sin nuevos runs; flags declarados LIVE siguen false. Runtime no verificado permanece UNKNOWN. |

Un rechazo por metadata ausente, hash distinto o excepción inesperada mantiene el bloqueo operativo, pero **no** satisface la prueba positiva de integridad del incidente: el check de ingeniería debe fallar.

## Comprobación reproducible actual

Ejemplo PowerShell para el futuro hook/job, con dependencias ya disponibles. No constituye una instalación ni cubre por sí solo admisión de cambios o aislamiento:

```powershell
$ErrorActionPreference = 'Stop'

& python -B -m pytest -q -p no:cacheprovider tests/test_holdout_evidence_guard.py
if ($LASTEXITCODE -ne 0) { throw 'ENGINEERING_REGRESSION_FAILED' }

$ciOutput = & python -B scripts/run_m0_registry_verifier.py
$ciExit = $LASTEXITCODE
if ($ciExit -ne 1) { throw 'EXPECTED_OPERATIONAL_BLOCK_MISSING' }

$ciState = ($ciOutput -join "`n") | ConvertFrom-Json
if (
    $ciState.status -cne 'BLOCKED' -or
    $ciState.formal_gate_status -cne 'BLOCKED' -or
    $ciState.certification_effect -cne 'NONE' -or
    @($ciState.errors).Count -ne 1 -or
    @($ciState.errors)[0] -cne 'HOLDOUT_EXPOSURE_CONFIRMED' -or
    $ciState.holdout_evidence.incident_evidence_status -cne 'VERIFIED_PRESERVED_SNAPSHOT' -or
    $ciState.holdout_evidence.exact_historical_read_operations -cne 'UNKNOWN' -or
    $ciState.holdout_evidence.exact_historical_holdout_bytes_read -cne 'UNKNOWN' -or
    $ciState.holdout_evidence.canonical_zero_counters_are_current_proof -isnot [bool] -or
    $ciState.holdout_evidence.canonical_zero_counters_are_current_proof -cne $false
) { throw 'OPERATIONAL_EVIDENCE_INVALID' }

Write-Output 'ENGINEERING_CHECK_OK; OPERATIONAL_EXECUTION_BLOCKED'
```

Exit 1 del verificador actual es el resultado operativo esperado, no una autorización y no un exit exitoso genérico. El job sólo acepta ese caso después de comprobar contenido y procedencia; nunca normaliza todos los códigos no cero como éxito.

Los códigos 0/10/20/30 propuestos para el futuro diagnóstico unificado no sustituyen los códigos actuales. No existe todavía un comando implementado `operational-status` que pueda utilizarse como requisito de CI.

## Revisión e integración pendientes

La integración local corresponde a `SPEC-ENGINEERING-GIT-CI-BOOTSTRAP-001`: checker y manifest confiables fuera del candidato, allowlist congelada, comprobación staged/tree, regresiones sintéticas y evidencia de bloqueo. Véase [Git/GitHub](GITHUB_ENGINEERING_SETUP.md) para ejecución y límites. El ejemplo anterior es diagnóstico auxiliar; el hook real no aprueba a partir del worktree.

Quedan pendientes activación remota autorizada, dependencias offline del runner, aislamiento global y protección de rama. Evidencia independiente debe ligar commit, política, hashes y salidas de tests. No se considera esta preparación equivalente a CI obligatorio ni al checklist P0 completo.

No hay auto-remediación: el check no cambia flags, no cierra incidentes, no reescribe recibos, no borra datasets y no inicia procesos del bot. Un error bloquea la integración hasta revisión explícita; completar este control no levanta STOP_PERMANENT_DEVELOPMENT.
