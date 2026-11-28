-- Vuelve a las plantillas anteriores solo donde siguen iguales a las nuevas por defecto.

update plantilla set texto = $t$¡Hola {nombre}! Tu cita quedó agendada para el {fecha} a las {hora} con {profesional}. Te esperamos en {direccion}. ¡Gracias por elegirnos!$t$ where clave = 'cita_agendada' and texto = $t$Hola, {nombre}. Su cita quedó agendada para el {fecha} a las {hora} con {profesional}. Le esperamos en {direccion}. Gracias por elegirnos.$t$;
update plantilla set texto = $t$Hola {nombre}, te recordamos tu cita del {fecha} a las {hora} con {profesional}. ¿Nos confirmas tu asistencia?$t$ where clave = 'recordatorio_48h' and texto = $t$Hola, {nombre}. Le recordamos su cita del {fecha} a las {hora} con {profesional}. ¿Nos confirma su asistencia?$t$;
update plantilla set texto = $t$Hola {nombre}, mañana es tu cita: {fecha} a las {hora} con {profesional}, en {direccion}. ¡Te esperamos!$t$ where clave = 'recordatorio_24h' and texto = $t$Hola, {nombre}. Mañana es su cita: {fecha} a las {hora} con {profesional}, en {direccion}. Le esperamos.$t$;
update plantilla set texto = $t$Hola {nombre}, aún no hemos recibido tu confirmación para la cita del {fecha} a las {hora} con {profesional}. ¿Puedes responder con un toque?$t$ where clave = 'segundo_intento' and texto = $t$Hola, {nombre}. Aún no hemos recibido su confirmación para la cita del {fecha} a las {hora} con {profesional}. ¿Puede responder con un toque?$t$;
update plantilla set texto = $t$¡Gracias, {nombre}! Tu cita del {fecha} a las {hora} quedó confirmada. Te esperamos en {direccion}.$t$ where clave = 'confirmacion_recibida' and texto = $t$Gracias, {nombre}. Su cita del {fecha} a las {hora} quedó confirmada. Le esperamos en {direccion}.$t$;
update plantilla set texto = $t$Listo {nombre}, cancelamos tu cita del {fecha}. Para mejorar nuestro servicio, ¿nos cuentas el motivo? Elige una opción.$t$ where clave = 'pedir_motivo' and texto = $t$Listo, {nombre}. Cancelamos su cita del {fecha}. Para mejorar nuestro servicio, ¿nos cuenta el motivo? Elija una opción.$t$;
update plantilla set texto = $t$Gracias, {nombre}. Tu cita del {fecha} quedó cancelada. Cuando quieras retomarla, elige un nuevo espacio aquí: {enlace}$t$ where clave = 'cancelacion_recibida' and texto = $t$Gracias, {nombre}. Su cita del {fecha} quedó cancelada. Cuando quiera retomarla, elija un nuevo espacio aquí: {enlace}$t$;
update plantilla set texto = $t$Hola {nombre}, queremos ayudarte a retomar la cita que cancelaste. Mira los espacios disponibles aquí: {enlace}$t$ where clave = 'seguimiento_reasignacion' and texto = $t$Hola, {nombre}. Volver a empezar es más fácil acompañado: {profesional} le guarda un espacio. Elija el que mejor le quede: {enlace}$t$;
update plantilla set texto = $t$Hola {nombre}, te extrañamos en tu cita del {fecha}. Si quieres reagendarla, elige un espacio aquí: {enlace}$t$ where clave = 'seguimiento_inasistencia' and texto = $t$Hola, {nombre}. Volver a empezar es más fácil acompañado: {profesional} le guarda un espacio. Si desea retomar su cita del {fecha}, elija el que mejor le quede: {enlace}$t$;
update plantilla set texto = $t$Hola {nombre}, queremos acompañarte a continuar tu plan de atención. Agenda tu próxima cita aquí: {enlace}$t$ where clave = 'continuidad_tratamiento' and texto = $t$Hola, {nombre}. Volver a empezar es más fácil acompañado: {profesional} le guarda un espacio para continuar su plan. Elija el que mejor le quede: {enlace}$t$;
update plantilla set texto = $t$Hola {nombre}, tu cita podría adelantarse de {fecha_actual} a las {hora_actual} a {fecha_nueva} a las {hora_nueva}. ¿Quieres hacerlo?$t$ where clave = 'oferta_adelanto' and texto = $t$Hola, {nombre}. Su cita podría adelantarse de {fecha_actual} a las {hora_actual} a {fecha_nueva} a las {hora_nueva}. ¿Desea hacerlo?$t$;
update plantilla set texto = $t$¡Listo, {nombre}! Adelantamos tu cita: ahora es el {fecha} a las {hora} con {profesional}, en {direccion}. Esta es tu nueva fecha.$t$ where clave = 'adelanto_confirmado' and texto = $t$Listo, {nombre}. Adelantamos su cita: ahora es el {fecha} a las {hora} con {profesional}, en {direccion}. Esta es su nueva fecha.$t$;
update plantilla set texto = $t$Hola {nombre}, ese espacio ya no está disponible. No te preocupes: tu cita original sigue igual.$t$ where clave = 'oferta_no_disponible' and texto = $t$Hola, {nombre}. Ese espacio ya no está disponible. No se preocupe: su cita original sigue igual.$t$;
update plantilla set texto = $t$Listo {nombre}, no te enviaremos más mensajes automáticos por WhatsApp. Los correos, si los recibes, se cancelan con el enlace que traen. Si necesitas algo, escríbenos o llámanos.$t$ where clave = 'baja_confirmada' and texto = $t$Listo, {nombre}. No le enviaremos más mensajes automáticos por WhatsApp. Los correos, si los recibe, se cancelan con el enlace que traen. Si necesita algo, escríbanos o llámenos.$t$;
update plantilla set texto = $t$Hola {nombre}, esa cita ya no está vigente. Si necesitas ayuda, la clínica te acompaña con gusto.$t$ where clave = 'respuesta_tardia' and texto = $t$Hola, {nombre}. Esa cita ya no está vigente. Si necesita ayuda, la clínica le acompaña con gusto.$t$;
update plantilla set texto = $t$Claro, {nombre}. Elige tu nueva fecha aquí: {enlace}. Tu cita actual se mantiene hasta que elijas otra.$t$ where clave = 'cambiar_fecha' and texto = $t$Claro, {nombre}. Elija su nueva fecha aquí: {enlace}. Su cita actual se mantiene hasta que elija otra.$t$;
update plantilla set texto = $t$Entendido, {nombre}. No insistiremos más sobre esto. Cuando quieras retomar, aquí estamos.$t$ where clave = 'seguimiento_pausado' and texto = $t$Entendido, {nombre}. No insistiremos más sobre esto. Cuando quiera retomar, aquí estamos.$t$;
update plantilla set texto = $t$¡Hola {nombre}! Te confirmamos lo que quedó agendado:
{lista}
Los esperamos en {direccion}. ¡Gracias por elegirnos!$t$ where clave = 'cita_agendada_hogar' and texto = $t$Hola, {nombre}. Le confirmamos lo que quedó agendado:
{lista}
Los esperamos en {direccion}. Gracias por elegirnos.$t$;
update plantilla set texto = $t$Hola {nombre}, te recordamos las próximas citas de tu familia:
{lista}
¿Nos confirmas la asistencia?$t$ where clave = 'recordatorio_48h_hogar' and texto = $t$Hola, {nombre}. Le recordamos las próximas citas de su familia:
{lista}
¿Nos confirma la asistencia?$t$;
update plantilla set texto = $t$Hola {nombre}, mañana tienen cita:
{lista}
Los esperamos en {direccion}.$t$ where clave = 'recordatorio_24h_hogar' and texto = $t$Hola, {nombre}. Mañana tienen cita:
{lista}
Los esperamos en {direccion}.$t$;
update plantilla set texto = $t$Hola {nombre}, mañana tienen cita:
{lista}
Aún nos falta la confirmación de las que dicen «sin confirmar». ¿Puedes responder con un toque?$t$ where clave = 'segundo_intento_hogar' and texto = $t$Hola, {nombre}. Mañana tienen cita:
{lista}
Aún nos falta la confirmación de las que dicen «sin confirmar». ¿Puede responder con un toque?$t$;
update plantilla set texto = $t$¡Gracias, {nombre}! Quedaron confirmadas:
{lista}
Los esperamos en {direccion}.$t$ where clave = 'confirmacion_recibida_hogar' and texto = $t$Gracias, {nombre}. Quedaron confirmadas:
{lista}
Los esperamos en {direccion}.$t$;
update plantilla set texto = $t$Claro, {nombre}. Desde aquí puedes cambiar o cancelar cada cita: {enlace}$t$ where clave = 'cambiar_hogar' and texto = $t$Claro, {nombre}. Desde aquí puede cambiar o cancelar cada cita: {enlace}$t$;
delete from configuracion where clave = 'version_plantillas';

alter table profesional drop column titulo;
