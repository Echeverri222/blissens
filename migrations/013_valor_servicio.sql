-- Valor promedio de cada servicio en pesos (indicadores: dinero perdido por inasistencias y cancelaciones tardías).
alter table servicio add column valor numeric(12,0) check (valor is null or valor >= 0);
