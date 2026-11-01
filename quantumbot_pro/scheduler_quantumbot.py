"""
quantumbot_pro/scheduler_quantumbot.py — Orquestador de Plataforma QuantumBot Pro v2.0
Ejecuta la evaluación cuantitativa completa en tiempo real cada 5 minutos en modo continuo.
"""

import os
import sys
import datetime
import asyncio

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir  = os.path.dirname(current_dir)
if current_dir not in sys.path: sys.path.append(current_dir)
if parent_dir not in sys.path: sys.path.append(parent_dir)

from main import QuantumBotEngine

LOG_DIR  = os.path.join(current_dir, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, 'quantumbot_v2_runs.log')


def log(msg):
    ts   = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


async def main():
    log('=' * 80)
    log('QUANTUMBOT PRO v2.0 — INSTITUTIONAL QUANT PLATFORM DAEMON')
    log(f'Directorio: {current_dir}')
    log(f'Log File:   {LOG_FILE}')
    log('=' * 80)

    config_dir = os.path.join(current_dir, 'config')
    bot = QuantumBotEngine(config_dir)

    while True:
        log('\n[+] Iniciando ciclo cuantitativo QuantumBot Pro v2.0...')
        try:
            await bot.run_cycle()
            log('[OK] Ciclo cuantitativo completado exitosamente.')
        except Exception as e:
            log(f'[!] Error en ciclo cuantitativo: {e}')

        log('Esperando 5 minutos para el siguiente cierre de vela...')
        await asyncio.sleep(300)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log('\nDaemon QuantumBot Pro v2.0 detenido.')
        sys.exit(0)
