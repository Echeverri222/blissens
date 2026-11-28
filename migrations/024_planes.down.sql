delete from intento where caso_id in (select id from caso_seguimiento where tipo = 'plan');
update caso_seguimiento set cita_resultante_id = null where tipo = 'plan';
delete from caso_seguimiento where tipo = 'plan';

drop index caso_abierto_tratamiento_neg;
create unique index caso_abierto_tratamiento_neg on caso_seguimiento(negocio_id, tratamiento_id)
    where estado = 'abierto' and tratamiento_id is not null;

alter table caso_seguimiento drop constraint caso_seguimiento_tipo_check;
alter table caso_seguimiento add constraint caso_seguimiento_tipo_check
    check (tipo in ('cancelacion','inasistencia','tratamiento_a_medias'));

alter table tratamiento drop column ultimo_abono_en;
alter table tratamiento drop column valor_plan;
alter table tratamiento drop column plan_entregado_en;
