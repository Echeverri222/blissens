-- Quién resuelve los pendientes del equipo y cuándo (indicadores: ¿el equipo cierra sus pendientes?).
alter table mensaje add column gestionado_en timestamptz;
alter table mensaje add column gestionado_por bigint references usuario(id) on delete set null;
alter table caso_seguimiento add column cerrado_por bigint references usuario(id) on delete set null;
