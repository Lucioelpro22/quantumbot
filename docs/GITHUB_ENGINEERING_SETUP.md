# Git/GitHub: baseline acotada de ingeniería

Fecha: 2026-10-01. SPEC: `SPEC-ENGINEERING-GIT-CI-BOOTSTRAP-001`.

## Alcance local

El commit inicial contiene exclusivamente una allowlist de código de ingeniería,
tests sintéticos y metadata de gobernanza. Los antiguos tests incluidos son
fuentes históricas para comprobar hashes, no suites a ejecutar. No contiene el
motor operativo, datasets, holdout, bases productivas, archivos `.env` ni claves.
El resto del workspace permanece local, sin borrado ni restauración.

El hook `.git/hooks/pre-commit` invoca copias revisadas del checker y manifest
en `.git/operational-ci/`, fuera del snapshot candidato. Valida paths, modos y
objetos del índice antes de leer blobs; sólo materializa bytes coincidentes con
la baseline. No ejecuta código modificado del worktree para aprobar un commit.
Después ejecuta tests sintéticos y verifica el bloqueo por exposición.

La baseline queda congelada: también rechaza cambios nuevos de ingeniería hasta
que una revisión independiente autorice otra baseline confiable. Un candidato
no puede autorizarse reemplazando su propio manifest, SPEC o checker. No hay
auto-actualización de las copias de confianza ni cierre formal de la SPEC.

Dependencias preinstaladas requeridas: Python compatible, Git, pytest `9.1.1` y
jsonschema `4.26.0`. El check no instala ni descarga dependencias. La prueba local
se ejecuta con Python 3.14; otras versiones deben reproducir los tests.

## GitHub: preparado, todavía no activado

No se creó ni configuró un remoto, no se hizo push y no se modificaron reglas de
rama ni variables de GitHub. El YAML preparado no demuestra CI activo.

Una activación posterior requiere autorización separada y:

1. Elegir el repositorio GitHub y publicar sólo esta baseline revisada.
2. Registrar su SHA completo como variable protegida de administración
   `OPERATIONAL_BASELINE_COMMIT`; no resolverla desde archivos del candidato.
3. Verificar dependencias offline en el runner. El runner hospedado estándar
   puede no traer esas versiones: el job fallará cerrado, sin hacer `pip install`.
   Una solución de entorno reproducible debe especificarse y aprobarse aparte;
   no usar un runner persistente con acceso al bot, credenciales o mercado.
4. Exigir revisión independiente y el check `engineering-only` mediante ruleset
   o protección de rama. Proteger workflow, checker y cambios de baseline; el
   YAML del candidato no constituye por sí solo una barrera obligatoria.
5. Reproducir un caso válido y rechazos por modificación/ausencia de evidencia,
   cambio de manifest, archivo extra y evasión del índice. No lanzar el bot.

El workflow sólo hace checkout de la baseline confiable fijada por administración.
Consulta metadata del objeto commit candidato en GitHub (respuesta acotada, sin
redirecciones) y exige que su SHA y árbol sean los esperados: el árbol debe ser
idéntico al de la baseline. No hace fetch ni checkout de blobs del candidato;
tests y SHA-256 se verifican sobre los bytes confiables de ese mismo árbol.
Cualquier árbol distinto falla antes de adquirir archivos candidatos. Sólo se
consulta metadata de repositorio, nunca APIs de mercado.

Usa action fijada a SHA, token efímero de lectura y sin credenciales persistentes;
evita `pull_request_target`, secretos productivos y despliegues. No acredita un
sandbox de red/procesos: las pruebas ejecutadas son código congelado auditado,
en snapshot temporal con entorno reducido. Aislamiento global permanece P0
pendiente, igual que protección remota e instrumentación de runtime.

Referencias oficiales: [seguridad de Actions](https://docs.github.com/en/actions/reference/security/secure-use),
[riesgos de pull_request_target](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target)
y [checkout fijado](https://github.com/actions/checkout/commit/11bd71901bbe5b1630ceea73d27597364c9af683).
La consulta metadata usa [Get a commit object](https://docs.github.com/en/rest/git/commits#get-a-commit-object).

## Interpretación

`ENGINEERING_CHECK_OK` no habilita LIVE ni investigación. El verificador vigente
debe devolver exit 1 con `BLOCKED`, `HOLDOUT_EXPOSURE_CONFIRMED`, evidencia
verificada y contadores exactos `UNKNOWN`; otro fallo no se acepta como éxito.
No se emite recibo canónico, promoción FASE61/M0 ni certificación de independencia.
El pre-commit sigue siendo una ayuda local eludible; no inspecciona procesos del
bot ni impide físicamente toda ejecución del harness histórico.
