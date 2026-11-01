# Bybit Demo: protocolo de validación

## Estado de la versión

Esta entrega está bloqueada a `https://api-demo.bybit.com`. No incluye promoción automática a real.

## Correcciones relevantes

- Apalancamiento reducido de 25x a 3x y máximo de dos posiciones.
- Tamaño calculado para arriesgar como máximo 0,25% del equity por entrada, incluyendo estimación de comisiones y slippage.
- Límite diario de 1% y drawdown máximo de 8% durante la sesión del proceso.
- Símbolos normalizados para Bybit (`BTCUSDT`), evitando duplicar posiciones por diferencias de formato.
- Cantidad ajustada al `qtyStep` y `minOrderQty` consultados en vivo.
- SL/TP incluidos en la creación de la orden y verificados en la posición.
- Una aceptación REST ya no se registra como fill: se consulta el estado y solo `Filled` se guarda como `FILLED_CONFIRMED`.
- Monte Carlo ya no inventa retornos cuando faltan datos.

## Cómo experimentar

1. Revoca todas las claves incluidas en el ZIP original.
2. Crea claves dentro de **Demo Trading** de Bybit y guárdalas como `BYBIT_API_KEY` y `BYBIT_SECRET_KEY`.
3. Instala dependencias con `pip install -r requirements.txt` desde la carpeta superior.
4. Ejecuta un solo ciclo: `python cli.py --mode demo`.
5. Repite la recolección de resultados cerrados: `python demo_profitability.py --collect`.

Bybit Demo conserva órdenes por un período limitado, por eso el recolector mantiene un ledger local deduplicado.

## Criterios mínimos de evidencia

El informe exige simultáneamente:

- al menos 100 operaciones cerradas;
- al menos 60 días calendario;
- PnL neto positivo;
- profit factor igual o superior a 1,20;
- límite inferior del intervalo bootstrap del retorno medio mayor que cero.

El comando `python demo_profitability.py --collect` actualiza el ledger y genera el informe. Un resultado `PASS_DEMO_EVIDENCE` solo habilita una nueva revisión técnica; no demuestra que el sistema vaya a ser rentable en real.
