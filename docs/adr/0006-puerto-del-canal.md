# 6. Puerto del canal y webhook que encamina al negocio

**Estado:** aceptada (PRD #4, D10).

`messaging` habla con un adaptador de tres operaciones (enviar, verificar la autenticidad de lo entrante, traducirlo a «botón o texto de tal remitente»). Cada negocio tiene su canal en `canal_negocio`, con la **referencia** al secreto (variable de entorno), nunca el secreto. `POST /canales/{tipo}/webhook` resuelve el negocio por el identificador del canal, verifica la firma con el secreto *de ese canal*, fija el contexto y llama a `messaging.receive`; el identificador del proveedor es único por negocio y canal, así que un reenvío no se procesa dos veces. Se prueba con un adaptador de prueba (no existe en producción) y dos negocios. **Queda para el PRD de WhatsApp:** estados de entrega reales, reintentos de envío y el celular compartido por varios pacientes (hoy se ignora el mensaje).
