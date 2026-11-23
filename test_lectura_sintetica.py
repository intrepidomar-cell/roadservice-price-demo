"""Prueba opcional. Ejecutar desde la raíz del repo después de instalar el lector."""
from pathlib import Path
from operation_reader import leer_invoice

sample = Path(__file__).with_name('Operation_Estimate_Synthetic_Test.pdf')
res = leer_invoice(sample)
assert len(res['tablas']) == 4, 'Se esperaban tres operaciones y una tabla de cargos.'
assert res.get('operation_fallback_used'), 'El complemento no se ejecutó en el PDF sintético.'
assert any('SHOP SUPPLIES' in str(t['datos'].to_string()) for t in res['tablas'])
print('OK: operaciones, cargos y tablas sintéticas reconocidos.')
