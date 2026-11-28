-- Planes de tratamiento (docs/prd-respuestas-clinica.md, R14): fecha de entrega del plan, valor (solo panel, nunca en
-- mensajes) y último abono. Un caso `plan` puede convivir con el de `tratamiento_a_medias` del mismo tratamiento.

alter table tratamiento add column plan_entregado_en timestamptz;
alter table tratamiento add column valor_plan numeric(12,0) check (valor_plan >= 0);
alter table tratamiento add column ultimo_abono_en timestamptz;

alter table caso_seguimiento drop constraint caso_seguimiento_tipo_check;
alter table caso_seguimiento add constraint caso_seguimiento_tipo_check
    check (tipo in ('cancelacion','inasistencia','tratamiento_a_medias','plan'));

drop index caso_abierto_tratamiento_neg;
create unique index caso_abierto_tratamiento_neg on caso_seguimiento(negocio_id, tratamiento_id, tipo)
    where estado = 'abierto' and tratamiento_id is not null;
