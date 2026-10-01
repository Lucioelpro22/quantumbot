# Corrección de integridad de evidencia del holdout — 001

SPEC de implementación: SPEC-FASE61-HOLDOUT-EVIDENCE-GUARD-001, autorizada por el usuario para esta corrección acotada. No modifica ni aprueba la SPEC prospectiva de diseño.

## Resultado operativo

Las entradas sucesoras de validación y verificación deben rechazar la evidencia de independencia del holdout del workflow expuesto. Los antiguos campos UNTOUCHED y cero accesos permanecen preservados, pero no pueden producir una aceptación actual.

El guard lee exclusivamente la ruta fija del incidente, con límite de 65.536 bytes más un byte de control y sin buffering. Rechaza aliases antes de abrirla y verifica el SHA-256 del snapshot preservado. Exposición confirmada produce HOLDOUT_EXPOSURE_CONFIRMED. Incidente ausente, alterado, ilegible, malformado, sobredimensionado o redirigido también bloquea; ninguno de esos estados significa ausencia de exposición. Cerrar administrativamente el incidente no recupera independencia.

Las operaciones y bytes históricos exactos continúan UNKNOWN; las 20.304 filas de la partición no se convierten en un contador de accesos.

## Entradas cubiertas

| Entrada sucesora | Disposición actual |
| --- | --- |
| review_m0 | BLOCKED, con estado histórico y exposición efectiva separados. |
| verify_registry | BLOCKED antes del hashing de fuentes; source_results vacío significa no verificado, no hashes coincidentes. |
| CLI validate | Exit 1 por exposición; no delega una validación histórica PASS. |
| CLI verify-all | Exit 1 antes de reconstruir/delegar una prueba histórica. |
| CLI fingerprint | Exit 1 con exposición; llamadas directas mantienen exit 2 para rutas protegidas. |
| cmd_gate/cmd_verify_all/cmd_validate/cmd_fingerprint del módulo sucesor | También bloquean llamadas directas, sin depender solamente del dispatcher CLI. |

Comandos reproducibles de diagnóstico, sin datos de mercado:

```powershell
python -B scripts/run_harness_v2_safe.py validate
python -B scripts/run_harness_v2_safe.py verify-all GATE-FASE611-PASSIVE-EXECUTION-001
python -B scripts/run_harness_v2_safe.py fingerprint quantumbot_harness/core/m0_invariants.py
python -B scripts/run_m0_registry_verifier.py
```

Se espera exit 1, no exit 0. Es evidencia de funcionamiento del rechazo, no una falla que deba eliminarse para obtener un PASS.

## Preservación y alcance de autoridad

No se modifican harness.py, PROJECT_STATE, policies, gates, receipts/index, TASK_LEDGER, REGISTRY de M0 ni el incidente. El snapshot anterior de los tres módulos sucesores y del linaje de tests se conserva en FASE61_HOLDOUT_EVIDENCE_GUARD_SNAPSHOT_001.json, con contenido y hashes. Ese archivo también registra hashes de las fuentes preservadas.

La actualización intencional de módulos sucesores deja obsoletas las vinculaciones a su implementación anterior en el registro histórico. No se reescriben esos hashes para aparentar continuidad. El verificador actual bloquea antes del hashing y no declara que esa vinculación antigua esté vigente. Cualquier reconciliación de registros requeriría un alcance formal separado y no podría certificar ausencia de exposición.

Los controles previos de recibos están preservados en el snapshot. En el workflow actual no se intenta validar combinaciones de recibos para eludir la exposición: ninguna combinación puede reparar esa independencia. No se afirma haber vuelto a validar las reglas históricas de recibos con las nuevas pruebas.

El harness histórico sigue físicamente invocable. Sus salidas no son autoridad para aceptación actual; no se implementa un sandbox global ni se protege toda llamada arbitraria o código modificado por un operador. Este límite queda declarado, no resuelto por inferencia.

FASE61 y M0 permanecen BLOCKED. LIVE permanece bloqueado. No se levanta STOP_PERMANENT_DEVELOPMENT, no se habilita HYP-21, no se reinicia el conteo de 20 hipótesis ni se adquieren nuevos datos.

## Tests vigentes frente a históricos

Se preservan íntegramente los archivos de tests anteriores. Se clasifican exactamente diez nodeids en tests/test_lineage.json, no módulos completos: esperaban PASS/READY o hashes del snapshot previo y ya no describen el estado actual. Cada entrada tiene una sustitución nominal en test_holdout_evidence_guard.py. Las assertions de denegación que siguen vigentes permanecen en la suite actual.

Las pruebas nuevas verifican el rechazo de exposición/UNKNOWN, integraciones antes de hashing/delegación, tamaño y aliases del incidente, cierre administrativo sin restauración de independencia y hashes de preservación. No se ejecuta la suite histórica completa, que podría acceder a datos de mercado. Un skip histórico no cuenta como prueba aprobada.

Los resultados, comandos, hashes finales y dictamen independiente se vinculan en FASE61_HOLDOUT_EVIDENCE_GUARD_REVIEW_001.json. Ese reporte no es un gate ni recibo canónico. La SPEC no se declara CLOSED sin el proceso formal requerido.
