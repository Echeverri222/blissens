-- Reversa de la migración inicial: deja la base sin tablas de dominio.
drop table if exists hecho_diario_profesional, hecho_diario, solicitud_contacto, configuracion, tarea_programada,
    mensaje, plantilla, oferta_adelanto, cupo_liberado, intento, caso_seguimiento, cancelacion, motivo_cancelacion,
    historial_estado, cita, tratamiento, bloqueo, horario_atencion, servicio, profesional, paciente cascade;
