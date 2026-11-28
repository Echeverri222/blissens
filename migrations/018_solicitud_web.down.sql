drop table solicitud_adjunto;
alter table solicitud_contacto
    drop column origen, drop column interes, drop column idioma, drop column nombre, drop column correo,
    drop column pais, drop column paquete, drop column mensaje, drop column paciente_id,
    drop column aviso_enviado_en, drop column acuse_enviado_en;
